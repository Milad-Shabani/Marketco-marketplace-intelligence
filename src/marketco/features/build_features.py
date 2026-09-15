"""
Builds the weekly-grain modeling dataset used by the global order
volume/GMV forecasting model - the operations counterpart to the CRM
churn model in `models/churn_model.py`.

Weekly grain matches how a marketplace ops team actually plans
(warehouse staffing, courier capacity), and lets the model see a full
promotional-event cycle within a handful of lag periods.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "weekly_orders"
GMV_TARGET = "weekly_gmv"


def load_raw(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    orders = pd.read_parquet(raw_dir / "orders.parquet")
    products = pd.read_csv(raw_dir / "products.csv")
    return orders, products


def to_weekly(orders: pd.DataFrame) -> pd.DataFrame:
    df = orders.copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["week_start"] = df["order_date"] - pd.to_timedelta(df["order_date"].dt.weekday, unit="D")
    weekly = df.groupby(["category", "week_start"], as_index=False).agg(
        weekly_orders=("order_id", "count"), weekly_gmv=("order_amount_usd", "sum")
    )
    # Drop partial boundary weeks (the first/last calendar week of the
    # study window is only partially covered by the data, which would
    # otherwise look like a demand collapse to the model).
    study_start, study_end = df["order_date"].min(), df["order_date"].max()
    full_weeks = weekly["week_start"][
        (weekly["week_start"] >= study_start) & (weekly["week_start"] + pd.Timedelta(days=6) <= study_end)
    ].unique()
    weekly = weekly[weekly["week_start"].isin(full_weeks)].reset_index(drop=True)
    return weekly


def build_feature_dataset(raw_dir: Path) -> pd.DataFrame:
    orders, products = load_raw(raw_dir)
    weekly = to_weekly(orders)
    cat_meta = products[["category", "seasonality_profile", "mega_sale_sensitivity"]].drop_duplicates()
    weekly = weekly.merge(cat_meta, on="category")
    weekly = weekly.sort_values(["category", "week_start"]).reset_index(drop=True)

    grp = weekly.groupby("category")
    for lag in [1, 2, 3, 4, 8, 52]:
        weekly[f"lag_{lag}"] = grp[TARGET].shift(lag)
    for window in [4, 8, 12]:
        weekly[f"rollmean_{window}"] = grp[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=1).mean()
        )
        weekly[f"rollstd_{window}"] = grp[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=2).std()
        )
    weekly["diff_1"] = grp[TARGET].diff(1)
    weekly["diff_52"] = grp[TARGET].diff(52)

    weekly["week_of_year"] = weekly["week_start"].dt.isocalendar().week.astype(int)
    weekly["month"] = weekly["week_start"].dt.month
    week_index_map = {w: i for i, w in enumerate(sorted(weekly["week_start"].unique()))}
    weekly["week_index"] = weekly["week_start"].map(week_index_map)
    weekly["woy_sin"] = np.sin(2 * np.pi * weekly["week_of_year"] / 52)
    weekly["woy_cos"] = np.cos(2 * np.pi * weekly["week_of_year"] / 52)

    # Distance (in weeks) to the nearest mega-sale event - lets the
    # model anticipate a spike a week or two ahead, and recognize the
    # comedown the week after.
    from marketco.data_generation.calendar_events import build_event_calendar
    events = build_event_calendar([2023, 2024, 2025])
    event_weeks = (
        pd.to_datetime(events["center_date"]) - pd.to_timedelta(pd.to_datetime(events["center_date"]).dt.weekday, unit="D")
    )
    weeks_sorted = np.array(sorted(weekly["week_start"].unique()))

    def _weeks_to_nearest_event(w):
        diffs = (event_weeks.values - np.datetime64(w)) / np.timedelta64(1, "W")
        return diffs[np.argmin(np.abs(diffs))]

    dist_map = {w: _weeks_to_nearest_event(w) for w in weeks_sorted}
    weekly["weeks_to_mega_sale"] = weekly["week_start"].map(dist_map)

    for cat_col in ["category", "seasonality_profile"]:
        weekly[f"{cat_col}_code"] = weekly[cat_col].astype("category").cat.codes

    return weekly


FEATURE_COLUMNS = [
    "week_index", "week_of_year", "month", "woy_sin", "woy_cos", "weeks_to_mega_sale",
    "mega_sale_sensitivity", "category_code", "seasonality_profile_code",
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_8", "lag_52",
    "rollmean_4", "rollmean_8", "rollmean_12",
    "rollstd_4", "rollstd_8", "rollstd_12",
    "diff_1", "diff_52",
]
