"""Push : entonnoir, statuts, Delivery% par catégorie, broadcasts."""

import plotly.graph_objects as go
import streamlit as st

from cvm_monitor.analytics import kpi
from cvm_monitor.dashboard.common import (
    CATEGORIES, PLOTLY_CONFIG, SEQ_BLUE, SERIES, base_layout, columns_config, date_filter, history, page_header, require_data,
)

page_header("Push")
require_data()
push, _ = history()

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    start, end = date_filter(push["date"], "push_period")
cats = c2.multiselect("Campaign Category", [c for c in CATEGORIES if c in set(push["category"])])
tech = c3.toggle("Inclure les Dummy BC", value=False)

df = push[(push["date"] >= start) & (push["date"] <= end)]
if cats:
    df = df[df["category"].isin(cats)]
if not tech:
    df = df[~df["bc_name"].fillna("").str.contains("Dummy BC", case=False)]

steps = ["generated", "sent", "acknowledged", "delivered", "conversions", "fulfillment_success"]
labels = ["Generated", "Sent", "Acknowledged", "Delivered", "Conv", "Fulfillment Success"]
tot = df[steps].sum()
c1, c2 = st.columns(2)
with c1:
    st.subheader("Entonnoir")
    fig = go.Figure(go.Bar(
        y=labels[::-1], x=[tot[k] for k in steps][::-1], orientation="h",
        marker=dict(color=SEQ_BLUE[::-1][: len(steps)][::-1], line=dict(width=0)),
        text=[f"{tot[k]:,.0f}".replace(",", " ") for k in steps][::-1],
        textposition="outside", cliponaxis=False, hovertemplate="%{y} : %{x:,.0f}<extra></extra>",
    ))
    base_layout(fig, 340, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, max(tot.max(), 1) * 1.3])
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
with c2:
    st.subheader("Status")
    stat = df.groupby("status").agg(broadcasts=("broadcast_id", "size"), sent=("sent", "sum")).sort_values("broadcasts")
    fig = go.Figure(go.Bar(y=stat.index, x=stat["broadcasts"], orientation="h", marker_color=SERIES[0],
                           customdata=stat["sent"],
                           hovertemplate="%{y} : %{x} broadcasts, Sent %{customdata:,.0f}<extra></extra>"))
    base_layout(fig, 340, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

st.subheader("Delivery% par Campaign Category")
bc = kpi.push_by(df[df["sent"] > 0], ["category", "date"])
if not bc.empty:
    pivot = bc.pivot(index="category", columns="date", values="delivery_rate")
    sent = bc.pivot(index="category", columns="date", values="sent")
    order = [c for c in CATEGORIES if c in pivot.index] + [c for c in pivot.index if c not in CATEGORIES]
    pivot, sent = pivot.loc[order], sent.loc[order]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index, customdata=sent.values, zmin=0, zmax=1,
        colorscale=[[i / (len(SEQ_BLUE) - 1), c] for i, c in enumerate(SEQ_BLUE)], xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Delivery%", side="right"), tickformat=".0%"),
        hovertemplate="%{y}<br>%{x}<br>Delivery% %{z:.1%}<br>Sent %{customdata:,.0f}<extra></extra>",
    ))
    base_layout(fig, 360, legend=False)
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(showgrid=False, tickformat=None, autorange="reversed")
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

st.subheader("Campaign Category")
cat = kpi.push_by(df, ["category"]).sort_values("sent", ascending=False)
cols = ["category", "broadcasts", "sent", "delivered", "delivery_rate", "conversions", "conv_rate",
        "cg_size", "cg_conversions", "cg_conv_rate", "net_conv_rate", "conversion_value"]
st.dataframe(cat[cols], hide_index=True, width="stretch",
             column_config=columns_config(cols, money=("conversion_value",)))

st.subheader("Broadcasts")
q = st.text_input("Recherche", placeholder="BC Name, Campaign Name…")
b = df if not q else df[df["bc_name"].str.contains(q, case=False, na=False)
                        | df["campaign_name"].str.contains(q, case=False, na=False)]
b = b.assign(delivery_rate=lambda x: x["delivered"] / x["sent"].where(x["sent"] > 0)) \
     .sort_values(["date", "sent"], ascending=[False, False])
cols = ["date", "scheduled_at", "bc_name", "campaign_name", "category", "status", "is_seeding", "generated", "sent",
        "acknowledged", "delivered", "delivery_rate", "conversions", "cg_size", "cg_conversions"]
cfg = columns_config(cols)
cfg["is_seeding"] = st.column_config.CheckboxColumn("Is Seeding")
st.dataframe(b[cols], hide_index=True, width="stretch", height=420, column_config=cfg)
