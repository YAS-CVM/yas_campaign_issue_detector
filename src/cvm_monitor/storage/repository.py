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
        "INSERT INTO snapshots(file_name, file_hash, snapshot_date, ingested_at, push_rows, im_rows, date_min, date_max,"
        " columns) VALUES (?,?,?,?,?,?,?,?,?)",
        (snap.path.name, snap.file_hash, snap.snapshot_date.isoformat(), _now(),
         len(snap.push), len(snap.im), date_min, date_max, json.dumps(snap.columns, ensure_ascii=False)),
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


FILL_SKIP = {"snapshot_id", "date", "age_days"}


def fill_rates(conn: sqlite3.Connection, upto_date: str | None = None) -> pd.DataFrame:
    """Part des lignes où chaque colonne est renseignée (non vide, non nulle), fichier par fichier.

    Colonnes : snapshot_id, snapshot_date, sheet (push | im), column, fill. Une colonne vide aujourd'hui peut se
    remplir demain : on la suit au lieu de l'ignorer.
    """
    frames = []
    for table, sheet in (("push_facts", "push"), ("im_facts", "im")):
        if not table_exists(conn, table):
            continue
        exprs = []
        for _, name, typ, *_ in conn.execute(f"PRAGMA table_info({table})").fetchall():
            if name in FILL_SKIP:
                continue
            cond = (f'"{name}" IS NOT NULL AND "{name}" <> 0' if typ in ("INTEGER", "REAL")
                    else f'"{name}" IS NOT NULL AND TRIM("{name}") <> \'\'')
            exprs.append((name, f"AVG(CASE WHEN {cond} THEN 1.0 ELSE 0 END)"))
        where = "WHERE s.snapshot_date <= ?" if upto_date else ""
        sql = (f"SELECT f.snapshot_id, s.snapshot_date, {', '.join(e for _, e in exprs)} FROM {table} f"
               f" JOIN snapshots s ON s.id = f.snapshot_id {where} GROUP BY f.snapshot_id")
        rows = conn.execute(sql, (upto_date,) if upto_date else ()).fetchall()
        wide = pd.DataFrame([tuple(r) for r in rows], columns=["snapshot_id", "snapshot_date", *[n for n, _ in exprs]])
        long = wide.melt(id_vars=["snapshot_id", "snapshot_date"], var_name="column", value_name="fill")
        long.insert(2, "sheet", sheet)
        frames.append(long)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["snapshot_id", "snapshot_date", "sheet", "column", "fill"])
    return out.sort_values(["snapshot_date", "snapshot_id", "sheet", "column"]).reset_index(drop=True)


DIMENSIONS = {"status": "push_facts", "category": "push_facts", "touchpoint": "im_facts", "program": "im_facts"}


def known_values(conn: sqlite3.Connection, before_snapshot_id: int) -> dict[str, set]:
    """Valeurs de chaque dimension déjà vues dans les fichiers antérieurs (nouveau statut, catégorie…)."""
    out: dict[str, set] = {}
    for col, table in DIMENSIONS.items():
        if not table_exists(conn, table):
            continue
        rows = conn.execute(f'SELECT DISTINCT "{col}" FROM {table} WHERE snapshot_id <> ?'
                            f" AND snapshot_id IN (SELECT id FROM snapshots WHERE snapshot_date <="
                            f" (SELECT snapshot_date FROM snapshots WHERE id = ?))", (before_snapshot_id, before_snapshot_id))
        out[col] = {r[0] for r in rows if r[0] is not None}
    return out


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


def _latest_versions(conn: sqlite3.Connection, table: str, key: list[str], upto_date: str) -> pd.DataFrame:
    """Dernière version de chaque ligne (clé `key`) sur les snapshots <= upto_date, dédoublonnée en SQL.

    Même résultat et même ordre qu'un tri (snapshot_date, id, ordre d'insertion) suivi de
    drop_duplicates(keep="last"), sans charger toutes les versions en mémoire.
    """
    part = ", ".join(f"f.{k}" for k in key)
    return pd.read_sql(
        f"SELECT * FROM (SELECT f.*, s.snapshot_date, s.id AS _sid, f.rowid AS _row,"
        f" ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY s.snapshot_date DESC, s.id DESC, f.rowid DESC) AS _rn"
        f" FROM {table} f JOIN snapshots s ON s.id = f.snapshot_id WHERE s.snapshot_date <= ?)"
        " WHERE _rn = 1 ORDER BY snapshot_date, _sid, _row",
        conn, params=(upto_date,),
    ).drop(columns=["_sid", "_row", "_rn"])


def history_push(conn: sqlite3.Connection, upto_date: str) -> pd.DataFrame:
    """Dernière version connue de chaque broadcast, sur tous les snapshots <= upto_date."""
    if not table_exists(conn, "push_facts"):
        return pd.DataFrame()
    df = _latest_versions(conn, "push_facts", ["broadcast_id"], upto_date)
    if "is_seeding" in df:
        df["is_seeding"] = df["is_seeding"].astype(bool)
    return df


def history_im(conn: sqlite3.Connection, upto_date: str) -> pd.DataFrame:
    if not table_exists(conn, "im_facts"):
        return pd.DataFrame()
    return _latest_versions(conn, "im_facts", IM_KEY, upto_date)


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
