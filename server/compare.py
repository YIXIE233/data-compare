"""Outer compare on (period, code). Equal rows are not diffs."""
from __future__ import annotations

import pandas as pd

ATOL = 1e-6
DIFF_VALUE = "数值不同"
DIFF_SRC = "源有库无"
DIFF_DB = "库有源无"


def _idx(df):
    out = df.copy()
    out["period"] = pd.to_datetime(out["period"]).dt.date
    out["code"] = out["code"].astype(str)
    return out.set_index(["period", "code"])["value"]


def compare(source_df, db_df, source_complete=True, atol=None):
    atol = ATOL if atol is None else float(atol)
    sm, dm = _idx(source_df), _idx(db_df)
    diffs = []
    for k in sm.index.union(dm.index):
        in_s, in_d = k in sm.index, k in dm.index
        if in_s and in_d:
            a, b = float(sm.loc[k]), float(dm.loc[k])
            if abs(a - b) > atol:
                diffs.append({"type": DIFF_VALUE, "period": k[0], "code": k[1], "source": a, "ref": b})
        elif in_s:
            diffs.append({"type": DIFF_SRC, "period": k[0], "code": k[1], "source": float(sm.loc[k]), "ref": None})
        elif in_d and source_complete:
            diffs.append({"type": DIFF_DB, "period": k[0], "code": k[1], "source": None, "ref": float(dm.loc[k])})
    return diffs
