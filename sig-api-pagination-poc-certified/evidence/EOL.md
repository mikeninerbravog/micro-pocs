# SIG MICRO-POC 001 — EOL Certification

- Certified (UTC): 2026-10-27T15:30:44.782503+00:00
- Scope: SQLite pagination OFFSET/LIMIT versus keyset cursor; local loopback HTTP.
- Dataset: 100000 sequential IDs.
- Measurements: 6 scenarios × 100 requests.
- Certification: **HERO**
- EOL: **CERTIFIED**

## Acceptance checks

| Criterion | Result |
|---|---|
| C01_DATASET | HERO |
| C02_EQUIVALENCE | HERO |
| C03_HTTP_BOUNDARIES | HERO |
| C04_BENCHMARK | HERO |
| C05_DOCUMENTATION | HERO |

## Results (p50 HTTP / p50 SQL, ms)

| Page | Mode | HTTP | SQL |
|---:|---|---:|---:|
| 1 | offset | 0.867 | 0.151 |
| 1 | cursor | 0.85 | 0.146 |
| 1000 | offset | 1.55 | 0.759 |
| 1000 | cursor | 0.842 | 0.144 |
| 4000 | offset | 3.828 | 2.858 |
| 4000 | cursor | 0.857 | 0.15 |

## Limitations

- Local loopback and SQLite measurements only; no production performance claim.
- Benchmark is serial and does not test concurrency or throughput.
- Cursor assumes stable integer identifiers and does not support arbitrary page jumps.
- No snapshot-consistency test for concurrent writes.
- No predefined minimum speedup; comparative measurements are descriptive.

This EOL closes the bounded experimental scope, not production readiness.
Follow-on experiments belong to a new mission.
