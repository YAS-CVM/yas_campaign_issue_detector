"""Vue d'ensemble."""

import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.analytics import kpi
from cvm_monitor.dashboard.common import (
    CATEGORIES, SERIES, anomalies, category_color, chart, columns_config, gap_line, history, line,
    page_header, require_data, severity_md,
)

page_header("Overview")
snaps = require_data()
push, im = history()
last_id = int(snaps.iloc[-1]["id"])

h = kpi.headline(push, im)
st.subheader(h.get("date", ""))
cols = st.columns(6)
tiles = [
    ("Sent", "sent", "{:,.0f}", "normal"),
    ("Delivery%", "delivery_rate", "{:.1%}", "normal"),
    ("Conv", "conversions", "{:,.0f}", "normal"),
    ("Impression", "impressions", "{:,.0f}", "normal"),
    ("Total Successful Purchases", "im_success", "{:,.0f}", "normal"),
    ("Fulfillment Failures%", "im_failure_rate", "{:.1%}", "inverse"),
]
for col, (label, key, fmt, mode) in zip(cols, tiles):
    k = h.get(key) or {}
    v, ref = k.get("value"), k.get("ref7")
    if v is None or ref is None:
        delta = None
    elif "rate" in key:
        delta = f"{100 * (v - ref):+.1f} pt vs 7 j"
    else:
        delta = f"{(v - ref) / ref:+.0%} vs 7 j" if ref else None
    col.metric(label, "–" if v is None else fmt.format(v).replace(",", " "), delta, delta_color=mode,
               help="Conv non définitives sur les 3 derniers jours" if key == "conversions" else None)

st.subheader("Anomalies ouvertes")
open_ = anomalies(["open"])
cols = st.columns(5)
for col, sev in zip(cols, ["critical", "major", "minor", "info"]):
    n = int((open_["severity"] == sev).sum()) if not open_.empty else 0
    col.metric(severity_md(sev, bold=False), n)
new_n = int((open_["first_seen_snapshot"] == last_id).sum()) if not open_.empty else 0
cols[4].metric(":material/fiber_new: Nouvelles", new_n)

top = open_[open_["severity"].isin(["critical", "major"])].head(10) if not open_.empty else open_
if top.empty:
    st.success("Aucune anomalie critique ou majeure ouverte.")
else:
    for r in top.itertuples():
        st.markdown(f"{severity_md(r.severity)} · `{r.rule_id}` {r.rule_name}  \n{r.message}")
    try:
        st.page_link("pages/1_Anomalies.py", label="Toutes les anomalies", icon=":material/arrow_forward:")
    except Exception:
        pass

st.subheader("Push")
daily = kpi.push_daily(push)
by_cat = kpi.push_by(push, ["date", "category"])
c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    present = [c for c in CATEGORIES if c in set(by_cat["category"])] + \
              sorted(set(by_cat["category"]) - set(CATEGORIES))
    for cat in present:
        d = by_cat[by_cat["category"] == cat]
        fig.add_trace(go.Bar(x=d["date"], y=d["sent"], name=cat, marker_color=category_color(cat),
                             marker_line=gap_line(), hovertemplate=f"{cat} : %{{y:,.0f}}<extra></extra>"))
    fig.update_layout(barmode="stack")
    chart(fig, "Sent par Campaign Category", height=360)
with c2:
    fig = go.Figure()
    line(fig, daily["date"], daily["delivery_rate"], "Delivery%", SERIES[0], pct=True)
    chart(fig, "Delivery%", height=360, pct=True, legend=False)

st.subheader("Inbound")
im_tp = kpi.im_daily(im, ["touchpoint"])
im_all = kpi.im_daily(im)
c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    for i, tp in enumerate(sorted(im_tp["touchpoint"].dropna().unique())):
        d = im_tp[im_tp["touchpoint"] == tp]
        line(fig, d["date"], d["impressions"], tp, SERIES[i % 3])
    chart(fig, "Impression par Touchpoint", height=320)
with c2:
    fig = go.Figure()
    line(fig, im_all["date"], im_all["failure_rate"], "Fulfillment Failures%", SERIES[1], pct=True)
    chart(fig, "Fulfillment Failures%", height=320, pct=True, legend=False)

with st.expander("Données Push par jour"):
    cols = ["date", "sent", "delivered", "delivery_rate", "conversions", "conv_rate", "cg_size", "cg_conversions",
            "cg_conv_rate", "net_conv_rate"]
    st.dataframe(daily[cols], hide_index=True, width="stretch", column_config=columns_config(cols))
