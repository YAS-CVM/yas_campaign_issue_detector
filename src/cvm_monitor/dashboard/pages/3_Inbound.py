"""Inbound : Impression, Fulfillment Success / Failures par Program Rule."""

import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.analytics import kpi
from cvm_monitor.dashboard.common import (
    PLOTLY_CONFIG, SERIES, base_layout, chart, columns_config, date_filter, gap_line, history, line, page_header, require_data,
)

page_header("Inbound")
require_data()
_, im = history()

c1, c2, c3 = st.columns([2, 1.5, 2])
with c1:
    start, end = date_filter(im["date"], "im_period")
tps = c2.multiselect("Touchpoint", sorted(im["touchpoint"].dropna().unique()))
progs = c3.multiselect("Program", sorted(im["program"].dropna().unique()))
df = im[(im["date"] >= start) & (im["date"] <= end)]
if tps:
    df = df[df["touchpoint"].isin(tps)]
if progs:
    df = df[df["program"].isin(progs)]

daily = kpi.im_daily(df)
tot = daily[["impressions", "fulfillment_success", "fulfillment_failures"]].sum()
attempts = tot["fulfillment_success"] + tot["fulfillment_failures"]
c = st.columns(4)
c[0].metric("Impression", f"{tot['impressions']:,.0f}".replace(",", " "))
c[1].metric("Total Successful Purchases", f"{tot['fulfillment_success']:,.0f}".replace(",", " "))
c[2].metric("Conv%", f"{tot['fulfillment_success'] / tot['impressions']:.2%}" if tot["impressions"] else "–")
c[3].metric("Fulfillment Failures%", f"{tot['fulfillment_failures'] / attempts:.1%}" if attempts else "–")

c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    by_prog = kpi.im_daily(df, ["program"])
    for i, p in enumerate(by_prog.groupby("program")["impressions"].sum().sort_values(ascending=False).index[:3]):
        d = by_prog[by_prog["program"] == p]
        line(fig, d["date"], d["impressions"], p, SERIES[i])
    chart(fig, "Impression par Program", height=340)
with c2:
    fig = go.Figure()
    line(fig, daily["date"], daily["failure_rate"], "Fulfillment Failures%", SERIES[1], pct=True)
    chart(fig, "Fulfillment Failures%", height=340, pct=True, legend=False)

st.subheader("Program Rule : Fulfillment Failures")
rules = kpi.im_by_rule(df)
worst = rules[rules["failures"] > 0].sort_values("failures", ascending=False).head(15).iloc[::-1]
if not worst.empty:
    fig = go.Figure()
    fig.add_trace(go.Bar(y=worst["rule_name"], x=worst["success"], name="Fulfillment Success", orientation="h",
                         marker=dict(color=SERIES[2], line=gap_line()),
                         hovertemplate="Fulfillment Success : %{x:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(y=worst["rule_name"], x=worst["failures"], name="Fulfillment Failures", orientation="h",
                         marker=dict(color=SERIES[1], line=gap_line()), customdata=worst["failure_rate"],
                         hovertemplate="Fulfillment Failures : %{x:,.0f} (%{customdata:.1%})<extra></extra>"))
    fig.update_layout(barmode="stack")
    base_layout(fig, 520)
    fig.update_layout(hovermode="y unified")
    fig.update_yaxes(showgrid=False, tickformat=None)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

st.subheader("Program Rule")
cols = ["rule_id", "rule_name", "program", "touchpoint", "impressions", "success", "failures", "failure_rate",
        "take_rate", "days", "last_date"]
cfg = columns_config(cols)
cfg["failure_rate"] = st.column_config.ProgressColumn("Fulfillment Failures%", format="percent", min_value=0, max_value=1)
st.dataframe(rules.sort_values("impressions", ascending=False)[cols], hide_index=True, width="stretch", height=420,
             column_config=cfg)
