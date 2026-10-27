# Micro-POC 001 — Pagination

Scope: compare HTTP/SQL performance of OFFSET/LIMIT and keyset cursor on the same indexed SQLite table, with a 100,000-row dataset and page size 20.

## Run

```bash
python3 poc.py init
python3 poc.py serve --port 8080
```

In another terminal:

```bash
curl -s 'http://127.0.0.1:8080/offset?page=4000&limit=20' | python3 -m json.tool
curl -s 'http://127.0.0.1:8080/cursor?after=79980&limit=20' | python3 -m json.tool
python3 benchmark.py --repeat 100
```

Endpoints: `/health`, `/offset?page=N&limit=20`, `/cursor?after=ID&limit=20`.

## Contract

- M01: generate exactly 100,000 items and validate count.
- M02: offset responds with ordered records, validates page/limit, and returns 400 for invalid parameters.
- M03: cursor uses ordered indexed `id > after`, validates cursor/limit, and returns 400 for invalid parameters.
- M04: compare 100 serial HTTP runs for each of 3 positions and both strategies; print HTTP latency p50/p95, SQL latency p50/p95, mean payload bytes.
- M05: report observations, limitations, and close the bounded POC when acceptance evidence is available.

This is a local laboratory, not a production capacity test. No load generator, cache, parallelism, auth, network latency emulation, or database migration is included. The cursor method assumes stable ascending integer IDs; it does not provide arbitrary page access or snapshot-consistent results across concurrent updates. The `next_cursor` contract is intentionally simple and may need a `limit+1` query for robust `has_more` behavior in a production API.

Operational note: no external Python packages required. No external runtime dependencies.

## M05: Final validation and completion

Run `python3 certify.py --repeat 100` from this folder. The script initializes a
missing dataset, uses an ephemeral loopback HTTP server, checks dataset and
pagination invariants, tests HTTP error boundaries, and collects six local
benchmark scenarios. It writes `evidence/validation.json`. Only when all
five checks pass does it write `evidence/RESULTS.md` and exit with status 0.
A failure records FAIL, exits nonzero, and does not leave an completion certificate.
This certificate applies only to the bounded local experiment; it is not a
production performance, concurrency, or throughput validation.


## Command Reference (Linux / Python 3)

Execute commands from the project root unless stated otherwise. Only Python standard library modules are required.

### 1. CLI help

```bash
python3 poc.py --help
python3 benchmark.py --help
python3 certify.py --help
```

### 2. Dataset and HTTP server

```bash
python3 poc.py init                 # Create or check 100,000 SQLite records
python3 poc.py serve                # Start HTTP server on 127.0.0.1:8080
python3 poc.py serve --port 8090    # Start on an alternative port
```

Run `init` before `serve` if the database is missing. `init` preserves an existing table with exactly 100,000 rows; it does not overwrite its contents when the count matches. The server listens on loopback only. Press **Ctrl+C** in its terminal to stop it.

### 3. HTTP API examples (server running on port 8080)

```bash
# Health check
curl -sS 'http://127.0.0.1:8080/health' | python3 -m json.tool

# First page and a deep page using OFFSET/LIMIT
curl -sS 'http://127.0.0.1:8080/offset?page=1&limit=20' | python3 -m json.tool
curl -sS 'http://127.0.0.1:8080/offset?page=4000&limit=20' | python3 -m json.tool

# First cursor page and a deep equivalent cursor position
curl -sS 'http://127.0.0.1:8080/cursor?after=0&limit=20' | python3 -m json.tool
curl -sS 'http://127.0.0.1:8080/cursor?after=79980&limit=20' | python3 -m json.tool

# Show HTTP status and response headers for invalid parameters
curl -i 'http://127.0.0.1:8080/offset?page=0'
curl -i 'http://127.0.0.1:8080/cursor?after=-1'
curl -i 'http://127.0.0.1:8080/not-found'
```

**Query parameters:** `/offset` accepts `page` (default 1, integer >= 1) and `limit` (default 20, integer 1..1000). `/cursor` accepts `after` (default 0, nonnegative integer) and `limit` (default 20, integer 1..1000). Invalid parameters return HTTP 400; unknown paths return HTTP 404. `next_page` and `next_cursor` are returned according to the POC's intentionally simplified pagination contract.

### 4. Benchmark (requires separately running API server)

```bash
python3 benchmark.py                  # Default: 100 requests per scenario
python3 benchmark.py --repeat 100
python3 benchmark.py --repeat 30
python3 benchmark.py --base http://127.0.0.1:8090 --repeat 100
```

The benchmark exercises pages 1, 1000 and 4000 in both modes (6 scenarios). Total measured HTTP requests = `6 * --repeat`, plus one equivalence-check request per scenario. The output reports `p50_ms`, `p95_ms`, `mean_ms` for HTTP and SQL, and `avg_bytes`. `--repeat` must be at least 2. The benchmark does **not** launch an HTTP server or create a database.

### 5. Final Micro-POC validation

```bash
python3 certify.py                  # Default: 100 measurements per scenario
python3 certify.py --repeat 100
```

Validation initializes the database if needed, runs an independent loopback HTTP server for its checks, validates C01–C05 and writes the evidence files below. **No separately started API server is required for validation.** The exit status is 0 only when required checks pass. As with the benchmark, `--repeat` controls samples per scenario.

```bash
cat evidence/validation.json
cat evidence/RESULTS.md
python3 -m json.tool evidence/validation.json
```

### 6. SQLite read-only inspection (optional)

```bash
python3 - <<'PYSQL'
import sqlite3
with sqlite3.connect('pagination.sqlite3') as db:
    print(db.execute('SELECT COUNT(*), MIN(id), MAX(id) FROM items').fetchone())
PYSQL
```

Expected result after initialization: `(100000, 1, 100000)`.

### 7. Local dataset reset (destructive; not required for validation)

Stop the server first. The following command deletes only the local SQLite database, after which `init` recreates the dataset:

```bash
rm -i pagination.sqlite3
python3 poc.py init
```

Do not run this reset while another POC process is using the database. A fresh run does not change the original mission's completion record unless its acceptance evidence is materially invalidated.

### Known boundaries

- Local SQLite/loopback study only; not a production throughput or concurrency validation.
- `--port` applies to `poc.py serve`; `--base` applies to `benchmark.py` only.
- The keyset implementation uses a stable ascending integer primary key and no snapshot semantics.
- Benchmark output alone is **not** the M05 certificate; use `certify.py` for the contract checks.
