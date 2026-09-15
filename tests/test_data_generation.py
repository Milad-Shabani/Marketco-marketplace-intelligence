import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from marketco.data_generation.catalog import products_dataframe
from marketco.data_generation.network import warehouses_dataframe, sellers_dataframe
from marketco.data_generation.customers import customers_dataframe
from marketco.data_generation.orders import generate_orders


def test_product_ids_unique_and_categories_present():
    df = products_dataframe()
    assert df["product_id"].is_unique
    assert df["category"].nunique() == 9


def test_sellers_tiers_valid_and_reliability_bounded():
    sellers = sellers_dataframe()
    assert set(sellers["tier"]).issubset({"Bronze", "Silver", "Gold", "Platinum"})
    assert sellers["fulfillment_reliability"].between(0, 1).all()


def test_customers_registration_dates_are_ordered_and_unique_ids():
    customers = customers_dataframe(n_customers=1000)
    assert customers["customer_id"].is_unique
    dates = pd.to_datetime(customers["registration_date"])
    assert dates.min() >= pd.Timestamp("2020-01-01")
    assert dates.max() <= pd.Timestamp("2024-12-15")


def test_orders_reference_valid_entities():
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe(n_sellers=50)
    customers = customers_dataframe(n_customers=2000)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=50, seed=1)

    assert set(orders["product_id"]).issubset(set(products["product_id"]))
    assert set(orders["seller_id"]).issubset(set(sellers["account_id"]))
    assert set(orders["warehouse_id"]).issubset(set(warehouses["warehouse_id"]))
    assert set(orders["customer_id"]).issubset(set(customers["customer_id"]))


def test_orders_do_not_predate_customer_registration():
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe(n_sellers=50)
    customers = customers_dataframe(n_customers=2000)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=50, seed=2)

    merged = orders.merge(customers[["customer_id", "registration_date"]], on="customer_id")
    assert (pd.to_datetime(merged["order_date"]) >= pd.to_datetime(merged["registration_date"])).all()


def test_mega_sale_week_has_much_higher_volume_than_baseline():
    """Sanity check that the promotional calendar actually produces a
    visible demand spike (MarketCo Friday, late November)."""
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe(n_sellers=100)
    customers = customers_dataframe(n_customers=8000)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=300, seed=3)

    daily = orders.groupby("order_date").size()
    daily.index = pd.to_datetime(daily.index)
    baseline = daily[(daily.index >= "2023-05-01") & (daily.index <= "2023-06-01")].mean()
    peak = daily[(daily.index >= "2023-11-20") & (daily.index <= "2023-11-28")].max()
    assert peak > baseline * 2
