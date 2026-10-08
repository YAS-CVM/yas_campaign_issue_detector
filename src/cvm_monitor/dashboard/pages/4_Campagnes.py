"""Campagnes : TG vs CG, % Net Conversion et significativité."""

import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.analytics import kpi
from cvm_monitor.analytics.uplift import two_proportion_test
from cvm_monitor.dashboard.common import (
    SERIES, chart, columns_config, get_config, history, line, page_header, require_data,
)

page_header("Campagnes")
require_data()
push, _ = history()
maturity = get_config().detection.get("maturity_days", 3)

c1, c2, c3 = st.columns([1.2, 1, 2])
level = c1.radio("Niveau", ["Campaign Name", "BC Name"], horizontal=True)
seeding = c2.toggle("Inclure Is Seeding", value=False)
key = "campaign_name" if level == "Campaign Name" else "bc_name"
df = push if seeding else push[~push["is_seeding"]]

score = kpi.campaign_scorecard(df, key, maturity)
verdicts = c3.multiselect("Verdict", sorted(score["verdict"].unique()))
view = score[score["verdict"].isin(verdicts)] if verdicts else score
cols = [key, "category", "broadcasts", "sent", "conversions", "conv_rate", "cg_size", "cg_conversions", "cg_conv_rate",
        "uplift", "ci_low", "ci_high", "p_value", "incremental_conversions", "verdict"]
cfg = columns_config(cols)
cfg.update({
    "uplift": st.column_config.NumberColumn("% Net Conversion", format="percent"),
    "ci_low": st.column_config.NumberColumn("IC 95 % bas", format="percent"),
    "ci_high": st.column_config.NumberColumn("IC 95 % haut", format="percent"),
    "p_value": st.column_config.NumberColumn("p-value", format="%.4f"),
    "incremental_conversions": st.column_config.NumberColumn("Conv incrémentales", format="localized"),
})
st.dataframe(view[cols], hide_index=True, width="stretch", height=420, column_config=cfg)

st.divider()
names = score.sort_values("sent", ascending=False)[key].tolist()
pick = st.selectbox(level, names)
d = df[df[key] == pick]
daily = kpi.push_by(d, ["date"]).sort_values("date")
mature = d[d["age_days"] >= maturity]
res = two_proportion_test(mature["unique_conversions"].sum(), mature["sent"].sum(),
                          mature["cg_conversions"].sum(), mature["cg_size"].sum())
c = st.columns(5)
c[0].metric("Sent", f"{d['sent'].sum():,.0f}".replace(",", " "))
c[1].metric("Delivery%", f"{d['delivered'].sum() / d['sent'].sum():.1%}" if d["sent"].sum() else "–")
c[2].metric("Conv", f"{d['conversions'].sum():,.0f}".replace(",", " "))
if res:
    c[3].metric("% Net Conversion", f"{res.uplift:+.2%}", f"IC 95 % [{res.ci_low:+.2%} ; {res.ci_high:+.2%}]",
                delta_color="off")
    c[4].metric("Significatif", "Oui" if res.significant else "Non", f"p = {res.p_value:.3f}", delta_color="off")
else:
    c[3].metric("% Net Conversion", "–", "CG = 0", delta_color="off")

c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    line(fig, daily["date"], daily["sent"], "Sent", SERIES[0])
    line(fig, daily["date"], daily["delivered"], "Delivered", SERIES[2])
    chart(fig, "Sent / Delivered", height=320)
with c2:
    fig = go.Figure()
    line(fig, daily["date"], daily["conv_rate"], "TG Conv%", SERIES[0], pct=True)
    line(fig, daily["date"], daily["cg_conv_rate"], "% CG Conversion", SERIES[1], pct=True, dash="dot")
    chart(fig, "TG Conv% / % CG Conversion", height=320, pct=True)

cols = ["date", "bc_name", "status", "sent", "delivered", "conversions", "cg_size", "cg_conversions", "age_days"]
st.dataframe(d.sort_values("date", ascending=False)[cols], hide_index=True, width="stretch",
             column_config=columns_config(cols))
