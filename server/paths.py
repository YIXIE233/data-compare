"""One demand folder: {root}/{module}/{category}/{demand}."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from server.db import ROOT
from server.namer import apply as namer_apply


def slug(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(s or "")).strip("._")
    return s or "x"


def folder_part(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", str(s or "")).strip(" .")
    return s


def settings_map(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


class PathResolver:
    def __init__(self, settings: dict, profile: dict | None, demand: dict | None):
        self.settings = settings or {}
        self.profile = profile or {}
        self.demand = demand or {}

    def _s(self, k, default=""):
        v = self.settings.get(k)
        if v is None:
            return default
        return str(v).strip() if isinstance(v, str) else str(v)

    @property
    def root(self) -> Path:
        raw = self._s("local_root")
        return Path(raw) if raw else ROOT / "data"

    def _path_cfg(self) -> dict:
        raw = self.demand.get("path_config_json")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw or "{}")
            except Exception:
                raw = {}
        return raw if isinstance(raw, dict) else {}

    def bits(self) -> dict:
        cfg = self._path_cfg()
        return namer_apply(
            self.demand.get("demand_name") or "",
            self.profile.get("name") or "",
            cfg.get("category") or "",
        )

    def demand_dir(self) -> Path:
        b = self.bits()
        parts = [folder_part(x) for x in (b["module"], b["category"], b["leaf"]) if x]
        if not parts:
            parts = ["lab", slug(self.demand.get("demand_name") or "d")]
        return self.root.joinpath(*parts)

    def source(self) -> Path | None:
        cfg = self.demand.get("source_config_json")
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg or "{}")
            except Exception:
                cfg = {}
        p = (cfg or {}).get("path")
        return Path(p) if p else None

    def artifact(self) -> Path:
        return self.demand_dir() / "diff.xlsx"

    def preview(self) -> dict:
        src = self.source()
        b = self.bits()
        dd = self.demand_dir()
        return {
            "source": str(src) if src else "",
            "source_exists": bool(src and src.exists()),
            "root": str(self.root),
            "demand_dir": str(dd),
            "artifact": str(self.artifact()),
            "module": b["module"],
            "category": b["category"],
            "rel": b["rel"],
        }


def inspect(path: str, kind: str = "file") -> dict:
    p = Path(path) if path else None
    if not p:
        return {"ok": False, "exists": False, "msg": "路径为空"}
    exists = p.exists()
    is_dir = p.is_dir() if exists else None
    readable = writable = False
    if exists:
        try:
            readable = os.access(p, os.R_OK)
            writable = os.access(p if (kind == "dir" or is_dir) else p.parent, os.W_OK)
        except Exception as e:
            return {"ok": False, "exists": True, "path": str(p), "msg": str(e)}
    else:
        writable = os.access(p.parent, os.W_OK) if p.parent.exists() else False
    ok = exists and (is_dir if kind == "dir" else p.is_file())
    return {
        "ok": bool(ok),
        "exists": exists,
        "is_dir": is_dir,
        "readable": readable,
        "writable": writable,
        "path": str(p),
        "msg": "可用" if ok else ("不存在" if not exists else "类型不符"),
    }


def write_replace(dest: Path, write_fn) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    try:
        write_fn(tmp)
        tmp.replace(dest)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return dest
