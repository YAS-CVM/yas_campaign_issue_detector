"""Traitement d'un fichier : ingestion -> détection -> synchronisation -> export -> alertes."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from .config import Config
from .detect.base import RuleContext
from .detect.engine import run_rules
from .ingest.loader import file_sha256, load_snapshot
from .storage import repository as repo
from .storage.db import connect

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    file: Path
    skipped: bool = False
    reason: str = ""
    snapshot_id: int | None = None
    snapshot_date: date | None = None
    detected: int = 0
    sync: repo.SyncResult | None = None
    rule_errors: dict[str, str] = field(default_factory=dict)
    report_path: Path | None = None
    notifications: dict[str, str] = field(default_factory=dict)
    site: str | None = None

    def summary(self) -> str:
        if self.skipped:
            return f"{self.file.name} : ignoré ({self.reason})"
        txt = f"{self.file.name} (snapshot du {self.snapshot_date}) : {self.detected} anomalies détectées ; {self.sync.summary()}"
        if self.rule_errors:
            txt += f" ; règles en erreur : {', '.join(self.rule_errors)}"
        return txt


def build_context(cfg: Config, conn, snapshot) -> RuleContext:
    snap_date = date.fromisoformat(snapshot["snapshot_date"])
    prev = repo.previous_snapshot(conn, snapshot["snapshot_date"], snapshot["id"])
    return RuleContext(
        cfg=cfg,
        snapshot_date=snap_date,
        push=repo.load_push(conn, snapshot["id"]),
        im=repo.load_im(conn, snapshot["id"]),
        hist_push=repo.history_push(conn, snapshot["snapshot_date"]),
        hist_im=repo.history_im(conn, snapshot["snapshot_date"]),
        prev_push=repo.load_push(conn, prev["id"]) if prev else None,
        prev_im=repo.load_im(conn, prev["id"]) if prev else None,
        prev_snapshot_date=date.fromisoformat(prev["snapshot_date"]) if prev else None,
        snapshots=_snapshots_upto(conn, snapshot),
        versions=_prior_versions(conn, snapshot),
        fill=repo.fill_rates(conn, snapshot["snapshot_date"]),
        known_values=repo.known_values(conn, snapshot["id"]),
    )


def _snapshots_upto(conn, snapshot) -> pd.DataFrame:
    snaps = repo.list_snapshots(conn)
    snaps = snaps[snaps["snapshot_date"] <= snapshot["snapshot_date"]]
    return snaps.sort_values(["snapshot_date", "id"]).reset_index(drop=True)


def _prior_versions(conn, snapshot) -> pd.DataFrame:
    """Versions Push des fichiers antérieurs : référence de maturité indépendante du fichier évalué."""
    from .analytics.maturity import LATE_METRICS
    cols = ", ".join(f"p.{c}" for c in ["broadcast_id", "age_days", *LATE_METRICS])
    try:
        return pd.read_sql(f"SELECT {cols}, s.snapshot_date FROM push_facts p JOIN snapshots s ON s.id = p.snapshot_id"
                           " WHERE s.snapshot_date < ?", conn, params=(snapshot["snapshot_date"],))
    except Exception:  # base vide (premier fichier) : pas de référence
        return pd.DataFrame()


def detect_snapshot(cfg: Config, conn, snapshot) -> tuple[list, set[str], dict[str, str], repo.SyncResult]:
    ctx = build_context(cfg, conn, snapshot)
    anomalies, executed, errors = run_rules(ctx)
    sync = repo.sync_anomalies(conn, snapshot, anomalies, executed)
    conn.commit()
    return anomalies, executed, errors, sync


def export_csv(cfg: Config, conn, snapshot) -> Path:
    df = repo.anomalies_df(conn, status=["open", "ack"])
    out = cfg.path("reports") / f"anomalies_{snapshot['snapshot_date']}.csv"
    cols = ["id", "severity", "status", "rule_id", "rule_name", "date", "category", "entity_type", "entity_key",
            "metric", "value", "expected", "volume", "message", "first_seen_at", "last_seen_at", "occurrences"]
    df.reindex(columns=cols).to_csv(out, index=False, encoding="utf-8-sig", sep=";")  # ; + BOM : Excel FR
    return out


def rebuild_site(cfg: Config) -> str:
    """Régénère le tableau de bord statique ; ne fait jamais échouer le traitement d'un fichier."""
    try:
        from .site.build import build_site
        return build_site(cfg).summary()
    except Exception as e:  # pragma: no cover - le traitement du fichier reste valide
        log.exception("Échec de la génération du site")
        return f"échec de la génération du site : {type(e).__name__}: {e}"


def process_file(cfg: Config, path: str | Path, notify: bool = True, archive: bool | None = None,
                 build: bool = True) -> RunResult:
    path = Path(path)
    result = RunResult(file=path)
    conn = connect(cfg.path("db"))
    try:
        snap = load_snapshot(path)
        existing = repo.snapshot_exists(conn, snap.file_hash)
        if existing:
            result.skipped, result.reason = True, f"déjà ingéré (snapshot #{existing['id']})"
            _archive(cfg, path, archive)
            return result

        snapshot_id = repo.insert_snapshot(conn, snap)
        conn.commit()
        snapshot = repo.get_snapshot(conn, snapshot_id)
        latest = repo.latest_snapshot(conn)
        result.snapshot_id, result.snapshot_date = snapshot_id, snap.snapshot_date

        anomalies, _, errors, sync = detect_snapshot(cfg, conn, snapshot)
        result.detected, result.sync, result.rule_errors = len(anomalies), sync, errors
        result.report_path = export_csv(cfg, conn, snapshot)

        # On n'alerte que pour le snapshot le plus récent (pas lors d'un rattrapage d'anciens fichiers).
        if notify and latest["id"] == snapshot_id:
            from .notify.dispatcher import dispatch
            result.notifications = dispatch(cfg, conn, snapshot, sync)
        _archive(cfg, path, archive)
        if build and latest["id"] == snapshot_id:
            result.site = rebuild_site(cfg)
        return result
    finally:
        conn.close()


def import_upload(cfg: Config, filename: str, data: bytes, notify: bool = True) -> RunResult:
    """Traite un fichier reçu depuis l'interface web, comme `cvm-monitor run`, puis l'archive.

    Le fichier est écrit hors de inbox/ pour ne pas être repris en parallèle par une exécution planifiée.
    """
    name = Path(filename).name
    if not name.lower().endswith(".xlsb"):
        raise ValueError(f"{name} : seuls les fichiers .xlsb sont acceptés")
    uploads = cfg.path("db").parent / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / name
    dest.write_bytes(data)
    try:
        conn = connect(cfg.path("db"))
        try:
            existing = repo.snapshot_exists(conn, file_sha256(dest))
        finally:
            conn.close()
        if existing:
            return RunResult(file=dest, skipped=True, reason=f"déjà importé le {existing['ingested_at'][:10]}",
                             snapshot_id=existing["id"], snapshot_date=date.fromisoformat(existing["snapshot_date"]))
        return process_file(cfg, dest, notify=notify, archive=True)
    finally:
        dest.unlink(missing_ok=True)


def _archive(cfg: Config, path: Path, archive: bool | None) -> None:
    if archive is None:
        archive = cfg.ingest.get("archive_after_ingest", True) and path.resolve().parent == cfg.path("inbox").resolve()
    if archive:
        dest = cfg.path("archive") / path.name
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{pd.Timestamp.now():%Y%m%d%H%M%S}{dest.suffix}")
        shutil.move(str(path), dest)
        log.info("Archivé : %s", dest)


def pending_files(cfg: Config) -> list[Path]:
    from .ingest.loader import snapshot_date_from_name
    files = sorted(cfg.path("inbox").glob(cfg.ingest.get("file_glob", "*.xlsb")))
    return sorted(files, key=lambda f: (snapshot_date_from_name(f.name) or date.max, f.name))
