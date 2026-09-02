"""data compare."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.setdefault("APP_SCHED", "1")
PORT = int(os.environ.get("APP_PORT", "8000"))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.app:app", host="127.0.0.1", port=PORT, log_level="info")
