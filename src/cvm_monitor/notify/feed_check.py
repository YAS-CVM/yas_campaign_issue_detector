"""Fichier NEON-dx attendu mais non reçu : seul contrôle qui ne peut pas tourner à l'import (il n'y a pas de fichier).

Le Daily Dashboard « till J-1 » est attendu chaque jour avant l'heure limite (`feed.deadline`). Lancé par
`cvm-monitor run` quand l'inbox est vide (la tâche cron tourne toutes les heures) ou par `cvm-monitor feed-check`.
Une seule alerte par fichier attendu (journal `notifications`, canal `feed-check:<date>`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd

from ..config import Config
from ..storage import repository as repo
from . import email as mail
from . import teams

log = logging.getLogger(__name__)


@dataclass
class MissingFile:
    expected: date             # date « till » du fichier attendu
    latest: date | None        # dernier fichier reçu
    deadline: str

    @property
    def lag_days(self) -> int | None:
        return (self.expected - self.latest).days if self.latest else None

    def message(self) -> str:
        last = f"dernier fichier reçu : till {self.latest:%d/%m/%Y}" if self.latest else "aucun fichier reçu"
        return (f"Le Daily Dashboard NEON-dx « till {self.expected:%d/%m/%Y} » n'est pas arrivé à {self.deadline} "
                f"({last}). Un fichier manquant en fin de mois fait perdre définitivement la maturité des derniers "
                "envois : relancer Flytxt.")


def check(cfg: Config, conn, now: datetime | None = None) -> MissingFile | None:
    feed = cfg.raw.get("feed", {}) or {}
    deadline = str(feed.get("deadline", "10:00"))
    weekdays = feed.get("expected_weekdays", [0, 1, 2, 3, 4, 5, 6])  # jour du fichier attendu (0 = lundi)
    now = now or datetime.now()
    if now.time() < time.fromisoformat(deadline):
        return None
    expected = now.date() - timedelta(days=1)
    if expected.weekday() not in weekdays:
        return None
    latest = repo.latest_snapshot(conn)
    latest_date = date.fromisoformat(latest["snapshot_date"]) if latest else None
    if latest_date and latest_date >= expected:
        return None
    return MissingFile(expected, latest_date, deadline)


def notify(cfg: Config, conn, now: datetime | None = None, send: bool = True) -> tuple[MissingFile | None, dict[str, str]]:
    """Vérifie et alerte (Teams, e-mail) au plus une fois par fichier attendu."""
    missing = check(cfg, conn, now)
    if missing is None or not send:
        return missing, {}
    channel = f"feed-check:{missing.expected.isoformat()}"
    sent = repo.notifications_df(conn)
    if not sent.empty and ((sent["channel"].str.startswith(channel)) & (sent["success"] == 1)).any():
        return missing, {"feed-check": "déjà signalé"}
    out: dict[str, str] = {}
    items = pd.DataFrame([{"severity": "major", "rule_id": "FEED-01", "rule_name": "Fichier NEON-dx manquant",
                           "message": missing.message()}])
    ncfg = cfg.notify
    webhook = cfg.env("TEAMS_WEBHOOK_URL")
    if webhook and ncfg.get("teams", {}).get("enabled", True):
        try:
            teams.post_card(webhook, teams.build_card("Yas CVM Monitor : fichier non reçu", f"Attendu avant {missing.deadline}",
                                                      items, {"major": 1}, ncfg.get("dashboard_url")))
            repo.log_notification(conn, None, channel + ":teams", 1, True)
            out["teams"] = "envoyé"
        except Exception as e:  # réseau, webhook refusé…
            repo.log_notification(conn, None, channel + ":teams", 1, False, str(e)[:300])
            out["teams"] = f"échec : {e}"
    if mail.is_configured(cfg) and ncfg.get("email", {}).get("enabled", True):
        try:
            prefix = ncfg.get("email", {}).get("subject_prefix", "[Yas CVM Monitor]")
            mail.send_email(cfg, f"{prefix} Fichier NEON-dx du {missing.expected:%d/%m} non reçu",
                            f"<p>{missing.message()}</p>", missing.message())
            repo.log_notification(conn, None, channel + ":email", 1, True)
            out["email"] = "envoyé"
        except Exception as e:
            repo.log_notification(conn, None, channel + ":email", 1, False, str(e)[:300])
            out["email"] = f"échec : {e}"
    conn.commit()
    return missing, out
