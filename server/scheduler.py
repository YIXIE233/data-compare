"""Job specs from DB. Optional APScheduler CronTrigger via trigger_factory."""
from __future__ import annotations

from datetime import datetime, timedelta


def job_id(demand_id):
    return f"demand:{demand_id}"


def enabled_specs(conn):
    rows = conn.execute(
        """SELECT id, frequency, run_time, weekly_dow, monthly_dom, interval, yearly_month
           FROM demands
           WHERE status='enabled' AND deleted_at IS NULL
             AND frequency IS NOT NULL AND frequency != ''"""
    )
    return [
        {
            "id": job_id(r["id"]),
            "demand_id": r["id"],
            "frequency": r["frequency"],
            "run_time": r["run_time"],
            "weekly_dow": r["weekly_dow"],
            "monthly_dom": r["monthly_dom"],
            "interval": r["interval"] if "interval" in r.keys() else 1,
            "yearly_month": r["yearly_month"] if "yearly_month" in r.keys() else None,
        }
        for r in rows
    ]


def _hm(spec):
    parts = (spec.get("run_time") or "09:00").split(":")
    return int(parts[0]), int(parts[1])


def _n(spec):
    try:
        n = int(spec.get("interval") or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, n)


def _tz():
    name = "Asia/Shanghai"
    try:
        from server.db import connect

        conn = connect()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key='timezone'").fetchone()
            if row and row["value"]:
                name = row["value"]
        finally:
            conn.close()
    except Exception:
        pass
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        return None


def parts(v):
    if v is None or v == "":
        return []
    seq = v if isinstance(v, (list, tuple)) else str(v).split(",")
    out = []
    for x in seq:
        s = str(x).strip()
        if not s:
            continue
        if s == "last":
            out.append("last")
            continue
        try:
            out.append(int(s))
        except ValueError:
            pass
    return out


def csv_field(v):
    xs = parts(v)
    return ",".join(str(x) for x in xs) if xs else None


def normalize_spec(frequency, weekly_dow=None, monthly_dom=None, yearly_month=None, interval=1, run_time=None):
    f = (frequency or "").strip()
    wd, md, ym = csv_field(weekly_dow), csv_field(monthly_dom), csv_field(yearly_month)
    try:
        n = max(1, int(interval or 1))
    except (TypeError, ValueError):
        n = 1
    if f == "weekdays":
        f, wd = "weekly", wd or "1,2,3,4,5"
    elif f == "yearly":
        f, ym = "monthly", ym or "12"
    elif f == "quarterly":
        f, ym, md = "monthly", ym or "3,6,9,12", md or "last"
    elif f == "semiannual":
        f, ym, md = "monthly", ym or "6,12", md or "last"
    if f == "monthly":
        n = 1
    return {
        "frequency": f,
        "weekly_dow": wd,
        "monthly_dom": md,
        "yearly_month": ym,
        "interval": n,
        "run_time": run_time,
    }


def _start(hh, mm, tz, weekday=None):
    now = datetime.now(tz) if tz else datetime.now()
    start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=1)
    if weekday is not None:
        while start.weekday() != weekday:
            start += timedelta(days=1)
    return start


def due(spec, now=None):
    n = _n(spec)
    if spec.get("frequency") != "weekly" or n <= 1:
        return True
    now = now or datetime.now(_tz() or None)
    # ponytail: week-index modulo, not anchored to enable date
    return (now.toordinal() // 7) % n == 0


_DOW = {1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat", 7: "sun", 0: "mon"}


def make_trigger(spec):
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    norm = normalize_spec(
        spec.get("frequency"),
        spec.get("weekly_dow"),
        spec.get("monthly_dom"),
        spec.get("yearly_month"),
        spec.get("interval"),
        spec.get("run_time"),
    )
    tz = _tz()
    hh, mm = _hm({"run_time": norm["run_time"] or spec.get("run_time")})
    n = norm["interval"]
    f = norm["frequency"]
    kw = {"hour": hh, "minute": mm, "timezone": tz}
    if f == "weekly":
        dows = [d for d in parts(norm["weekly_dow"]) if d in _DOW]
        names = ",".join(_DOW[d] for d in (dows or [1]))
        return CronTrigger(day_of_week=names, **kw)
    if f == "monthly":
        months = [m for m in parts(norm["yearly_month"]) if isinstance(m, int) and 1 <= m <= 12]
        days = parts(norm["monthly_dom"]) or ["last"]
        if months and len(set(months)) < 12:
            kw["month"] = ",".join(str(m) for m in months)
        return CronTrigger(day=",".join(str(d) for d in days), **kw)
    if f == "daily" and n > 1:
        return IntervalTrigger(days=n, start_date=_start(hh, mm, tz), timezone=tz)
    return CronTrigger(**kw)


def next_fire(spec, now=None):
    trig = make_trigger(spec)
    tz = _tz()
    now = now or (datetime.now(tz) if tz else datetime.now())
    t = trig.get_next_fire_time(None, now)
    return t.isoformat(timespec="seconds") if t else None

def rebuild_jobs(scheduler, conn, callback=None, trigger_factory=None):
    want = {s["id"]: s for s in enabled_specs(conn)}
    have = {getattr(j, "id", j): j for j in scheduler.get_jobs()}
    for i in list(have):
        scheduler.remove_job(i)
    fn = callback or (lambda **_k: None)
    for i, spec in want.items():
        extra = {}
        if trigger_factory:
            extra["trigger"] = trigger_factory(spec)
            extra["replace_existing"] = True
            extra["misfire_grace_time"] = 3600
            extra["coalesce"] = True
        scheduler.add_job(fn, id=i, kwargs=spec, **extra)
    return list(want)


def recover_stale(conn, now=None, stale_after=None):
    now = now or datetime.now().astimezone()
    if stale_after is None:
        row = conn.execute("SELECT value FROM settings WHERE key='run_stale_after'").fetchone()
        stale_after = int(row["value"] if row else 3600)
    n = 0
    for r in conn.execute(
        "SELECT id, started_at, heartbeat_at FROM runs WHERE execution_status='RUNNING'"
    ):
        ts = r["heartbeat_at"] or r["started_at"]
        t = datetime.fromisoformat(ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=now.tzinfo)
        if now - t > timedelta(seconds=stale_after):
            conn.execute(
                """UPDATE runs SET execution_status='FAILED', check_result=NULL,
                   failed_step='stale', error_type='stale', error_message='heartbeat expired',
                   finished_at=? WHERE id=?""",
                (now.isoformat(timespec="seconds"), r["id"]),
            )
            n += 1
    conn.commit()
    return n


_sched = None


def get_scheduler():
    return _sched


def start_scheduler(callback):
    global _sched
    from apscheduler.schedulers.background import BackgroundScheduler

    from server.db import connect

    _sched = BackgroundScheduler(timezone=_tz())
    _sched.start()
    conn = connect()
    try:
        recover_stale(conn)
        rebuild_jobs(_sched, conn, callback=callback, trigger_factory=make_trigger)
    finally:
        conn.close()
    return _sched
