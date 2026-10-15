"""Mesure de l'uplift (TG vs CG) et test de significativité."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class UpliftResult:
    tg_rate: float
    cg_rate: float
    uplift: float           # tg_rate - cg_rate (points de fraction)
    z: float
    p_value: float          # bilatéral
    ci_low: float           # IC 95 % de l'uplift
    ci_high: float
    significant: bool

    @property
    def relative(self) -> float:
        return self.uplift / self.cg_rate if self.cg_rate else float("nan")


def _normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def two_proportion_test(tg_conv: float, tg_n: float, cg_conv: float, cg_n: float, alpha: float = 0.05) -> UpliftResult | None:
    """Test z de différence de deux proportions. None si les effectifs sont insuffisants."""
    if tg_n <= 0 or cg_n <= 0:
        return None
    tg_conv, cg_conv = min(tg_conv, tg_n), min(cg_conv, cg_n)
    p1, p2 = tg_conv / tg_n, cg_conv / cg_n
    pooled = (tg_conv + cg_conv) / (tg_n + cg_n)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / tg_n + 1 / cg_n))
    se = math.sqrt(p1 * (1 - p1) / tg_n + p2 * (1 - p2) / cg_n)
    diff = p1 - p2
    z = diff / se_pooled if se_pooled > 0 else 0.0
    p_value = 2 * _normal_sf(abs(z))
    return UpliftResult(p1, p2, diff, z, p_value, diff - 1.96 * se, diff + 1.96 * se, p_value < alpha)
