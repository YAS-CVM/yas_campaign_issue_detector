"""Serveur du tableau de bord : site statique (site/) et API d'écriture.

Toute la lecture se fait dans la page (données embarquées à la génération) : aucune requête à l'affichage.
L'API ne sert plus qu'aux actions : acquitter / mettre en sourdine / rouvrir, importer un fichier,
consulter et tester les canaux d'alerte. Chaque écriture régénère le site en arrière-plan.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import Scope

from cvm_monitor import pipeline
from cvm_monitor.ingest.schema import SchemaError
from cvm_monitor.services import alerts
from cvm_monitor.storage import repository as repo

from .deps import Cfg, Conn, get_config, write_lock


def _clean(obj):
    """NaN / ±inf → null : JSON n'accepte pas ces valeurs."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return super().render(_clean(content))


app = FastAPI(title="CVM Monitor", version="0.2.0", default_response_class=SafeJSONResponse)
app.add_middleware(GZipMiddleware, minimum_size=1024)
v1 = "/api/v1"


@app.get("/health")
def health(cfg: Cfg):
    return {"status": "ok", "db": str(cfg.path("db")), "site": str(site_dir(cfg))}


# ------------------------------------------------------------------ régénération du site

_rebuild = {"lock": threading.Lock(), "pending": False}


def rebuild_site_async(cfg) -> None:
    """Régénère le site ; les demandes rapprochées sont fusionnées (une seule génération en attente)."""
    if _rebuild["pending"]:
        return
    _rebuild["pending"] = True

    def work():
        with _rebuild["lock"]:
            _rebuild["pending"] = False
            pipeline.rebuild_site(cfg)
    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ anomalies

class StatusUpdate(BaseModel):
    ids: list[int]
    status: Literal["open", "ack", "muted", "resolved"]
    by: str | None = None
    note: str | None = None


@app.patch(f"{v1}/anomalies")
def update_anomalies(body: StatusUpdate, cfg: Cfg, conn: Conn):
    if not body.ids:
        raise HTTPException(400, "Aucune anomalie sélectionnée")
    with write_lock:
        repo.set_status(conn, body.ids, body.status, body.by, body.note)
    rebuild_site_async(cfg)
    # Même horloge que meta.generated_at : la page sait si le site qu'elle affiche inclut déjà cette écriture.
    return {"updated": len(body.ids), "at": datetime.now().isoformat(timespec="seconds")}


# ------------------------------------------------------------------ paramètres : canaux d'alerte

_last_test: dict[str, float] = {}
TEST_COOLDOWN_S = 5.0


@app.get(f"{v1}/settings/alerts")
def alerts_status(cfg: Cfg):
    """Configuration des canaux, sans aucun secret (l'URL du webhook et le mot de passe SMTP ne sortent jamais)."""
    return alerts.channel_status(cfg)


@app.post(f"{v1}/settings/alerts/test/{{channel}}")
def alerts_test(channel: Literal["teams", "email"], cfg: Cfg):
    """Envoie un message de test réel ; un délai minimal évite de spammer le canal par double-clic."""
    now = time.monotonic()
    if now - _last_test.get(channel, -TEST_COOLDOWN_S) < TEST_COOLDOWN_S:
        raise HTTPException(429, "Un test vient d'être envoyé : patientez quelques secondes.")
    _last_test[channel] = now
    return alerts.send_test(cfg, channel)


# ------------------------------------------------------------------ import

_jobs: dict[str, dict] = {}


def _run_import(job_id: str, cfg, filename: str, data: bytes, notify: bool) -> None:
    try:
        with write_lock:  # process_file régénère le site si le fichier est le plus récent
            res = pipeline.import_upload(cfg, filename, data, notify=notify)
        _jobs[job_id] = {"state": "done", "summary": res.summary(), "skipped": res.skipped,
                         "snapshot_id": res.snapshot_id, "site": res.site}
    except (ValueError, SchemaError) as e:
        _jobs[job_id] = {"state": "error", "error": str(e)}
    except Exception as e:  # pragma: no cover
        _jobs[job_id] = {"state": "error", "error": f"{type(e).__name__}: {e}"}


@app.post(f"{v1}/import", status_code=202)
async def import_file(cfg: Cfg, tasks: BackgroundTasks, file: UploadFile = File(...), notify: bool = False):
    if not (file.filename or "").lower().endswith(".xlsb"):
        raise HTTPException(400, "Extension non supportée (attendu : .xlsb)")
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"state": "running"}
    tasks.add_task(_run_import, job_id, cfg, file.filename, await file.read(), notify)
    return {"job_id": job_id}


@app.get(f"{v1}/import/{{job_id}}")
def import_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "job inconnu")
    return _jobs[job_id]


# ------------------------------------------------------------------ site statique

def site_dir(cfg) -> Path:
    return cfg.path("site") if "site" in cfg.raw.get("paths", {}) else cfg.root / "site"


class SiteFiles(StaticFiles):
    """Pages HTML revalidées à chaque visite (ETag → 304 si inchangées) ; assets à empreinte en cache permanent."""

    async def get_response(self, path: str, scope: Scope):
        resp = await super().get_response(path, scope)
        if path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache"
        return resp


class LazySite:
    """Monte site/ à la première requête : la config (et donc le dossier) n'est lue qu'à l'exécution.

    Si le site n'a jamais été généré (premier démarrage), il l'est à ce moment depuis la base.
    """

    def __init__(self) -> None:
        self._files: SiteFiles | None = None
        self._dir: Path | None = None

    async def __call__(self, scope: Scope, receive, send) -> None:
        cfg = get_config()
        site = site_dir(cfg)
        if self._files is None or self._dir != site:
            if not (site / "index.html").exists():
                pipeline.rebuild_site(cfg)
            site.mkdir(parents=True, exist_ok=True)
            self._files, self._dir = SiteFiles(directory=site, html=True), site
        await self._files(scope, receive, send)


# Doit rester en dernier : le montage "/" ne doit pas masquer les routes de l'API.
app.mount("/", LazySite(), name="site")
