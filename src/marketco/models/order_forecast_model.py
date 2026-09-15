"""
A single global LightGBM model trained across all 9 category series
together (the same "one model, not N per-series models" architecture
used for the pharma demand-planning sibling project), with P50/P95
quantile objectives so the P95 forecast can double as a
capacity-planning buffer (warehouse staffing, courier capacity) around
mega-sale events - exactly the moments capacity planning matters most.
"""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from marketco.features.build_features import FEATURE_COLUMNS, TARGET

CATEGORICAL_FEATURES = ["category_code", "seasonality_profile_code"]

BASE_PARAMS = dict(
    n_estimators=450,
    num_leaves=47,
    learning_rate=0.045,
    min_child_samples=10,
    subsample=0.85,
    subsample_freq=1,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    random_state=42,
    verbosity=-1,
)


@dataclass
class QuantileModels:
    p50: lgb.LGBMRegressor
    p95: lgb.LGBMRegressor
    feature_importance_p50: pd.Series


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    required = ["lag_1", "lag_2", "lag_3", "lag_4", "rollmean_4"]
    return df.dropna(subset=required)


def train_quantile_models(train_df: pd.DataFrame) -> QuantileModels:
    clean = _prep(train_df)
    X = clean[FEATURE_COLUMNS]
    y = clean[TARGET]

    p50_model = lgb.LGBMRegressor(objective="quantile", alpha=0.5, **BASE_PARAMS)
    p50_model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)

    p95_model = lgb.LGBMRegressor(objective="quantile", alpha=0.95, **BASE_PARAMS)
    p95_model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)

    importance = pd.Series(p50_model.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    return QuantileModels(p50=p50_model, p95=p95_model, feature_importance_p50=importance)


def predict(models: QuantileModels, feature_df: pd.DataFrame) -> pd.DataFrame:
    X = feature_df[FEATURE_COLUMNS]
    p50 = np.clip(models.p50.predict(X), 0, None)
    p95 = np.clip(models.p95.predict(X), 0, None)
    p95 = np.maximum(p95, p50)
    return pd.DataFrame({"forecast_p50": p50, "forecast_p95": p95}, index=feature_df.index)


def recursive_forecast(
    models: QuantileModels,
    weekly_history: pd.DataFrame,
    n_future_weeks: int,
    static_lookup: pd.DataFrame,
) -> pd.DataFrame:
    from marketco.features.build_features import build_feature_dataset  # noqa: F401 (kept for API symmetry)

    working = weekly_history.copy()
    last_week = working["week_start"].max()
    future_weeks = [last_week + pd.Timedelta(weeks=i) for i in range(1, n_future_weeks + 1)]

    categories = working[["category"]].drop_duplicates()
    all_new_rows = []

    for week in future_weeks:
        new_rows = categories.copy()
        new_rows["week_start"] = week
        new_rows[TARGET] = np.nan
        working = pd.concat([working, new_rows], ignore_index=True)
        working = working.merge(static_lookup, on="category", how="left", suffixes=("", "_dup"))
        working = working[[c for c in working.columns if not c.endswith("_dup")]]

        featured = _recompute_features(working)
        this_week_mask = featured["week_start"] == week
        preds = predict(models, featured.loc[this_week_mask])
        working.loc[this_week_mask, TARGET] = preds["forecast_p50"].to_numpy()

        snapshot = featured.loc[this_week_mask, ["category", "week_start"]].copy()
        snapshot["forecast_p50"] = preds["forecast_p50"].to_numpy()
        snapshot["forecast_p95"] = preds["forecast_p95"].to_numpy()
        all_new_rows.append(snapshot)

    return pd.concat(all_new_rows, ignore_index=True)


def _recompute_features(working: pd.DataFrame) -> pd.DataFrame:
    from marketco.data_generation.calendar_events import build_event_calendar

    df = working.sort_values(["category", "week_start"]).reset_index(drop=True)
    grp = df.groupby("category")
    for lag in [1, 2, 3, 4, 8, 52]:
        df[f"lag_{lag}"] = grp[TARGET].shift(lag)
    for window in [4, 8, 12]:
        df[f"rollmean_{window}"] = grp[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=1).mean()
        )
        df[f"rollstd_{window}"] = grp[TARGET].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=2).std()
        )
    df["diff_1"] = grp[TARGET].diff(1)
    df["diff_52"] = grp[TARGET].diff(52)

    df["week_of_year"] = pd.to_datetime(df["week_start"]).dt.isocalendar().week.astype(int)
    df["month"] = pd.to_datetime(df["week_start"]).dt.month
    week_index_map = {w: i for i, w in enumerate(sorted(df["week_start"].unique()))}
    df["week_index"] = df["week_start"].map(week_index_map)
    df["woy_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["woy_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)

    events = build_event_calendar([2023, 2024, 2025])
    event_weeks = (
        pd.to_datetime(events["center_date"]) - pd.to_timedelta(pd.to_datetime(events["center_date"]).dt.weekday, unit="D")
    )
    weeks_sorted = np.array(sorted(df["week_start"].unique()))

    def _weeks_to_nearest_event(w):
        diffs = (event_weeks.values - np.datetime64(w)) / np.timedelta64(1, "W")
        return diffs[np.argmin(np.abs(diffs))]

    dist_map = {w: _weeks_to_nearest_event(w) for w in weeks_sorted}
    df["weeks_to_mega_sale"] = df["week_start"].map(dist_map)

    for cat_col in ["category", "seasonality_profile"]:
        df[f"{cat_col}_code"] = df[cat_col].astype("category").cat.codes
    return df
