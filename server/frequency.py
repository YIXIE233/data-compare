"""Period-gap frequency suggestion. Empty when evidence is weak."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time

BINS = (
    ("weekly", 5, 9),
    ("monthly", 28, 31),
    ("quarterly", 89, 92),
    ("semiannual", 170, 190),
    ("yearly", 360, 370),
)


def _as_date(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x)[:10]
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def _dom(d):
    import calendar
    last = calendar.monthrange(d.year, d.month)[1]
    return "last" if d.day >= last - 2 else d.day


def _p80(times):
    parsed = []
    for t in times or []:
        if t is None or t == "":
            continue
        if isinstance(t, datetime):
            parsed.append(t.time())
        elif isinstance(t, time):
            parsed.append(t)
        else:
            hh, mm, *_ = str(t).split(":")
            parsed.append(time(int(hh), int(mm)))
    if not parsed:
        return None
    parsed.sort()
    i = min(len(parsed) - 1, int(round(0.8 * (len(parsed) - 1))))
    t = parsed[i]
    return f"{t.hour:02d}:{t.minute:02d}"


def _empty():
    return {
        "frequency": None,
        "weekly_dow": None,
        "monthly_dom": None,
        "yearly_month": None,
        "interval": 1,
        "suggested_time": None,
        "evidence": None,
    }


def _classify(dates, gaps, min_consistency):
    if all(g == 1 for g in gaps):
        return "daily", 1, 1.0
    if all(d.weekday() < 5 for d in dates) and all(g in (1, 3) for g in gaps):
        n1 = sum(g == 1 for g in gaps)
        return "weekdays", 1, n1 / len(gaps)
    mode, _n = Counter(gaps).most_common(1)[0]
    best = None
    for name, lo, hi in BINS:
        cons = sum(lo <= g <= hi for g in gaps) / len(gaps)
        if cons >= min_consistency and (best is None or cons > best[0]):
            best = (cons, name, mode)
    if best:
        return best[1], best[2], best[0]
    return None, mode, sum(g == mode for g in gaps) / len(gaps)


def _canon(freq, dates, dow, dom):
    months = sorted({d.month for d in dates})
    if freq == "weekdays":
        return "weekly", {"weekly_dow": "1,2,3,4,5", "interval": 1}
    if freq == "quarterly":
        return "monthly", {"yearly_month": ",".join(str(m) for m in months) or "3,6,9,12", "monthly_dom": dom, "interval": 1}
    if freq == "semiannual":
        return "monthly", {"yearly_month": ",".join(str(m) for m in months) or "6,12", "monthly_dom": dom, "interval": 1}
    if freq == "yearly":
        return "monthly", {"yearly_month": ",".join(str(m) for m in months) or "12", "monthly_dom": dom, "interval": 1}
    extra = {"interval": 1}
    if freq == "weekly":
        extra["weekly_dow"] = dow
    if freq == "monthly":
        extra["monthly_dom"] = dom
    return freq, extra


def suggest(period_list, time_list=None, min_n=5, min_consistency=0.7):
    dates = sorted({_as_date(x) for x in period_list})
    if len(dates) < min_n:
        return _empty()
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    freq, mode, cons = _classify(dates, gaps, min_consistency)
    if not freq:
        return _empty()
    dow = Counter(d.isoweekday() for d in dates).most_common(1)[0][0]
    dom = Counter(_dom(d) for d in dates).most_common(1)[0][0]
    freq, extra = _canon(freq, dates, dow, dom)
    out = _empty()
    out.update({"frequency": freq, "suggested_time": _p80(time_list), "evidence": {"n": len(dates), "gap_mode": mode, "consistency": cons}})
    out.update(extra)
    return out
