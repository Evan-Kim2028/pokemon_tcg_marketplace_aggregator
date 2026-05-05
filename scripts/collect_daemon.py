"""
Background collection daemon.
Fetches a full snapshot every INTERVAL_HOURS hours, logs to data/cron.log.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_DIR / "data" / "cron.log"
INTERVAL_HOURS = 4

UV = sys.executable.replace("python", "uv").split("/bin/")[0] + "/bin/uv"
# Fallback: assume uv is on PATH
import shutil
UV_BIN = shutil.which("uv") or UV


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def run_snapshot() -> int:
    log("Starting snapshot…")
    result = subprocess.run(
        [UV_BIN, "run", "pokemon_tcg_marketplace_aggregator"],
        cwd=PROJECT_DIR,
        capture_output=False,
    )
    log(f"Snapshot finished (exit {result.returncode})")
    return result.returncode


if __name__ == "__main__":
    log(f"Daemon started — collecting every {INTERVAL_HOURS}h from {PROJECT_DIR}")
    while True:
        run_snapshot()
        log(f"Sleeping {INTERVAL_HOURS}h until next run…")
        time.sleep(INTERVAL_HOURS * 3600)
