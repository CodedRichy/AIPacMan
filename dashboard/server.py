#!/usr/bin/env python3
"""Dashboard server (stdlib only: fastapi/uvicorn are not installed here).

    python3 dashboard/server.py [--host 127.0.0.1] [--port 8765]

Routes
  GET  /                         static page
  GET  /api/traces               list of recorded traces (+ header summary)
  GET  /api/traces/<name>        download a trace (JSONL)
  GET  /stream?trace=<name>&speed=2&start=0
                                 Server-Sent Events replay (one-way telemetry)
  POST /api/run                  record a new game (JSON body or query string:
                                 layout, pacman, ghosts, seed, maxTicks)
"""
import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, 'static')
TRACES = os.path.join(HERE, 'traces')
NAME_RE = re.compile(r'^[A-Za-z0-9_.\-]+\.jsonl$')
IDENT_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')
BASE_TPS = 8.0          # ticks per second at 1x speed


def list_traces():
    out = []
    if not os.path.isdir(TRACES):
        return out
    for name in sorted(os.listdir(TRACES)):
        if not NAME_RE.match(name):
            continue
        path = os.path.join(TRACES, name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                header = json.loads(f.readline())
                last = None
                for line in f:
                    last = line
            end = json.loads(last) if last else {}
        except (OSError, ValueError):
            continue
        out.append(dict(
            name=name, bytes=os.path.getsize(path), mtime=os.path.getmtime(path),
            layout=header.get('layout'), pacmanAgent=header.get('pacmanAgent'),
            ghostTeam=header.get('ghostTeam'), seed=header.get('seed'),
            ticks=end.get('ticks'), score=end.get('score'),
            win=end.get('win'), lose=end.get('lose')))
    out.sort(key=lambda t: -t['mtime'])
    return out


def run_recorder(params):
    layout = str(params.get('layout', 'mediumClassic'))
    pacman = str(params.get('pacman', 'GreedyAgent'))
    ghosts = str(params.get('ghosts', 'EnhancedCoordinatedGhostTeam'))
    for v in (layout, pacman, ghosts):
        if not IDENT_RE.match(v):
            raise ValueError('bad identifier: %r' % v)
    seed = int(params.get('seed', 0))
    max_ticks = max(1, min(int(params.get('maxTicks', 400)), 3000))
    cmd = [sys.executable, os.path.join(HERE, 'record.py'), '-l', layout, '-p', pacman,
           '-g', ghosts, '--seed', str(seed), '--max-ticks', str(max_ticks)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, encoding='utf-8')
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-600:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    info['name'] = os.path.basename(info['path'])
    del info['path']
    return info


class Handler(BaseHTTPRequestHandler):
    server_version = 'PacDash/1'

    def log_message(self, fmt, *args):
        if os.environ.get('DASH_QUIET') != '1':
            sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # ---- helpers ---------------------------------------------------------
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code, msg):
        self._json({'error': msg}, code)

    def _file(self, path, ctype=None, download=False):
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError:
            return self._err(404, 'not found')
        ctype = ctype or mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            ctype += '; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(path))
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == '/api/traces':
            return self._json(list_traces())
        if p.startswith('/api/traces/'):
            name = p[len('/api/traces/'):]
            if not NAME_RE.match(name):
                return self._err(400, 'bad trace name')
            return self._file(os.path.join(TRACES, name), 'application/x-ndjson', download=True)
        if p == '/stream':
            return self._stream(q)
        if p == '/':
            p = '/index.html'
        rel = os.path.normpath(p.lstrip('/'))
        full = os.path.join(STATIC, rel)
        if rel.startswith('..') or not os.path.abspath(full).startswith(STATIC + os.sep):
            return self._err(403, 'forbidden')
        if not os.path.isfile(full):
            return self._err(404, 'not found')
        return self._file(full)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/api/run':
            return self._err(404, 'not found')
        params = {k: v[0] for k, v in parse_qs(u.query).items()}
        n = int(self.headers.get('Content-Length') or 0)
        if n:
            try:
                params.update(json.loads(self.rfile.read(min(n, 65536)).decode('utf-8')))
            except ValueError:
                return self._err(400, 'bad json')
        try:
            return self._json(run_recorder(params))
        except (ValueError, TypeError) as e:
            return self._err(400, str(e))
        except subprocess.TimeoutExpired:
            return self._err(504, 'recording timed out')
        except Exception as e:   # recorder failure: surface it to the UI
            return self._err(500, str(e))

    # ---- SSE replay -------------------------------------------------------
    def _stream(self, q):
        name = q.get('trace', '')
        if not NAME_RE.match(name):
            return self._err(400, 'bad trace name')
        path = os.path.join(TRACES, name)
        if not os.path.isfile(path):
            return self._err(404, 'no such trace')
        try:
            speed = min(max(float(q.get('speed', 1)), 0.1), 64.0)
            start = max(int(q.get('start', 0)), 0)
        except ValueError:
            return self._err(400, 'bad speed/start')
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            header, footer = json.loads(lines[0]), json.loads(lines[-1])
            frames = lines[1:-1]
            header['frames'] = len(frames)
            self._send('header', json.dumps(header), -1)
            dt = 1.0 / (BASE_TPS * speed)
            nxt = time.monotonic()
            for i in range(start, len(frames)):
                self._send('frame', frames[i], i)
                nxt += dt
                delay = nxt - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            self._send('end', json.dumps(footer), len(frames))
        except (BrokenPipeError, ConnectionResetError):
            pass     # client paused / scrubbed / left

    def _send(self, event, data, ident):
        msg = 'id: %d\nevent: %s\ndata: %s\n\n' % (ident, event, data)
        self.wfile.write(msg.encode('utf-8'))
        self.wfile.flush()


def make_server(host='127.0.0.1', port=8765):
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    srv = make_server(a.host, a.port)
    print('Pac-Man dashboard on http://%s:%d/' % (a.host, a.port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
