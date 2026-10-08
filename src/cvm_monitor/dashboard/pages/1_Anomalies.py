"""Anomalies : filtrer, examiner, acquitter."""

import json

import pandas as pd
import streamlit as st

from cvm_monitor.dashboard.common import (
    SEVERITY, STATUS_LABEL, anomalies, conn, page_header, require_data, severity_label, severity_md, style_severity,
)
from cvm_monitor.storage import repository as repo

page_header("Anomalies")
require_data()

df = anomalies()
if df.empty:
    st.success("Aucune anomalie détectée.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns([1.8, 1.4, 1.2, 1.6, 1.6])
sev = c1.multiselect("Sévérité", list(SEVERITY), default=["critical", "major"], format_func=severity_label)
status = c2.multiselect("Statut", list(STATUS_LABEL), default=["open"], format_func=STATUS_LABEL.get)
rules = c3.multiselect("Règle", sorted(df["rule_id"].unique()))
cats = c4.multiselect("Campaign Category / Program", sorted(df["category"].dropna().unique()))
search = c5.text_input("Recherche", placeholder="BC Name, Campaign Name, Program Rule…")

f = df
if sev:
    f = f[f["severity"].isin(sev)]
if status:
    f = f[f["status"].isin(status)]
if rules:
    f = f[f["rule_id"].isin(rules)]
if cats:
    f = f[f["category"].isin(cats)]
if search:
    f = f[f["message"].str.contains(search, case=False, na=False) | f["entity_key"].str.contains(search, case=False, na=False)]

st.caption(f"{len(f)} / {len(df)}")
view = pd.DataFrame({
    "#": f["id"],
    "Sévérité": f["severity"].map(severity_label),
    "Message": f["message"],
    "Règle": f["rule_id"] + " · " + f["rule_name"].fillna(""),
    "Date": f["date"],
    "Campaign Category / Program": f["category"],
    "Volume": f["volume"],
    "Statut": f["status"].map(STATUS_LABEL),
    "Première détection": f["first_seen_at"],
    "Occurrences": f["occurrences"],
})
event = st.dataframe(
    style_severity(view.style, "Sévérité"), hide_index=True, width="stretch", height=460,
    on_select="rerun", selection_mode="multi-row",
    column_config={"Volume": st.column_config.NumberColumn(format="localized"),
                   "Message": st.column_config.TextColumn(width="large")},
)
selected = f.iloc[event.selection.rows] if event and event.selection.rows else f.iloc[0:0]

st.download_button("Exporter CSV", f.drop(columns=["details"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                   file_name="anomalies.csv", mime="text/csv", icon=":material/download:")

if selected.empty:
    st.stop()

st.divider()
st.subheader(f"Sélection ({len(selected)})")
with st.form("ack"):
    c1, c2 = st.columns([1, 3])
    by = c1.text_input("Nom")
    note = c2.text_input("Note")
    b1, b2, b3 = st.columns(3)
    do_ack = b1.form_submit_button("Acquitter", icon=":material/task_alt:", type="primary",
                                   help="Plus de rappel, sauf si l'anomalie s'aggrave")
    do_mute = b2.form_submit_button("Mettre en sourdine", icon=":material/notifications_off:",
                                    help="Plus aucune alerte pour cette anomalie")
    do_open = b3.form_submit_button("Rouvrir", icon=":material/undo:")
    if do_ack or do_mute or do_open:
        new_status = "ack" if do_ack else ("muted" if do_mute else "open")
        repo.set_status(conn(), selected["id"].astype(int).tolist(), new_status, by or None, note or None)
        st.success(f"{len(selected)} → {STATUS_LABEL[new_status]}")
        st.rerun()

for r in selected.head(10).itertuples():
    with st.expander(f"{severity_md(r.severity)} · #{r.id} · {r.rule_id} · {r.entity_key}", expanded=len(selected) == 1):
        st.markdown(r.message)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Valeur", "–" if pd.isna(r.value) else f"{r.value:,.4g}".replace(",", " "))
        c2.metric("Attendu", r.expected or "–")
        c3.metric("Volume", f"{int(r.volume or 0):,}".replace(",", " "))
        c4.metric("Occurrences", r.occurrences)
        st.caption(f"{STATUS_LABEL[r.status]} · {r.first_seen_at} → {r.last_seen_at}"
                   + (f" · {r.ack_by}" if r.ack_by else "")
                   + (f" · {r.ack_note}" if r.ack_note else ""))
        try:
            details = json.loads(r.details or "{}")
        except json.JSONDecodeError:
            details = {}
        if details:
            st.json(details, expanded=False)
