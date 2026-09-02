"""In-memory reference catalog. indicators + observations."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

INDICATORS = [
    {"code": "A001", "name": "item1"},
    {"code": "A002", "name": "item2"},
    {"code": "A003", "name": "item3"},
    {"code": "A004", "name": "item4"},
]

OBSERVATIONS = [
    {"code": "A001", "period": date(2026, 3, 31), "value": 80000},
    {"code": "A002", "period": date(2026, 3, 31), "value": 20000},
    {"code": "A003", "period": date(2026, 3, 31), "value": 10000},
]

PERIODS = [
    date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31),
    date(2025, 4, 30), date(2025, 5, 31), date(2025, 6, 30),
    date(2025, 7, 31), date(2025, 8, 31), date(2025, 9, 30),
]


class RefError(RuntimeError):
    pass


def as_date(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    y, m, d = str(x)[:10].split("-")
    return date(int(y), int(m), int(d))


class FakeRef:
    def __init__(self, rows=None, indicators=None):
        self.rows = list(rows if rows is not None else OBSERVATIONS)
        self._indicators = list(indicators if indicators is not None else INDICATORS)
        self.fail = False

    def indicators(self, module=None):
        return list(self._indicators)

    def observations(self, codes, periods):
        if self.fail:
            raise RefError("ref error")
        pset = {as_date(p) for p in periods}
        zset = {str(z) for z in codes}
        out = [r for r in self.rows if as_date(r["period"]) in pset and str(r["code"]) in zset]
        return pd.DataFrame(out, columns=["code", "period", "value"])

    def periods(self):
        return list(PERIODS)


def get_ref():
    return FakeRef()
