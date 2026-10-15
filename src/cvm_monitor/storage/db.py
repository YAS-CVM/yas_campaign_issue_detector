"""Connexion SQLite et création du schéma."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name     TEXT NOT NULL,
    file_hash     TEXT NOT NULL UNIQUE,
    snapshot_date TEXT NOT NULL,
    ingested_at   TEXT NOT NULL,
    push_rows     INTEGER,
    im_rows       INTEGER,
    date_min      TEXT,
    date_max      TEXT,
    columns       TEXT          -- JSON : colonnes brutes par feuille (changements de format NEON-dx)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint         TEXT NOT NULL UNIQUE,
    rule_id             TEXT NOT NULL,
    rule_name           TEXT,
    scope               TEXT,
    severity            TEXT NOT NULL,
    entity_type         TEXT,
    entity_key          TEXT,
    category            TEXT,
    date                TEXT,
    metric              TEXT,
    value               REAL,
    expected            TEXT,
    volume              INTEGER,
    message             TEXT,
    details             TEXT,
    status              TEXT NOT NULL DEFAULT 'open',   -- open | ack | muted | resolved
    first_seen_snapshot INTEGER,
    last_seen_snapshot  INTEGER,
    first_seen_at       TEXT,
    last_seen_at        TEXT,
    occurrences         INTEGER NOT NULL DEFAULT 1,
    resolved_at         TEXT,
    ack_by              TEXT,
    ack_note            TEXT,
    ack_at              TEXT,
    last_notified_at    TEXT,
    notified_severity   TEXT
);
CREATE INDEX IF NOT EXISTS ix_anomalies_status ON anomalies(status);
CREATE INDEX IF NOT EXISTS ix_anomalies_rule ON anomalies(rule_id);

CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id  INTEGER,
    channel      TEXT NOT NULL,
    sent_at      TEXT NOT NULL,
    n_anomalies  INTEGER,
    success      INTEGER NOT NULL,
    error        TEXT
);
"""

FACT_INDEXES = {
    "push_facts": ["snapshot_id", "broadcast_id", "date"],
    "im_facts": ["snapshot_id", "rule_id", "date"],
}


def connect(db_path: str | Path, check_same_thread: bool = True) -> sqlite3.Connection:
    """`check_same_thread=False` : pour l'API, où une dépendance FastAPI ouvre et ferme la connexion dans des threads
    différents du pool. Chaque requête a sa propre connexion, jamais partagée entre requêtes concurrentes."""
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes apparues après la création d'une base existante."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(snapshots)")}
    if "columns" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN columns TEXT")


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def ensure_fact_indexes(conn: sqlite3.Connection) -> None:
    for table, cols in FACT_INDEXES.items():
        if table_exists(conn, table):
            for col in cols:
                conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table}({col})")
