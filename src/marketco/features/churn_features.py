"""
Builds a customer-snapshot panel dataset for churn prediction -
genuinely different in character from the order-volume forecasting
task: this is a **binary classification** problem (will this customer
go quiet?) built on classic **RFM** (Recency, Frequency, Monetary)
features plus CRM engagement signals (support case volume and
satisfaction), which is exactly the blended "commerce + CRM" analysis
a Dynamics 365 + e-commerce data stack is built for.

Methodology
-----------
At each of several monthly **snapshot dates**, every customer who
placed at least one order in the trailing `lookback_days` window
(180 days) is considered "active as of that snapshot" and becomes one
training row. Features are computed **only from data before the
snapshot** (no leakage). The label is whether that customer placed
**zero** orders in the following `forward_days` window (90 days) -
the standard "went quiet" churn definition for a non-subscription
marketplace, where there's no explicit cancellation event to observe.

Multiple snapshots are pooled into one panel so the model sees many
different points in the customer lifecycle and calendar (not just one
end-of-data snapshot), and the final snapshot is held out for
time-based evaluation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK_DAYS = 180
FORWARD_DAYS = 90

FEATURE_COLUMNS = [
    "recency_days", "frequency_180d", "monetary_180d", "avg_order_value",
    "tenure_days", "n_categories_180d", "return_rate_180d",
    "late_delivery_rate_180d", "n_cases_180d", "avg_csat_180d",
    "marketing_opt_in", "acquisition_channel_code", "region_code",
]
LABEL_COLUMN = "churned"


def _snapshot_features(
    snapshot: pd.Timestamp,
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    cases: pd.DataFrame,
) -> pd.DataFrame:
    lookback_start = snapshot - pd.Timedelta(days=LOOKBACK_DAYS)
    forward_end = snapshot + pd.Timedelta(days=FORWARD_DAYS)

    window = orders[(orders["order_date"] > lookback_start) & (orders["order_date"] <= snapshot)]
    if window.empty:
        return pd.DataFrame()

    agg = window.groupby("customer_id").agg(
        recency_days=("order_date", lambda s: (snapshot - s.max()).days),
        frequency_180d=("order_id", "count"),
        monetary_180d=("order_amount_usd", "sum"),
        n_categories_180d=("category", "nunique"),
        return_rate_180d=("is_returned", "mean"),
        late_delivery_rate_180d=("on_time_delivery", lambda s: 1 - s.mean()),
    ).reset_index()
    agg["avg_order_value"] = agg["monetary_180d"] / agg["frequency_180d"]

    case_window = cases[(pd.to_datetime(cases["created_date"]) > lookback_start) & (pd.to_datetime(cases["created_date"]) <= snapshot)]
    case_agg = case_window.groupby("customer_id").agg(
        n_cases_180d=("case_id", "count"),
        avg_csat_180d=("csat_score", "mean"),
    ).reset_index()

    panel = agg.merge(case_agg, on="customer_id", how="left")
    panel["n_cases_180d"] = panel["n_cases_180d"].fillna(0)
    panel["avg_csat_180d"] = panel["avg_csat_180d"].fillna(panel["avg_csat_180d"].mean())

    panel = panel.merge(customers, on="customer_id", how="left")
    panel["tenure_days"] = (snapshot - pd.to_datetime(panel["registration_date"])).dt.days

    future = orders[(orders["order_date"] > snapshot) & (orders["order_date"] <= forward_end)]
    ordered_again = set(future["customer_id"].unique())
    panel["churned"] = ~panel["customer_id"].isin(ordered_again)

    panel["snapshot_date"] = snapshot
    return panel


def build_churn_panel(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    cases: pd.DataFrame,
    snapshot_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    orders = orders.copy()
    orders["order_date"] = pd.to_datetime(orders["order_date"])

    panels = []
    for snap in snapshot_dates:
        p = _snapshot_features(snap, orders, customers, cases)
        if not p.empty:
            panels.append(p)
    full = pd.concat(panels, ignore_index=True)

    full["marketing_opt_in"] = full["marketing_opt_in"].astype(int)
    for cat_col in ["acquisition_channel", "region"]:
        full[f"{cat_col}_code"] = full[cat_col].astype("category").cat.codes

    return full


def default_snapshot_dates() -> list[pd.Timestamp]:
    """Monthly snapshots that leave room for a full 180-day lookback and
    90-day forward label within the 2023-2024 study window."""
    return list(pd.date_range("2023-08-01", "2024-09-01", freq="MS"))
