"""
Generates the marketplace's core orders fact table (~350-400K rows)
over the 2-year study window, driven by the category seasonal curves
and promotional calendar in `calendar_events.py`.

Generation strategy (kept fully vectorized so ~400K rows generate in
a couple of seconds rather than minutes):

1. Build a (day x category) grid of expected daily order volume, and
   flatten it into a single probability vector. One `np.random.choice`
   call over that flattened grid assigns every order's date AND
   category simultaneously - proportional to the true seasonal/event
   demand curve - without looping per day.
2. Within each category, product is sampled uniformly.
3. Customers are sampled per unique order-day (731 iterations, not
   400K), restricted to customers already registered by that date and
   weighted by a per-customer purchase-propensity score (a lognormal
   draw - the standard way to get a realistic "some customers buy a
   lot, most buy a little" repeat-purchase distribution) - this is
   what makes the later RFM/churn features meaningful rather than
   uniform noise.
4. Seller, warehouse, delivery, payment, and return fields are drawn
   with realistic conditional probabilities (seller tier -> order
   share; seller reliability + warehouse region -> on-time delivery;
   category -> return rate).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from marketco.data_generation.calendar_events import (
    STUDY_START, STUDY_END, seasonal_factor, event_multiplier,
)

PAYMENT_METHODS = ["Online Payment", "Cash on Delivery", "Wallet Credit", "Installment Plan"]
PAYMENT_PROBS = [0.52, 0.20, 0.16, 0.12]

_RETURN_RATE_BY_CATEGORY = {
    "Fashion & Apparel": 0.13, "Beauty & Health": 0.05, "Mobile & Tablet": 0.05,
    "Home Appliances": 0.04, "Home & Kitchen": 0.04, "Sports & Outdoor": 0.06,
    "Books & Media": 0.02, "Digital Goods": 0.01, "Grocery & Gourmet": 0.015,
}

_TIER_ORDER_WEIGHT = {"Bronze": 1.0, "Silver": 1.8, "Gold": 3.2, "Platinum": 5.5}
_WAREHOUSE_BASE_DELIVERY_DAYS = {"WH-01": 1.6, "WH-02": 2.4, "WH-03": 2.6, "WH-04": 2.8, "WH-05": 2.9}


def _build_day_category_grid(products: pd.DataFrame, base_total_daily_orders: float, annual_growth: float):
    categories = products[["category", "seasonality_profile", "mega_sale_sensitivity"]].drop_duplicates()
    dates = pd.date_range(STUDY_START, STUDY_END, freq="D")
    n_days = len(dates)
    day_index = np.arange(n_days)

    category_share = (products.groupby("category").size() / len(products)).to_dict()

    weekday_factor = np.where(pd.DatetimeIndex(dates).weekday.isin([3, 4]), 1.15, 1.0)
    trend = 1.0 + annual_growth * (day_index / 365.25)

    grid = np.zeros((n_days, len(categories)))
    cat_names = categories["category"].tolist()
    for j, cat in enumerate(categories.itertuples(index=False)):
        seasonal = seasonal_factor(cat.seasonality_profile, pd.DatetimeIndex(dates))
        events = event_multiplier(pd.DatetimeIndex(dates), cat.mega_sale_sensitivity)
        share = category_share.get(cat.category, 1 / len(categories))
        grid[:, j] = base_total_daily_orders * share * seasonal * events * trend * weekday_factor

    return dates, cat_names, grid


def generate_orders(
    products: pd.DataFrame,
    customers: pd.DataFrame,
    sellers: pd.DataFrame,
    warehouses: pd.DataFrame,
    base_total_daily_orders: float = 480,
    annual_growth: float = 0.35,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    dates, cat_names, grid = _build_day_category_grid(products, base_total_daily_orders, annual_growth)
    n_days, n_cats = grid.shape
    flat_probs = grid.flatten()
    flat_probs = flat_probs / flat_probs.sum()

    n_orders = int(grid.sum())
    flat_idx = rng.choice(len(flat_probs), size=n_orders, p=flat_probs)
    day_idx = flat_idx // n_cats
    cat_idx = flat_idx % n_cats
    order_dates = dates[day_idx]
    order_categories = np.array(cat_names)[cat_idx]

    order_df = pd.DataFrame({"order_date": order_dates, "category": order_categories})
    order_df = order_df.sort_values("order_date").reset_index(drop=True)

    products_by_cat = {cat: g["product_id"].to_numpy() for cat, g in products.groupby("category")}
    prices_by_cat = {cat: g.set_index("product_id")["price_usd"] for cat, g in products.groupby("category")}
    product_ids = np.empty(len(order_df), dtype=object)
    prices = np.empty(len(order_df), dtype=float)
    for cat, group_idx in order_df.groupby("category").groups.items():
        idx = group_idx.to_numpy()
        choices = rng.choice(products_by_cat[cat], size=len(idx))
        product_ids[idx] = choices
        prices[idx] = prices_by_cat[cat].loc[choices].to_numpy()
    order_df["product_id"] = product_ids
    quantities = rng.choice([1, 1, 1, 2, 2, 3], size=len(order_df))
    order_df["quantity"] = quantities
    order_df["order_amount_usd"] = np.round(prices * quantities, 2)

    customers_sorted = customers.sort_values("registration_date").reset_index(drop=True)
    reg_dates = pd.to_datetime(customers_sorted["registration_date"]).to_numpy()
    propensity = rng.lognormal(mean=0.0, sigma=1.1, size=len(customers_sorted))
    cust_ids_sorted = customers_sorted["customer_id"].to_numpy()

    assigned_customer = np.empty(len(order_df), dtype=object)
    for day_val, group_idx in order_df.groupby("order_date").groups.items():
        idx = group_idx.to_numpy()
        eligible_n = int(np.searchsorted(reg_dates, np.datetime64(day_val), side="right"))
        eligible_n = max(eligible_n, 1)
        w = propensity[:eligible_n]
        w = w / w.sum()
        picks = rng.choice(eligible_n, size=len(idx), p=w)
        assigned_customer[idx] = cust_ids_sorted[picks]
    order_df["customer_id"] = assigned_customer

    seller_weights = sellers["tier"].map(_TIER_ORDER_WEIGHT).to_numpy()
    seller_weights = seller_weights / seller_weights.sum()
    order_df["seller_id"] = rng.choice(sellers["account_id"].to_numpy(), size=len(order_df), p=seller_weights)

    cust_region = customers.set_index("customer_id")["region"]
    order_df["customer_region"] = order_df["customer_id"].map(cust_region)
    region_to_wh = warehouses.set_index("region")["warehouse_id"].to_dict()
    home_wh = order_df["customer_region"].map(region_to_wh)
    use_central = rng.random(len(order_df)) < 0.10
    order_df["warehouse_id"] = np.where(use_central, "WH-01", home_wh)

    seller_reliability = sellers.set_index("account_id")["fulfillment_reliability"]
    reliability = order_df["seller_id"].map(seller_reliability).to_numpy()
    base_days = order_df["warehouse_id"].map(_WAREHOUSE_BASE_DELIVERY_DAYS).to_numpy()
    noise = rng.gamma(shape=1.6, scale=0.35, size=len(order_df))
    unreliable_penalty = (1 - reliability) * rng.uniform(1.5, 4.5, size=len(order_df))
    delivery_days = base_days + noise + unreliable_penalty
    order_df["delivery_days"] = np.round(delivery_days, 1)
    sla_days = np.where(order_df["warehouse_id"] == "WH-01", 3, 4)
    order_df["on_time_delivery"] = order_df["delivery_days"] <= sla_days

    order_df["payment_method"] = rng.choice(PAYMENT_METHODS, size=len(order_df), p=PAYMENT_PROBS)

    return_prob = order_df["category"].map(_RETURN_RATE_BY_CATEGORY).to_numpy()
    order_df["is_returned"] = rng.random(len(order_df)) < return_prob

    order_df.insert(0, "order_id", [f"ORD-{i+1:07d}" for i in range(len(order_df))])
    order_df["order_date"] = pd.to_datetime(order_df["order_date"]).dt.strftime("%Y-%m-%d")

    return order_df[[
        "order_id", "order_date", "customer_id", "customer_region", "product_id", "category",
        "seller_id", "warehouse_id", "quantity", "order_amount_usd", "payment_method",
        "delivery_days", "on_time_delivery", "is_returned",
    ]]
