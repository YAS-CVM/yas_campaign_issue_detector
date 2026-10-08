"""Accès aux données : snapshots, faits Push / IM, cycle de vie des anomalies."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from ..config import severity_rank
from ..detect.base import Anomaly
from ..ingest.loader import Snapshot
from .db import ensure_fact_indexes, table_exists

IM_KEY = ["date", "touchpoint", "rule_id", "offer_id"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- snapshots

def snapshot_exists(conn: sqlite3.Connection, file_hash: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM snapshots WHERE file_hash=?", (file_hash,)).fetchone()


def insert_snapshot(conn: sqlite3.Connection, snap: Snapshot) -> int:
    date_min, date_max = snap.date_range
    cur = conn.execute(
        "INSERT INTO snapshots(file_name, file_hash, snapshot_date, ingested_at, push_rows, im_rows, date_min, date_max)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (snap.path.name, snap.file_hash, snap.snapshot_date.isoformat(), _now(),
         len(snap.push), len(snap.im), date_min, date_max),
    )
    snapshot_id = cur.lastrowid
    for table, df in (("push_facts", snap.push), ("im_facts", snap.im)):
        out = df.copy()
        out.insert(0, "snapshot_id", snapshot_id)
        for c in out.columns:  # dtypes pyarrow / string -> types SQLite natifs
            if out[c].dtype == bool or str(out[c].dtype).startswith("bool"):
                out[c] = out[c].astype(int)
            elif not pd.api.types.is_numeric_dtype(out[c]):
                out[c] = out[c].astype(object).where(out[c].notna(), None)
        _align_columns(conn, table, out)
        out.to_sql(table, conn, if_exists="append", index=False)
    ensure_fact_indexes(conn)
    return snapshot_id


def _align_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """Ajoute les colonnes nouvelles si le format du fichier évolue."""
    if not table_exists(conn, table):
        return
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    for col in df.columns:
        if col not in existing:
            sql_type = "REAL" if pd.api.types.is_numeric_dtype(df[col]) else "TEXT"
            conn.execute(f'ALTER TABLE {table} ADD COLUMN "{col}" {sql_type}')


def list_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM snapshots ORDER BY snapshot_date, id", conn)


def get_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()


def latest_snapshot(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1").fetchone()


def previous_snapshot(conn: sqlite3.Connection, snapshot_date: str, exclude_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM snapshots WHERE snapshot_date < ? AND id != ? ORDER BY snapshot_date DESC, id DESC LIMIT 1",
        (snapshot_date, exclude_id),
    ).fetchone()


def load_push(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    if not table_exists(conn, "push_facts"):
        return pd.DataFrame()
    df = pd.read_sql("SELECT * FROM push_facts WHERE snapshot_id=?", conn, params=(snapshot_id,))
    if "is_seeding" in df:
        df["is_seeding"] = df["is_seeding"].astype(bool)
    return df


def load_im(conn: sqlite3.Connection, snapshot_id: int) -> pd.DataFrame:
    if not table_exists(conn, "im_facts"):
        return pd.DataFrame()
    return pd.read_sql("SELECT * FROM im_facts WHERE snapshot_id=?", conn, params=(snapshot_id,))


def push_versions(conn: sqlite3.Connection) -> pd.DataFrame:
    """Toutes les versions de chaque broadcast, avec la date du snapshot (courbe de maturité)."""
    if not table_exists(conn, "push_facts"):
        return pd.DataFrame()
    return pd.read_sql(
        "SELECT p.*, s.snapshot_date FROM push_facts p JOIN snapshots s ON s.id = p.snapshot_id",
        conn,
    )


def history_push(conn: sqlite3.Connection, upto_date: str) -> pd.DataFrame:
    """Dernière version connue de chaque broadcast, sur tous les snapshots <= upto_date."""
    if not table_exists(conn, "push_facts"):
        return pd.DataFrame()
    df = pd.read_sql(
        "SELECT p.*, s.snapshot_date FROM push_facts p JOIN snapshots s ON s.id = p.snapshot_id"
        " WHERE s.snapshot_date <= ? ORDER BY s.snapshot_date, s.id",
        conn, params=(upto_date,),
    )
    if "is_seeding" in df:
        df["is_seeding"] = df["is_seeding"].astype(bool)
    return df.drop_duplicates("broadcast_id", keep="last").reset_index(drop=True)


def history_im(conn: sqlite3.Connection, upto_date: str) -> pd.DataFrame:
    if not table_exists(conn, "im_facts"):
        return pd.DataFrame()
    df = pd.read_sql(
        "SELECT i.*, s.snapshot_date FROM im_facts i JOIN snapshots s ON s.id = i.snapshot_id"
        " WHERE s.snapshot_date <= ? ORDER BY s.snapshot_date, s.id",
        conn, params=(upto_date,),
    )
    return df.drop_duplicates(IM_KEY, keep="last").reset_index(drop=True)


# --------------------------------------------------------------------------- anomalies

@dataclass
class SyncResult:
    new: list[int] = field(default_factory=list)
    reopened: list[int] = field(default_factory=list)
    escalated: list[int] = field(default_factory=list)
    ongoing: list[int] = field(default_factory=list)
    resolved: list[int] = field(default_factory=list)

    @property
    def to_notify(self) -> list[int]:
        return self.new + self.reopened + self.escalated

    def summary(self) -> str:
        return (f"{len(self.new)} nouvelle(s), {len(self.reopened)} rouverte(s), {len(self.escalated)} aggravée(s), "
                f"{len(self.ongoing)} en cours, {len(self.resolved)} résolue(s)")


def sync_anomalies(
    conn: sqlite3.Connection,
    snapshot: sqlite3.Row,
    anomalies: list[Anomaly],
    executed_rules: set[str],
) -> SyncResult:
    """Fusionne les anomalies détectées avec celles déjà connues (anti-doublon + résolution)."""
    result = SyncResult()
    snap_id, snap_date = snapshot["id"], snapshot["snapshot_date"]
    seen: set[str] = set()

    for a in anomalies:
        fp = a.fingerprint
        if fp in seen:
            continue
        seen.add(fp)
        row = conn.execute("SELECT id, status, severity FROM anomalies WHERE fingerprint=?", (fp,)).fetchone()
        values = dict(
            rule_id=a.rule_id, rule_name=a.rule_name, scope=a.scope, severity=a.severity,
            entity_type=a.entity_type, entity_key=a.entity_key, category=a.category, date=a.date,
            metric=a.metric, value=a.value, expected=a.expected, volume=int(a.volume or 0),
            message=a.message, details=json.dumps(a.details, ensure_ascii=False, default=str),
        )
        if row is None:
            cols = ", ".join(values) + ", fingerprint, status, first_seen_snapshot, last_seen_snapshot, first_seen_at, last_seen_at"
            params = list(values.values()) + [fp, "open", snap_id, snap_id, snap_date, snap_date]
            cur = conn.execute(f"INSERT INTO anomalies({cols}) VALUES ({', '.join('?' * len(params))})", params)
            result.new.append(cur.lastrowid)
            continue

        status = row["status"]
        if status == "resolved":
            status = "open"
            result.reopened.append(row["id"])
        elif severity_rank(a.severity) > severity_rank(row["severity"]) and status != "muted":
            status = "open"  # une aggravation annule l'acquittement
            result.escalated.append(row["id"])
        else:
            result.ongoing.append(row["id"])
        sets = ", ".join(f"{k}=?" for k in values)
        conn.execute(
            f"UPDATE anomalies SET {sets}, status=?, last_seen_snapshot=?, last_seen_at=?, occurrences=occurrences+1,"
            " resolved_at=NULL WHERE id=?",
            list(values.values()) + [status, snap_id, snap_date, row["id"]],
        )

    # Résolution : anomalies actives d'une règle exécutée, dans la période couverte, non revues.
    if executed_rules:
        placeholders = ",".join("?" * len(executed_rules))
        rows = conn.execute(
            f"SELECT id, fingerprint FROM anomalies WHERE status IN ('open','ack') AND rule_id IN ({placeholders})"
            " AND date >= ? AND date <= ?",
            [*executed_rules, snapshot["date_min"], snapshot["date_max"]],
        ).fetchall()
        for r in rows:
            if r["fingerprint"] not in seen:
                conn.execute("UPDATE anomalies SET status='resolved', resolved_at=? WHERE id=?", (snap_date, r["id"]))
                result.resolved.append(r["id"])
    return result


def anomalies_df(conn: sqlite3.Connection, status: list[str] | None = None, ids: list[int] | None = None) -> pd.DataFrame:
    sql, params = "SELECT * FROM anomalies WHERE 1=1", []
    if status:
        sql += f" AND status IN ({','.join('?' * len(status))})"
        params += status
    if ids is not None:
        if not ids:
            return pd.read_sql("SELECT * FROM anomalies WHERE 0", conn)
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params += ids
    df = pd.read_sql(sql, conn, params=params)
    if not df.empty:
        df["_rank"] = df["severity"].map(severity_rank)
        df = df.sort_values(["_rank", "volume", "date"], ascending=[False, False, False]).drop(columns="_rank")
    return df.reset_index(drop=True)


def set_status(conn: sqlite3.Connection, ids: list[int], status: str, by: str | None = None, note: str | None = None) -> None:
    if status not in ("open", "ack", "muted", "resolved"):
        raise ValueError(status)
    for i in ids:
        conn.execute(
            "UPDATE anomalies SET status=?, ack_by=COALESCE(?, ack_by), ack_note=COALESCE(?, ack_note), ack_at=? WHERE id=?",
            (status, by, note, _now(), i),
        )
    conn.commit()


def reminder_candidates(conn: sqlite3.Connection, realert_after_days: int, min_severity: str, today: date) -> list[int]:
    """Anomalies encore ouvertes, déjà notifiées depuis plus de N jours (rappel)."""
    df = anomalies_df(conn, status=["open"])
    if df.empty:
        return []
    df = df[df["severity"].map(severity_rank) >= severity_rank(min_severity)]
    last = pd.to_datetime(df["last_notified_at"], errors="coerce")
    due = last.notna() & ((pd.Timestamp(today) - last).dt.days >= realert_after_days)
    return df.loc[due, "id"].astype(int).tolist()


def mark_notified(conn: sqlite3.Connection, ids: list[int]) -> None:
    now = _now()
    for i in ids:
        conn.execute("UPDATE anomalies SET last_notified_at=?, notified_severity=severity WHERE id=?", (now, i))


def log_notification(conn: sqlite3.Connection, snapshot_id: int | None, channel: str, n: int, ok: bool, error: str | None = None) -> None:
    conn.execute(
        "INSERT INTO notifications(snapshot_id, channel, sent_at, n_anomalies, success, error) VALUES (?,?,?,?,?,?)",
        (snapshot_id, channel, _now(), n, int(ok), error),
    )


def notifications_df(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM notifications ORDER BY id DESC", conn)
