"""Fichiers ingérés et comparaison entre deux snapshots."""

import pandas as pd
import streamlit as st

from cvm_monitor.dashboard.common import LABEL, columns_config, page_header, require_data, snapshot_data

page_header("Snapshots")
snaps = require_data()

st.dataframe(snaps.sort_values("snapshot_date", ascending=False), hide_index=True, width="stretch",
             column_config={"file_hash": None, "id": "#", "file_name": "Fichier", "snapshot_date": "Date",
                            "ingested_at": "Ingéré le", "push_rows": "Lignes Data_Push", "im_rows": "Lignes Data_IM",
                            "date_min": "Du", "date_max": "Au"})

if len(snaps) < 2:
    st.stop()

labels = {int(r.id): f"#{r.id} · {r.snapshot_date} · {r.file_name}" for r in snaps.itertuples()}
ids = list(labels)
c1, c2 = st.columns(2)
a = c1.selectbox("Ancien", ids, index=len(ids) - 2, format_func=labels.get)
b = c2.selectbox("Récent", ids, index=len(ids) - 1, format_func=labels.get)
pa, _ = snapshot_data(a)
pb, _ = snapshot_data(b)

cols = ["generated", "sent", "delivered", "conversions", "unique_conversions", "cg_size", "cg_conversions",
        "conversion_value"]
m = pa.merge(pb, on="broadcast_id", suffixes=("_old", ""), how="inner")
st.subheader(f"Broadcasts communs : {len(m)}")
summary = pd.DataFrame({"Ancien": [m[f"{c}_old"].sum() for c in cols], "Récent": [m[c].sum() for c in cols]},
                       index=[LABEL.get(c, c) for c in cols])
summary["Écart"] = summary["Récent"] - summary["Ancien"]
summary["Écart %"] = summary["Écart"] / summary["Ancien"].where(summary["Ancien"] != 0)
st.dataframe(summary, width="stretch", column_config={"Écart %": st.column_config.NumberColumn(format="percent")})

changed = m[(m[[f"{c}_old" for c in cols]].to_numpy() != m[cols].to_numpy()).any(axis=1)]
if not changed.empty:
    st.subheader(f"Broadcasts révisés : {len(changed)}")
    show_cols = ["date", "bc_name", "status_old", "status"] + [x for c in cols for x in (f"{c}_old", c)]
    cfg = columns_config(["date", "bc_name", "status"] + cols)
    cfg.update({f"{c}_old": f"{LABEL.get(c, c)} (ancien)" for c in cols + ["status"]})
    st.dataframe(changed[show_cols], hide_index=True, width="stretch", column_config=cfg)

gone = pa[~pa["broadcast_id"].isin(pb["broadcast_id"]) & (pa["date"] >= pb["date"].min())]
if not gone.empty:
    st.subheader(f"Broadcasts disparus : {len(gone)}")
    cols = ["date", "bc_name", "status", "sent"]
    st.dataframe(gone[cols], hide_index=True, width="stretch", column_config=columns_config(cols))
