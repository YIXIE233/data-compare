"""CSV source. Columns: name, value, period."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

REQUIRED = ("name", "value", "period")


class Batch:
    def __init__(self, df, complete=True, no_new_data=False, fetched_at=None, fingerprint=""):
        self.df = df
        self.complete = complete
        self.no_new_data = no_new_data
        self.fetched_at = fetched_at or datetime.now().astimezone().isoformat(timespec="seconds")
        self.fingerprint = fingerprint


def read_csv(path):
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"缺列 {missing}")
    return df.loc[:, list(REQUIRED)]


def pull_csv(path, complete=True, no_new_data=False):
    p = Path(path)
    raw = p.read_bytes() if p.exists() else b""
    fp = sha256(raw).hexdigest()
    if not p.exists():
        raise FileNotFoundError(path)
    return Batch(read_csv(p), complete=complete, no_new_data=no_new_data, fingerprint=fp)
