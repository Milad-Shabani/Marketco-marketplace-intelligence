"""
Dynamics 365-style sales pipeline for seller acquisition: **Leads**
progress into **Opportunities**, which close Won (creating/renewing a
seller Account relationship) or Lost. This is the standard B2B
CRM pattern Dynamics 365 ships out of the box, applied here to how a
marketplace actually grows its seller base - plus a smaller stream of
**expansion opportunities** account managers run against existing
top-tier sellers (upsell/renegotiation deals), so the pipeline isn't
just "new seller acquisition".

Every onboarded seller (`sellers.csv`) is traced back to a Won Lead ->
Opportunity pair with a `created_date` before that seller's
`onboarding_date` - the funnel is internally consistent, not just
independently sampled dates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEAD_SOURCES = ["Outbound Prospecting", "Marketplace Inquiry", "Referral", "Trade Show", "Partner Channel"]
LOSS_REASONS = ["Price Too High", "Chose Competitor", "Poor Fit", "No Response", "Timing Not Right"]

_TIER_ANNUAL_GMV_ESTIMATE = {"Bronze": 15000, "Silver": 55000, "Gold": 180000, "Platinum": 600000}


def build_seller_acquisition_pipeline(sellers: pd.DataFrame, seed: int = 51) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_sellers = len(sellers)

    onboarding = pd.to_datetime(sellers["onboarding_date"])
    lead_lag_days = rng.integers(15, 90, size=n_sellers)
    lead_created = onboarding - pd.to_timedelta(lead_lag_days, unit="D")
    opp_lag_days = rng.integers(5, lead_lag_days)
    opp_created = lead_created + pd.to_timedelta(opp_lag_days, unit="D")

    won_leads = pd.DataFrame({
        "lead_id": [f"LEAD-{i+1:05d}" for i in range(n_sellers)],
        "lead_source": rng.choice(LEAD_SOURCES, size=n_sellers, p=[0.32, 0.28, 0.18, 0.12, 0.10]),
        "created_date": lead_created.dt.strftime("%Y-%m-%d"),
        "status": "Converted",
        "converted_account_id": sellers["account_id"].to_numpy(),
    })
    won_opps = pd.DataFrame({
        "opportunity_id": [f"OPP-{i+1:05d}" for i in range(n_sellers)],
        "lead_id": won_leads["lead_id"].to_numpy(),
        "account_id": sellers["account_id"].to_numpy(),
        "opportunity_type": "New Seller Onboarding",
        "created_date": opp_created.dt.strftime("%Y-%m-%d"),
        "close_date": onboarding.dt.strftime("%Y-%m-%d"),
        "stage": "Closed Won",
        "estimated_value_usd": sellers["tier"].map(_TIER_ANNUAL_GMV_ESTIMATE).to_numpy() * rng.uniform(0.8, 1.2, n_sellers),
        "loss_reason": None,
    })

    n_lost = int(n_sellers * 1.9)
    lost_created = pd.Timestamp("2021-01-01") + pd.to_timedelta(
        rng.integers(0, (pd.Timestamp("2024-11-01") - pd.Timestamp("2021-01-01")).days, size=n_lost), unit="D"
    )
    lost_leads = pd.DataFrame({
        "lead_id": [f"LEAD-{n_sellers + i + 1:05d}" for i in range(n_lost)],
        "lead_source": rng.choice(LEAD_SOURCES, size=n_lost, p=[0.32, 0.28, 0.18, 0.12, 0.10]),
        "created_date": lost_created.strftime("%Y-%m-%d"),
        "status": rng.choice(["Disqualified", "Open"], size=n_lost, p=[0.85, 0.15]),
        "converted_account_id": None,
    })

    reached_opp_mask = (lost_leads["status"] == "Disqualified") & (rng.random(n_lost) < 0.45)
    n_lost_opps = int(reached_opp_mask.sum())
    lost_opp_created = pd.to_datetime(lost_leads.loc[reached_opp_mask, "created_date"]) + pd.to_timedelta(
        rng.integers(5, 30, size=n_lost_opps), unit="D"
    )
    lost_opps = pd.DataFrame({
        "opportunity_id": [f"OPP-{n_sellers + i + 1:05d}" for i in range(n_lost_opps)],
        "lead_id": lost_leads.loc[reached_opp_mask, "lead_id"].to_numpy(),
        "account_id": None,
        "opportunity_type": "New Seller Onboarding",
        "created_date": lost_opp_created.dt.strftime("%Y-%m-%d"),
        "close_date": (lost_opp_created + pd.to_timedelta(rng.integers(10, 45, size=n_lost_opps), unit="D")).dt.strftime("%Y-%m-%d"),
        "stage": "Closed Lost",
        "estimated_value_usd": rng.uniform(10000, 200000, size=n_lost_opps),
        "loss_reason": rng.choice(LOSS_REASONS, size=n_lost_opps),
    })

    top_sellers = sellers[sellers["tier"].isin(["Gold", "Platinum"])]
    n_expansion = int(len(top_sellers) * 0.6)
    exp_accounts = rng.choice(top_sellers["account_id"].to_numpy(), size=n_expansion, replace=False) if n_expansion else np.array([])
    exp_created = pd.Timestamp("2023-01-01") + pd.to_timedelta(
        rng.integers(0, (pd.Timestamp("2024-11-01") - pd.Timestamp("2023-01-01")).days, size=n_expansion), unit="D"
    )
    exp_stage = rng.choice(["Closed Won", "Closed Lost", "Negotiation", "Proposal"], size=n_expansion, p=[0.45, 0.15, 0.20, 0.20])
    exp_close = exp_created + pd.to_timedelta(rng.integers(15, 60, size=n_expansion), unit="D")
    exp_stage_series = pd.Series(exp_stage)
    expansion_opps = pd.DataFrame({
        "opportunity_id": [f"OPP-{n_sellers + n_lost_opps + i + 1:05d}" for i in range(n_expansion)],
        "lead_id": None,
        "account_id": exp_accounts,
        "opportunity_type": "Account Expansion",
        "created_date": exp_created.strftime("%Y-%m-%d"),
        "close_date": np.where(exp_stage_series.isin(["Closed Won", "Closed Lost"]), exp_close.strftime("%Y-%m-%d"), None),
        "stage": exp_stage,
        "estimated_value_usd": rng.uniform(20000, 250000, size=n_expansion),
        "loss_reason": np.where(exp_stage_series == "Closed Lost", rng.choice(LOSS_REASONS, size=n_expansion), None),
    })

    leads = pd.concat([won_leads, lost_leads], ignore_index=True)
    opportunities = pd.concat([won_opps, lost_opps, expansion_opps], ignore_index=True)
    opportunities["estimated_value_usd"] = opportunities["estimated_value_usd"].round(2)

    return leads, opportunities
