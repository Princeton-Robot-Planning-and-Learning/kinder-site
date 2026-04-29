#!/usr/bin/env python3
"""Watch source files, regenerate the site on change, and serve with live reload.

Usage:
    python dev_server.py
    python dev_server.py --port 8080
"""
import argparse
import http.server
import os
import queue
import socketserver
import subprocess
import sys
import threading
import time
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# Changes here trigger a full `generate_pages.py` run.
REGEN_PATHS = [
    'index_template.html',
    'generate_pages.py',
    'env_whitelist.txt',
]
REGEN_GLOBS = [
    'kindergarden/docs/envs/*.md',
    'kindergarden/docs/envs/**/*.md',
    'kindergarden/notebooks/*.ipynb',
    'kinder-baselines/kinder-trajopt/notebooks/*.ipynb',
    'kinder-baselines/kinder-bilevel-planning/notebooks/*.ipynb',
]
# Changes here only trigger a browser reload (no regen needed).
RELOAD_PATHS = ['styles.css']

POLL_INTERVAL = 0.5
DEBOUNCE = 0.3


def collect_watched():
    seen = {}
    for rel in REGEN_PATHS:
        p = ROOT / rel
        if p.is_file():
            seen[p] = (p.stat().st_mtime, True)
    for pattern in REGEN_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                seen[p] = (p.stat().st_mtime, True)
    for rel in RELOAD_PATHS:
        p = ROOT / rel
        if p.is_file():
            seen[p] = (p.stat().st_mtime, False)
    return seen


class ReloadBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = []

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def broadcast(self):
        with self._lock:
            for q in list(self._subscribers):
                q.put('reload')


bus = ReloadBus()
regen_lock = threading.Lock()


def regenerate():
    with regen_lock:
        print('[dev] regenerating...', flush=True)
        start = time.time()
        result = subprocess.run(
            [sys.executable, 'generate_pages.py'],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - start
        if result.returncode != 0:
            print(f'[dev] regeneration FAILED ({elapsed:.1f}s)', flush=True)
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            return False
        print(f'[dev] regenerated ({elapsed:.1f}s)', flush=True)
        return True


def watcher_loop():
    state = collect_watched()
    pending = None
    while True:
        time.sleep(POLL_INTERVAL)
        current = collect_watched()
        changed = []
        needs_regen = False
        for path, (mtime, regen_flag) in current.items():
            prev = state.get(path)
            if prev is None or prev[0] != mtime:
                changed.append(path)
                if regen_flag:
                    needs_regen = True
        for path, (_, regen_flag) in state.items():
            if path not in current:
                changed.append(path)
                if regen_flag:
                    needs_regen = True
        if changed:
            for p in changed:
                try:
                    rel = p.relative_to(ROOT)
                except ValueError:
                    rel = p
                print(f'[dev] changed: {rel}', flush=True)
            deadline = time.time() + DEBOUNCE
            pending = (deadline, (pending[1] if pending else False) or needs_regen)
            state = current
            continue
        if pending and time.time() >= pending[0]:
            do_regen = pending[1]
            pending = None
            ok = regenerate() if do_regen else True
            if ok:
                bus.broadcast()


RELOAD_SCRIPT = b'''
<script>
(function() {
    function connect() {
        var es = new EventSource('/__reload');
        es.addEventListener('reload', function() { location.reload(); });
        es.onerror = function() { es.close(); setTimeout(connect, 1000); };
    }
    connect();
})();
</script>
'''


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        return

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def end_headers(self):
        if self.path != '/__reload':
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        if self.path == '/__reload':
            self._handle_reload_stream()
            return
        super().do_GET()

    def _handle_reload_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        q = bus.subscribe()
        try:
            try:
                self.wfile.write(b': connected\n\n')
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            while True:
                try:
                    q.get(timeout=15)
                except queue.Empty:
                    try:
                        self.wfile.write(b': ping\n\n')
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    continue
                try:
                    self.wfile.write(b'event: reload\ndata: 1\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
        finally:
            bus.unsubscribe(q)

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            for name in ('index.html', 'index.htm'):
                idx = os.path.join(path, name)
                if os.path.isfile(idx):
                    path = idx
                    break
        if path.endswith('.html') and os.path.isfile(path):
            try:
                with open(path, 'rb') as f:
                    content = f.read()
            except OSError:
                self.send_error(404)
                return None
            for marker in (b'</body>', b'</html>'):
                if marker in content:
                    content = content.replace(marker, RELOAD_SCRIPT + marker, 1)
                    break
            else:
                content = content + RELOAD_SCRIPT
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            return BytesIO(content)
        return super().send_head()


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-initial-regen', action='store_true')
    args = parser.parse_args()

    if not args.no_initial_regen:
        regenerate()

    threading.Thread(target=watcher_loop, daemon=True).start()

    server = ThreadedServer(('127.0.0.1', args.port), Handler)
    print(f'[dev] serving http://localhost:{args.port}', flush=True)
    print('[dev] press Ctrl-C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[dev] shutting down', flush=True)


if __name__ == '__main__':
    main()
