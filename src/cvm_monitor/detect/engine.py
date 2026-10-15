"""Exécution des règles actives."""

from __future__ import annotations

import logging

from ..config import severity_rank
from . import rules_business, rules_feed, rules_im, rules_push, rules_snapshot  # noqa: F401  (enregistrement des règles)
from .base import REGISTRY, Anomaly, RuleContext

log = logging.getLogger(__name__)


def run_rules(ctx: RuleContext, only: set[str] | None = None) -> tuple[list[Anomaly], set[str], dict[str, str]]:
    """Renvoie (anomalies, règles exécutées avec succès, erreurs par règle)."""
    anomalies: list[Anomaly] = []
    executed: set[str] = set()
    errors: dict[str, str] = {}

    for rule_id, spec in sorted(REGISTRY.items()):
        if only and rule_id not in only:
            continue
        rule_cfg = ctx.cfg.rule(rule_id)
        if not rule_cfg.get("enabled", True):
            continue
        if spec.needs_previous and ctx.prev_push is None:
            continue
        data = ctx.im if spec.scope == "im" else ctx.push
        if data is None or data.empty:
            continue

        params = {**spec.defaults, **{k: v for k, v in rule_cfg.items() if k != "enabled"}}
        params.setdefault("severity", spec.severity)
        try:
            found = list(spec.func(ctx, params))
        except Exception as e:  # une règle en erreur ne doit pas bloquer les autres
            log.exception("Règle %s en erreur", rule_id)
            errors[rule_id] = f"{type(e).__name__}: {e}"
            continue

        for a in found:
            a.rule_id, a.rule_name, a.scope = rule_id, spec.name, spec.scope
            a.severity = a.severity or params["severity"]
            cap = params.get("max_severity")  # règle rétrogradée : visible dans le site, jamais notifiée
            if cap and severity_rank(a.severity) > severity_rank(cap):
                a.severity = cap
        anomalies.extend(found)
        executed.add(rule_id)

    return anomalies, executed, errors
