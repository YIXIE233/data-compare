"""Diff xlsx is a view of diff_ledger. Only written when there are diffs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

COLS = ["period", "code", "name", "src_value", "ref_value", "diff_type"]


def write_xlsx(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLS).to_excel(path, index=False)
    return path


def from_ledger(conn, run_id, path):
    cur = conn.execute(
        "SELECT period, code, name, src_value, ref_value, diff_type FROM diff_ledger WHERE run_id=? ORDER BY id",
        (run_id,),
    )
    rows = [dict(r) for r in cur]
    return write_xlsx(path, rows), rows
