"""
MarketCo's promotional calendar and category-level seasonal demand
curves, covering the 2-year study window 2023-01-01 -> 2024-12-31.

Four recurring mega-sale events anchor the year - each a real pattern
from large regional e-commerce calendars:

  * **Nowruz Sale** (~March 10-20): pre-Iranian-New-Year shopping rush
    - home goods, appliances, and new clothes are a strong cultural
    buying pattern ahead of Nowruz.
  * **MarketCo Summer Fest** (~July 5-10): the marketplace's own
    mid-year flagship campaign (mirrors real marketplaces' big summer
    sale events).
  * **MarketCo Friday** (the last Friday of November, +/- a few days):
    a Black-Friday-style event - by far the single biggest demand
    spike of the year, especially for electronics and digital goods.
  * **Yalda Night Sale** (~December 19-21): winter-solstice gifting
    and grocery (nuts, fruit) shopping spike.

`event_multiplier(dates)` returns a per-day, per-category uplift
factor combining all four events, scaled by each category's
`mega_sale_sensitivity`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STUDY_START = pd.Timestamp("2023-01-01")
STUDY_END = pd.Timestamp("2024-12-31")

EVENT_WINDOWS = [
    # (name, month, day, duration_days, peak_uplift)
    ("Nowruz Sale", 3, 13, 9, 0.9),
    ("MarketCo Summer Fest", 7, 7, 5, 1.1),
    ("MarketCo Friday", 11, 24, 4, 1.8),
    ("Yalda Night Sale", 12, 20, 3, 0.7),
]


def build_event_calendar(years: list[int]) -> pd.DataFrame:
    rows = []
    for year in years:
        for name, month, day, duration, peak_uplift in EVENT_WINDOWS:
            center = pd.Timestamp(year=year, month=month, day=day)
            rows.append({"event_name": name, "year": year, "center_date": center,
                         "duration_days": duration, "peak_uplift": peak_uplift})
    return pd.DataFrame(rows)


def _event_bump(dates: pd.DatetimeIndex, events: pd.DataFrame) -> np.ndarray:
    x = np.zeros(len(dates))
    for ev in events.itertuples(index=False):
        width = ev.duration_days / 2.2
        days_from_center = (dates - ev.center_date).days.to_numpy().astype(float)
        x += ev.peak_uplift * np.exp(-0.5 * (days_from_center / width) ** 2)
    return x


def event_multiplier(dates: pd.DatetimeIndex, mega_sale_sensitivity: float = 1.0) -> np.ndarray:
    years = sorted(set(dates.year.tolist()))
    events = build_event_calendar(years)
    bump = _event_bump(dates, events)
    return 1.0 + bump * mega_sale_sensitivity


def _day_angle(dates: pd.DatetimeIndex) -> np.ndarray:
    return 2 * np.pi * dates.dayofyear.to_numpy(dtype=float) / 365.25


def seasonal_factor(profile: str, dates: pd.DatetimeIndex) -> np.ndarray:
    theta = _day_angle(dates)
    if profile == "flat_growth":
        return np.ones(len(dates))
    if profile == "nowruz_bump":
        # broad bump centered on day-of-year ~72 (mid-March)
        doy = dates.dayofyear.to_numpy(dtype=float)
        return 1.0 + 0.25 * np.exp(-((doy - 74) ** 2) / (2 * 20 ** 2))
    if profile == "spring_bump":
        return 1.0 + 0.30 * np.cos(theta - np.pi / 2.2)
    if profile == "gifting_bump":
        doy = dates.dayofyear.to_numpy(dtype=float)
        return 1.0 + 0.20 * np.exp(-((doy - 355) ** 2) / (2 * 15 ** 2))
    if profile == "back_to_school":
        doy = dates.dayofyear.to_numpy(dtype=float)
        return 1.0 + 0.35 * np.exp(-((doy - 250) ** 2) / (2 * 15 ** 2))
    if profile == "yalda_bump":
        doy = dates.dayofyear.to_numpy(dtype=float)
        return 1.0 + 0.40 * np.exp(-((doy - 354) ** 2) / (2 * 8 ** 2))
    if profile == "summer_bump":
        return 1.0 + 0.30 * np.cos(theta - np.pi)
    return np.ones(len(dates))
