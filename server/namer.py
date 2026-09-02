"""module / optional category / demand name."""
from __future__ import annotations


def join_rel(*parts: str) -> str:
    return "\\".join(p for p in parts if p)


def apply(name: str, module: str = "", category: str = "") -> dict:
    leaf = (name or "").strip()
    mod = (module or "").strip() or "lab"
    cat = (category or "").strip()
    return {
        "module": mod,
        "category": cat,
        "leaf": leaf,
        "rel": join_rel(mod, cat, leaf),
    }
