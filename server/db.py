"""SQLite WAL. Schema v3."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS module_profiles (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS categories (
  id     INTEGER PRIMARY KEY,
  module TEXT NOT NULL,
  name   TEXT NOT NULL,
  UNIQUE(module, name)
);

CREATE TABLE IF NOT EXISTS demands (
  id                       INTEGER PRIMARY KEY,
  demand_name              TEXT NOT NULL,
  source_type              TEXT NOT NULL DEFAULT 'csv',
  source_config_json       TEXT,
  module_profile_id        INTEGER REFERENCES module_profiles(id),
  notify                   INTEGER NOT NULL DEFAULT 1,
  status                   TEXT NOT NULL DEFAULT 'draft'
                           CHECK (status IN ('draft','ready','enabled')),
  mapping_confirmed        INTEGER NOT NULL DEFAULT 0,
  schedule_confirmed       INTEGER NOT NULL DEFAULT 0,
  mapping_version          INTEGER NOT NULL DEFAULT 0,
  frequency                TEXT,
  run_time                 TEXT,
  weekly_dow               INTEGER,
  monthly_dom              TEXT,
  interval                 INTEGER NOT NULL DEFAULT 1,
  yearly_month             INTEGER,
  suggested_frequency      TEXT,
  suggested_time           TEXT,
  frequency_evidence_json  TEXT,
  config_version           INTEGER NOT NULL DEFAULT 0,
  last_run_id              INTEGER,
  last_run_status          TEXT,
  last_check_result        TEXT,
  last_diff_count          INTEGER,
  last_unmapped_count      INTEGER,
  next_run_at              TEXT,
  path_config_json         TEXT,
  created_at               TEXT NOT NULL,
  updated_at               TEXT NOT NULL,
  deleted_at               TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_demands_name_active
  ON demands(demand_name) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS template_rows (
  demand_id INTEGER NOT NULL REFERENCES demands(id),
  code      TEXT NOT NULL,
  name      TEXT,
  pulled_at TEXT,
  PRIMARY KEY (demand_id, code)
);

CREATE TABLE IF NOT EXISTS mapping_rows (
  demand_id        INTEGER NOT NULL REFERENCES demands(id),
  raw_name         TEXT NOT NULL,
  code             TEXT,
  mapping_state    TEXT NOT NULL DEFAULT 'needs_review'
                   CHECK (mapping_state IN ('active','needs_review')),
  first_seen_at    TEXT,
  last_seen_at     TEXT,
  last_seen_run_id INTEGER,
  PRIMARY KEY (demand_id, raw_name)
);

CREATE TABLE IF NOT EXISTS runs (
  id                     INTEGER PRIMARY KEY,
  demand_id              INTEGER NOT NULL REFERENCES demands(id),
  trigger                TEXT NOT NULL,
  execution_status       TEXT NOT NULL,
  check_result           TEXT,
  started_at             TEXT NOT NULL,
  heartbeat_at           TEXT,
  source_fetched_at      TEXT,
  finished_at            TEXT,
  failed_step            TEXT,
  error_type             TEXT,
  error_message          TEXT,
  source_complete        INTEGER,
  no_new_data            INTEGER,
  input_fingerprint      TEXT,
  n_obs                  INTEGER,
  n_mapped               INTEGER,
  n_unmapped             INTEGER,
  n_invalid              INTEGER,
  n_diff                 INTEGER,
  periods_json           TEXT,
  unmapped_json          TEXT,
  config_version         INTEGER,
  config_snapshot_json   TEXT,
  template_snapshot_json TEXT,
  mapping_snapshot_json  TEXT,
  artifact_path          TEXT,
  delivery_status        TEXT,
  diff_signature         TEXT,
  notification_signature TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_one_running
  ON runs(demand_id) WHERE execution_status = 'RUNNING';

CREATE TABLE IF NOT EXISTS diff_ledger (
  id        INTEGER PRIMARY KEY,
  run_id    INTEGER NOT NULL REFERENCES runs(id),
  demand_id INTEGER NOT NULL REFERENCES demands(id),
  period    TEXT NOT NULL,
  code      TEXT NOT NULL,
  name      TEXT,
  src_value REAL,
  ref_value REAL,
  diff_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_diff_demand_period ON diff_ledger(demand_id, period);
CREATE INDEX IF NOT EXISTS ix_diff_run ON diff_ledger(run_id);

CREATE TABLE IF NOT EXISTS notifications (
  id           INTEGER PRIMARY KEY,
  demand_id    INTEGER NOT NULL REFERENCES demands(id),
  run_id       INTEGER NOT NULL REFERENCES runs(id),
  event        TEXT NOT NULL,
  status       TEXT NOT NULL,
  signature    TEXT,
  payload_json TEXT,
  attempts     INTEGER NOT NULL DEFAULT 0,
  last_error   TEXT,
  created_at   TEXT NOT NULL,
  sent_at      TEXT
);
"""

DROP = (
    "audit_log", "users", "mapping_history", "template_snapshots", "template_snapshot_rows",
    "run_periods", "notification_targets", "notification_routes",
    "notifications", "diff_ledger", "runs", "mapping_rows", "template_rows",
    "demands", "categories", "module_profiles", "settings",
)


def db_path(path: Path | None = None) -> Path:
    return Path(path or os.environ.get("APP_DB") or ROOT / "data" / "app.db")


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = db_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init(path: Path | None = None) -> sqlite3.Connection:
    conn = connect(path)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver < 3:
        conn.execute("PRAGMA foreign_keys=OFF")
        for t in DROP:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version=3")
        conn.commit()
    from server.seed import seed
    seed(conn)
    return conn
