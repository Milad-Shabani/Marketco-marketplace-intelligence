"""
Fulfillment network (warehouses) and marketplace seller accounts.

Sellers are modeled as the Dynamics 365 **Account** entity - the
standard CRM pattern for a marketplace that account-manages its
vendor base: each seller has a relationship tier, an assigned account
manager, an onboarding date, and a commission rate, exactly the
fields a real Dynamics 365 CRM implementation would carry on a
vendor/partner Account record.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WAREHOUSES = [
    {"warehouse_id": "WH-01", "warehouse_name": "Central Fulfillment Hub", "region": "Central", "capacity_orders_per_day": 9000},
    {"warehouse_id": "WH-02", "warehouse_name": "North Distribution Center", "region": "North", "capacity_orders_per_day": 4000},
    {"warehouse_id": "WH-03", "warehouse_name": "South Distribution Center", "region": "South", "capacity_orders_per_day": 3500},
    {"warehouse_id": "WH-04", "warehouse_name": "East Fulfillment Center", "region": "East", "capacity_orders_per_day": 3000},
    {"warehouse_id": "WH-05", "warehouse_name": "West Fulfillment Center", "region": "West", "capacity_orders_per_day": 2800},
]

ACCOUNT_MANAGERS = [
    "Sara Ahmadi", "Kian Rostami", "Leila Moradi", "Arman Hosseini", "Niloofar Karimi", "Babak Sadeghi",
]

SELLER_TIERS = ["Bronze", "Silver", "Gold", "Platinum"]


def warehouses_dataframe() -> pd.DataFrame:
    return pd.DataFrame(WAREHOUSES)


def sellers_dataframe(n_sellers: int = 260, seed: int = 21) -> pd.DataFrame:
    """Accounts entity: marketplace sellers/vendors."""
    rng = np.random.default_rng(seed)
    study_start = pd.Timestamp("2021-01-01")
    study_end = pd.Timestamp("2024-10-01")

    tier_probs = [0.45, 0.32, 0.18, 0.05]  # most sellers are small (Bronze)
    tiers = rng.choice(SELLER_TIERS, size=n_sellers, p=tier_probs)
    tier_commission = {"Bronze": 0.18, "Silver": 0.15, "Gold": 0.12, "Platinum": 0.09}
    tier_reliability = {"Bronze": 0.88, "Silver": 0.92, "Gold": 0.96, "Platinum": 0.985}

    onboarding_days = rng.integers(0, (study_end - study_start).days, size=n_sellers)
    onboarding_dates = study_start + pd.to_timedelta(onboarding_days, unit="D")

    rows = []
    for i in range(n_sellers):
        tier = tiers[i]
        rows.append({
            "account_id": f"ACC-{i+1:04d}",
            "account_name": f"Seller Co. {i+1:04d}",
            "account_type": "Seller",
            "tier": tier,
            "onboarding_date": onboarding_dates[i].strftime("%Y-%m-%d"),
            "account_manager": rng.choice(ACCOUNT_MANAGERS),
            "commission_rate": tier_commission[tier],
            "fulfillment_reliability": round(float(np.clip(rng.normal(tier_reliability[tier], 0.03), 0.5, 0.999)), 3),
            "region": rng.choice(["Central", "North", "South", "East", "West"]),
        })
    return pd.DataFrame(rows)
