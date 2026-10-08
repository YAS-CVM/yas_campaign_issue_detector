"""Point d'entrée du tableau de bord Yas CVM Monitor (navigation)."""

from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Yas CVM Monitor", page_icon=":material/monitoring:", layout="wide")

PAGES = Path(__file__).parent / "pages"
nav = st.navigation({
    "Suivi": [
        st.Page(PAGES / "0_Vue_ensemble.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page(PAGES / "1_Anomalies.py", url_path="anomalies", title="Anomalies", icon=":material/notification_important:"),
        st.Page(PAGES / "8_Importer.py", url_path="importer", title="Importer", icon=":material/upload_file:"),
    ],
    "Analyse": [
        st.Page(PAGES / "2_Push.py", url_path="push", title="Push", icon=":material/outbox:"),
        st.Page(PAGES / "3_Inbound.py", url_path="inbound", title="Inbound", icon=":material/move_to_inbox:"),
        st.Page(PAGES / "4_Campagnes.py", url_path="campagnes", title="Campagnes", icon=":material/insights:"),
        st.Page(PAGES / "5_Maturite.py", url_path="maturite", title="Maturité des Conv", icon=":material/hourglass_empty:"),
    ],
    "Données": [
        st.Page(PAGES / "6_Snapshots.py", url_path="snapshots", title="Snapshots", icon=":material/folder_open:"),
        st.Page(PAGES / "7_Qualite_donnees.py", url_path="qualite", title="Qualité des données", icon=":material/fact_check:"),
    ],
})
nav.run()
