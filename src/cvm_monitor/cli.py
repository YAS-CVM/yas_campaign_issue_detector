"""Commande `cvm-monitor`."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from .config import SEVERITIES, load_config

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Yas CVM Monitor : surveillance et alertes des campagnes.")
ConfigOpt = typer.Option(None, "--config", "-c", help="Chemin de config.yaml (défaut : config/config.yaml)")


def _setup(config: Optional[Path], verbose: bool = False):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        return load_config(config)
    except Exception as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(2)


def _print_result(r) -> None:
    color = "yellow" if r.skipped else ("red" if r.rule_errors else "green")
    typer.secho(r.summary(), fg=color)
    if r.report_path:
        typer.echo(f"  CSV : {r.report_path}")
    for channel, status in r.notifications.items():
        typer.echo(f"  {channel} : {status}")


@app.command()
def run(
    file: Optional[list[Path]] = typer.Argument(None, help="Fichier(s) .xlsb. Par défaut : tous ceux du dossier inbox/"),
    no_notify: bool = typer.Option(False, "--no-notify", help="Ne pas envoyer d'alertes"),
    config: Optional[Path] = ConfigOpt,
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Traite les nouveaux fichiers : ingestion, détection, alertes."""
    from .pipeline import pending_files, process_file
    cfg = _setup(config, verbose)
    files = file or pending_files(cfg)
    if not files:
        typer.echo(f"Aucun fichier à traiter dans {cfg.path('inbox')}")
        return
    failed = False
    for f in files:
        try:
            _print_result(process_file(cfg, f, notify=not no_notify))
        except Exception as e:
            failed = True
            logging.exception("Échec du traitement de %s", f)
            typer.secho(f"{Path(f).name} : ÉCHEC ({e})", fg="red", err=True)
    raise typer.Exit(1 if failed else 0)


@app.command()
def backfill(
    files: list[Path] = typer.Argument(..., help="Anciens fichiers .xlsb à historiser (ordre indifférent)"),
    config: Optional[Path] = ConfigOpt,
):
    """Historise d'anciens fichiers sans envoyer d'alertes (ne les déplace pas)."""
    from .ingest.loader import snapshot_date_from_name
    from .pipeline import process_file
    cfg = _setup(config)
    for f in sorted(files, key=lambda p: (snapshot_date_from_name(p.name) or date.max, p.name)):
        _print_result(process_file(cfg, f, notify=False, archive=False))


@app.command()
def watch(
    interval: int = typer.Option(10, help="Délai (s) d'attente de fin de copie d'un fichier"),
    no_notify: bool = typer.Option(False, "--no-notify"),
    config: Optional[Path] = ConfigOpt,
):
    """Surveille le dossier inbox/ et traite chaque nouveau fichier dès son arrivée (Ctrl+C pour arrêter)."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    from .pipeline import pending_files, process_file
    cfg = _setup(config)
    inbox = cfg.path("inbox")
    pattern = cfg.ingest.get("file_glob", "*.xlsb")

    def handle(path: Path) -> None:
        # attendre que la copie soit terminée (taille stable)
        last = -1
        while path.exists() and path.stat().st_size != last:
            last = path.stat().st_size
            time.sleep(interval)
        if path.exists():
            try:
                _print_result(process_file(cfg, path, notify=not no_notify))
            except Exception:
                logging.exception("Échec du traitement de %s", path)

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            p = Path(event.src_path)
            if not event.is_directory and p.match(pattern) and not p.name.startswith("~$"):
                handle(p)

        def on_moved(self, event):
            p = Path(event.dest_path)
            if not event.is_directory and p.match(pattern):
                handle(p)

    for f in pending_files(cfg):
        handle(f)
    observer = Observer()
    observer.schedule(Handler(), str(inbox), recursive=False)
    observer.start()
    typer.echo(f"Surveillance de {inbox} … (Ctrl+C pour arrêter)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


@app.command()
def status(config: Optional[Path] = ConfigOpt):
    """Résumé : snapshots ingérés et anomalies ouvertes."""
    from .storage import repository as repo
    from .storage.db import connect
    cfg = _setup(config)
    conn = connect(cfg.path("db"))
    snaps = repo.list_snapshots(conn)
    typer.echo(f"Base : {cfg.path('db')}")
    typer.echo(f"Snapshots ingérés : {len(snaps)}")
    if not snaps.empty:
        for r in snaps.tail(5).itertuples():
            typer.echo(f"  #{r.id} {r.snapshot_date}  {r.file_name}  ({r.push_rows} Push / {r.im_rows} IM)")
    df = repo.anomalies_df(conn)
    if df.empty:
        typer.echo("Aucune anomalie.")
        return
    counts = df.groupby(["status", "severity"]).size().unstack(fill_value=0).reindex(columns=SEVERITIES[::-1], fill_value=0)
    typer.echo("\nAnomalies :\n" + counts.to_string())


@app.command("list")
def list_anomalies(
    severity: str = typer.Option("major", help=f"Sévérité minimale ({', '.join(SEVERITIES)})"),
    status_: str = typer.Option("open", "--status", help="open, ack, muted, resolved ou all"),
    rule: Optional[str] = typer.Option(None, help="Filtrer sur une règle (ex. PM-EXE-01)"),
    limit: int = typer.Option(30),
    config: Optional[Path] = ConfigOpt,
):
    """Liste les anomalies."""
    from .config import severity_rank
    from .storage import repository as repo
    from .storage.db import connect
    cfg = _setup(config)
    conn = connect(cfg.path("db"))
    df = repo.anomalies_df(conn, status=None if status_ == "all" else [status_])
    if df.empty:
        typer.echo("Aucune anomalie.")
        return
    df = df[df["severity"].map(severity_rank) >= severity_rank(severity)]
    if rule:
        df = df[df["rule_id"] == rule]
    colors = {"critical": "red", "major": "yellow", "minor": "white", "info": "bright_black"}
    for r in df.head(limit).itertuples():
        typer.secho(f"#{r.id:<5} {r.severity:<8} {r.rule_id:<10} {r.status:<8} {r.message}", fg=colors[r.severity])
    if len(df) > limit:
        typer.echo(f"… {len(df) - limit} de plus (--limit)")


@app.command()
def ack(
    ids: list[int] = typer.Argument(..., help="Identifiants d'anomalies (#id)"),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Commentaire (cause, ticket…)"),
    by: Optional[str] = typer.Option(None, "--by", help="Votre nom"),
    mute: bool = typer.Option(False, "--mute", help="Mettre en sourdine (plus jamais d'alerte)"),
    reopen: bool = typer.Option(False, "--reopen", help="Rouvrir"),
    config: Optional[Path] = ConfigOpt,
):
    """Acquitte (ou met en sourdine / rouvre) des anomalies."""
    from .storage import repository as repo
    from .storage.db import connect
    cfg = _setup(config)
    conn = connect(cfg.path("db"))
    new_status = "open" if reopen else ("muted" if mute else "ack")
    repo.set_status(conn, ids, new_status, by, note)
    typer.echo(f"{len(ids)} anomalie(s) → {new_status}")


@app.command()
def report(
    period: str = typer.Option("week", help="week ou month"),
    config: Optional[Path] = ConfigOpt,
):
    """Génère un rapport Excel (KPI, scorecards campagnes, règles IM, anomalies)."""
    from .report import build_report
    from .storage.db import connect
    cfg = _setup(config)
    out = build_report(cfg, connect(cfg.path("db")), period)
    typer.secho(f"Rapport : {out}", fg="green")


@app.command()
def preview(config: Optional[Path] = ConfigOpt):
    """Écrit l'e-mail récapitulatif en HTML (sans l'envoyer) pour vérifier son rendu."""
    from .notify.dispatcher import preview_digest
    from .storage import repository as repo
    from .storage.db import connect
    cfg = _setup(config)
    conn = connect(cfg.path("db"))
    snap = repo.latest_snapshot(conn)
    if snap is None:
        typer.secho("Aucun snapshot ingéré.", fg="red")
        raise typer.Exit(1)
    out = preview_digest(cfg, conn, snap, cfg.path("reports") / f"apercu_email_{snap['snapshot_date']}.html")
    typer.secho(f"Aperçu : {out}", fg="green")


@app.command("notify-test")
def notify_test(config: Optional[Path] = ConfigOpt):
    """Envoie un message de test sur chaque canal configuré."""
    from .services import alerts
    cfg = _setup(config)
    status = alerts.channel_status(cfg)
    for channel, label in (("teams", "Teams"), ("email", "E-mail")):
        if not status[channel]["configured"]:
            typer.echo(f"{label} : non configuré ({', '.join(status[channel]['missing'])})")
            continue
        res = alerts.send_test(cfg, channel)
        typer.secho(f"{label} : {'OK' if res['ok'] else 'ERREUR'} — {res['message']}", fg="green" if res["ok"] else "red")


@app.command()
def dashboard(
    port: int = typer.Option(8000),
    config: Optional[Path] = ConfigOpt,
):
    """Lance le tableau de bord Streamlit."""
    cfg = _setup(config)
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port),
           "--browser.gatherUsageStats", "false"]
    env = {**os.environ, "CVM_MONITOR_CONFIG": str(cfg.config_path)}
    raise typer.Exit(subprocess.call(cmd, env=env))


@app.command()
def serve(
    port: int = typer.Option(8000),
    host: str = typer.Option("0.0.0.0", help="Interface d'écoute : 0.0.0.0 = toutes (accessible depuis le réseau), 127.0.0.1 = local seulement."),
    reload: bool = typer.Option(False, help="Rechargement auto (développement)."),
    config: Optional[Path] = ConfigOpt,
):
    """Lance l'API FastAPI (et sert web/dist s'il existe)."""
    import socket

    import uvicorn
    cfg = _setup(config)
    os.environ["CVM_MONITOR_CONFIG"] = str(cfg.config_path)
    if host in ("0.0.0.0", "::"):
        try:
            lan = socket.gethostbyname(socket.gethostname())
        except OSError:
            lan = None
        typer.echo(f"Live on http://localhost:{port}" + (f" and http://{lan}:{port} (network)" if lan else ""))
        typer.secho("Attention : No authentification", fg="yellow")
    uvicorn.run("cvm_monitor.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
