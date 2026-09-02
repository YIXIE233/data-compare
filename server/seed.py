"""Idempotent seed: 4 lab modules + local settings."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from server.notifications import LOCAL_HOOK

PROFILES = ["lab", "alpha", "beta", "gamma"]
SETTINGS = [
    ("timezone", "Asia/Shanghai"),
    ("local_root", str(Path(__file__).resolve().parent.parent / "data")),
    ("run_stale_after", "1800"),
    ("compare_atol", "1e-6"),
    ("webhook_url", LOCAL_HOOK),
    ("notification_retry", "3"),
]
CATS = {
    "lab": ["cat1", "cat2"],
    "alpha": ["cat1"],
    "beta": ["cat1"],
    "gamma": ["cat1"],
}


def seed(conn: sqlite3.Connection) -> None:
    for name in PROFILES:
        conn.execute("INSERT OR IGNORE INTO module_profiles(name, enabled) VALUES (?,1)", (name,))
    for k, v in SETTINGS:
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
    conn.execute("UPDATE settings SET value=? WHERE key='webhook_url'", (LOCAL_HOOK,))
    for mod, names in CATS.items():
        for n in names:
            conn.execute("INSERT OR IGNORE INTO categories(module, name) VALUES (?,?)", (mod, n))
    conn.commit()
