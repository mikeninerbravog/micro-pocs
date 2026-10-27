# Micro-POC 002 — Async Logging

## Objective
Compare local synchronous buffered file logging and asynchronous bounded-queue logging with batch writes and periodic flush. Measure producer p50/p95, producer throughput, end-to-end throughput, loss and integrity. The worker executes final `fsync` during graceful shutdown.

**Important:** This Python implementation does **not** implement a lock-free ring buffer. `queue.Queue` uses synchronization primitives. Logging is asynchronous, but pending events can be lost on process crash and **overflow drops events**. A return from `log()` means queue acceptance, not disk durability. No performance improvement is assumed beforehand.

## Requirements
Python 3.10+ (standard library); Linux recommended. No external dependencies. Only write to a writable local directory.

## Commands

```bash
python3 poc.py --help
python3 poc.py bench --help
python3 poc.py certify --help

# Run both modes with 10k events and local files in runs/
python3 poc.py bench

# Change workload, bounded queue, batch and periodic flush interval
python3 poc.py bench --events 100000 --capacity 8192 --batch 512 --interval-ms 100

# Write benchmark files elsewhere
python3 poc.py bench --events 10000 --output /tmp/async-logging-bench

# Validate contracts and generate evidence/validation.json and evidence/RESULTS.md
python3 poc.py certify --events 10000

# Inspect evidence
cat evidence/validation.json
cat evidence/RESULTS.md
wc -l evidence/sync.log evidence/async.log evidence/paced.log
```

## Validation contract
- C01: all synchronous messages stored intact.
- C02: async accepted + dropped = submitted, and written = accepted with unique ordered IDs.
- C03: a paced 100-event test completes with no drops under graceful shutdown.
- C04: benchmark records producer and end-to-end timing for both modes.
- C05: documentation exists.

`PASS` is earned only if all five checks pass, then the script issues the completion record. A measured improvement is a **finding**, not a mandatory acceptance gate. Saturation is intentionally not treated as lossless: dropped messages are counted. For a production system, choose an explicit backpressure or durable queue policy separately.

## Interpretation
`producer_events_per_second` = events submitted / time spent submitting; async includes dropped submissions. `durable_events_per_second` = events written / time through graceful `fsync`. Producer p50/p95 measure only submission/write-call duration, **not per-event disk durability**. Synchronous mode uses buffered I/O followed by one `fsync`, so it too is not durable after each `write()` call. The benchmark is single-producer and does not characterize production parallelism, crash recovery, or storage power loss.
