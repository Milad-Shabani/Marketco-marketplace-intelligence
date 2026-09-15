"""
Product catalog: ~150 SKUs across 9 marketplace categories, each
tagged with a demand-seasonality profile and a `mega_sale_sensitivity`
multiplier - how strongly that category's order volume reacts to the
marketplace's own promotional calendar (`data_generation.calendar_events`).
Big-ticket electronics and digital goods react enormously to
promotions (the classic e-commerce "wait for the sale" behavior);
grocery barely reacts at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (category, seasonality_profile, mega_sale_sensitivity, base_daily_orders_share,
#  avg_price_usd, avg_margin_pct)
_CATEGORIES = [
    ("Mobile & Tablet", "flat_growth", 3.2, 0.16, 340, 9),
    ("Home Appliances", "nowruz_bump", 2.6, 0.12, 260, 14),
    ("Fashion & Apparel", "spring_bump", 2.0, 0.17, 45, 32),
    ("Beauty & Health", "gifting_bump", 1.6, 0.13, 28, 38),
    ("Books & Media", "back_to_school", 1.1, 0.06, 12, 22),
    ("Digital Goods", "flat_growth", 3.6, 0.09, 18, 55),
    ("Grocery & Gourmet", "yalda_bump", 1.2, 0.11, 22, 18),
    ("Home & Kitchen", "nowruz_bump", 2.1, 0.10, 55, 26),
    ("Sports & Outdoor", "summer_bump", 1.7, 0.06, 65, 24),
]
_CAT_COLUMNS = [
    "category", "seasonality_profile", "mega_sale_sensitivity",
    "base_daily_orders_share", "avg_price_usd", "avg_margin_pct",
]

_PRODUCTS_PER_CATEGORY = 17  # ~150 total SKUs


def _product_name(category: str, i: int) -> str:
    return f"{category.split(' ')[0]} Item {i:03d}"


def products_dataframe(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    categories = pd.DataFrame(_CATEGORIES, columns=_CAT_COLUMNS)

    rows = []
    pid = 0
    for cat in categories.itertuples(index=False):
        for i in range(1, _PRODUCTS_PER_CATEGORY + 1):
            pid += 1
            price = max(round(cat.avg_price_usd * rng.uniform(0.4, 2.2), 2), 2.0)
            rows.append({
                "product_id": f"PRD-{pid:04d}",
                "product_name": _product_name(cat.category, i),
                "category": cat.category,
                "seasonality_profile": cat.seasonality_profile,
                "mega_sale_sensitivity": cat.mega_sale_sensitivity,
                "price_usd": price,
                "margin_pct": round(cat.avg_margin_pct * rng.uniform(0.7, 1.3), 1),
            })
    return pd.DataFrame(rows)


def categories_dataframe() -> pd.DataFrame:
    return pd.DataFrame(_CATEGORIES, columns=_CAT_COLUMNS)
