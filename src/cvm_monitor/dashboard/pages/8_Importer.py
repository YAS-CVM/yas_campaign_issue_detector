"""Importer un ou plusieurs Daily Dashboard (.xlsb) depuis le navigateur."""

from datetime import date

import streamlit as st

from cvm_monitor.config import severity_rank
from cvm_monitor.dashboard.common import anomalies, get_config, page_header, severity_md, snapshots
from cvm_monitor.ingest.loader import snapshot_date_from_name
from cvm_monitor.ingest.schema import SchemaError
from cvm_monitor.pipeline import import_upload

page_header("Importer")
cfg = get_config()

files = st.file_uploader("Daily Dashboard (.xlsb)", type=["xlsb"], accept_multiple_files=True)
c1, c2 = st.columns([1, 3])
notify = c1.toggle("Envoyer les alertes", value=True, help="Teams et e-mail, pour le fichier le plus récent")
clicked = c2.button("Importer", type="primary", icon=":material/upload:", disabled=not files)

if clicked and files:
    ordered = sorted(files, key=lambda f: (snapshot_date_from_name(f.name) or date.max, f.name))
    new_ids: list[int] = []
    for f in ordered:
        with st.status(f.name, expanded=True) as box:
            try:
                r = import_upload(cfg, f.name, f.getvalue(), notify=notify)
            except SchemaError as e:
                box.update(label=f"{f.name} · format non reconnu", state="error", expanded=True)
                st.write(str(e))
                continue
            except Exception as e:
                box.update(label=f"{f.name} · fichier illisible", state="error", expanded=True)
                st.write(f"{type(e).__name__} : {e}")
                continue

            if r.skipped:
                box.update(label=f"{f.name} · {r.reason}", state="complete", expanded=False)
                continue

            s = r.sync
            c = st.columns(4)
            c[0].metric("Date", str(r.snapshot_date))
            c[1].metric("Nouvelles", len(s.new) + len(s.reopened))
            c[2].metric("Aggravées", len(s.escalated))
            c[3].metric("Résolues", len(s.resolved))
            for channel, status in r.notifications.items():
                st.caption(f"{channel.capitalize()} : {status}")
            if r.rule_errors:
                st.warning("Règles en erreur : " + ", ".join(r.rule_errors))
            new_ids += s.new + s.reopened + s.escalated
            box.update(label=f"{f.name} · {r.snapshot_date}", state="complete", expanded=True)

    if new_ids:
        df = anomalies()
        df = df[df["id"].isin(new_ids) & (df["severity"].map(severity_rank) >= severity_rank("major"))]
        if not df.empty:
            st.subheader("Nouvelles anomalies critiques et majeures")
            for r in df.head(15).itertuples():
                st.markdown(f"{severity_md(r.severity)} · `{r.rule_id}` {r.rule_name}  \n{r.message}")
    try:
        st.page_link("pages/1_Anomalies.py", label="Toutes les anomalies", icon=":material/arrow_forward:")
    except Exception:
        pass

snaps = snapshots()
if not snaps.empty:
    st.subheader("Derniers fichiers")
    st.dataframe(snaps.sort_values("id", ascending=False).head(10)[["snapshot_date", "file_name", "ingested_at", "date_min",
                                                                   "date_max"]],
                 hide_index=True, width="stretch",
                 column_config={"snapshot_date": "Date", "file_name": "Fichier", "ingested_at": "Importé le",
                                "date_min": "Du", "date_max": "Au"})
