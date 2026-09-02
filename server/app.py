"""FastAPI: /api/* . In-memory reference catalog."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from server.artifacts import from_ledger
from server.db import ROOT, connect, init
from server.frequency import suggest
from server.mapping import MappingError, validate_mappings
from server.notifications import INBOX, flush as notif_flush, receive_inbox, send_row
from server.pipeline import RunConflict, run as pipeline_run
from server.refdata import get_ref
from server.scheduler import due, get_scheduler, make_trigger, next_fire, normalize_spec, rebuild_jobs, start_scheduler
from server.source import read_csv

app = FastAPI()


@app.on_event("startup")
def _startup():
    init()
    if os.environ.get("APP_SCHED") == "1":
        start_scheduler(_on_job)


@app.exception_handler(HTTPException)
async def _http_err(_req, exc: HTTPException):
    code = {401: "unauthorized", 400: "bad_request", 404: "not_found", 409: "conflict"}.get(exc.status_code, "error")
    return JSONResponse({"error": code, "detail": exc.detail}, status_code=exc.status_code)


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _demand(conn, did):
    row = conn.execute("SELECT * FROM demands WHERE id=? AND deleted_at IS NULL", (did,)).fetchone()
    if row is None:
        raise HTTPException(404, "demand not found")
    return row


def _paths(conn, d):
    from server.paths import PathResolver, settings_map
    prof = conn.execute("SELECT * FROM module_profiles WHERE id=?", (d.get("module_profile_id"),)).fetchone()
    return PathResolver(settings_map(conn), dict(prof) if prof else {}, dict(d)).preview()


def _n_mapped(conn, did):
    return conn.execute(
        """SELECT COUNT(*) FROM mapping_rows
           WHERE demand_id=? AND code IS NOT NULL AND code!='' AND mapping_state='active'""",
        (did,),
    ).fetchone()[0]


def _require_mapped(conn, did):
    d = _demand(conn, did)
    if not d["mapping_confirmed"] or not _n_mapped(conn, did):
        raise HTTPException(400, "无有效映射")
    return d


def _flush(conn):
    settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    notif_flush(conn, lambda item: send_row(settings, item))


def _run_and_flush(did, trigger, periods=None):
    try:
        result = pipeline_run(did, trigger=trigger, periods=periods)
    except RunConflict:
        raise HTTPException(409, "该需求正在运行中")
    c2 = connect()
    try:
        _flush(c2)
    finally:
        c2.close()
    return JSONResponse(status_code=202, content={"run_id": result["run_id"]})


def _on_job(**spec):
    if not due(spec):
        return
    did = spec.get("demand_id")
    try:
        pipeline_run(did, trigger="schedule")
    except RunConflict:
        pass
    conn = connect()
    try:
        _flush(conn)
    finally:
        conn.close()


def _resync():
    s = get_scheduler()
    if not s:
        return
    conn = connect()
    try:
        rebuild_jobs(s, conn, callback=_on_job, trigger_factory=make_trigger)
    finally:
        conn.close()


def _catalog(conn, module, _name=""):
    return [r["name"] for r in conn.execute("SELECT name FROM categories WHERE module=?", (module,))]


def _ensure_cat(conn, module, name):
    name = (name or "").strip()
    if module and name:
        conn.execute("INSERT OR IGNORE INTO categories(module, name) VALUES (?,?)", (module, name))


def _abc(module_profile_id, source_path):
    conn = connect()
    try:
        profile = conn.execute("SELECT * FROM module_profiles WHERE id=?", (module_profile_id,)).fetchone()
    finally:
        conn.close()
    if profile is None:
        raise HTTPException(400, "模块不存在")
    template = get_ref().indicators()
    if not template:
        raise HTTPException(400, "参考目录为空")
    try:
        df = read_csv(source_path)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    if df is None or len(df) == 0:
        raise HTTPException(400, "empty source")
    names, seen = [], set()
    for x in df["name"].tolist():
        n = "" if x is None else str(x).strip()
        if not n or n.lower() == "nan" or n in seen:
            continue
        seen.add(n)
        names.append(n)
    if not names:
        raise HTTPException(400, "empty source names")
    freq = suggest(get_ref().periods())
    return dict(profile), template, names, freq


def _refresh_status(conn, did):
    d = conn.execute("SELECT * FROM demands WHERE id=?", (did,)).fetchone()
    n = _n_mapped(conn, did)
    if d["status"] == "enabled":
        return
    if d["mapping_confirmed"] and d["schedule_confirmed"] and n:
        conn.execute("UPDATE demands SET status='ready', updated_at=? WHERE id=?", (_now(), did))
    else:
        conn.execute("UPDATE demands SET status='draft', updated_at=? WHERE id=?", (_now(), did))


def _bump_mapping(conn, did, now):
    n = _n_mapped(conn, did)
    conn.execute(
        "UPDATE demands SET mapping_version=mapping_version+1, mapping_confirmed=?, updated_at=? WHERE id=?",
        (1 if n else 0, now, did),
    )
    _refresh_status(conn, did)


class SourcePreviewIn(BaseModel):
    path: str


class DemandIn(BaseModel):
    demand_name: str
    module_profile_id: int
    source_path: str
    notify: int = 1
    category: str | None = None


class PathParseIn(BaseModel):
    name: str = ""
    module: str = ""
    category: str | None = None


class MappingIn(BaseModel):
    mapping_version: int
    rows: list[dict] = Field(default_factory=list)


class BulkIn(BaseModel):
    mapping_version: int
    raw_names: list[str] = Field(default_factory=list)


class BackfillIn(BaseModel):
    periods: list[str] | None = None


class ScheduleIn(BaseModel):
    frequency: str
    run_time: str | None = None
    weekly_dow: int | str | list[int] | None = None
    monthly_dom: int | str | list[int | str] | None = None
    interval: int | None = 1
    yearly_month: int | str | list[int] | None = None


class ProfileIn(BaseModel):
    name: str | None = None
    enabled: int | None = None


class ProfileNew(BaseModel):
    name: str


class PickIn(BaseModel):
    start: str | None = None


class DemandPatch(BaseModel):
    demand_name: str | None = None
    source_path: str | None = None
    notify: int | None = None
    category: str | None = None


class CatIn(BaseModel):
    module: str
    name: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings")
def settings_get():
    conn = connect()
    try:
        out = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
        from server.paths import PathResolver
        pr = PathResolver(out, {}, {})
        out["local_root"] = (out.get("local_root") or "").strip() or str(pr.root)
        return out
    finally:
        conn.close()


@app.put("/api/settings")
def settings_put(body: dict):
    conn = connect()
    try:
        for k, v in body.items():
            if isinstance(v, (dict, list)):
                continue
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)", (k, str(v)))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/module-profiles")
def profiles(all: int = 0):
    conn = connect()
    try:
        sql = "SELECT * FROM module_profiles" if all else "SELECT * FROM module_profiles WHERE enabled=1"
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


@app.put("/api/module-profiles/{pid}")
def profiles_put(pid: int, body: ProfileIn):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM module_profiles WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "模块不存在")
        data = dict(row)
        data.update({k: v for k, v in body.model_dump().items() if v is not None})
        conn.execute("UPDATE module_profiles SET name=?, enabled=? WHERE id=?", (data["name"], data["enabled"], pid))
        conn.commit()
        return dict(conn.execute("SELECT * FROM module_profiles WHERE id=?", (pid,)).fetchone())
    finally:
        conn.close()


@app.post("/api/module-profiles")
def profiles_post(body: ProfileNew):
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM module_profiles WHERE name=?", (body.name.strip(),)).fetchone():
            raise HTTPException(409, "模块名已存在")
        conn.execute("INSERT INTO module_profiles(name, enabled) VALUES (?,1)", (body.name.strip(),))
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        return dict(conn.execute("SELECT * FROM module_profiles WHERE id=?", (pid,)).fetchone())
    finally:
        conn.close()


@app.delete("/api/module-profiles/{pid}")
def profiles_del(pid: int):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM module_profiles WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "模块不存在")
        n = conn.execute(
            "SELECT COUNT(*) FROM demands WHERE module_profile_id=? AND deleted_at IS NULL", (pid,)
        ).fetchone()[0]
        if n:
            raise HTTPException(409, f"有 {n} 个任务在用，不能删")
        conn.execute("UPDATE demands SET module_profile_id=NULL WHERE module_profile_id=?", (pid,))
        conn.execute("DELETE FROM module_profiles WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.post("/api/pick/file")
def pick_file_api(body: PickIn):
    from server.pick import pick_file
    try:
        path = pick_file(body.start)
    except Exception as e:
        raise HTTPException(400, str(e))
    if not path:
        raise HTTPException(400, "已取消")
    return {"path": path}


@app.post("/api/pick/dir")
def pick_dir_api(body: PickIn):
    from server.pick import pick_dir
    try:
        path = pick_dir(body.start)
    except Exception as e:
        raise HTTPException(400, str(e))
    if not path:
        raise HTTPException(400, "已取消")
    return {"path": path}


@app.post("/api/paths/check")
def paths_check(body: dict):
    from server.paths import inspect
    return inspect(body.get("path") or "", body.get("kind") or "file")


@app.post("/api/hook/inbox")
def hook_inbox(body: dict):
    return receive_inbox(body)


@app.get("/api/hook/inbox")
def hook_inbox_get():
    return list(INBOX)


@app.get("/api/categories")
def cats_get(module: str = ""):
    conn = connect()
    try:
        if module:
            return [dict(r) for r in conn.execute("SELECT * FROM categories WHERE module=?", (module,))]
        return [dict(r) for r in conn.execute("SELECT * FROM categories")]
    finally:
        conn.close()


@app.post("/api/categories")
def cats_post(body: CatIn):
    conn = connect()
    try:
        _ensure_cat(conn, body.module, body.name)
        conn.commit()
        return {"ok": True, "module": body.module, "name": body.name.strip()}
    finally:
        conn.close()


@app.delete("/api/categories/{cid}")
def cats_del(cid: int):
    conn = connect()
    try:
        conn.execute("DELETE FROM categories WHERE id=?", (cid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/path-parse")
def path_parse(body: PathParseIn):
    from server.namer import apply
    from server.paths import PathResolver, settings_map
    conn = connect()
    try:
        sm = settings_map(conn)
    finally:
        conn.close()
    out = dict(apply(body.name, body.module, body.category or ""))
    pr = PathResolver(sm, {"name": body.module}, {})
    pv = pr.preview()
    out["root"] = pv["root"]
    return out


@app.post("/api/sources/preview")
def source_preview(body: SourcePreviewIn):
    try:
        df = read_csv(body.path)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    names = list(dict.fromkeys(str(x).strip() for x in df["name"].tolist() if str(x).strip() and str(x).lower() != "nan"))
    return {"n_names": len(names), "names": names[:20]}


@app.post("/api/demands/preview")
def demand_preview(body: DemandIn):
    _profile, template, names, freq = _abc(body.module_profile_id, body.source_path)
    from server.namer import apply
    path = apply(body.demand_name, _profile["name"], body.category or "")
    return {"template": template[:5], "n_template": len(template), "n_names": len(names), "names": names, "frequency": freq, "path": path}


@app.get("/api/demands")
def demands_list():
    conn = connect()
    try:
        sql = """SELECT d.*, p.name AS module_name, (
            SELECT COUNT(*) FROM mapping_rows m
            WHERE m.demand_id=d.id AND (m.code IS NULL OR m.code='' OR m.mapping_state='needs_review')
          ) AS unmapped_count,
          (SELECT COUNT(*) FROM mapping_rows m WHERE m.demand_id=d.id) AS n_names,
          (SELECT COUNT(*) FROM mapping_rows m
            WHERE m.demand_id=d.id AND m.code IS NOT NULL AND m.code!='' AND m.mapping_state='active') AS n_mapped,
          (SELECT started_at FROM runs WHERE id=d.last_run_id) AS last_run_at
          FROM demands d
          LEFT JOIN module_profiles p ON p.id=d.module_profile_id
          WHERE d.deleted_at IS NULL"""
        rows = [dict(r) for r in conn.execute(sql)]
        for r in rows:
            if r.get("status") == "enabled" and r.get("frequency"):
                r["next_run_at"] = next_fire(r) or r.get("next_run_at")
        rows.sort(key=lambda r: (0 if r.get("status") == "enabled" else 1, r.get("next_run_at") or "9999", r["id"]))
        return rows
    finally:
        conn.close()


@app.post("/api/demands")
def demands_post(body: DemandIn):
    profile, template, names, freq = _abc(body.module_profile_id, body.source_path)
    now = _now()
    cfg = json.dumps({"path": body.source_path, "complete": True})
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO demands(demand_name, source_type, source_config_json, module_profile_id,
               notify, status, mapping_confirmed, schedule_confirmed, mapping_version,
               suggested_frequency, suggested_time, frequency_evidence_json, created_at, updated_at)
               VALUES (?,'csv',?,?,?, 'draft', 0, 0, 0, ?, ?, ?, ?, ?)""",
            (
                body.demand_name, cfg, body.module_profile_id, body.notify,
                freq.get("frequency"), freq.get("suggested_time"),
                json.dumps(freq.get("evidence"), ensure_ascii=False, default=str) if freq else None,
                now, now,
            ),
        )
        did = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        from server.namer import apply
        bits = apply(body.demand_name, profile["name"], body.category or "")
        _ensure_cat(conn, bits["module"], bits["category"])
        conn.execute(
            "UPDATE demands SET path_config_json=? WHERE id=?",
            (json.dumps({"category": bits["category"]}, ensure_ascii=False), did),
        )
        for t in template:
            conn.execute(
                "INSERT INTO template_rows(demand_id, code, name, pulled_at) VALUES (?,?,?,?)",
                (did, t["code"], t.get("name"), now),
            )
        for n in names:
            conn.execute(
                """INSERT INTO mapping_rows(demand_id, raw_name, code, mapping_state, first_seen_at, last_seen_at)
                   VALUES (?,?,NULL,'needs_review',?,?)""",
                (did, n, now, now),
            )
        conn.commit()
        return {"id": did}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "需求名已存在")
    finally:
        conn.close()


@app.get("/api/demands/{did}")
def demands_get(did: int):
    conn = connect()
    try:
        d = dict(_demand(conn, did))
        cfg = json.loads(d.get("source_config_json") or "{}")
        d["source_path"] = cfg.get("path")
        d["n_mapped"] = _n_mapped(conn, did)
        d["n_names"] = conn.execute("SELECT COUNT(*) FROM mapping_rows WHERE demand_id=?", (did,)).fetchone()[0]
        d["n_template"] = conn.execute("SELECT COUNT(*) FROM template_rows WHERE demand_id=?", (did,)).fetchone()[0]
        d["paths"] = _paths(conn, d)
        if d.get("status") == "enabled" and d.get("frequency"):
            d["next_run_at"] = next_fire(d) or d.get("next_run_at")
        return d
    finally:
        conn.close()


@app.put("/api/demands/{did}")
def demands_put(did: int, body: DemandPatch):
    conn = connect()
    try:
        d = _demand(conn, did)
        cfg = json.loads(d["source_config_json"] or "{}")
        if body.source_path is not None:
            cfg["path"] = body.source_path
        notify = body.notify if body.notify is not None else d["notify"]
        name = body.demand_name.strip() if body.demand_name is not None else d["demand_name"]
        if not name:
            raise HTTPException(400, "需求名不能为空")
        pc = {}
        try:
            pc = json.loads(d["path_config_json"] or "{}") or {}
        except Exception:
            pc = {}
        if body.category is not None:
            pc["category"] = body.category.strip()
            prof = conn.execute("SELECT name FROM module_profiles WHERE id=?", (d["module_profile_id"],)).fetchone()
            _ensure_cat(conn, (prof["name"] if prof else ""), pc["category"])
        try:
            conn.execute(
                "UPDATE demands SET demand_name=?, source_config_json=?, notify=?, path_config_json=?, updated_at=? WHERE id=?",
                (name, json.dumps(cfg, ensure_ascii=False), notify, json.dumps(pc, ensure_ascii=False), _now(), did),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "需求名已存在")
    finally:
        conn.close()
    return {"ok": True}


@app.delete("/api/demands/{did}")
def demands_del(did: int):
    conn = connect()
    try:
        _demand(conn, did)
        conn.execute("UPDATE demands SET deleted_at=?, status='draft', updated_at=? WHERE id=?", (_now(), _now(), did))
        conn.commit()
    finally:
        conn.close()
    _resync()
    return {"ok": True}


@app.get("/api/demands/{did}/mapping")
def mapping_get(did: int):
    conn = connect()
    try:
        d = _demand(conn, did)
        rows = [dict(r) for r in conn.execute("SELECT * FROM mapping_rows WHERE demand_id=?", (did,))]
        tpl = [dict(r) for r in conn.execute("SELECT * FROM template_rows WHERE demand_id=?", (did,))]
        return {"mapping_version": d["mapping_version"], "rows": rows, "template": tpl}
    finally:
        conn.close()


@app.put("/api/demands/{did}/mapping")
def mapping_put(did: int, body: MappingIn):
    conn = connect()
    try:
        d = _demand(conn, did)
        if body.mapping_version != d["mapping_version"]:
            raise HTTPException(409, "mapping_version")
        tpl = {r["code"] for r in conn.execute("SELECT code FROM template_rows WHERE demand_id=?", (did,))}
        try:
            validate_mappings(body.rows, tpl)
        except MappingError as e:
            raise HTTPException(400, str(e)) from e
        now = _now()
        for row in body.rows:
            code = row.get("code") or None
            state = row.get("mapping_state") or ("active" if code else "needs_review")
            conn.execute(
                """INSERT INTO mapping_rows(demand_id, raw_name, code, mapping_state, first_seen_at, last_seen_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(demand_id, raw_name) DO UPDATE SET
                     code=excluded.code, mapping_state=excluded.mapping_state, last_seen_at=excluded.last_seen_at""",
                (did, row["raw_name"], code, state, now, now),
            )
        _bump_mapping(conn, did, now)
        conn.commit()
        return dict(conn.execute("SELECT mapping_version, status, mapping_confirmed FROM demands WHERE id=?", (did,)).fetchone())
    finally:
        conn.close()


@app.post("/api/demands/{did}/mapping/bulk-confirm")
def mapping_bulk_confirm(did: int, body: BulkIn):
    conn = connect()
    try:
        d = _demand(conn, did)
        if body.mapping_version != d["mapping_version"]:
            raise HTTPException(409, "mapping_version")
        now = _now()
        for name in body.raw_names:
            conn.execute(
                "UPDATE mapping_rows SET mapping_state='active', last_seen_at=? WHERE demand_id=? AND raw_name=? AND code IS NOT NULL AND code!=''",
                (now, did, name),
            )
        _bump_mapping(conn, did, now)
        conn.commit()
        return dict(conn.execute("SELECT mapping_version, status, mapping_confirmed FROM demands WHERE id=?", (did,)).fetchone())
    finally:
        conn.close()


@app.post("/api/demands/{did}/mapping/bulk-clear")
def mapping_bulk_clear(did: int, body: BulkIn):
    conn = connect()
    try:
        d = _demand(conn, did)
        if body.mapping_version != d["mapping_version"]:
            raise HTTPException(409, "mapping_version")
        now = _now()
        for name in body.raw_names:
            conn.execute(
                "UPDATE mapping_rows SET code=NULL, mapping_state='needs_review', last_seen_at=? WHERE demand_id=? AND raw_name=?",
                (now, did, name),
            )
        _bump_mapping(conn, did, now)
        conn.commit()
        return dict(conn.execute("SELECT mapping_version, status, mapping_confirmed FROM demands WHERE id=?", (did,)).fetchone())
    finally:
        conn.close()


@app.post("/api/demands/{did}/refresh-template")
def refresh_template(did: int):
    conn = connect()
    try:
        d = _demand(conn, did)
        fresh = {t["code"]: t for t in get_ref().indicators()}
        now = _now()
        have = {r["code"] for r in conn.execute("SELECT code FROM template_rows WHERE demand_id=?", (did,))}
        for z, t in fresh.items():
            if z not in have:
                conn.execute(
                    "INSERT INTO template_rows(demand_id, code, name, pulled_at) VALUES (?,?,?,?)",
                    (did, t["code"], t.get("name"), now),
                )
        gone = have - set(fresh)
        if gone:
            conn.execute(
                f"""UPDATE mapping_rows SET mapping_state='needs_review'
                    WHERE demand_id=? AND code IN ({','.join('?' * len(gone))})""",
                (did, *gone),
            )
            conn.execute("UPDATE demands SET mapping_confirmed=0, status='draft', updated_at=? WHERE id=?", (now, did))
        conn.commit()
        return {"added": len(set(fresh) - have), "removed": list(gone)}
    finally:
        conn.close()


@app.post("/api/demands/{did}/refresh-source")
def refresh_source(did: int):
    conn = connect()
    try:
        d = _demand(conn, did)
        cfg = json.loads(d["source_config_json"] or "{}")
        df = read_csv(cfg["path"])
        now = _now()
        added = 0
        for x in df["name"].tolist():
            n = "" if x is None else str(x).strip()
            if not n:
                continue
            conn.execute(
                """INSERT INTO mapping_rows(demand_id, raw_name, mapping_state, first_seen_at, last_seen_at)
                   VALUES (?,?, 'needs_review', ?, ?)
                   ON CONFLICT(demand_id, raw_name) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                (did, n, now, now),
            )
            if conn.execute(
                "SELECT first_seen_at FROM mapping_rows WHERE demand_id=? AND raw_name=?", (did, n)
            ).fetchone()["first_seen_at"] == now:
                added += 1
        if added:
            conn.execute("UPDATE demands SET mapping_version=mapping_version+1, updated_at=? WHERE id=?", (now, did))
        conn.commit()
        return {"added": added}
    finally:
        conn.close()


@app.get("/api/demands/{did}/schedule")
def schedule_get(did: int):
    conn = connect()
    try:
        d = _demand(conn, did)
        return {
            "frequency": d["frequency"],
            "run_time": d["run_time"],
            "weekly_dow": d["weekly_dow"],
            "monthly_dom": d["monthly_dom"],
            "interval": d["interval"] if "interval" in d.keys() else 1,
            "yearly_month": d["yearly_month"] if "yearly_month" in d.keys() else None,
            "suggested_frequency": d["suggested_frequency"],
            "suggested_time": d["suggested_time"],
            "schedule_confirmed": d["schedule_confirmed"],
        }
    finally:
        conn.close()


@app.put("/api/demands/{did}/schedule")
def schedule_put(did: int, body: ScheduleIn):
    conn = connect()
    try:
        _demand(conn, did)
        if not (body.frequency or "").strip():
            raise HTTPException(400, "请选择频率")
        norm = normalize_spec(
            body.frequency, body.weekly_dow, body.monthly_dom, body.yearly_month, body.interval, body.run_time,
        )
        f = norm["frequency"]
        if f not in ("daily", "weekly", "monthly"):
            raise HTTPException(400, "频率须为每天、每周或每月")
        if f == "weekly" and not norm["weekly_dow"]:
            raise HTTPException(400, "请选择星期")
        if f == "monthly" and not norm["monthly_dom"]:
            raise HTTPException(400, "请选择日期")
        conn.execute(
            """UPDATE demands SET frequency=?, run_time=?, weekly_dow=?, monthly_dom=?, interval=?, yearly_month=?,
               schedule_confirmed=1, updated_at=? WHERE id=?""",
            (f, norm["run_time"], norm["weekly_dow"], norm["monthly_dom"], norm["interval"], norm["yearly_month"], _now(), did),
        )
        _refresh_status(conn, did)
        conn.commit()
        out = dict(conn.execute("SELECT frequency, run_time, status, schedule_confirmed FROM demands WHERE id=?", (did,)).fetchone())
    finally:
        conn.close()
    _resync()
    return out


@app.post("/api/demands/{did}/enable")
def enable(did: int):
    conn = connect()
    try:
        d = _require_mapped(conn, did)
        if not d["frequency"]:
            raise HTTPException(400, "空频率")
        if not d["schedule_confirmed"]:
            raise HTTPException(400, "未确认调度")
        conn.execute("UPDATE demands SET status='enabled', updated_at=? WHERE id=?", (_now(), did))
        conn.commit()
    finally:
        conn.close()
    _resync()
    return {"status": "enabled"}


@app.post("/api/demands/{did}/disable")
def disable(did: int):
    conn = connect()
    try:
        _demand(conn, did)
        conn.execute("UPDATE demands SET status='ready', updated_at=? WHERE id=?", (_now(), did))
        conn.commit()
    finally:
        conn.close()
    _resync()
    return {"status": "ready"}


@app.post("/api/demands/{did}/run")
def demand_run(did: int):
    conn = connect()
    try:
        _require_mapped(conn, did)
    finally:
        conn.close()
    return _run_and_flush(did, "manual")


@app.post("/api/demands/{did}/backfill")
def demand_backfill(did: int, body: BackfillIn):
    conn = connect()
    try:
        _require_mapped(conn, did)
    finally:
        conn.close()
    return _run_and_flush(did, "backfill", periods=body.periods)


@app.get("/api/demands/{did}/runs")
def demand_runs(did: int, limit: int = 20, offset: int = 0):
    conn = connect()
    try:
        _demand(conn, did)
        return [dict(r) for r in conn.execute(
            "SELECT * FROM runs WHERE demand_id=? ORDER BY id DESC LIMIT ? OFFSET ?", (did, limit, offset),
        )]
    finally:
        conn.close()


@app.get("/api/runs/{rid}")
def run_get(rid: int):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "run not found")
        return dict(row)
    finally:
        conn.close()


@app.post("/api/runs/{rid}/retry")
def run_retry(rid: int):
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "run not found")
        did = row["demand_id"]
        _require_mapped(conn, did)
    finally:
        conn.close()
    return _run_and_flush(did, "retry")


@app.get("/api/runs/{rid}/diffs")
def run_diffs(rid: int):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM diff_ledger WHERE run_id=? ORDER BY id", (rid,))]
    finally:
        conn.close()


@app.get("/api/runs/{rid}/diffs.xlsx")
def run_xlsx(rid: int):
    conn = connect()
    try:
        row = conn.execute("SELECT artifact_path FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "run not found")
        path = row["artifact_path"]
        if path and Path(path).exists():
            return FileResponse(path, filename=Path(path).name)
        tmp = ROOT / "data" / "output" / f"run_{rid}_diff.xlsx"
        from_ledger(conn, rid, tmp)
        return FileResponse(tmp, filename=tmp.name)
    finally:
        conn.close()


@app.get("/{full_path:path}")
def spa(full_path: str):
    dist = ROOT / "web" / "dist"
    if not dist.exists():
        raise HTTPException(404, "no ui")
    target = (dist / full_path).resolve() if full_path else dist
    if full_path and target.is_file() and str(target).startswith(str(dist.resolve())):
        return FileResponse(target)
    index = dist / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    raise HTTPException(404, "no ui")
