"""Chargement de la configuration (config.yaml + .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

SEVERITIES = ["info", "minor", "major", "critical"]
DEFAULT_CONFIG = Path("config") / "config.yaml"


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity)


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path
    config_path: Path

    def path(self, key: str) -> Path:
        p = Path(self.raw["paths"][key])
        return p if p.is_absolute() else self.root / p

    @property
    def detection(self) -> dict[str, Any]:
        return self.raw.get("detection", {})

    @property
    def ingest(self) -> dict[str, Any]:
        return self.raw.get("ingest", {})

    @property
    def notify(self) -> dict[str, Any]:
        return self.raw.get("notify", {})

    def rule(self, rule_id: str) -> dict[str, Any]:
        return self.raw.get("rules", {}).get(rule_id, {}) or {}

    @staticmethod
    def env(key: str, default: str | None = None) -> str | None:
        value = os.environ.get(key, default)
        return value if value not in ("", None) else default


def _validate(raw: dict[str, Any]) -> None:
    for key in ("inbox", "archive", "db", "reports"):
        if key not in raw.get("paths", {}):
            raise ConfigError(f"paths.{key} manquant dans config.yaml")
    for rule_id, rule_cfg in (raw.get("rules") or {}).items():
        severity = (rule_cfg or {}).get("severity")
        if severity and severity not in SEVERITIES:
            raise ConfigError(f"rules.{rule_id}.severity invalide : {severity!r} (attendu : {SEVERITIES})")
    for channel in ("teams", "email"):
        severity = raw.get("notify", {}).get(channel, {}).get("min_severity")
        if severity and severity not in SEVERITIES:
            raise ConfigError(f"notify.{channel}.min_severity invalide : {severity!r}")


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path or os.environ.get("CVM_MONITOR_CONFIG") or DEFAULT_CONFIG).resolve()
    if not config_path.exists():
        raise ConfigError(f"Fichier de configuration introuvable : {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    _validate(raw)
    root = config_path.parent.parent if config_path.parent.name == "config" else config_path.parent
    load_dotenv(config_path.parent / ".env")
    cfg = Config(raw=raw, root=root, config_path=config_path)
    for key in ("inbox", "archive", "reports"):
        cfg.path(key).mkdir(parents=True, exist_ok=True)
    cfg.path("db").parent.mkdir(parents=True, exist_ok=True)
    return cfg
