"""Outbox. Same signature as last row for the demand → suppressed. Plain JSON webhook."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime

LOCAL_HOOK = "http://127.0.0.1:8000/api/hook/inbox"
INBOX: list[dict] = []


def enqueue(conn, demand_id, run_id, event, signature, payload="{}"):
    last = conn.execute(
        "SELECT signature FROM notifications WHERE demand_id=? ORDER BY id DESC LIMIT 1",
        (demand_id,),
    ).fetchone()
    status = "suppressed" if last and last["signature"] == signature else "pending"
    conn.execute(
        """INSERT INTO notifications(demand_id, run_id, event, status, signature, payload_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (demand_id, run_id, event, status, signature, payload,
         datetime.now().astimezone().isoformat(timespec="seconds")),
    )
    return status


def flush(conn, send_fn):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    retry = 3
    row = conn.execute("SELECT value FROM settings WHERE key='notification_retry'").fetchone()
    if row:
        try:
            retry = max(1, int(row["value"]))
        except (TypeError, ValueError):
            pass
    n = 0
    for row in [dict(r) for r in conn.execute("SELECT * FROM notifications WHERE status='pending'")]:
        err, tries, ok = None, 0, False
        for tries in range(1, retry + 1):
            try:
                send_fn(row)
                ok = True
                break
            except Exception as e:
                err = e
        if ok:
            conn.execute(
                "UPDATE notifications SET status='sent', sent_at=?, attempts=attempts+? WHERE id=?",
                (now, tries, row["id"]),
            )
        else:
            conn.execute(
                "UPDATE notifications SET status='failed', last_error=?, attempts=attempts+? WHERE id=?",
                (str(err)[:200], tries, row["id"]),
            )
        n += 1
    conn.commit()
    return n


def _post(url, data, timeout=8):
    req = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=timeout)


def _body(row):
    try:
        p = json.loads(row.get("payload_json") or "{}")
    except Exception:
        p = {}
    if not isinstance(p, dict):
        p = {"text": str(p)}
    ev = row.get("event") or "notice"
    title = p.get("title") or f"compare · {ev}"
    if p.get("text"):
        text = p["text"]
    elif p.get("n") is not None:
        text = f"{ev}: {p['n']} diffs"
    else:
        text = ev
    return {"title": title, "text": text, "event": ev}


def receive_inbox(body):
    INBOX.append({"at": datetime.now().astimezone().isoformat(timespec="seconds"), "body": body})
    del INBOX[:-20]
    return {"ok": True}


def send_row(settings, row):
    url = (settings.get("webhook_url") or "").strip()
    if not url:
        raise ValueError("未配置 webhook")
    payload = _body(row)
    if "/api/hook/inbox" in url:
        receive_inbox(payload)
        return
    _post(url, payload)
