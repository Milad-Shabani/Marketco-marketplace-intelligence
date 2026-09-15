"""
Generates the full synthetic raw dataset for MarketCo: product
catalog, network topology, customers, the large orders fact table,
and the full Dynamics 365-style CRM layer (Leads, Opportunities,
Cases, Activities).

Usage:
    python scripts/generate_sample_data.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from marketco.data_generation.catalog import products_dataframe, categories_dataframe  # noqa: E402
from marketco.data_generation.network import warehouses_dataframe, sellers_dataframe  # noqa: E402
from marketco.data_generation.customers import customers_dataframe  # noqa: E402
from marketco.data_generation.orders import generate_orders  # noqa: E402
from marketco.data_generation.crm_pipeline import build_seller_acquisition_pipeline  # noqa: E402
from marketco.data_generation.cases import generate_cases  # noqa: E402
from marketco.data_generation.activities import generate_activities  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("Generating product catalog...")
    products = products_dataframe()
    categories_dataframe().to_csv(RAW_DIR / "categories.csv", index=False)
    products.to_csv(RAW_DIR / "products.csv", index=False)
    print(f"  -> {len(products)} SKUs across {products['category'].nunique()} categories")

    print("Generating network (warehouses + seller accounts)...")
    warehouses = warehouses_dataframe()
    sellers = sellers_dataframe()
    warehouses.to_csv(RAW_DIR / "warehouses.csv", index=False)
    sellers.to_csv(RAW_DIR / "accounts.csv", index=False)
    print(f"  -> {len(warehouses)} warehouses, {len(sellers)} seller accounts")

    print("Generating customer base (Contacts)...")
    customers = customers_dataframe()
    customers.to_csv(RAW_DIR / "contacts.csv", index=False)
    print(f"  -> {len(customers):,} customers")

    print("Generating orders fact table (this is the large one)...")
    orders = generate_orders(products, customers, sellers, warehouses)
    orders.to_parquet(RAW_DIR / "orders.parquet", index=False)
    orders.head(5000).to_csv(RAW_DIR / "orders_sample.csv", index=False)
    print(f"  -> {len(orders):,} orders, "
          f"GMV ${orders['order_amount_usd'].sum()/1e6:,.1f}M, "
          f"on-time delivery {orders['on_time_delivery'].mean():.1%}")

    print("Building seller acquisition CRM pipeline (Leads + Opportunities)...")
    leads, opportunities = build_seller_acquisition_pipeline(sellers)
    leads.to_csv(RAW_DIR / "leads.csv", index=False)
    opportunities.to_csv(RAW_DIR / "opportunities.csv", index=False)
    conv_rate = (leads["status"] == "Converted").mean()
    print(f"  -> {len(leads)} leads ({conv_rate:.1%} conversion), {len(opportunities)} opportunities")

    print("Generating support Cases...")
    cases = generate_cases(orders, customers)
    cases.to_csv(RAW_DIR / "cases.csv", index=False)
    print(f"  -> {len(cases):,} cases, SLA compliance {cases['met_sla'].mean():.1%}")

    print("Generating CRM Activities log...")
    activities = generate_activities(leads, opportunities, cases)
    activities.to_parquet(RAW_DIR / "activities.parquet", index=False)
    activities.head(5000).to_csv(RAW_DIR / "activities_sample.csv", index=False)
    print(f"  -> {len(activities):,} activities")

    print(f"\nAll raw files written to: {RAW_DIR}")
    print(f"Total generation time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
