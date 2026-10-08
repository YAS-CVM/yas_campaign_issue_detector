"""Libellés des colonnes, identiques à ceux du Daily Dashboard (.xlsb)."""

LABEL = {
    "date": "Date", "scheduled_at": "Scheduled Date", "broadcast_id": "Broadcast ID", "bc_name": "BC Name",
    "campaign_name": "Campaign Name", "category": "Campaign Category", "status": "Status", "is_seeding": "Is Seeding",
    "generated": "Generated", "sent": "Sent", "acknowledged": "Acknowledged", "delivered": "Delivered",
    "delivery_rate": "Delivery%", "conversions": "Conv", "unique_conversions": "Unique Conversions",
    "conv_rate": "TG Conv%", "cg_size": "CG", "cg_conversions": "CG Conv", "cg_conv_rate": "% CG Conversion",
    "net_conv_rate": "% Net Conversion", "conversion_value": "Conversion Value",
    "fulfillment_success": "Fulfillment Success", "fulfillment_failure": "Fulfillment Failure",
    "fulfillment_failures": "Fulfillment Failures", "broadcasts": "Broadcasts", "age_days": "Age (j)",
    "touchpoint": "Touchpoint", "program": "Program", "rule_id": "Rule ID", "rule_name": "Program Rule",
    "offer_name": "Offer Name", "impressions": "Impression", "success": "Fulfillment Success",
    "failures": "Fulfillment Failures", "failure_rate": "Fulfillment Failures%", "take_rate": "Conv%",
    "days": "Jours", "last_date": "Dernier jour", "uplift": "% Net Conversion", "ci_low": "IC 95 % bas",
    "ci_high": "IC 95 % haut", "p_value": "p-value", "significant": "Significatif",
    "incremental_conversions": "Conv incrémentales", "verdict": "Verdict",
}


def rename(df):
    """Renomme les colonnes d'un DataFrame avec les libellés du Daily Dashboard."""
    return df.rename(columns={c: LABEL[c] for c in df.columns if c in LABEL})
