"""python -m server.check [unit|pipeline|http]"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from server.compare import DIFF_DB, DIFF_SRC, DIFF_VALUE, compare
from server.db import init
from server.frequency import suggest
from server.mapping import MappingError, apply_mapping, suggest_prefill, validate_mappings
from server.namer import apply as namer_apply
from server.pipeline import run
from server.refdata import FakeRef

def _case(cid, fn, failed):
    try:
        fn()
        print(f"  {cid} ok")
    except Exception as e:
        print(f"  {cid} FAIL: {e}")
        failed.append(cid)


def _df(rows):
    return pd.DataFrame(rows)


def unit():
    failed = []

    def u_prefill():
        got = suggest_prefill(
            ["item1", "item1 ", "FOO", "item2"],
            [{"name": "item1", "code": "A001"}, {"name": "item2", "code": "A002"}],
        )
        assert got[0] == {"raw_name": "item1", "code": "A001", "pending": True}
        assert got[1]["code"] is None and not got[1]["pending"]
        assert got[3]["code"] == "A002"

    def u_validate():
        try:
            validate_mappings(
                [{"raw_name": "item1", "code": "A001"}, {"raw_name": "item2", "code": "A001"}],
                {"A001", "A002"},
            )
            raise AssertionError("expected MappingError")
        except MappingError:
            pass

    def u_map():
        obs = _df([
            {"name": "item1", "value": 80000, "period": "2026-03-31"},
            {"name": "item2", "value": 20000, "period": "2026-03-31"},
            {"name": "item3", "value": 25000, "period": "2026-03-31"},
        ])
        mapped, unmapped = apply_mapping(obs, [
            {"raw_name": "item1", "code": "A001"},
            {"raw_name": "item2", "code": "A002"},
            {"raw_name": "item3", "code": None},
        ])
        assert unmapped == ["item3"]
        assert list(mapped["code"]) == ["A001", "A002"]

    def u_compare():
        src = _df([
            {"code": "A001", "period": "2026-03-31", "value": 80000},
            {"code": "A002", "period": "2026-03-31", "value": 1},
            {"code": "A004", "period": "2026-03-31", "value": 9},
        ])
        db = _df([
            {"code": "A001", "period": "2026-03-31", "value": 80000},
            {"code": "A002", "period": "2026-03-31", "value": 20000},
            {"code": "A003", "period": "2026-03-31", "value": 10000},
        ])
        d = compare(src, db)
        by = {x["code"]: x["type"] for x in d}
        assert by["A002"] == DIFF_VALUE
        assert by["A004"] == DIFF_SRC
        assert by["A003"] == DIFF_DB
        assert "A001" not in by

    def u_freq():
        months = [date(2025, m, 28 if m == 2 else 30 if m in (4, 6, 9, 11) else 31) for m in range(1, 10)]
        s = suggest(months)
        assert s["frequency"] == "monthly"

    def u_namer():
        p = namer_apply("leaf", "lab", "cat1")
        assert p["rel"] == "lab\\cat1\\leaf"
        assert "HY" not in p["rel"]

    def u_inbox():
        from server.notifications import receive_inbox, INBOX
        INBOX.clear()
        receive_inbox({"title": "t", "text": "x", "event": "diff"})
        assert INBOX[-1]["body"]["title"] == "t"

    for cid, fn in [
        ("prefill", u_prefill), ("validate", u_validate), ("map", u_map),
        ("compare", u_compare), ("freq", u_freq), ("namer", u_namer), ("inbox", u_inbox),
    ]:
        _case(cid, fn, failed)
    return failed


def _setup(tmp: Path):
    os.environ["APP_DB"] = str(tmp / "t.db")
    conn = init(tmp / "t.db")
    csv = tmp / "s.csv"
    csv.write_text("name,value,period\nitem1,80000,2026-03-31\nitem2,20000,2026-03-31\nitem3,25000,2026-03-31\n", encoding="utf-8")
    now = "2026-04-01T00:00:00+08:00"
    pid = conn.execute("SELECT id FROM module_profiles WHERE name='lab'").fetchone()[0]
    conn.execute(
        """INSERT INTO demands(demand_name, source_type, source_config_json, module_profile_id, notify, status,
           mapping_confirmed, schedule_confirmed, mapping_version, created_at, updated_at)
           VALUES ('d1','csv',?,?,1,'draft',1,0,0,?,?)""",
        (json.dumps({"path": str(csv), "complete": True}), pid, now, now),
    )
    did = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for t in [{"code": "A001", "name": "item1"}, {"code": "A002", "name": "item2"}, {"code": "A003", "name": "item3"}, {"code": "A004", "name": "item4"}]:
        conn.execute("INSERT INTO template_rows(demand_id, code, name, pulled_at) VALUES (?,?,?,?)", (did, t["code"], t["name"], now))
    for raw, code in [("item1", "A001"), ("item2", "A002"), ("item3", "A003")]:
        conn.execute(
            "INSERT INTO mapping_rows(demand_id, raw_name, code, mapping_state, first_seen_at, last_seen_at) VALUES (?,?,?,'active',?,?)",
            (did, raw, code, now, now),
        )
    conn.commit()
    return conn, did


def pipeline():
    failed = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        conn, did = _setup(tmp)

        def p_run():
            r = run(did, conn=conn, ref=FakeRef())
            assert r["execution_status"] == "COMPLETED"
            assert r["check_result"] == "DIFF_FOUND"
            types = {row["diff_type"] for row in conn.execute("SELECT diff_type FROM diff_ledger WHERE run_id=?", (r["run_id"],))}
            assert DIFF_VALUE in types

        def p_unmap():
            conn.execute("UPDATE mapping_rows SET code=NULL, mapping_state='needs_review' WHERE demand_id=? AND raw_name='item3'", (did,))
            conn.commit()
            r = run(did, conn=conn, ref=FakeRef())
            assert "item3" in r["unmapped"]

        def p_conflict():
            from server.pipeline import RunConflict, _claim
            try:
                _claim(conn, did, "manual")
                run(did, conn=conn, ref=FakeRef())
                raise AssertionError("expected RunConflict")
            except RunConflict:
                pass
            conn.execute("UPDATE runs SET execution_status='FAILED' WHERE execution_status='RUNNING'")
            conn.commit()

        _case("run", p_run, failed)
        _case("unmap", p_unmap, failed)
        _case("conflict", p_conflict, failed)
        conn.close()
    return failed


def http():
    failed = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        os.environ["APP_DB"] = str(tmp / "h.db")
        init()
        csv = tmp / "s.csv"
        csv.write_text("name,value,period\nitem1,80000,2026-03-31\nitem2,20000,2026-03-31\nitem3,25000,2026-03-31\n", encoding="utf-8")
        from fastapi.testclient import TestClient
        from server.app import app
        c = TestClient(app)

        def h_health():
            assert c.get("/api/health").json()["ok"] is True

        def h_flow():
            profiles = c.get("/api/module-profiles").json()
            lab = next(p for p in profiles if p["name"] == "lab")
            created = c.post("/api/demands", json={
                "demand_name": "demo-1",
                "module_profile_id": lab["id"],
                "source_path": str(csv),
            })
            assert created.status_code == 200, created.text
            did = created.json()["id"]
            m = c.get(f"/api/demands/{did}/mapping").json()
            rows = [{"raw_name": r["raw_name"], "code": next((t["code"] for t in m["template"] if t["name"] == r["raw_name"]), None)} for r in m["rows"]]
            put = c.put(f"/api/demands/{did}/mapping", json={"mapping_version": m["mapping_version"], "rows": rows})
            assert put.status_code == 200, put.text
            ran = c.post(f"/api/demands/{did}/run")
            assert ran.status_code == 202, ran.text
            rid = ran.json()["run_id"]
            got = c.get(f"/api/runs/{rid}").json()
            assert got["execution_status"] == "COMPLETED"
            assert got["check_result"] == "DIFF_FOUND"

        def h_inbox():
            r = c.post("/api/hook/inbox", json={"title": "t", "text": "x"})
            assert r.json()["ok"] is True

        _case("health", h_health, failed)
        _case("flow", h_flow, failed)
        _case("inbox", h_inbox, failed)
    return failed


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    failed = []
    if which in ("all", "unit"):
        print("unit")
        failed += unit()
    if which in ("all", "pipeline"):
        print("pipeline")
        failed += pipeline()
    if which in ("all", "http"):
        print("http")
        failed += http()
    if failed:
        print("FAILED", failed)
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
