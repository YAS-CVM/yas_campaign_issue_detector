"""Éléments partagés du tableau de bord : config, accès données (avec cache), palette, graphiques."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.config import load_config
from cvm_monitor.labels import LABEL
from cvm_monitor.storage import repository as repo
from cvm_monitor.storage.db import connect

# ---- Palette (référence dataviz : catégoriel ordonné, séquentiel bleu, statuts réservés)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INK_MUTED = "#898781"
SEVERITY = {  # couleur de statut + icône Material + libellé (jamais la couleur seule)
    "critical": {"color": "#d03b3b", "tone": "red", "icon": ":material/error:", "label": "Critique"},
    "major": {"color": "#ec835a", "tone": "orange", "icon": ":material/warning:", "label": "Majeure"},
    "minor": {"color": "#2a78d6", "tone": "blue", "icon": ":material/info:", "label": "Mineure"},
    "info": {"color": "#898781", "tone": "gray", "icon": ":material/radio_button_unchecked:", "label": "Info"},
}
STATUS_LABEL = {"open": "Ouverte", "ack": "Acquittée", "muted": "En sourdine", "resolved": "Résolue"}
# Couleur liée à l'entité (catégorie), jamais à son rang
CATEGORIES = ["Informative", "Bundle Drive Campaign", "CVM", "Upsell Campaign",
              "Nursery Campaign", "DATAFRAMEWORK", "Engagements", "Voice Campaigns"]


def is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def surface() -> str:
    """Couleur de fond (sert aux séparations de 2 px entre segments)."""
    return "#0e1117" if is_dark() else "#ffffff"


def grid_color() -> str:
    return "#2c2c2a" if is_dark() else "#e1e0d9"


def gap_line() -> dict:
    return dict(width=2, color=surface())


def category_color(cat: str) -> str:
    return SERIES[CATEGORIES.index(cat)] if cat in CATEGORIES else INK_MUTED


@st.cache_resource
def get_config():
    return load_config(os.environ.get("CVM_MONITOR_CONFIG"))


def db_path() -> Path:
    return get_config().path("db")


def _db_version() -> float:
    p = db_path()
    return max((f.stat().st_mtime for f in p.parent.glob(p.name + "*")), default=0.0)


def conn():
    return connect(db_path())


@st.cache_data(show_spinner=False)
def _snapshots(version: float) -> pd.DataFrame:
    return repo.list_snapshots(conn())


@st.cache_data(show_spinner=False)
def _history(version: float, upto: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = conn()
    return repo.history_push(c, upto), repo.history_im(c, upto)


@st.cache_data(show_spinner=False)
def _snapshot_data(version: float, snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = conn()
    return repo.load_push(c, snapshot_id), repo.load_im(c, snapshot_id)


@st.cache_data(show_spinner=False)
def _versions(version: float) -> pd.DataFrame:
    return repo.push_versions(conn())


def snapshots() -> pd.DataFrame:
    return _snapshots(_db_version())


def history() -> tuple[pd.DataFrame, pd.DataFrame]:
    snaps = snapshots()
    if snaps.empty:
        return pd.DataFrame(), pd.DataFrame()
    return _history(_db_version(), snaps["snapshot_date"].max())


def snapshot_data(snapshot_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _snapshot_data(_db_version(), snapshot_id)


def push_versions() -> pd.DataFrame:
    return _versions(_db_version())


def anomalies(status: list[str] | None = None) -> pd.DataFrame:
    return repo.anomalies_df(conn(), status=status)


def require_data() -> pd.DataFrame:
    snaps = snapshots()
    if snaps.empty:
        st.info("Aucune donnée.")
        try:
            st.page_link("pages/8_Importer.py", label="Importer un fichier", icon=":material/upload_file:")
        except Exception:
            pass
        st.stop()
    return snaps


def page_header(title: str) -> None:
    st.title(title)
    snaps = snapshots()
    if not snaps.empty:
        last = snaps.iloc[-1]
        st.caption(f"{last['file_name']} · {last['date_min']} → {last['date_max']}")


def columns_config(cols: list[str], pct: tuple[str, ...] = (), money: tuple[str, ...] = ()) -> dict:
    """Configuration de colonnes st.dataframe avec les libellés du Daily Dashboard."""
    out = {}
    for c in cols:
        label = LABEL.get(c, c)
        if c in pct or c.endswith("_rate"):
            out[c] = st.column_config.NumberColumn(label, format="percent")
        elif c in money or c in ("sent", "delivered", "generated", "acknowledged", "conversions", "cg_size",
                                 "cg_conversions", "impressions", "success", "failures", "fulfillment_success",
                                 "fulfillment_failure", "fulfillment_failures", "unique_conversions"):
            out[c] = st.column_config.NumberColumn(label, format="localized")
        else:
            out[c] = label
    return out


def date_filter(dates: pd.Series, key: str, default_days: int = 31) -> tuple[str, str]:
    d = pd.to_datetime(pd.Series(dates.unique())).sort_values()
    lo, hi = d.min().date(), d.max().date()
    start_default = max(lo, (d.max() - pd.Timedelta(days=default_days - 1)).date())
    picked = st.date_input("Période", (start_default, hi), min_value=lo, max_value=hi, key=key, format="DD/MM/YYYY")
    if isinstance(picked, tuple) and len(picked) == 2:
        return picked[0].isoformat(), picked[1].isoformat()
    return lo.isoformat(), hi.isoformat()


PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}

# ---- Graphiques (traits fins, grille discrète, un seul axe Y, survol par défaut)

def base_layout(fig: go.Figure, height: int = 320, y_title: str | None = None, pct: bool = False,
                legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), title=None,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13),
        hovermode="x unified", showlegend=legend,
        legend=dict(orientation="h", yanchor="top", y=-0.14, x=0, title=None, traceorder="normal"),
    )
    fig.update_xaxes(showgrid=False, linecolor=grid_color(), tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(gridcolor=grid_color(), gridwidth=1, zeroline=False, tickfont=dict(color=INK_MUTED),
                     title=y_title, tickformat=".0%" if pct else "~s", rangemode="tozero")
    return fig


def chart(fig: go.Figure, title: str | None = None, **layout) -> None:
    """Titre en texte au-dessus (jamais en collision avec la légende) + graphique."""
    if title:
        st.markdown(f"**{title}**")
    st.plotly_chart(base_layout(fig, **layout), width="stretch", config=PLOTLY_CONFIG)


def line(fig: go.Figure, x, y, name: str, color: str, pct: bool = False, dash: str | None = None) -> None:
    fmt = "%{y:.1%}" if pct else "%{y:,.0f}"
    fig.add_trace(go.Scatter(x=x, y=y, name=name, mode="lines+markers",
                             line=dict(color=color, width=2, dash=dash), marker=dict(size=8, color=color),
                             hovertemplate=f"{name} : {fmt}<extra></extra>"))


def severity_md(sev: str, bold: bool = True) -> str:
    """Icône + libellé colorés (Markdown Streamlit : titres, métriques, expanders)."""
    s = SEVERITY.get(sev, SEVERITY["info"])
    label = f"**{s['label']}**" if bold else s["label"]
    return f":{s['tone']}[{s['icon']} {label}]"


def severity_label(sev: str) -> str:
    """Libellé texte seul (listes déroulantes, tableaux)."""
    return SEVERITY.get(sev, SEVERITY["info"])["label"]


def style_severity(styler, column: str):
    """Colore la colonne sévérité d'un tableau (Styler pandas)."""
    colors = {s["label"]: s["color"] for s in SEVERITY.values()}
    return styler.map(lambda v: f"color: {colors.get(v, 'inherit')}; font-weight: 600", subset=[column])
