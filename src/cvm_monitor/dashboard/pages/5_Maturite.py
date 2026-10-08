"""Maturité des Conv Push selon l'âge du broadcast."""

import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.analytics.maturity import maturity_curve, nowcast
from cvm_monitor.dashboard.common import SERIES, chart, history, line, page_header, push_versions, require_data

page_header("Maturité des Conv")
snaps = require_data()
push, _ = history()
versions = push_versions()

ref = st.slider("Conv définitives à J+", 7, 30, 14)
curve = maturity_curve(versions, ref)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Part des Conv connues selon l'âge")
    if len(curve) < 2:
        st.info(f"Historique insuffisant ({len(snaps)} fichier(s)).")
    else:
        fig = go.Figure()
        line(fig, curve["age_days"], curve["completion"], "Part connue", SERIES[0], pct=True)
        fig.update_xaxes(title="Âge (j)")
        chart(fig, None, height=340, pct=True, legend=False)
        st.dataframe(curve, hide_index=True, width="stretch",
                     column_config={"age_days": "Âge (j)", "broadcasts": "Broadcasts",
                                    "completion": st.column_config.NumberColumn("Part connue", format="percent")})
with c2:
    st.subheader("Conv par jour")
    nc = nowcast(push, curve)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=nc["date"], y=nc["conversions"], name="Conv", marker_color=SERIES[0],
                         hovertemplate="Conv : %{y:,.0f}<extra></extra>"))
    if nc["expected_final"].notna().any():
        line(fig, nc["date"], nc["expected_final"], f"Conv estimées à J+{ref}", SERIES[1], dash="dot")
    chart(fig, None, height=340)
