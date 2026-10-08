"""Qualité des données du dernier fichier."""

import pandas as pd
import streamlit as st

from cvm_monitor.dashboard.common import anomalies, page_header, require_data, snapshot_data, style_severity, severity_label

page_header("Qualité des données")
snaps = require_data()
last = snaps.iloc[-1]
push, im = snapshot_data(int(last["id"]))

checks = [
    ("Data_Push", "Lignes", len(push), None),
    ("Data_Push", "Jours", push["date"].nunique(), None),
    ("Data_Push", "Sent > Generated (Generated > 0)", int(((push["generated"] > 0) & (push["sent"] > push["generated"])).sum()), 0),
    ("Data_Push", "Generated = 0 et Sent > 0", int(((push["generated"] == 0) & (push["sent"] > 0)).sum()), None),
    ("Data_Push", "Delivered > Sent", int((push["delivered"] > push["sent"]).sum()), 0),
    ("Data_Push", "Fulfillment Success > Conversions", int(((push["conversions"] > 0) & (push["fulfillment_success"] > push["conversions"])).sum()), 0),
    ("Data_Push", "Overall Ctrl Grp = 0 et Sent > 0", int(((push["cg_size"] == 0) & (push["sent"] > 0)).sum()), None),
    ("Data_Push", "Value(Total_Con_Val) renseignée", int(push["total_con_val"].notna().sum()) if "total_con_val" in push else 0, None),
    ("Data_IM", "Lignes", len(im), None),
    ("Data_IM", "Jours", im["date"].nunique(), None),
    ("Data_IM", "Conversions", int(im["conversions"].sum()), None),
    ("Data_IM", "Fulfillment Success", int(im["fulfillment_success"].sum()), None),
    ("Data_IM", "Last Refresh Date Time (min)", im["last_refresh"].min() if "last_refresh" in im else "–", None),
    ("Data_IM", "Last Refresh Date Time (max)", im["last_refresh"].max() if "last_refresh" in im else "–", None),
]
df = pd.DataFrame(checks, columns=["Feuille", "Contrôle", "Valeur", "Attendu"])
df["État"] = df.apply(lambda r: "" if r["Attendu"] is None else ("OK" if r["Valeur"] == r["Attendu"] else "À vérifier"), axis=1)
df["Valeur"] = df["Valeur"].astype(str)
df["Attendu"] = df["Attendu"].map(lambda v: "" if v is None or pd.isna(v) else str(int(v)))
st.dataframe(
    df.style.map(lambda v: {"OK": "color: #0ca30c; font-weight: 600",
                            "À vérifier": "color: #ec835a; font-weight: 600"}.get(v, ""), subset=["État"]),
    hide_index=True, width="stretch")

dq = anomalies(["open", "ack"])
dq = dq[dq["rule_id"].str.contains("-DQ-|SNP-", regex=True)] if not dq.empty else dq
st.subheader(f"Anomalies de qualité ouvertes : {len(dq)}")
if not dq.empty:
    view = pd.DataFrame({"Règle": dq["rule_id"] + " · " + dq["rule_name"], "Sévérité": dq["severity"].map(severity_label),
                         "Date": dq["date"], "Message": dq["message"]})
    st.dataframe(style_severity(view.style, "Sévérité"), hide_index=True, width="stretch")

st.subheader("Lignes par jour")
per_day = pd.DataFrame({"Data_Push": push.groupby("date").size(), "Data_IM": im.groupby("date").size()}).fillna(0).astype(int)
st.dataframe(per_day.T, width="stretch")
