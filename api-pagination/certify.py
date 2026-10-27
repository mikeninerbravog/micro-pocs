#!/usr/bin/env python3
"""Bounded Micro-POC validation of the pagination micro-POC."""
import argparse
import json
import platform
import sqlite3
import statistics
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import poc
import benchmark

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'


def check_http(base, endpoint):
    try:
        with urlopen(base + endpoint, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, {'error_body': exc.read().decode('utf-8', errors='replace')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeat', type=int, default=100)
    args = parser.parse_args()
    if args.repeat < 2:
        parser.error('--repeat must be >= 2')
    EVIDENCE.mkdir(exist_ok=True)
    record = {
        'mission': 'Micro-POC 001 — API Pagination',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(),
        'sqlite': sqlite3.sqlite_version,
        'dataset_expected': poc.TOTAL,
        'repeat': args.repeat,
        'checks': {},
        'measurements': [],
        'limitations': [
            'Local loopback and SQLite measurements only; no production performance claim.',
            'Benchmark is serial and does not test concurrency or throughput.',
            'Cursor assumes stable integer identifiers and does not support arbitrary page jumps.',
            'No snapshot-consistency test for concurrent writes.',
            'No predefined minimum speedup; comparative measurements are descriptive.'
        ]
    }

    def verify(name, condition, detail):
        record['checks'][name] = {'status': 'PASS' if condition else 'FAIL', 'detail': detail}
        print(f'{name}: {record["checks"][name]["status"]} — {detail}', flush=True)

    server = None
    try:
        if not poc.DB.exists():
            poc.init()
        with poc.connect() as db:
            count, minimum, maximum, unique_count = db.execute(
                'SELECT COUNT(*), MIN(id), MAX(id), COUNT(DISTINCT id) FROM items'
            ).fetchone()
            bad_payloads = db.execute(
                "SELECT COUNT(*) FROM items WHERE payload != printf('item-%06d', id)"
            ).fetchone()[0]
        verify('C01_DATASET',
               count == poc.TOTAL and minimum == 1 and maximum == poc.TOTAL
               and unique_count == poc.TOTAL and bad_payloads == 0,
               f'rows={count}; min={minimum}; max={maximum}; unique={unique_count}; bad_payloads={bad_payloads}')
        if record['checks']['C01_DATASET']['status'] == 'FAIL':
            raise RuntimeError('Dataset invariant failed')

        server = ThreadingHTTPServer(('127.0.0.1', 0), poc.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'

        equivalent = True
        details = []
        for page in (1, 1000, 4000, 5000, 5001):
            after = (page - 1) * 20
            status_a, result_a = check_http(base, f'/offset?page={page}&limit=20')
            status_b, result_b = check_http(base, f'/cursor?after={after}&limit=20')
            ids_a = [r['id'] for r in result_a.get('items', [])]
            ids_b = [r['id'] for r in result_b.get('items', [])]
            expected = list(range(after + 1, min(after + 21, poc.TOTAL + 1)))
            passed = status_a == 200 and status_b == 200 and ids_a == ids_b == expected
            equivalent &= passed
            details.append(f'p{page}={"OK" if passed else "FAIL"}({len(ids_a)}/{len(ids_b)})')
        verify('C02_EQUIVALENCE', equivalent, '; '.join(details))

        cases = [
            ('/offset?page=0', 400),
            ('/offset?page=-1', 400),
            ('/offset?limit=0', 400),
            ('/offset?limit=1001', 400),
            ('/offset?page=abc', 400),
            ('/cursor?after=-1', 400),
            ('/cursor?after=abc', 400),
            ('/cursor?limit=0', 400),
            ('/cursor?limit=1001', 400),
            ('/not-found', 404),
            ('/health', 200),
        ]
        observed = [(path, check_http(base, path)[0], expected) for path, expected in cases]
        verify('C03_HTTP_BOUNDARIES', all(actual == expected for _, actual, expected in observed),
               '; '.join(f'{path}:{actual}/{expected}' for path, actual, expected in observed))

        for page in (1, 1000, 4000):
            after = (page - 1) * 20
            for mode, suffix in (
                ('offset', f'/offset?page={page}&limit=20'),
                ('cursor', f'/cursor?after={after}&limit=20'),
            ):
                times, sql, sizes = [], [], []
                for _ in range(args.repeat):
                    body, elapsed, size = benchmark.fetch(base + suffix)
                    times.append(elapsed)
                    sql.append(body['sql_ms'])
                    sizes.append(size)
                record['measurements'].append({
                    'page': page, 'mode': mode, 'runs': args.repeat,
                    'http': benchmark.stats(times), 'sql': benchmark.stats(sql),
                    'avg_bytes': round(statistics.mean(sizes)),
                })
        verify('C04_BENCHMARK', len(record['measurements']) == 6 and
               all(m['runs'] == args.repeat for m in record['measurements']),
               f'{len(record["measurements"])} scenarios x {args.repeat} HTTP requests')

        verify('C05_DOCUMENTATION', (HERE / 'README.md').exists() and
               all(len(entry) > 0 for entry in record['limitations']) and
               len(record['measurements']) == 6,
               'README, measurable evidence and scope limitations recorded')
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        print('CERTIFICATION ERROR:', record['error'], flush=True)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    all_ok = len(record['checks']) == 5 and all(
        v['status'] == 'PASS' for v in record['checks'].values()
    ) and 'error' not in record
    record['validation'] = 'PASS' if all_ok else 'FAIL'
    record['completion'] = 'COMPLETE' if all_ok else 'NOT COMPLETE'
    evidence_path = EVIDENCE / 'validation.json'
    evidence_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')

    eol_path = EVIDENCE / 'RESULTS.md'
    if all_ok:
        table = '\n'.join(f'| {name} | {value["status"]} |' for name, value in record['checks'].items())
        lines = [
            '# Micro-POC 001 — completion Validation', '',
            f'- Certified (UTC): {record["timestamp_utc"]}',
            '- Scope: SQLite pagination OFFSET/LIMIT versus keyset cursor; local loopback HTTP.',
            f'- Dataset: {poc.TOTAL} sequential IDs.',
            f'- Measurements: 6 scenarios × {args.repeat} requests.',
            '- Validation: **PASS**', '- completion: **COMPLETE**', '',
            '## Acceptance checks', '', '| Criterion | Result |', '|---|---|', table, '',
            '## Results (p50 HTTP / p50 SQL, ms)', '',
            '| Page | Mode | HTTP | SQL |', '|---:|---|---:|---:|',
        ]
        for m in record['measurements']:
            lines.append(f'| {m["page"]} | {m["mode"]} | {m["http"]["p50_ms"]} | {m["sql"]["p50_ms"]} |')
        lines += ['', '## Limitations', ''] + [f'- {x}' for x in record['limitations']]
        lines += ['', 'This completion closes the bounded experimental scope, not production readiness.',
                  'Follow-on experiments belong to a new mission.', '']
        eol_path.write_text('\n'.join(lines))
    elif eol_path.exists():
        eol_path.unlink()
    print(f'CERTIFICATION: {record["validation"]}')
    print(f'completion: {record["completion"]}')
    print(f'EVIDENCE: {evidence_path}')
    raise SystemExit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
