#!/usr/bin/env python3
"""Benchmark serial HTTP latency and response bytes under matched conditions."""
import argparse
import json
import statistics
import time
from urllib.request import urlopen


def fetch(url):
    start = time.perf_counter_ns()
    with urlopen(url, timeout=10) as response:
        raw = response.read()
    elapsed_ms = (time.perf_counter_ns() - start) / 1e6
    return json.loads(raw), elapsed_ms, len(raw)


def stats(samples):
    ordered = sorted(samples)
    return {'p50_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 3),
            'mean_ms': round(statistics.mean(samples), 3)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='http://127.0.0.1:8080')
    p.add_argument('--repeat', type=int, default=100)
    a = p.parse_args()
    if a.repeat < 2:
        p.error('--repeat must be >= 2')
    # Compare equal result sets at shallow and deep positions.
    output = []
    for page in (1, 1000, 4000):
        offset = (page - 1) * 20
        for mode, suffix in [('offset', f'/offset?page={page}&limit=20'),
                             ('cursor', f'/cursor?after={offset}&limit=20')]:
            url = a.base + suffix
            data, _, _ = fetch(url)
            expected = list(range(offset + 1, offset + 21))
            actual = [item['id'] for item in data['items']]
            if actual != expected:
                raise SystemExit(f'FAIL: unexpected IDs for {url}')
            times, sizes, sql = [], [], []
            for _ in range(a.repeat):
                d, latency, size = fetch(url)
                times.append(latency)
                sizes.append(size)
                sql.append(d['sql_ms'])
            result = {'page': page, 'mode': mode, 'runs': a.repeat,
                      'http': stats(times), 'sql': stats(sql),
                      'avg_bytes': round(statistics.mean(sizes))}
            output.append(result)
            print(json.dumps(result), flush=True)
    print('BENCHMARK COMPLETE: functional page equivalence validated; performance threshold not predefined')


if __name__ == '__main__':
    main()
