#!/usr/bin/env python3
"""SIG micro-POC 003: deterministic cache-aside over SQLite."""
import argparse
import json
import random
import sqlite3
import statistics
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def database(path, rows):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, value TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)')
    n = con.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    if n != rows:
        con.execute('DELETE FROM items')
        con.executemany('INSERT INTO items(id,value) VALUES (?,?)', ((i, f'payload-{i:06d}') for i in range(1, rows+1)))
        con.commit()
    return con

class CacheAside:
    def __init__(self, con, capacity=512, ttl=60.0, clock=time.monotonic):
        self.con, self.capacity, self.ttl, self.clock = con, capacity, ttl, clock
        self.entries = OrderedDict()
        self.hits = self.misses = self.evictions = 0

    def read_db(self, key):
        row = self.con.execute('SELECT id,value,version FROM items WHERE id=?', (key,)).fetchone()
        return tuple(row) if row is not None else None

    def get(self, key):
        now = self.clock()
        if key in self.entries:
            value, expiry = self.entries[key]
            if expiry > now:
                self.hits += 1
                self.entries.move_to_end(key)
                return value
            del self.entries[key]
        self.misses += 1
        value = self.read_db(key)
        if value is not None and self.capacity > 0:
            if len(self.entries) >= self.capacity:
                self.entries.popitem(last=False)
                self.evictions += 1
            self.entries[key] = (value, now + self.ttl)
        return value

    def update(self, key, value):
        with self.con:
            cur = self.con.execute('UPDATE items SET value=?, version=version+1 WHERE id=?', (value, key))
        self.entries.pop(key, None)
        return cur.rowcount


def measured(func, keys):
    durations = []
    start = time.perf_counter_ns()
    checksum = 0
    for key in keys:
        t0 = time.perf_counter_ns()
        record = func(key)
        durations.append((time.perf_counter_ns()-t0)/1000)
        if record is not None:
            checksum += record[0] + record[2]
    elapsed = (time.perf_counter_ns()-start)/1e9
    durations.sort()
    return {'requests': len(keys), 'p50_us': round(statistics.median(durations), 3), 'p95_us': round(durations[int((len(durations)-1)*0.95)], 3), 'throughput_rps': round(len(keys)/elapsed, 1), 'checksum': checksum}


def bench(args):
    con = database(args.db, args.rows)
    rng = random.Random(args.seed)
    # 90% of requests target a bounded working set; 10% use the full dataset.
    keys = [rng.randint(1, args.hot) if rng.random() < 0.9 else rng.randint(1,args.rows) for _ in range(args.requests)]
    raw = CacheAside(con, 0, args.ttl)
    cached = CacheAside(con, args.capacity, args.ttl)
    base = measured(raw.read_db, keys)
    result = measured(cached.get, keys)
    assert base['checksum'] == result['checksum']
    print(json.dumps({'mode':'db','metrics':base}))
    print(json.dumps({'mode':'cache_aside','metrics':result,'cache':{'hits':cached.hits,'misses':cached.misses,'hit_rate':round(cached.hits/len(keys),4),'evictions':cached.evictions},'config':{'rows':args.rows,'hot':args.hot,'capacity':args.capacity,'ttl':args.ttl,'seed':args.seed}}))
    con.close()


def certify(args):
    checks = []
    with tempfile.TemporaryDirectory() as d:
        con = database(Path(d)/'test.sqlite3', 100)
        tick = [100.0]
        cache = CacheAside(con, 2, 10, lambda: tick[0])
        def record(name, ok, evidence):
            checks.append({'criterion':name,'state':'HERO' if ok else 'ZERO','evidence':evidence})
        a = cache.get(1)
        b = cache.get(1)
        record('C01_HIT_MISS',a==b and cache.hits==1 and cache.misses==1,'first read miss; second read hit')
        cache.get(2); cache.get(3)
        record('C02_LRU',list(cache.entries)==[2,3] and cache.evictions==1,'capacity=2 evicts oldest entry')
        cache.get(2);tick[0]+=11; cache.get(2)
        record('C03_TTL',cache.misses==4,'expired entry fetches from database')
        old=cache.get(3)
        affected=cache.update(3,'changed')
        new=cache.get(3)
        record('C04_INVALIDATION',affected==1 and old[1]!=new[1] and new[1]=='changed' and new[2]==2,'update commits and invalidates cached record')
        record('C05_NOT_FOUND',cache.get(999) is None,'missing key returns null')
        record('C06_DB_INTEGRITY',con.execute('SELECT COUNT(*) FROM items').fetchone()[0]==100,'100 unique records')
        con.close()
    summary={'mission':'SIG-MICRO-POC-003','certification':'HERO' if all(c['state']=='HERO' for c in checks) else 'ZERO','criteria':checks}
    summary['eol']='CERTIFIED' if summary['certification']=='HERO' else 'NOT CERTIFIED'
    folder=HERE/'evidence';folder.mkdir(exist_ok=True)
    (folder/'certification.json').write_text(json.dumps(summary,indent=2)+'\n')
    (folder/'EOL.md').write_text('# SIG MICRO-POC 003 — Closure\n\n'+f"Certification: **{summary['certification']}**  \nEOL: **{summary['eol']}**\n\n"+'Scope: SQLite cache-aside, LRU capacity, TTL, invalidation and deterministic tests. No Redis, concurrency, multi-process consistency or production durability claims.\n')
    for c in checks: print(f"{c['criterion']}: {c['state']} — {c['evidence']}")
    print(f"CERTIFICATION: {summary['certification']}; EOL: {summary['eol']}")
    return 0 if summary['certification']=='HERO' else 1


def main():
    parser=argparse.ArgumentParser(description='SIG caching micro-POC')
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init',help='Initialize SQLite dataset')
    init.add_argument('--rows',type=int,default=100000)
    run=sub.add_parser('bench',help='Compare direct SQLite and cache-aside')
    run.add_argument('--rows',type=int,default=100000)
    run.add_argument('--requests',type=int,default=100000)
    run.add_argument('--hot',type=int,default=100)
    run.add_argument('--capacity',type=int,default=512)
    run.add_argument('--ttl',type=float,default=60)
    run.add_argument('--seed',type=int,default=42)
    sub.add_parser('certify',help='Run deterministic acceptance checks')
    args=parser.parse_args()
    if args.command in ('init','bench'):
        args.db=HERE/'cache.sqlite3'
        if args.rows<1: parser.error('--rows must be positive')
    if args.command=='bench' and (args.requests<1 or not 1<=args.hot<=args.rows or args.capacity<0 or args.ttl<=0):
        parser.error('invalid benchmark parameters')
    if args.command=='init':
        con=database(args.db,args.rows);con.close();print(json.dumps({'rows':args.rows,'db':str(args.db)}))
    elif args.command=='bench': bench(args)
    else: raise SystemExit(certify(args))

if __name__=='__main__':main()
