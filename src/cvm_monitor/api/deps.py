"""Accès config / base / données consolidées, filtres de requête, sérialisation JSON."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from typing import Annotated, Any

import pandas as pd
from fastapi import Depends, Query

from cvm_monitor.config import Config, load_config
from cvm_monitor.services.filters import Filters
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect

_cfg: Config | None = None
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()
write_lock = threading.Lock()  # un seul import / pipeline à la fois (SQLite)


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = load_config(os.environ.get("CVM_MONITOR_CONFIG"))
    return _cfg


def get_conn(cfg: Annotated[Config, Depends(get_config)]) -> Iterator:
    conn = connect(cfg.path("db"), check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[Any, Depends(get_conn)]
Cfg = Annotated[Config, Depends(get_config)]


def _db_version(cfg: Config) -> float:
    p = cfg.path("db")
    return max((f.stat().st_mtime for f in p.parent.glob(p.name + "*")), default=0.0)


def history(cfg: Config, conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dernière version de chaque broadcast / ligne IM, mise en cache tant que la base ne change pas."""
    snaps = repo.list_snapshots(conn)
    if snaps.empty:
        return pd.DataFrame(), pd.DataFrame()
    key = (_db_version(cfg), snaps["snapshot_date"].max())
    with _cache_lock:
        if _cache.get("key") != key:
            _cache["key"] = key
            _cache["data"] = (repo.history_push(conn, key[1]), repo.history_im(conn, key[1]))
        return _cache["data"]


def filters(
    date_from: str | None = None, date_to: str | None = None,
    category: Annotated[list[str] | None, Query()] = None,
    campaign: Annotated[list[str] | None, Query()] = None,
    bc: Annotated[list[str] | None, Query()] = None,
    broadcast: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    touchpoint: Annotated[list[str] | None, Query()] = None,
    program: Annotated[list[str] | None, Query()] = None,
    rule: Annotated[list[str] | None, Query()] = None,
    offer: Annotated[list[str] | None, Query()] = None,
    include_seeding: bool = False, mature_only: bool = False, maturity_days: int = 3,
) -> Filters:
    return Filters(date_from, date_to, category or [], campaign or [], bc or [], broadcast or [],
                   status or [], touchpoint or [], program or [], rule or [], offer or [],
                   include_seeding, mature_only, maturity_days)


F = Annotated[Filters, Depends(filters)]


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → liste JSON (NaN/NaT → null, types numpy gérés)."""
    return json.loads(df.to_json(orient="records")) if not df.empty else []
