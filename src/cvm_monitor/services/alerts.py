"""État des canaux d'alerte (Teams, e-mail) et envoi de messages de test. Partagé par la CLI et l'API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import pandas as pd

from cvm_monitor.config import Config
from cvm_monitor.notify import email as mail
from cvm_monitor.notify import teams

CHANNELS = ("teams", "email")


def _webhook_hint(url: str | None) -> str | None:
    """Hôte seul : l'URL complète contient la clé d'accès (`sig=`) et ne doit jamais quitter le serveur."""
    return urlsplit(url).hostname if url else None


def channel_status(cfg: Config) -> dict[str, Any]:
    teams_cfg, mail_cfg = cfg.notify.get("teams", {}), cfg.notify.get("email", {})
    webhook = cfg.env("TEAMS_WEBHOOK_URL")
    return {
        "teams": {
            "configured": bool(webhook), "enabled": bool(teams_cfg.get("enabled", True)),
            "min_severity": teams_cfg.get("min_severity"), "max_items": teams_cfg.get("max_items"),
            "webhook_host": _webhook_hint(webhook),
            "missing": [] if webhook else ["TEAMS_WEBHOOK_URL"],
        },
        "email": {
            "configured": mail.is_configured(cfg), "enabled": bool(mail_cfg.get("enabled", True)),
            "backend": mail_cfg.get("backend", "smtp"), "min_severity": mail_cfg.get("min_severity"),
            "recipients": mail.recipients(cfg), "smtp_host": cfg.env("SMTP_HOST"), "smtp_port": cfg.env("SMTP_PORT"),
            "sender": cfg.env("MAIL_FROM") or cfg.env("SMTP_USER"),
            "missing": [k for k, ok in (("MAIL_TO", bool(mail.recipients(cfg))),
                                         ("SMTP_HOST", mail_cfg.get("backend", "smtp") == "outlook" or bool(cfg.env("SMTP_HOST")))) if not ok],
        },
        "dashboard_url": cfg.notify.get("dashboard_url"),
    }


def _scrub(message: str, cfg: Config) -> str:
    """Retire de tout message d'erreur les secrets que `requests` ou `smtplib` pourraient citer."""
    for secret in (cfg.env("TEAMS_WEBHOOK_URL"), cfg.env("SMTP_PASSWORD")):
        if secret:
            message = message.replace(secret, "<masqué>")
    return message


def send_test(cfg: Config, channel: str) -> dict[str, Any]:
    """Envoie un message de test ; ne lève jamais : renvoie {ok, message, at}."""
    at = datetime.now().isoformat(timespec="seconds")
    try:
        if channel == "teams":
            webhook = cfg.env("TEAMS_WEBHOOK_URL")
            if not webhook:
                return {"ok": False, "message": "Non configuré : TEAMS_WEBHOOK_URL est absent de config/.env", "at": at}
            items = pd.DataFrame([{"severity": "info", "rule_id": "TEST", "rule_name": "Message de test",
                                   "message": "Si vous lisez ceci, les alertes Teams fonctionnent."}])
            teams.post_card(webhook, teams.build_card("Yas CVM Monitor : test", "Vérification du webhook", items, {},
                                                      cfg.notify.get("dashboard_url")))
            return {"ok": True, "message": "Message de test publié dans Teams.", "at": at}
        if channel == "email":
            if not mail.is_configured(cfg):
                return {"ok": False, "message": "Non configuré : MAIL_TO et SMTP_HOST (ou backend outlook) sont requis", "at": at}
            mail.send_email(cfg, "[Yas CVM Monitor] Test", "<p>Les alertes e-mail fonctionnent.</p>",
                            "Les alertes e-mail fonctionnent.")
            return {"ok": True, "message": f"E-mail de test envoyé à {', '.join(mail.recipients(cfg))}.", "at": at}
        return {"ok": False, "message": f"Canal inconnu : {channel}", "at": at}
    except Exception as e:  # erreur réseau, authentification, webhook refusé, …
        return {"ok": False, "message": _scrub(f"{type(e).__name__} : {e}", cfg), "at": at}
