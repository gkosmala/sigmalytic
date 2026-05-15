"""
start_sigmalytic.py
-------------------
One-command process manager for Sigmalytic.
Starts FastAPI (Uvicorn) and Dash (Gunicorn) together.
Ctrl+C shuts both down cleanly.

Usage:
    python start_sigmalytic.py              # production-style
    python start_sigmalytic.py --dev        # Uvicorn auto-reload enabled
"""

import subprocess
import sys
import os
import signal
import time
import argparse

# ── Configuration ─────────────────────────────────────────────────────────────

BACKEND_HOST  = "0.0.0.0"
BACKEND_PORT  = "8000"
FRONTEND_HOST = "0.0.0.0"
FRONTEND_PORT = "8050"

# Paths relative to this script (assumed to live in project root)
BACKEND_APP   = "backend.main:app"
FRONTEND_APP  = "frontend.app:server"

# Gunicorn worker count — 2-4 is fine for a single-machine dev/beta setup
GUNICORN_WORKERS = "2"

# ── Argument Parsing ───────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Sigmalytic process manager")
parser.add_argument(
    "--dev",
    action="store_true",
    help="Enable Uvicorn auto-reload (development mode)"
)
args = parser.parse_args()

# ── Build subprocess commands ──────────────────────────────────────────────────

uvicorn_cmd = [
    sys.executable, "-m", "uvicorn",
    BACKEND_APP,
    "--host", BACKEND_HOST,
    "--port", BACKEND_PORT,
    "--log-level", "info",
]
if args.dev:
    uvicorn_cmd.append("--reload")

gunicorn_cmd = [
    "gunicorn",
    FRONTEND_APP,
    "--bind", f"{FRONTEND_HOST}:{FRONTEND_PORT}",
    "--workers", GUNICORN_WORKERS,
    "--timeout", "120",
    "--log-level", "info",
]

# ── Startup ────────────────────────────────────────────────────────────────────

def banner(text, char="─"):
    width = 60
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}\n")

processes = []

def shutdown(signum=None, frame=None):
    banner("Shutting down Sigmalytic...", char="━")
    for p in processes:
        if p.poll() is None:          # still running
            p.terminate()
    time.sleep(1)
    for p in processes:
        if p.poll() is None:          # still hasn't stopped
            p.kill()
    print("  All processes stopped. Goodbye.\n")
    sys.exit(0)

signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

banner("Starting Sigmalytic" + (" [DEV MODE]" if args.dev else ""), char="═")
print(f"  Backend  → http://{BACKEND_HOST}:{BACKEND_PORT}")
print(f"  Frontend → http://{FRONTEND_HOST}:{FRONTEND_PORT}")
print(f"  Mode     → {'Development (auto-reload)' if args.dev else 'Production'}")
print(f"\n  Press Ctrl+C to stop both servers.\n")

# Launch backend first, give it a moment to bind
backend_proc = subprocess.Popen(uvicorn_cmd)
processes.append(backend_proc)
time.sleep(2)

# Launch frontend
frontend_proc = subprocess.Popen(gunicorn_cmd)
processes.append(frontend_proc)

# ── Monitor loop ───────────────────────────────────────────────────────────────
# If either process dies unexpectedly, report it and bring everything down.

while True:
    time.sleep(3)
    for name, proc in [("Backend (Uvicorn)", backend_proc),
                        ("Frontend (Gunicorn)", frontend_proc)]:
        rc = proc.poll()
        if rc is not None:
            print(f"\n  ⚠  {name} exited unexpectedly (code {rc}). Shutting down.")
            shutdown()