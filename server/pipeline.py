"""pipeline.run — one path for now-run and schedule."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from hashlib import sha256

import pandas as pd

from server.artifacts import write_xlsx
from server.compare import compare
from server.db import connect
from server.mapping import apply_mapping
from server.notifications import enqueue
from server.refdata import RefError, get_ref
from server.source import pull_csv


class RunConflict(Exception):
    code = 409


class PipelineError(Exception):
    def __init__(self, step, message, err_type="error"):
        super().__init__(message)
        self.step = step
        self.err_type = err_type


def _now():
    return datetime.now().astimezone()


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _d(row):
    return {k: row[k] for k in row.keys()}


def _as_date(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    y, m, d = str(x)[:10].split("-")
    return date(int(y), int(m), int(d))


def _sig(payload):
    return sha256(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()


def _check_result(diffs, unmapped, n_invalid, complete):
    if diffs:
        return "DIFF_FOUND"
    if unmapped or n_invalid or not complete:
        return "INCOMPLETE"
    return "CLEAN"


def run(demand_id, trigger="manual", conn=None, ref=None, batch=None, after_claim=None, periods=None):
    own = conn is None
    if own:
        conn = connect()
    try:
        return _run(conn, demand_id, trigger, ref, batch, after_claim, periods)
    finally:
        if own:
            conn.close()


def _claim(conn, demand_id, trigger):
    d = conn.execute("SELECT * FROM demands WHERE id=? AND deleted_at IS NULL", (demand_id,)).fetchone()
    if d is None:
        raise PipelineError("claim", f"demand {demand_id} not found")
    if conn.execute(
        "SELECT id FROM runs WHERE demand_id=? AND execution_status='RUNNING'", (demand_id,)
    ).fetchone():
        raise RunConflict("正在运行中")
    mappings = [_d(r) for r in conn.execute("SELECT * FROM mapping_rows WHERE demand_id=?", (demand_id,))]
    template = [_d(r) for r in conn.execute("SELECT * FROM template_rows WHERE demand_id=?", (demand_id,))]
    profile = None
    if d["module_profile_id"]:
        profile = _d(conn.execute("SELECT * FROM module_profiles WHERE id=?", (d["module_profile_id"],)).fetchone())
    snap = {"demand": _d(d), "mappings": mappings, "template": template, "profile": profile}
    started = _iso()
    cur = conn.execute(
        """INSERT INTO runs(demand_id, trigger, execution_status, started_at, heartbeat_at,
             config_version, config_snapshot_json, template_snapshot_json, mapping_snapshot_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            demand_id, trigger, "RUNNING", started, started, d["config_version"],
            json.dumps(snap["demand"], ensure_ascii=False, default=str),
            json.dumps(template, ensure_ascii=False, default=str),
            json.dumps(mappings, ensure_ascii=False, default=str),
        ),
    )
    conn.commit()
    return cur.lastrowid, snap


def _validate(df):
    n_invalid = 0
    rows = []
    for _, r in df.iterrows():
        raw = "" if r["name"] is None else str(r["name"]).strip()
        if not raw or raw.lower() == "nan":
            n_invalid += 1
            continue
        try:
            v = float(r["value"])
        except Exception:
            n_invalid += 1
            continue
        try:
            jzrq = _as_date(r["period"])
        except Exception:
            n_invalid += 1
            continue
        rows.append({"name": raw, "value": v, "period": jzrq})
    return pd.DataFrame(rows), n_invalid


def _run(conn, demand_id, trigger, ref, batch, after_claim, periods_filter=None):
    run_id, snap = _claim(conn, demand_id, trigger)
    d = snap["demand"]
    if after_claim:
        after_claim(conn, run_id)
    try:
        from server.paths import PathResolver, settings_map, write_replace
        pr = PathResolver(settings_map(conn), snap.get("profile"), d)
        if batch is None:
            cfg = json.loads(d["source_config_json"] or "{}")
            batch = pull_csv(cfg["path"], complete=cfg.get("complete", True), no_new_data=cfg.get("no_new_data", False))
        conn.execute(
            """UPDATE runs SET source_fetched_at=?, source_complete=?, no_new_data=?, input_fingerprint=? WHERE id=?""",
            (batch.fetched_at, int(bool(batch.complete)), int(bool(batch.no_new_data)), batch.fingerprint, run_id),
        )
        conn.commit()

        if batch.no_new_data:
            if batch.df is not None and len(batch.df):
                raise PipelineError("pull", "no_new_data but observations present")
            return _finish(conn, run_id, demand_id, snap, "NO_NEW_DATA", [], [], 0, 0, True, None)

        obs, n_invalid = _validate(batch.df)
        if periods_filter:
            want = {_as_date(p) for p in periods_filter}
            obs = obs[obs["period"].map(_as_date).isin(want)]
            if len(obs) == 0:
                raise PipelineError("validate", "指定期间在来源中不存在")
        names = list(dict.fromkeys(obs["name"].tolist()))
        now = _iso()
        existing = {r["raw_name"] for r in conn.execute("SELECT raw_name FROM mapping_rows WHERE demand_id=?", (demand_id,))}
        new = 0
        for name in names:
            conn.execute(
                """INSERT INTO mapping_rows(demand_id, raw_name, mapping_state, first_seen_at, last_seen_at, last_seen_run_id)
                   VALUES (?,?, 'needs_review', ?, ?, ?)
                   ON CONFLICT(demand_id, raw_name) DO UPDATE SET
                     last_seen_at=excluded.last_seen_at,
                     last_seen_run_id=excluded.last_seen_run_id""",
                (demand_id, name, now, now, run_id),
            )
            if name not in existing:
                new += 1
                existing.add(name)
        if new:
            conn.execute("UPDATE demands SET mapping_version=mapping_version+1 WHERE id=?", (demand_id,))
        conn.commit()

        numeric = obs[obs["value"].notna()]
        mapped, unmapped = apply_mapping(numeric, snap["mappings"])

        periods = sorted({_as_date(x) for x in obs["period"]})
        codes = [
            str(m["code"])
            for m in snap["mappings"]
            if m.get("code") and m.get("mapping_state", "active") != "needs_review"
        ]
        adapter = ref if ref is not None else get_ref()
        try:
            db_df = adapter.observations(codes, periods)
            if db_df is None:
                raise RefError("null result")
        except RefError as e:
            raise PipelineError("query", str(e), "ref") from e

        _atol_row = conn.execute("SELECT value FROM settings WHERE key='compare_atol'").fetchone()
        _atol = float(_atol_row["value"]) if _atol_row and _atol_row["value"] else None
        empty = pd.DataFrame(columns=["period", "code", "value"])
        diffs = compare(mapped.rename(columns={"value": "value"}) if len(mapped) else empty, db_df, source_complete=bool(batch.complete), atol=_atol)
        name_by = {t["code"]: t.get("name") for t in snap["template"]}
        ledger = []
        for diff in diffs:
            ledger.append(
                {
                    "period": str(diff["period"]),
                    "code": diff["code"],
                    "name": name_by.get(diff["code"]),
                    "src_value": diff["source"],
                    "ref_value": diff["ref"],
                    "diff_type": diff["type"],
                }
            )
        for row in ledger:
            conn.execute(
                """INSERT INTO diff_ledger(run_id, demand_id, period, code, name, src_value, ref_value, diff_type)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (run_id, demand_id, row["period"], row["code"], row["name"], row["src_value"], row["ref_value"], row["diff_type"]),
            )

        artifact = None
        delivery = "NONE"
        if ledger:
            artifact = pr.artifact()
            try:
                write_replace(artifact, lambda tmp: write_xlsx(tmp, ledger))
                delivery = "WRITTEN"
            except Exception as e:
                delivery = "WRITE_FAILED"
                enqueue(conn, demand_id, run_id, "error", f"write-{run_id}", json.dumps({"title": "结果文件写入失败", "text": str(e)}, ensure_ascii=False))
                artifact = None
        cr = _check_result(ledger, unmapped, n_invalid, batch.complete)
        return _finish(
            conn, run_id, demand_id, snap, cr, ledger, unmapped, n_invalid, batch.complete, artifact,
            n_obs=len(obs), n_mapped=len(mapped), periods=periods, delivery=delivery,
        )
    except RunConflict:
        raise
    except Exception as e:
        step = getattr(e, "step", "run")
        return _fail(conn, run_id, demand_id, step, e, notify=d.get("notify", 1))


def _finish(conn, run_id, demand_id, snap, check_result, ledger, unmapped, n_invalid, complete, artifact, n_obs=0, n_mapped=0, periods=None, delivery="NONE"):
    d = snap["demand"]
    sig = _sig([{"t": r["diff_type"], "p": r["period"], "c": r["code"], "a": r["src_value"], "b": r["ref_value"]} for r in ledger]) if ledger else None
    notif_status = None
    if d.get("notify", 1) and check_result == "DIFF_FOUND":
        notif_status = enqueue(conn, demand_id, run_id, "diff", sig or "", json.dumps({"n": len(ledger)}, ensure_ascii=False))
    if d.get("notify", 1) and unmapped:
        enqueue(conn, demand_id, run_id, "error", "unmap-" + ",".join(unmapped), json.dumps({"title": "来源出现未映射指标", "text": "、".join(unmapped)}, ensure_ascii=False))
    conn.execute(
        """UPDATE runs SET execution_status='COMPLETED', check_result=?, finished_at=?,
           n_obs=?, n_mapped=?, n_unmapped=?, n_invalid=?, n_diff=?,
           periods_json=?, unmapped_json=?, artifact_path=?, diff_signature=?, notification_signature=?,
           source_complete=?, delivery_status=?
           WHERE id=?""",
        (
            check_result, _iso(), n_obs, n_mapped, len(unmapped), n_invalid, len(ledger),
            json.dumps([str(p) for p in (periods or [])]),
            json.dumps(unmapped, ensure_ascii=False),
            str(artifact) if artifact else None, sig, sig if notif_status else None,
            int(bool(complete)), delivery, run_id,
        ),
    )
    conn.execute(
        """UPDATE demands SET last_run_id=?, last_run_status='COMPLETED', last_check_result=?,
           last_diff_count=?, last_unmapped_count=?, updated_at=? WHERE id=?""",
        (run_id, check_result, len(ledger), len(unmapped), _iso(), demand_id),
    )
    conn.commit()
    return {
        "run_id": run_id,
        "execution_status": "COMPLETED",
        "check_result": check_result,
        "n_diff": len(ledger),
        "n_unmapped": len(unmapped),
        "artifact_path": str(artifact) if artifact else None,
        "delivery_status": delivery,
        "notification": notif_status,
        "unmapped": unmapped,
        "periods": [str(p) for p in (periods or [])],
    }


def _fail(conn, run_id, demand_id, step, e, notify=1):
    msg = str(e)
    et = getattr(e, "err_type", type(e).__name__)
    if notify:
        enqueue(conn, demand_id, run_id, "error", f"fail-{run_id}-{step}", json.dumps({"title": "运行失败", "text": msg}, ensure_ascii=False))
    conn.execute(
        """UPDATE runs SET execution_status='FAILED', failed_step=?, error_type=?, error_message=?, finished_at=? WHERE id=?""",
        (step, et, msg[:500], _iso(), run_id),
    )
    conn.execute(
        "UPDATE demands SET last_run_id=?, last_run_status='FAILED', updated_at=? WHERE id=?",
        (run_id, _iso(), demand_id),
    )
    conn.commit()
    return {
        "run_id": run_id,
        "execution_status": "FAILED",
        "failed_step": step,
        "error_message": msg,
    }
