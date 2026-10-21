"""Modèle d'anomalie, registre des règles et contexte d'exécution."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ..config import SEVERITIES, Config, severity_rank


# Règles « d'état » : l'alerte décrit la situation courante d'une entité (BC, offre), pas un jour précis.
# Identité = règle + entité, sans date : l'alerte vit tant que le phénomène dure, se résout quand il disparaît
# et se rouvre s'il réapparaît (BC récurrents).
STATE_RULE_PREFIX = "CVM-"


@dataclass
class Anomaly:
    entity_type: str          # broadcast | bc_name | campaign | category | im_rule | touchpoint | global | column
    entity_key: str
    date: str                 # date de référence (ISO) : jour concerné ou début de l'épisode
    message: str
    severity: str | None = None
    metric: str | None = None
    value: float | None = None
    expected: str | None = None
    volume: int = 0           # clients / messages impactés, sert au tri et à la sévérité
    category: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    rule_id: str = ""         # renseignés par le moteur
    rule_name: str = ""
    scope: str = ""

    @property
    def fingerprint(self) -> str:
        day = "" if self.rule_id.startswith(STATE_RULE_PREFIX) else self.date
        raw = f"{self.rule_id}|{self.entity_type}|{self.entity_key}|{day}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


RuleFunc = Callable[["RuleContext", dict[str, Any]], Iterable[Anomaly]]


@dataclass
class RuleSpec:
    id: str
    name: str
    scope: str                # push | im | snapshot
    severity: str
    func: RuleFunc
    needs_previous: bool = False
    defaults: dict[str, Any] = field(default_factory=dict)


REGISTRY: dict[str, RuleSpec] = {}


def rule(rule_id: str, name: str, scope: str, severity: str = "major",
         needs_previous: bool = False, **defaults: Any) -> Callable[[RuleFunc], RuleFunc]:
    def decorator(func: RuleFunc) -> RuleFunc:
        REGISTRY[rule_id] = RuleSpec(rule_id, name, scope, severity, func, needs_previous, defaults)
        return func
    return decorator


@dataclass
class RuleContext:
    cfg: Config
    snapshot_date: date
    push: pd.DataFrame                    # snapshot courant
    im: pd.DataFrame
    hist_push: pd.DataFrame               # dernière version connue de chaque broadcast (tous snapshots)
    hist_im: pd.DataFrame
    prev_push: pd.DataFrame | None = None  # snapshot précédent
    prev_im: pd.DataFrame | None = None
    prev_snapshot_date: date | None = None
    # Contexte du flux NEON-dx (règles FEED) : renseigné par pipeline.build_context, facultatif ailleurs.
    snapshots: pd.DataFrame | None = None         # fichiers reçus jusqu'au courant inclus (id, snapshot_date, columns…)
    versions: pd.DataFrame | None = None          # versions Push des fichiers ANTÉRIEURS (maturité de référence)
    fill: pd.DataFrame | None = None              # taux de remplissage par fichier (snapshot_id, sheet, column, fill)
    known_values: dict[str, set] = field(default_factory=dict)  # valeurs déjà vues avant ce fichier, par dimension

    @property
    def det(self) -> dict[str, Any]:
        return self.cfg.detection

    def scaled(self, severity: str, volume: float) -> str:
        """Sévérité ajustée au volume : +1 cran au-delà de critical_volume, « minor » sous low_volume."""
        rank = severity_rank(severity)
        if volume >= self.det.get("critical_volume", 500_000):
            return SEVERITIES[min(rank + 1, len(SEVERITIES) - 1)]
        if volume < self.det.get("low_volume", 1_000) and rank > severity_rank("minor"):
            return "minor"
        return severity

    def in_blackout(self, scheduled_at: pd.Series) -> pd.Series:
        """Broadcasts planifiés dans la fenêtre de blackout SMS (réglementaire, 19h-07h par défaut) : arrêt normal.

        00:00:00 exactement = flow déclenché (pas d'heure d'envoi réelle) : jamais considéré en blackout.
        """
        cfg = self.det.get("sms_blackout") or {}
        start, end = (int(str(cfg.get(k, d)).split(":")[0]) for k, d in (("start", "19:00"), ("end", "07:00")))
        ts = pd.to_datetime(scheduled_at, errors="coerce")
        hour = ts.dt.hour
        inside = (hour >= start) | (hour < end) if start > end else (hour >= start) & (hour < end)
        midnight = (hour == 0) & (ts.dt.minute == 0) & (ts.dt.second == 0)
        return (inside & ~midnight).fillna(False)

    def business(self, df: pd.DataFrame) -> pd.DataFrame:
        """Retire les BC techniques (ex. « Dummy BC » qui démarrent un flow) : leur Sent n'est pas un vrai message."""
        patterns = self.det.get("technical_bc_patterns", [])
        if not patterns or df.empty:
            return df
        mask = df["bc_name"].fillna("").str.contains("|".join(map(re.escape, patterns)), case=False, regex=True)
        return df[~mask]

    def conversion_scope(self, df: pd.DataFrame) -> pd.DataFrame:
        """Broadcasts pertinents pour les règles de conversion (hors catégories informatives et seeding)."""
        out = self.business(df)
        out = out[~out["category"].isin(self.det.get("non_conversion_categories", []))]
        if self.det.get("exclude_seeding_from_conversion", True) and "is_seeding" in out:
            out = out[~out["is_seeding"]]
        return out


def fmt_int(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def fmt_pct(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{100 * x:.2f} %" if abs(x) < 0.1 else f"{100 * x:.1f} %"
