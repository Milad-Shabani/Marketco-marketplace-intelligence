import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from marketco.models import evaluate
from marketco.planning.crm_funnel import compute_funnel_summary, win_rate_by_source
from marketco.planning.ops_metrics import warehouse_performance, seller_scorecard, case_sla_summary


def test_wape_zero_for_perfect_forecast():
    y = np.array([10.0, 20.0, 30.0])
    assert evaluate.wape(y, y) == 0


def test_wape_known_value():
    y_true = np.array([100.0, 100.0])
    y_pred = np.array([90.0, 110.0])
    assert evaluate.wape(y_true, y_pred) == 10.0


def test_funnel_summary_conversion_and_win_rate():
    leads = pd.DataFrame({
        "lead_id": ["L1", "L2", "L3", "L4"],
        "status": ["Converted", "Converted", "Disqualified", "Open"],
    })
    opportunities = pd.DataFrame({
        "opportunity_id": ["O1", "O2", "O3"],
        "lead_id": ["L1", "L2", "L3"],
        "stage": ["Closed Won", "Closed Won", "Closed Lost"],
        "estimated_value_usd": [1000, 2000, 500],
    })
    summary = compute_funnel_summary(leads, opportunities)
    assert summary["leads_total"] == 4
    assert summary["leads_converted"] == 2
    assert summary["lead_conversion_rate"] == 0.5
    assert summary["win_rate"] == round(2 / 3, 4)


def test_win_rate_by_source_only_counts_closed_opportunities():
    leads = pd.DataFrame({"lead_id": ["L1", "L2"], "lead_source": ["Referral", "Referral"]})
    opps = pd.DataFrame({
        "opportunity_id": ["O1", "O2"],
        "lead_id": ["L1", "L2"],
        "stage": ["Closed Won", "Negotiation"],
    })
    result = win_rate_by_source(leads, opps)
    assert result.loc[result["lead_source"] == "Referral", "opportunities"].iloc[0] == 1


def test_warehouse_performance_on_time_rate_bounded():
    orders = pd.DataFrame({
        "order_id": ["O1", "O2", "O3"],
        "warehouse_id": ["WH-01", "WH-01", "WH-02"],
        "on_time_delivery": [True, False, True],
        "delivery_days": [2.0, 5.0, 3.0],
        "order_amount_usd": [100, 200, 150],
    })
    warehouses = pd.DataFrame({"warehouse_id": ["WH-01", "WH-02"], "warehouse_name": ["A", "B"], "region": ["N", "S"]})
    perf = warehouse_performance(orders, warehouses)
    assert perf["on_time_rate"].between(0, 1).all()


def test_seller_scorecard_sorted_by_gmv_desc():
    orders = pd.DataFrame({
        "order_id": ["O1", "O2", "O3"],
        "seller_id": ["A", "A", "B"],
        "order_amount_usd": [100, 100, 500],
        "on_time_delivery": [True, True, True],
        "is_returned": [False, False, False],
    })
    sellers = pd.DataFrame({
        "account_id": ["A", "B"], "account_name": ["SellerA", "SellerB"],
        "tier": ["Bronze", "Gold"], "account_manager": ["X", "Y"],
    })
    result = seller_scorecard(orders, sellers, top_n=5)
    assert result.iloc[0]["account_id"] == "B"


def test_case_sla_summary_compliance_between_0_and_1():
    cases = pd.DataFrame({
        "category": ["Delivery Issue", "Delivery Issue", "Return Request"],
        "case_id": ["C1", "C2", "C3"],
        "met_sla": [True, False, True],
        "resolution_hours": [10, 30, 5],
        "csat_score": [4, 2, 5],
    })
    summary = case_sla_summary(cases)
    assert summary["sla_compliance"].between(0, 1).all()
