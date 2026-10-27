# Micro-POC 003 — Cache-aside

## Goal
Compare indexed SQLite reads to an in-process cache-aside implementation with LRU eviction, TTL, and write invalidation. Python standard library only. This is a deterministic single-process test, **not** a Redis simulation or a production recommendation.

## Commands

```bash
python3 poc.py --help
python3 poc.py init --rows 100000
python3 poc.py bench --requests 100000
python3 poc.py bench --rows 100000 --requests 100000 --hot 100 --capacity 512 --ttl 60 --seed 42
python3 poc.py certify
cat evidence/validation.json
cat evidence/RESULTS.md
```

The benchmark seeds a repeatable key workload: 90% target the first `--hot` records; 10% sample across the dataset. Same requests and checksum are used for uncached and cached reads. Timings include Python overhead and OS filesystem caching. Output includes p50/p95 latency, throughput, cache hit rate and evictions. A cache can be slower on indexed local DB reads; no improvement is presumed.

## Design and guarantees

- Cache-aside: read cache; on miss fetch SQLite; cache the result.
- Capacity: bounded LRU eviction, not a lock-free cache.
- TTL: expiration uses monotonic time.
- Update: commit database transaction, then invalidate key.
- Missing keys: return `None`; negative results are not cached.
- Scope: single-process, single-threaded, no cross-process cache coherence, Redis, networking or concurrent-update guarantees.

## Micro-POC acceptance / completion

`certify` tests hits and misses, LRU eviction, TTL, write invalidation, not-found handling and dataset integrity. It emits `evidence/validation.json` and `evidence/RESULTS.md`. PASS is awarded only on passing all tests. completion closes this limited lab, not a general production caching claim.

## Files

- `poc.py`: database, cache, benchmark and validation.
- `cache.sqlite3`: generated database (disposable).
- `evidence/`: generated validation and closure records.
