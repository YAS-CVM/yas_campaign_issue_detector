"""Schéma attendu des feuilles brutes et renommage en snake_case."""

from __future__ import annotations

import pandas as pd

PUSH_SHEET = "Data_Push"
IM_SHEET = "Data_IM"

# Colonne source -> colonne interne. pandas renomme la 2e « Scheduled Date » en « Scheduled Date.1 ».
PUSH_COLUMNS = {
    "Scheduled Date": "date",
    "Scheduled Date.1": "scheduled_at",
    "Broadcast Name": "broadcast_name",
    "BC Name": "bc_name",
    "Broadcast ID": "broadcast_id",
    "Campaign Name": "campaign_name",
    "Campaign ID": "campaign_id",
    "Campaign Category": "category",
    "Status": "status",
    "Generated": "generated",
    "Sent": "sent",
    "Acknowledged": "acknowledged",
    "Conversions": "conversions",
    "Unique Conversions": "unique_conversions",
    "Conversion Value": "conversion_value",
    "Fulfillment Success": "fulfillment_success",
    "Fulfillment Failure": "fulfillment_failure",
    "Overall Ctrl Grp": "cg_size",
    "Overall Ctrl Grp Conversions": "cg_conversions",
    "Acknowledged %": "ack_rate",
    "Conversion %": "conv_rate",
    "Fulfillment Success %": "fulfillment_rate",
    "Ctrl Grp Conversion %": "cg_conv_rate",
    "Net Conversion %": "net_conv_rate",
    "Unique Conversion Value": "unique_conversion_value",
    "Is Seeding": "is_seeding",
    "Delivered": "delivered",
    "Value(Total_Con_Val)": "total_con_val",
}
PUSH_REQUIRED = [
    "Scheduled Date", "Broadcast ID", "BC Name", "Campaign Name", "Campaign Category", "Status",
    "Generated", "Sent", "Delivered", "Conversions", "Overall Ctrl Grp", "Overall Ctrl Grp Conversions",
]
PUSH_COUNTS = [
    "generated", "sent", "acknowledged", "conversions", "unique_conversions", "fulfillment_success",
    "fulfillment_failure", "cg_size", "cg_conversions", "delivered",
]
PUSH_AMOUNTS = ["conversion_value", "unique_conversion_value", "total_con_val"]
PUSH_PCTS = ["ack_rate", "conv_rate", "fulfillment_rate", "cg_conv_rate", "net_conv_rate"]

IM_COLUMNS = {
    "Date": "date",
    "Date.1": "date_text",
    "Touchpoint": "touchpoint",
    "Touchpoint ID": "touchpoint_id",
    "Program": "program",
    "Program ID": "program_id",
    "Program Rule": "rule_name",
    "Rule ID": "rule_id",
    "Product Name": "product_name",
    "Product ID": "product_id",
    "Offer Name": "offer_name",
    "Offer ID": "offer_id",
    "Current Rule Status": "rule_status",
    "Current Program Status": "program_status",
    "Created By": "created_by",
    "Created Date": "created_at",
    "Last Modified by": "modified_by",
    "Last Modified Date": "modified_at",
    "Last Refresh Date Time": "last_refresh",
    "Next Refresh Date Time": "next_refresh",
    "Impressions": "impressions",
    "Conversions": "conversions",
    "Fulfillment Success": "fulfillment_success",
    "Fulfillment Failures": "fulfillment_failures",
    "Accepted": "accepted",
    "Declined": "declined",
    "May be Later": "maybe_later",
    "Conversion %": "conv_rate",
    "Fulfillment %": "fulfillment_rate",
    "Approved By": "approved_by",
    "Approved Time": "approved_at",
}
IM_REQUIRED = [
    "Date", "Touchpoint", "Program", "Program Rule", "Rule ID", "Offer ID",
    "Impressions", "Fulfillment Success", "Fulfillment Failures",
]
IM_COUNTS = [
    "impressions", "conversions", "fulfillment_success", "fulfillment_failures",
    "accepted", "declined", "maybe_later",
]
IM_PCTS = ["conv_rate", "fulfillment_rate"]


class SchemaError(ValueError):
    pass


def check_and_rename(df: pd.DataFrame, sheet: str, mapping: dict[str, str], required: list[str]) -> pd.DataFrame:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(
            f"Feuille {sheet!r} : colonnes obligatoires absentes {missing}. "
            f"Le format du Daily Dashboard a peut-être changé. Colonnes trouvées : {list(df.columns)}"
        )
    known = [c for c in df.columns if c in mapping]
    return df[known].rename(columns=mapping)
