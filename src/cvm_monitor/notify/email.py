"""Envoi d'e-mails HTML : SMTP (Linux / Windows) ou Outlook local (Windows)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from ..config import Config


class EmailError(RuntimeError):
    pass


def recipients(cfg: Config) -> list[str]:
    return [a.strip() for a in (cfg.env("MAIL_TO") or "").replace(";", ",").split(",") if a.strip()]


def is_configured(cfg: Config) -> bool:
    if not recipients(cfg):
        return False
    if cfg.notify.get("email", {}).get("backend", "smtp") == "outlook":
        return True
    return bool(cfg.env("SMTP_HOST"))


def send_email(cfg: Config, subject: str, html: str, text: str, attachments: list[Path] | None = None) -> None:
    to = recipients(cfg)
    if not to:
        raise EmailError("MAIL_TO est vide dans config/.env")
    backend = cfg.notify.get("email", {}).get("backend", "smtp")
    if backend == "outlook":
        _send_outlook(to, subject, html, attachments or [])
    else:
        _send_smtp(cfg, to, subject, html, text, attachments or [])


def _send_smtp(cfg: Config, to: list[str], subject: str, html: str, text: str, attachments: list[Path]) -> None:
    host, port = cfg.env("SMTP_HOST"), int(cfg.env("SMTP_PORT", "587"))
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


def _send_outlook(to: list[str], subject: str, html: str, attachments: list[Path]) -> None:
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as e:
        raise EmailError("Backend outlook : installer pywin32 (pip install pywin32), Windows uniquement") from e
    mail = win32com.client.Dispatch("Outlook.Application").CreateItem(0)
    mail.To = "; ".join(to)
    mail.Subject = subject
    mail.HTMLBody = html
    for path in attachments:
        mail.Attachments.Add(str(path.resolve()))
    mail.Send()
