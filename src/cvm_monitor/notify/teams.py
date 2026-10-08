"""Envoi d'une Adaptive Card vers Microsoft Teams via un webhook « Workflows » (Power Automate).

Création du webhook : dans le canal Teams > « ... » > Workflows >
« Publier dans un canal lorsqu'une requête webhook est reçue », puis copier l'URL dans TEAMS_WEBHOOK_URL.
"""

from __future__ import annotations

import pandas as pd
import requests

SEVERITY_COLOR = {"critical": "Attention", "major": "Warning", "minor": "Accent", "info": "Default"}
SEVERITY_LABEL = {"critical": "Critique", "major": "Majeure", "minor": "Mineure", "info": "Info"}


class TeamsError(RuntimeError):
    pass


def build_card(title: str, subtitle: str, items: pd.DataFrame, counts: dict[str, int],
               dashboard_url: str | None, max_items: int = 5) -> dict:
    body: list[dict] = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Large", "wrap": True},
        {"type": "TextBlock", "text": subtitle, "isSubtle": True, "spacing": "None", "wrap": True},
        {"type": "FactSet", "facts": [
            {"title": SEVERITY_LABEL[s], "value": str(counts.get(s, 0))}
            for s in ("critical", "major", "minor") if counts.get(s)
        ]},
    ]
    for r in items.head(max_items).itertuples():
        body.append({
            "type": "Container", "separator": True, "spacing": "Medium",
            "items": [
                {"type": "TextBlock", "wrap": True, "weight": "Bolder",
                 "color": SEVERITY_COLOR.get(r.severity, "Default"),
                 "text": f"{SEVERITY_LABEL.get(r.severity, '').upper()} · {r.rule_id} · {r.rule_name}"},
                {"type": "TextBlock", "wrap": True, "spacing": "Small", "text": r.message},
            ],
        })
    if len(items) > max_items:
        body.append({"type": "TextBlock", "isSubtle": True, "wrap": True,
                     "text": f"… et {len(items) - max_items} autre(s) dans le tableau de bord."})
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard", "version": "1.4", "msteams": {"width": "Full"}, "body": body,
    }
    if dashboard_url:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "Ouvrir le tableau de bord", "url": dashboard_url}]
    return card


def post_card(webhook_url: str, card: dict, timeout: int = 20) -> None:
    payload = {
        "type": "message",
        "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}],
    }
    resp = requests.post(webhook_url, json=payload, timeout=timeout)
    if resp.status_code >= 300:
        raise TeamsError(f"Teams a répondu {resp.status_code} : {resp.text[:300]}")
