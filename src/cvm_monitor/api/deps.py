"""Accès à la configuration et à la base pour l'API d'écriture."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends

from cvm_monitor.config import Config, load_config
from cvm_monitor.storage.db import connect

_cfg: Config | None = None
write_lock = threading.Lock()  # un seul import / pipeline / acquittement à la fois (SQLite)


def get_config() -> Config:
    global _cfg
    if _cfg is None:
        _cfg = load_config(os.environ.get("CVM_MONITOR_CONFIG"))
    return _cfg


def get_conn(cfg: Annotated[Config, Depends(get_config)]) -> Iterator:
    """`check_same_thread=False` : la dépendance ouvre et ferme la connexion dans des threads différents du pool."""
    conn = connect(cfg.path("db"), check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[Any, Depends(get_conn)]
Cfg = Annotated[Config, Depends(get_config)]
