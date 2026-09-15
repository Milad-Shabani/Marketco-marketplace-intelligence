"""
Customer support tickets, modeled as the Dynamics 365 **Case** entity.
Most cases are triggered by a genuine order-level problem already
present in the orders fact table (a late delivery or a return), so
case volume is internally consistent with operational performance
rather than sampled independently - a spike in late deliveries during
a mega-sale event shows up as a matching spike in delivery-related
cases a few days later, exactly as it would in a real support queue.
A smaller share of cases are general inquiries unrelated to any
specific order (account questions, pre-sale questions, etc.).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CASE_PRIORITIES = ["Low", "Medium", "High", "Urgent"]


def generate_cases(orders: pd.DataFrame, customers: pd.DataFrame, seed: int = 61) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    order_dates = pd.to_datetime(orders["order_date"])

    rows = []
    case_counter = 0

    late = orders[~orders["on_time_delivery"]]
    late_case_mask = rng.random(len(late)) < 0.35
    late_cases = late[late_case_mask]
    lag = rng.integers(1, 5, size=len(late_cases))
    created = pd.to_datetime(late_cases["order_date"]).to_numpy() + pd.to_timedelta(lag, unit="D")
    for i, (_, row) in enumerate(late_cases.iterrows()):
        case_counter += 1
        rows.append(_case_row(case_counter, row["customer_id"], row["order_id"], "Delivery Issue",
                               pd.Timestamp(created[i]), rng, priority_bias=0.15))

    returned = orders[orders["is_returned"]]
    lag = rng.integers(0, 3, size=len(returned))
    created = pd.to_datetime(returned["order_date"]).to_numpy() + pd.to_timedelta(lag, unit="D")
    for i, (_, row) in enumerate(returned.iterrows()):
        case_counter += 1
        rows.append(_case_row(case_counter, row["customer_id"], row["order_id"], "Return Request",
                               pd.Timestamp(created[i]), rng, priority_bias=0.05))

    defect_mask = rng.random(len(orders)) < 0.012
    defect_orders = orders[defect_mask]
    lag = rng.integers(1, 10, size=len(defect_orders))
    created = pd.to_datetime(defect_orders["order_date"]).to_numpy() + pd.to_timedelta(lag, unit="D")
    for i, (_, row) in enumerate(defect_orders.iterrows()):
        case_counter += 1
        rows.append(_case_row(case_counter, row["customer_id"], row["order_id"], "Product Defect",
                               pd.Timestamp(created[i]), rng, priority_bias=0.20))

    pay_mask = orders["payment_method"].isin(["Installment Plan", "Cash on Delivery"]) & (rng.random(len(orders)) < 0.02)
    pay_orders = orders[pay_mask]
    lag = rng.integers(0, 4, size=len(pay_orders))
    created = pd.to_datetime(pay_orders["order_date"]).to_numpy() + pd.to_timedelta(lag, unit="D")
    for i, (_, row) in enumerate(pay_orders.iterrows()):
        case_counter += 1
        rows.append(_case_row(case_counter, row["customer_id"], row["order_id"], "Payment Issue",
                               pd.Timestamp(created[i]), rng, priority_bias=0.10))

    n_general = int(len(orders) * 0.015)
    gen_customers = rng.choice(customers["customer_id"].to_numpy(), size=n_general)
    gen_dates = order_dates.min() + pd.to_timedelta(
        rng.integers(0, (order_dates.max() - order_dates.min()).days, size=n_general), unit="D"
    )
    for i in range(n_general):
        case_counter += 1
        rows.append(_case_row(case_counter, gen_customers[i], None, "General Inquiry",
                               pd.Timestamp(gen_dates[i]), rng, priority_bias=0.02))

    cases = pd.DataFrame(rows)
    return cases.sort_values("created_date").reset_index(drop=True)


def _case_row(counter: int, customer_id: str, order_id, category: str, created: pd.Timestamp,
              rng: np.random.Generator, priority_bias: float) -> dict:
    priority_probs = np.array([0.45, 0.35, 0.15, 0.05]) + np.array([-1, -0.3, 0.6, 0.7]) * priority_bias
    priority_probs = np.clip(priority_probs, 0.01, None)
    priority_probs = priority_probs / priority_probs.sum()
    priority = rng.choice(CASE_PRIORITIES, p=priority_probs)

    sla_hours = {"Low": 72, "Medium": 48, "High": 24, "Urgent": 8}[priority]
    resolution_hours = max(rng.gamma(shape=2.0, scale=sla_hours / 2.5), 0.5)
    is_resolved = rng.random() < 0.94
    resolved_at = created + pd.Timedelta(hours=resolution_hours) if is_resolved else pd.NaT

    csat = None
    if is_resolved:
        met_sla = resolution_hours <= sla_hours
        base_csat = 4.3 if met_sla else 3.1
        csat = int(np.clip(round(rng.normal(base_csat, 0.9)), 1, 5))

    return {
        "case_id": f"CASE-{counter:06d}",
        "customer_id": customer_id,
        "order_id": order_id,
        "category": category,
        "priority": priority,
        "created_date": created.strftime("%Y-%m-%d"),
        "resolved_date": resolved_at.strftime("%Y-%m-%d") if is_resolved else None,
        "resolution_hours": round(resolution_hours, 1) if is_resolved else None,
        "sla_hours": sla_hours,
        "met_sla": bool(is_resolved and resolution_hours <= sla_hours),
        "status": "Resolved" if is_resolved else rng.choice(["Open", "Escalated"], p=[0.7, 0.3]),
        "csat_score": csat,
    }
