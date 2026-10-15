"""Lecture d'un Daily Dashboard .xlsb -> DataFrames Push / IM nettoyés."""

from __future__ import annotations

import hashlib
import re
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import schema

EXCEL_EPOCH = pd.Timestamp("1899-12-30")
MONTHS = {
    "jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "avr": 4, "may": 5, "mai": 5, "jun": 6, "jui": 6,
    "jul": 7, "aug": 8, "aou": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
FILENAME_RE = re.compile(r"till_(\d{1,2})_([A-Za-zéû]{3,9})_?(\d{4})", re.IGNORECASE)


@dataclass
class Snapshot:
    path: Path
    file_hash: str
    snapshot_date: date
    push: pd.DataFrame
    im: pd.DataFrame
    columns: dict[str, list[str]] = field(default_factory=dict)  # colonnes brutes par feuille, telles que reçues

    @property
    def date_range(self) -> tuple[str, str]:
        dates = pd.concat([self.push["date"], self.im["date"]])
        return dates.min(), dates.max()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_date_from_name(name: str) -> date | None:
    m = FILENAME_RE.search(name)
    if not m:
        return None
    day, month_txt, year = m.groups()
    month = MONTHS.get(month_txt[:3].lower())
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def excel_serial_to_iso(values: pd.Series) -> pd.Series:
    serial = pd.to_numeric(values, errors="coerce")
    return (EXCEL_EPOCH + pd.to_timedelta(serial, unit="D")).dt.strftime("%Y-%m-%d")


def _strip_gmt(values: pd.Series) -> pd.Series:
    return values.astype("string").str.replace(" GMT", "", regex=False).str.strip()


def _read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            df = pd.read_excel(path, sheet_name=sheet, engine="pyxlsb")
        except ValueError as e:
            raise schema.SchemaError(f"Feuille {sheet!r} introuvable dans {path.name} ({e})") from e
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def _to_int(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round().astype("int64")


def clean_push(raw: pd.DataFrame) -> pd.DataFrame:
    df = schema.check_and_rename(raw, schema.PUSH_SHEET, schema.PUSH_COLUMNS, schema.PUSH_REQUIRED)
    df["date"] = excel_serial_to_iso(df["date"])
    df = df[df["date"].notna() & df["broadcast_id"].notna()].copy()
    if "scheduled_at" in df:
        df["scheduled_at"] = _strip_gmt(df["scheduled_at"])
    _to_int(df, schema.PUSH_COUNTS + ["broadcast_id", "campaign_id"])
    for c in schema.PUSH_AMOUNTS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in schema.PUSH_PCTS:  # 0-100 dans la source -> fraction 0-1
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    for c in ("bc_name", "campaign_name", "category", "status", "broadcast_name"):
        if c in df:
            df[c] = df[c].astype("string").str.strip()
    df["is_seeding"] = df.get("is_seeding", pd.Series("No", index=df.index)).astype("string").str.lower().eq("yes").fillna(False).astype(bool)
    return df.reset_index(drop=True)


def clean_im(raw: pd.DataFrame) -> pd.DataFrame:
    df = schema.check_and_rename(raw, schema.IM_SHEET, schema.IM_COLUMNS, schema.IM_REQUIRED)
    df["date"] = excel_serial_to_iso(df["date"])
    df = df[df["date"].notna() & df["rule_id"].notna()].copy()
    df = df.drop(columns=["date_text"], errors="ignore")
    for c in ("created_at", "modified_at", "last_refresh", "next_refresh", "approved_at"):
        if c in df:
            df[c] = _strip_gmt(df[c])
    _to_int(df, schema.IM_COUNTS + ["rule_id", "offer_id", "product_id", "program_id", "touchpoint_id"])
    for c in schema.IM_PCTS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    for c in ("touchpoint", "program", "rule_name", "product_name", "offer_name", "rule_status", "program_status"):
        if c in df:
            df[c] = df[c].astype("string").str.strip()
    return df.reset_index(drop=True)


def load_snapshot(path: str | Path) -> Snapshot:
    path = Path(path)
    raw_push, raw_im = _read_sheet(path, schema.PUSH_SHEET), _read_sheet(path, schema.IM_SHEET)
    columns = {schema.PUSH_SHEET: list(raw_push.columns), schema.IM_SHEET: list(raw_im.columns)}
    push, im = clean_push(raw_push), clean_im(raw_im)

    snap_date = snapshot_date_from_name(path.name)
    if snap_date is None:  # repli : dernier jour présent dans les données
        latest = max(d for d in (push["date"].max(), im["date"].max()) if isinstance(d, str))
        snap_date = datetime.strptime(latest, "%Y-%m-%d").date()

    push["age_days"] = (pd.Timestamp(snap_date) - pd.to_datetime(push["date"])).dt.days.astype("int64")
    return Snapshot(path=path, file_hash=file_sha256(path), snapshot_date=snap_date, push=push, im=im, columns=columns)
