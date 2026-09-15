import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from marketco.data_generation.network import sellers_dataframe
from marketco.data_generation.crm_pipeline import build_seller_acquisition_pipeline
from marketco.data_generation.catalog import products_dataframe
from marketco.data_generation.network import warehouses_dataframe
from marketco.data_generation.customers import customers_dataframe
from marketco.data_generation.orders import generate_orders
from marketco.data_generation.cases import generate_cases
from marketco.data_generation.activities import generate_activities


def test_every_onboarded_seller_traces_back_to_a_won_opportunity():
    sellers = sellers_dataframe(n_sellers=80)
    leads, opps = build_seller_acquisition_pipeline(sellers, seed=1)
    won = opps[opps["stage"] == "Closed Won"]
    assert set(sellers["account_id"]).issubset(set(won["account_id"].dropna()))


def test_won_opportunity_closes_before_or_on_onboarding_date():
    sellers = sellers_dataframe(n_sellers=80)
    leads, opps = build_seller_acquisition_pipeline(sellers, seed=1)
    won = opps[(opps["stage"] == "Closed Won") & (opps["opportunity_type"] == "New Seller Onboarding")].merge(
        sellers[["account_id", "onboarding_date"]], on="account_id"
    )
    assert (pd.to_datetime(won["close_date"]) == pd.to_datetime(won["onboarding_date"])).all()


def test_lead_created_before_its_opportunity():
    sellers = sellers_dataframe(n_sellers=80)
    leads, opps = build_seller_acquisition_pipeline(sellers, seed=1)
    merged = opps.dropna(subset=["lead_id"]).merge(leads, on="lead_id", suffixes=("_opp", "_lead"))
    assert (pd.to_datetime(merged["created_date_opp"]) >= pd.to_datetime(merged["created_date_lead"])).all()


def test_cases_only_reference_valid_orders_or_none():
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe(n_sellers=50)
    customers = customers_dataframe(n_customers=3000)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=80, seed=5)
    cases = generate_cases(orders, customers, seed=5)

    order_backed = cases.dropna(subset=["order_id"])
    assert set(order_backed["order_id"]).issubset(set(orders["order_id"]))


def test_case_resolution_after_creation():
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe(n_sellers=50)
    customers = customers_dataframe(n_customers=3000)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=80, seed=6)
    cases = generate_cases(orders, customers, seed=6)
    resolved = cases.dropna(subset=["resolved_date"])
    assert (pd.to_datetime(resolved["resolved_date"]) >= pd.to_datetime(resolved["created_date"])).all()


def test_activities_reference_valid_leads_opportunities_cases():
    sellers = sellers_dataframe(n_sellers=30)
    leads, opps = build_seller_acquisition_pipeline(sellers, seed=2)
    products = products_dataframe()
    warehouses = warehouses_dataframe()
    customers = customers_dataframe(n_customers=1500)
    orders = generate_orders(products, customers, sellers, warehouses, base_total_daily_orders=40, seed=7)
    cases = generate_cases(orders, customers, seed=7)
    activities = generate_activities(leads, opps, cases, seed=8)

    lead_acts = activities[activities["regarding_type"] == "Lead"]
    assert set(lead_acts["regarding_id"]).issubset(set(leads["lead_id"]))
    opp_acts = activities[activities["regarding_type"] == "Opportunity"]
    assert set(opp_acts["regarding_id"]).issubset(set(opps["opportunity_id"]))
    case_acts = activities[activities["regarding_type"] == "Case"]
    assert set(case_acts["regarding_id"]).issubset(set(cases["case_id"]))
