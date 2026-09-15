"""
Sales-pipeline (Lead -> Opportunity -> Won) funnel metrics: conversion
rates by stage, win rate by lead source, and pipeline value by stage -
the standard CRM sales-ops report.
"""
from __future__ import annotations

import pandas as pd


def compute_acquisition_funnel_stages(
    leads: pd.DataFrame, opportunities: pd.DataFrame, orders: pd.DataFrame, sellers: pd.DataFrame,
) -> list[tuple[str, int]]:
    """
    A strictly monotonic, lead-traceable funnel: each stage is a proper
    subset of the one above it.

    Earlier versions mixed Account Expansion opportunities (deals against
    *existing* sellers, with no Lead behind them at all) into the same
    "Opportunities" count as new-seller-acquisition deals - which could
    make the Opportunities stage bigger than the Leads stage feeding it,
    breaking the basic shape a funnel is supposed to have. Restricting to
    `opportunity_type == "New Seller Onboarding"` keeps every stage a
    genuine subset of the one before it.
    """
    onboarding_opps = opportunities[opportunities["opportunity_type"] == "New Seller Onboarding"]

    n_leads = len(leads)
    n_opportunities = onboarding_opps["lead_id"].notna().sum()
    n_won = int((onboarding_opps["stage"] == "Closed Won").sum())

    won_account_ids = set(onboarding_opps.loc[onboarding_opps["stage"] == "Closed Won", "account_id"].dropna())
    active_seller_ids = set(orders["seller_id"].unique()) & won_account_ids
    high_performing_ids = set(sellers.loc[sellers["tier"].isin(["Gold", "Platinum"]), "account_id"]) & active_seller_ids

    return [
        ("Leads", int(n_leads)),
        ("Opportunities", int(n_opportunities)),
        ("Won (Onboarded)", int(n_won)),
        ("High-Performing (Gold/Platinum)", len(high_performing_ids)),
    ]


def compute_funnel_summary(leads: pd.DataFrame, opportunities: pd.DataFrame) -> dict:
    n_leads = len(leads)
    n_converted = int((leads["status"] == "Converted").sum())
    n_opps = len(opportunities)
    n_won = int((opportunities["stage"] == "Closed Won").sum())
    n_lost = int((opportunities["stage"] == "Closed Lost").sum())
    n_open = n_opps - n_won - n_lost

    return {
        "leads_total": n_leads,
        "leads_converted": n_converted,
        "lead_conversion_rate": round(n_converted / n_leads, 4) if n_leads else 0,
        "opportunities_total": n_opps,
        "opportunities_won": n_won,
        "opportunities_lost": n_lost,
        "opportunities_open": n_open,
        "win_rate": round(n_won / (n_won + n_lost), 4) if (n_won + n_lost) else 0,
        "won_pipeline_value_usd": round(opportunities.loc[opportunities["stage"] == "Closed Won", "estimated_value_usd"].sum(), 2),
        "open_pipeline_value_usd": round(
            opportunities.loc[~opportunities["stage"].isin(["Closed Won", "Closed Lost"]), "estimated_value_usd"].sum(), 2
        ),
    }


def win_rate_by_source(leads: pd.DataFrame, opportunities: pd.DataFrame) -> pd.DataFrame:
    merged = opportunities.merge(
        leads[["lead_id", "lead_source"]], on="lead_id", how="left"
    )
    closed = merged[merged["stage"].isin(["Closed Won", "Closed Lost"])]
    summary = closed.groupby("lead_source").agg(
        opportunities=("opportunity_id", "count"),
        won=("stage", lambda s: (s == "Closed Won").sum()),
    ).reset_index()
    summary["win_rate"] = (summary["won"] / summary["opportunities"]).round(3)
    return summary.sort_values("win_rate", ascending=False)


def pipeline_by_stage(opportunities: pd.DataFrame) -> pd.DataFrame:
    return opportunities.groupby("stage").agg(
        count=("opportunity_id", "count"), total_value_usd=("estimated_value_usd", "sum")
    ).reset_index()
