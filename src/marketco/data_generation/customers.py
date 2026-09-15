"""
Customers, modeled as the Dynamics 365 **Contact** entity: each
customer has a registration date, region, and acquisition channel -
the standard fields a CRM-integrated marketplace would track from
first sign-up. Registration dates are spread from three years before
the study window through its end, so the customer base has a
realistic mix of long-tenured and brand-new customers when the
churn/RFM analysis runs at the end of the window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ACQUISITION_CHANNELS = ["Organic Search", "Paid Ads", "Social Media", "Referral", "Email Campaign", "Direct"]
CHANNEL_PROBS = [0.28, 0.22, 0.18, 0.14, 0.10, 0.08]
REGIONS = ["Central", "North", "South", "East", "West"]


def customers_dataframe(n_customers: int = 36000, seed: int = 31) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    reg_start = pd.Timestamp("2020-01-01")
    reg_end = pd.Timestamp("2024-12-15")
    total_days = (reg_end - reg_start).days

    # Growing registration rate over time (the marketplace itself is
    # growing), implemented by biasing the random day index toward
    # later dates with a mild power-law skew.
    u = rng.random(n_customers)
    day_offsets = (u ** 0.6) * total_days
    reg_dates = reg_start + pd.to_timedelta(day_offsets.astype(int), unit="D")

    channels = rng.choice(ACQUISITION_CHANNELS, size=n_customers, p=CHANNEL_PROBS)
    regions = rng.choice(REGIONS, size=n_customers, p=[0.34, 0.18, 0.16, 0.16, 0.16])

    df = pd.DataFrame({
        "customer_id": [f"CUST-{i+1:06d}" for i in range(n_customers)],
        "registration_date": reg_dates.strftime("%Y-%m-%d"),
        "region": regions,
        "acquisition_channel": channels,
        "marketing_opt_in": rng.random(n_customers) < 0.62,
    })
    return df
