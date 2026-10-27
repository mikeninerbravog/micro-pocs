#!/usr/bin/env python3
"""Micro-POC 002: bounded asynchronous logging demonstration (standard library only)."""
import argparse
import json
import os
import queue
import statistics
import tempfile
import threading
import time
from pathlib import Path


def event(i):
    return (f'{i:08d}|event=benchmark|payload=Micro-POC 002\n').encode()


class AsyncLogger:
    def __init__(self, path, capacity=4096, batch=256, interval=0.05):
        self.path = Path(path)
        self.q = queue.Queue(maxsize=capacity)
        self.batch = batch
        self.interval = interval
        self.accepted = 0
        self.dropped = 0
        self.written = 0
        self.flushes = 0
        self.error = None
        self._closed = False
        self._stop = object()
        self.thread = threading.Thread(target=self._worker, daemon=False)
        self.thread.start()

    def log(self, data):
        if self._closed:
            raise RuntimeError('logger is closed')
        try:
            self.q.put_nowait(data)
            self.accepted += 1
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def _worker(self):
        pending = []
        deadline = time.monotonic() + self.interval
        try:
            with self.path.open('wb', buffering=1024 * 1024) as f:
                while True:
                    try:
                        item = self.q.get(timeout=max(0, deadline - time.monotonic()))
                    except queue.Empty:
                        item = None
                    if item is self._stop:
                        if pending:
                            f.write(b''.join(pending))
                            self.written += len(pending)
                            pending.clear()
                        f.flush()
                        os.fsync(f.fileno())
                        self.flushes += 1
                        break
                    if item is not None:
                        pending.append(item)
                    if len(pending) >= self.batch or time.monotonic() >= deadline:
                        if pending:
                            f.write(b''.join(pending))
                            self.written += len(pending)
                            pending.clear()
                        f.flush()
                        self.flushes += 1
                        deadline = time.monotonic() + self.interval
        except Exception as exc:
            self.error = repr(exc)

    def close(self):
        self._closed = True
        # A blocking sentinel is acceptable during graceful shutdown.
        if self.thread.is_alive():
            self.q.put(self._stop)
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise RuntimeError('worker shutdown timeout')
        if self.error:
            raise RuntimeError(self.error)


def measure(mode, n, path, capacity, batch, interval, producer_delay=0):
    lat = []
    start = time.perf_counter()
    if mode == 'sync':
        accepted = n
        with open(path, 'wb', buffering=1024 * 1024) as f:
            for i in range(n):
                t = time.perf_counter_ns()
                f.write(event(i))
                lat.append((time.perf_counter_ns() - t) / 1000)
                if producer_delay:
                    time.sleep(producer_delay)
            producer_elapsed = time.perf_counter() - start
            f.flush()
            os.fsync(f.fileno())
        dropped = 0
        flushes = 1
        written = n
    else:
        logger = AsyncLogger(path, capacity, batch, interval)
        for i in range(n):
            t = time.perf_counter_ns()
            logger.log(event(i))
            lat.append((time.perf_counter_ns() - t) / 1000)
            if producer_delay:
                time.sleep(producer_delay)
        producer_elapsed = time.perf_counter() - start
        logger.close()
        accepted, dropped, written, flushes = logger.accepted, logger.dropped, logger.written, logger.flushes
    total_elapsed = time.perf_counter() - start
    lines = Path(path).read_bytes().splitlines()
    ids = [int(line.split(b'|', 1)[0]) for line in lines]
    valid = (len(ids) == written == accepted and len(ids) == len(set(ids)) and ids == sorted(ids))
    if mode == 'sync':
        valid = valid and ids == list(range(n))
    latency_sorted = sorted(lat)
    result = dict(mode=mode, events=n, accepted=accepted, dropped=dropped, written=written,
                  valid=valid, producer_seconds=round(producer_elapsed, 6),
                  total_seconds=round(total_elapsed, 6),
                  producer_events_per_second=round(n / producer_elapsed, 1),
                  durable_events_per_second=round(written / total_elapsed, 1),
                  producer_p50_us=round(statistics.median(lat), 3),
                  producer_p95_us=round(latency_sorted[min(n - 1, int(n * .95))], 3),
                  flushes=flushes, file_bytes=Path(path).stat().st_size)
    return result


def main():
    ap = argparse.ArgumentParser(description='Micro-POC 002 async logging micro-POC')
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('bench', 'certify'):
        p = sub.add_parser(name)
        p.add_argument('--events', type=int, default=10000)
        p.add_argument('--capacity', type=int, default=4096)
        p.add_argument('--batch', type=int, default=256)
        p.add_argument('--interval-ms', type=float, default=50)
        p.add_argument('--output', default='evidence' if name == 'certify' else 'runs')
    args = ap.parse_args()
    if args.events < 1 or args.capacity < 1 or args.batch < 1 or args.interval_ms <= 0:
        ap.error('events, capacity, batch and interval-ms must all be positive')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    results = [measure(mode, args.events, out / f'{mode}.log', args.capacity,
                       args.batch, args.interval_ms / 1000) for mode in ('sync', 'async')]
    for x in results:
        print(json.dumps(x))
    if args.command == 'certify':
        # A flood can legitimately drop messages; this is a documented policy, not a failure.
        # A second paced case validates the normal no-loss graceful close path.
        paced_path = out / 'paced.log'
        paced = measure('async', 100, paced_path, 128, 32, .01, .002)
        checks = {
            'C01_sync_integrity': results[0]['valid'] and results[0]['written'] == args.events,
            'C02_async_accounting': results[1]['valid'] and results[1]['accepted'] + results[1]['dropped'] == args.events,
            'C03_paced_no_loss': paced['valid'] and paced['dropped'] == 0 and paced['written'] == 100,
            'C04_benchmark': all(x['producer_seconds'] > 0 and x['total_seconds'] > 0 for x in results),
            'C05_documentation': (Path(__file__).with_name('README.md')).is_file(),
        }
        status = 'PASS' if all(checks.values()) else 'FAIL'
        evidence = {'mission': 'Micro-POC 002', 'status': status, 'completion': status == 'PASS',
                    'checks': checks, 'benchmark': results, 'paced': paced,
                    'limitations': ['in-process memory queue is not lock-free',
                                    'queued events are not crash-durable',
                                    'saturation drops messages',
                                    'one producer; one consumer; local filesystem']}
        (out / 'validation.json').write_text(json.dumps(evidence, indent=2) + '\n')
        (out / 'completion.md').write_text(f'# Micro-POC 002 Validation\n\nStatus: **{status}**\n\nEOL: **{"COMPLETE" if status == "PASS" else "NOT COMPLETE"}**\n\n'
                                    + '\n'.join(f'- {k}: {"PASS" if v else "FAIL"}' for k, v in checks.items())
                                    + '\n\nScope: in-process asynchronous logging with bounded queue, batch and periodic flush.\n'
                                    + '\nLimits: not lock-free; crash loss possible; overflow policy drops logs.\n')
        for k, v in checks.items():
            print(f'{k}: {"PASS" if v else "FAIL"}')
        print(f'CERTIFICATION: {status}; completion: {"COMPLETE" if status == "PASS" else "NOT COMPLETE"}')
        if status != 'PASS':
            raise SystemExit(1)

if __name__ == '__main__':
    main()
