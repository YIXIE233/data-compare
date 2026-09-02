"""Exact-name prefill, validate, apply. Unmapped names never become codes."""
from __future__ import annotations

import pandas as pd


class MappingError(ValueError):
    pass


def suggest_prefill(raw_names, template):
    hit = {t["name"]: t["code"] for t in template}
    return [{"raw_name": n, "code": hit.get(n), "pending": n in hit} for n in raw_names]


def validate_mappings(rows, template_codes):
    seen = {}
    for r in rows:
        z = r.get("code")
        if not z:
            continue
        if z not in template_codes:
            raise MappingError(f"编码不在目录: {z}")
        if z in seen:
            raise MappingError(f"编码重复: {z}")
        seen[z] = r["raw_name"]
    return True


def apply_mapping(obs, mappings):
    by = {m["raw_name"]: m for m in mappings}
    mapped, unmapped, seen_u = [], [], set()
    for _, row in obs.iterrows():
        raw = row["name"]
        m = by.get(raw)
        code = (m or {}).get("code")
        state = (m or {}).get("mapping_state", "active")
        if not code or state == "needs_review":
            if raw not in seen_u:
                unmapped.append(raw)
                seen_u.add(raw)
            continue
        mapped.append(
            {
                "raw_name": raw,
                "code": str(code),
                "value": float(row["value"]),
                "period": row["period"],
            }
        )
    return pd.DataFrame(mapped), unmapped
