# Data Dictionary

## Provenance summary

**Everything in this repository is synthetically generated** for a
data-engineering / data-science portfolio project. "MarketCo", its
sellers, warehouses, customers, and every CRM/financial figure are
fictional. The scenario is conceptually modeled on large regional
multi-seller e-commerce marketplaces (of which Digikala is a
well-known example) and on a Microsoft Dynamics 365-style CRM data
model, but no real company's sales, customer, or CRM data is used or
implied.

## Entity-relationship overview

```
categories (9) ──< products (153)
warehouses (5)           accounts / sellers (260) ──< leads (754) ──< opportunities (490)
     |                          |                                          |
     +──────< orders (578,767) >+                                          |
                    |                                                      |
     contacts (36,000) ─+                                          activities (102,334)
                    |
                    +──< cases (65,716) ──< activities
```

## `categories.csv` (9 rows) / `products.csv` (153 rows)

9 marketplace categories (Mobile & Tablet, Home Appliances, Fashion &
Apparel, Beauty & Health, Books & Media, Digital Goods, Grocery &
Gourmet, Home & Kitchen, Sports & Outdoor), each with a
`seasonality_profile` and a `mega_sale_sensitivity` multiplier (how
strongly that category reacts to the promotional calendar - Mobile &
Tablet and Digital Goods react far more than Grocery).

## `warehouses.csv` (5 rows) / `accounts.csv` (260 rows)

`accounts.csv` is the Dynamics 365 **Account** entity, used here for
seller/vendor relationship management: `tier` (Bronze/Silver/Gold/
Platinum), `account_manager`, `commission_rate`, and
`fulfillment_reliability` (used by the orders generator to drive
realistic on-time delivery variance).

## `contacts.csv` (36,000 rows)

The Dynamics 365 **Contact** entity - individual marketplace
customers, with `registration_date`, `region`, `acquisition_channel`,
and `marketing_opt_in`.

## `orders.parquet` (578,767 rows) - the core fact table

One row per order (order = one product line, quantity 1-3, for
simplicity - see `docs/methodology.md`).

| Column | Description |
|---|---|
| `order_date` | ISO date, 2023-01-01 -> 2024-12-31 |
| `customer_id` / `product_id` / `category` / `seller_id` / `warehouse_id` | Foreign keys |
| `order_amount_usd` | `price x quantity` |
| `payment_method` | Online Payment / Cash on Delivery / Wallet Credit / Installment Plan |
| `delivery_days` / `on_time_delivery` | Realized delivery performance vs. a 3-4 day SLA |
| `is_returned` | Category-dependent return probability (Fashion highest at 13%) |

A 5,000-row sample (`orders_sample.csv`) is included for quick
inspection without a Parquet reader.

## `leads.csv` (754 rows) / `opportunities.csv` (490 rows)

Dynamics 365 **Lead** and **Opportunity** entities modeling seller
acquisition: every onboarded seller traces back to a Won Lead ->
Opportunity pair with internally consistent dates (lead created
before the opportunity, which closes exactly on the seller's
onboarding date). Also includes lost leads/opportunities (funnel
drop-off) and **Account Expansion** opportunities against existing
top-tier sellers.

## `cases.csv` (65,716 rows)

The Dynamics 365 **Case** entity - customer support tickets. Most
cases are generated from a genuine order-level trigger (late delivery,
return, product defect, or a payment-method risk factor), so case
volume is internally consistent with operational performance rather
than sampled independently.

| Column | Description |
|---|---|
| `category` | Delivery Issue / Return Request / Product Defect / Payment Issue / General Inquiry |
| `priority` | Low / Medium / High / Urgent, each with its own SLA |
| `met_sla` / `resolution_hours` | Whether the case was resolved within its SLA |
| `csat_score` | 1-5, higher when the SLA was met |

## `activities.parquet` (102,334 rows)

The Dynamics 365 **Activity** entity (Phone Call / Email / Task /
Meeting) logged against Leads, Opportunities, or Cases - volume is
derived from those tables (a handful of touches per lead/opportunity,
1-2 per case), not an arbitrary log.

## Derived modeling & report outputs

| File | Description |
|---|---|
| `data/processed/weekly_order_features.parquet` | Weekly (category) order-volume series with calendar/lag/rolling and mega-sale-distance features |
| `data/processed/churn_panel.parquet` | Multi-snapshot RFM + CRM engagement panel used to train the churn classifier |
| `reports/customer_segments.csv` | Latest-snapshot RFM x churn-risk segment for every active customer |
| `reports/order_model_performance.csv` / `reports/churn_model_performance.csv` | Held-out accuracy metrics for both models |
| `MarketCo_Ops_CRM_Report.xlsx` | 8-sheet planner workbook |
| `marketco_dashboard.html` | Standalone interactive dashboard (indigo/violet/teal theme) |
