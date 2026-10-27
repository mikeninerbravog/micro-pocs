#!/usr/bin/env python3
"""Micro-POC pagination micro-POC: deterministic HTTP API backed by SQLite."""
import argparse
import json
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB = Path(__file__).with_name('pagination.sqlite3')
TOTAL = 100_000


def connect():
    return sqlite3.connect(DB)


def init():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
        count = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        if count != TOTAL:
            db.execute('DELETE FROM items')
            db.executemany('INSERT INTO items (id, payload) VALUES (?, ?)',
                           ((i, f'item-{i:06d}') for i in range(1, TOTAL + 1)))
        print(json.dumps({'rows': db.execute('SELECT COUNT(*) FROM items').fetchone()[0], 'db': str(DB)}))


def query(mode, limit, page=1, after=0):
    if limit < 1 or limit > 1000 or page < 1 or after < 0:
        raise ValueError('invalid pagination parameters')
    with connect() as db:
        start = time.perf_counter_ns()
        if mode == 'offset':
            rows = db.execute('SELECT id, payload FROM items ORDER BY id LIMIT ? OFFSET ?',
                              (limit, (page - 1) * limit)).fetchall()
        elif mode == 'cursor':
            rows = db.execute('SELECT id, payload FROM items WHERE id > ? ORDER BY id LIMIT ?',
                              (after, limit)).fetchall()
        else:
            raise ValueError('unknown mode')
        sql_ms = (time.perf_counter_ns() - start) / 1e6
    result = {'mode': mode, 'items': [{'id': r[0], 'payload': r[1]} for r in rows],
              'sql_ms': round(sql_ms, 4)}
    if mode == 'offset':
        result.update({'page': page, 'next_page': page + 1 if len(rows) == limit else None})
    else:
        result.update({'after': after, 'next_cursor': rows[-1][0] if len(rows) == limit else None})
    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        try:
            if p.path == '/health':
                result = {'ok': DB.exists()}
            elif p.path in ('/offset', '/cursor'):
                args = parse_qs(p.query)
                val = lambda k, default: int(args.get(k, [default])[0])
                result = query(p.path[1:], val('limit', 20), val('page', 1), val('after', 0))
            else:
                self.send_error(404)
                return
            data = json.dumps(result, separators=(',', ':')).encode()
            self.send_response(200)
        except (ValueError, OverflowError) as exc:
            data = json.dumps({'error': str(exc)}).encode()
            self.send_response(400)
        except sqlite3.Error as exc:
            data = json.dumps({'error': 'database error'}).encode()
            self.send_response(500)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['init', 'serve'])
    p.add_argument('--port', type=int, default=8080)
    a = p.parse_args()
    if a.action == 'init':
        init()
    else:
        if not DB.exists():
            p.error('run init first')
        server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
        print(f'http://127.0.0.1:{a.port}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
