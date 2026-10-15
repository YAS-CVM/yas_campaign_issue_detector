"""Envoi d'e-mails HTML par SMTP (serveur au choix, ou Outlook / Office 365)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from ..config import Config


OUTLOOK_HOST, OUTLOOK_PORT = "smtp.office365.com", 587


class EmailError(RuntimeError):
    pass


def backend(cfg: Config) -> str:
    return cfg.notify.get("email", {}).get("backend", "smtp")


def smtp_server(cfg: Config) -> tuple[str | None, int]:
    """Hôte et port SMTP : ceux de config/.env, sinon ceux d'Office 365 pour le backend outlook."""
    outlook = backend(cfg) == "outlook"
    host = cfg.env("SMTP_HOST") or (OUTLOOK_HOST if outlook else None)
    return host, int(cfg.env("SMTP_PORT") or (OUTLOOK_PORT if outlook else 587))


def missing_settings(cfg: Config) -> list[str]:
    """Variables de config/.env manquantes pour envoyer ; Office 365 exige toujours une authentification."""
    required = [("MAIL_TO", bool(recipients(cfg))), ("SMTP_HOST", bool(smtp_server(cfg)[0]))]
    if backend(cfg) == "outlook":
        required += [("SMTP_USER", bool(cfg.env("SMTP_USER"))), ("SMTP_PASSWORD", bool(cfg.env("SMTP_PASSWORD")))]
    return [k for k, ok in required if not ok]


def recipients(cfg: Config) -> list[str]:
    return [a.strip() for a in (cfg.env("MAIL_TO") or "").replace(";", ",").split(",") if a.strip()]


def is_configured(cfg: Config) -> bool:
    return not missing_settings(cfg)


def send_email(cfg: Config, subject: str, html: str, text: str, attachments: list[Path] | None = None) -> None:
    to = recipients(cfg)
    if not to:
        raise EmailError("MAIL_TO est vide dans config/.env")
    _send_smtp(cfg, to, subject, html, text, attachments or [])


def _send_smtp(cfg: Config, to: list[str], subject: str, html: str, text: str, attachments: list[Path]) -> None:
    host, port = smtp_server(cfg)
    user, password = cfg.env("SMTP_USER"), cfg.env("SMTP_PASSWORD")
    sender = cfg.env("MAIL_FROM") or user
    if not host or not sender:
        raise EmailError("SMTP_HOST et MAIL_FROM (ou SMTP_USER) doivent être renseignés dans config/.env")

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for path in attachments:
        msg.add_attachment(path.read_bytes(), maintype="text", subtype="csv", filename=path.name)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())
        with server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"Échec SMTP ({host}:{port}) : {e}") from e

