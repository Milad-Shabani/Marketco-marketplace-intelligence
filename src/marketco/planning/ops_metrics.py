"""
Operational KPIs: per-warehouse delivery performance, per-seller
scorecards, and support-case SLA compliance - the "how well is the
marketplace actually running" complement to the CRM/churn analysis.
"""
from __future__ import annotations

import pandas as pd


def warehouse_performance(orders: pd.DataFrame, warehouses: pd.DataFrame) -> pd.DataFrame:
    perf = orders.groupby("warehouse_id").agg(
        orders=("order_id", "count"),
        on_time_rate=("on_time_delivery", "mean"),
        avg_delivery_days=("delivery_days", "mean"),
        gmv_usd=("order_amount_usd", "sum"),
    ).reset_index()
    return perf.merge(warehouses[["warehouse_id", "warehouse_name", "region"]], on="warehouse_id").sort_values("on_time_rate")


def seller_scorecard(orders: pd.DataFrame, sellers: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    perf = orders.groupby("seller_id").agg(
        orders=("order_id", "count"),
        gmv_usd=("order_amount_usd", "sum"),
        on_time_rate=("on_time_delivery", "mean"),
        return_rate=("is_returned", "mean"),
    ).reset_index()
    perf = perf.merge(sellers[["account_id", "account_name", "tier", "account_manager"]],
                       left_on="seller_id", right_on="account_id")
    return perf.sort_values("gmv_usd", ascending=False).head(top_n)


def case_sla_summary(cases: pd.DataFrame) -> pd.DataFrame:
    summary = cases.groupby("category").agg(
        cases=("case_id", "count"),
        sla_compliance=("met_sla", "mean"),
        avg_resolution_hours=("resolution_hours", "mean"),
        avg_csat=("csat_score", "mean"),
    ).reset_index()
    return summary.sort_values("cases", ascending=False)


def monthly_case_volume(cases: pd.DataFrame) -> pd.DataFrame:
    df = cases.copy()
    df["month"] = pd.to_datetime(df["created_date"]).dt.to_period("M").astype(str)
    return df.groupby("month", as_index=False).agg(
        cases=("case_id", "count"), sla_compliance=("met_sla", "mean")
    )


def monthly_gmv_trend(orders: pd.DataFrame) -> pd.DataFrame:
    """Full-history monthly GMV and order count, plus year-over-year GMV
    growth for each month that has a same-month prior-year comparison -
    the "big picture" trend a 30-week forecast window doesn't show."""
    df = orders.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["month"] = df["order_date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month", as_index=False).agg(
        gmv_usd=("order_amount_usd", "sum"), orders=("order_id", "count")
    ).sort_values("month")
    monthly["yoy_growth"] = monthly["gmv_usd"].pct_change(12)
    return monthly


def seller_tier_performance(orders: pd.DataFrame, sellers: pd.DataFrame) -> pd.DataFrame:
    """Revenue, order volume, and service quality rolled up by seller
    tier - connects the CRM account-tiering structure to what it
    actually produces commercially."""
    merged = orders.merge(sellers[["account_id", "tier"]], left_on="seller_id", right_on="account_id")
    perf = merged.groupby("tier", as_index=False).agg(
        sellers=("account_id", "nunique"),
        orders=("order_id", "count"),
        gmv_usd=("order_amount_usd", "sum"),
        on_time_rate=("on_time_delivery", "mean"),
    )
    perf["gmv_per_seller"] = perf["gmv_usd"] / perf["sellers"]
    tier_order = {"Bronze": 0, "Silver": 1, "Gold": 2, "Platinum": 3}
    perf["_sort"] = perf["tier"].map(tier_order)
    return perf.sort_values("_sort").drop(columns="_sort")


def acquisition_channel_effectiveness(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Customer count, spend, and average order value by acquisition
    channel - ties marketing-attribution data (a CRM/Contact-level
    field) to the commercial outcome it's supposed to predict."""
    merged = orders.merge(customers[["customer_id", "acquisition_channel"]], on="customer_id")
    perf = merged.groupby("acquisition_channel", as_index=False).agg(
        customers=("customer_id", "nunique"),
        gmv_usd=("order_amount_usd", "sum"),
        orders=("order_id", "count"),
    )
    perf["gmv_per_customer"] = perf["gmv_usd"] / perf["customers"]
    return perf.sort_values("gmv_usd", ascending=False)
