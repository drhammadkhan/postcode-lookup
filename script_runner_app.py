#!/usr/bin/env python3
"""
Local Script Runner — a tiny web UI to run the data pipeline scripts.
Runs on port 5002, separate from the main Flask app on 5001.
Uses only the stdlib (no Flask needed).
"""
import os, sys, threading, subprocess, json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = [
    {"key": "postcode_lookup", "label": "postcode_lookup.py", "cmd": [sys.executable, "-u", "postcode_lookup.py"]},
    {"key": "generate_map",    "label": "generate_map.py",    "cmd": [sys.executable, "-u", "generate_map.py"]},
    {"key": "build_static",    "label": "build_static.py",    "cmd": [sys.executable, "-u", "build_static.py"]},
]
SCRIPT_MAP = {s["key"]: s for s in SCRIPTS}

# ── shared state ──────────────────────────────────────────────
state_lock = threading.Lock()
state = {
    "running": False,
    "current": None,
    "log": [],
    "last_exit": None,
    "last_run": None,
}

def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with state_lock:
        state["log"].append(f"[{ts}] {msg}")
        state["log"] = state["log"][-500:]

def _run_one(key):
    s = SCRIPT_MAP[key]
    _log(f"▶ Starting {s['label']} …")
    try:
        proc = subprocess.Popen(
            s["cmd"], cwd=BASE_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            _log(line.rstrip("\n"))
        rc = proc.wait()
    except Exception as exc:
        _log(f"ERROR: {exc}")
        rc = 1
    _log(f"{'✓' if rc == 0 else '✗'} Finished {s['label']} (exit {rc})")
    return rc

def _worker(keys):
    with state_lock:
        state["running"] = True
        state["current"] = None
        state["log"] = []
        state["last_exit"] = None
        state["last_run"] = datetime.now().strftime("%H:%M:%S")
    for key in keys:
        with state_lock:
            state["current"] = key
        rc = _run_one(key)
        with state_lock:
            state["last_exit"] = rc
        if rc != 0:
            _log("⚠ Pipeline stopped — a script failed.")
            break
    with state_lock:
        state["running"] = False
        state["current"] = None

# ── HTML ──────────────────────────────────────────────────────
HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Script Runner</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:24px;color:#111;background:#f5f7fa}
h1{margin:0 0 4px}
.note{color:#555;margin-bottom:18px;font-size:14px}
.buttons{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
button{padding:10px 18px;font-size:14px;border-radius:8px;border:1px solid #bbb;background:#fff;cursor:pointer;transition:.15s}
button:hover{background:#eee}
button.primary{background:#2563eb;color:#fff;border-color:#2563eb;font-weight:600}
button.primary:hover{background:#1d4ed8}
button:disabled{opacity:.5;cursor:not-allowed}
.bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.pill{background:#e0e7ff;color:#1e3a8a;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:500}
.pill.ok{background:#dcfce7;color:#166534}
.pill.err{background:#fee2e2;color:#991b1b}
#log{background:#0f172a;color:#cbd5e1;padding:14px;border-radius:10px;height:380px;overflow-y:auto;font-size:12px;font-family:"SF Mono",Menlo,Consolas,monospace;white-space:pre-wrap;line-height:1.5}
</style></head><body>
<h1>🚀 Script Runner</h1>
<p class="note">Run the data pipeline without the terminal. Separate from the main app (port 5001).</p>

<div class="buttons">
  <button class="primary" id="btn-all" onclick="go('all')">Run All  (lookup → map → static)</button>
  <button id="btn-postcode_lookup" onclick="go('postcode_lookup')">postcode_lookup.py</button>
  <button id="btn-generate_map" onclick="go('generate_map')">generate_map.py</button>
  <button id="btn-build_static" onclick="go('build_static')">build_static.py</button>
</div>

<div class="bar">
  <span class="pill" id="p-status">● Idle</span>
  <span class="pill" id="p-current">—</span>
  <span class="pill" id="p-exit">—</span>
  <span class="pill" id="p-time">—</span>
</div>

<div id="log">Ready. Click a button above to start.</div>

<script>
const btns = document.querySelectorAll('button');
const logEl = document.getElementById('log');

async function go(key) {
  try {
    const r = await fetch('/run', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({key: key})
    });
    const d = await r.json();
    if (d.error) alert(d.error);
  } catch(e) { alert('Request failed: ' + e); }
}

async function poll() {
  try {
    const r = await fetch('/status');
    const d = await r.json();

    const ps = document.getElementById('p-status');
    ps.textContent = d.running ? '⏳ Running' : '● Idle';
    ps.className = 'pill' + (d.running ? ' ok' : '');

    document.getElementById('p-current').textContent = d.current ? '▸ ' + d.current : '—';

    const pe = document.getElementById('p-exit');
    if (d.last_exit === null) { pe.textContent = '—'; pe.className = 'pill'; }
    else if (d.last_exit === 0) { pe.textContent = '✓ exit 0'; pe.className = 'pill ok'; }
    else { pe.textContent = '✗ exit ' + d.last_exit; pe.className = 'pill err'; }

    document.getElementById('p-time').textContent = d.last_run ? '🕐 ' + d.last_run : '—';

    btns.forEach(function(b){ b.disabled = d.running; });

    var atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 60;
    logEl.textContent = (d.log && d.log.length) ? d.log.join('\n') : 'Ready. Click a button above to start.';
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;
  } catch(e) {}
}
setInterval(poll, 800);
poll();
</script>
</body></html>"""

# ── HTTP handler ──────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            with state_lock:
                body = json.dumps(state).encode()
            self._reply(200, body, "application/json")
        else:
            self._reply(200, HTML.encode(), "text/html")

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw)
            key = data.get("key", "")

            with state_lock:
                if state["running"]:
                    self._reply(409, json.dumps({"error": "A run is already in progress"}).encode(), "application/json")
                    return

            if key == "all":
                keys = [s["key"] for s in SCRIPTS]
            elif key in SCRIPT_MAP:
                keys = [key]
            else:
                self._reply(400, json.dumps({"error": f"Unknown script: {key}"}).encode(), "application/json")
                return

            threading.Thread(target=_worker, args=(keys,), daemon=True).start()
            self._reply(200, json.dumps({"ok": True}).encode(), "application/json")
        else:
            self._reply(404, json.dumps({"error": "Not found"}).encode(), "application/json")

    def _reply(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # keep console quiet

if __name__ == "__main__":
    port = 5002
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Script Runner running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
