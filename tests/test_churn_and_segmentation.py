import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from marketco.features.churn_features import build_churn_panel, FEATURE_COLUMNS, LABEL_COLUMN
from marketco.models import churn_model as cm
from marketco.planning.rfm_segmentation import assign_segments, score_rfm_quintiles


def _toy_data(n_customers: int = 300, n_orders: int = 3000, seed: int = 1):
    rng = np.random.default_rng(seed)
    customers = pd.DataFrame({
        "customer_id": [f"CUST-{i:04d}" for i in range(n_customers)],
        "registration_date": pd.date_range("2022-01-01", periods=n_customers, freq="2D").strftime("%Y-%m-%d"),
        "region": rng.choice(["North", "South"], size=n_customers),
        "acquisition_channel": rng.choice(["Organic Search", "Paid Ads"], size=n_customers),
        "marketing_opt_in": rng.random(n_customers) < 0.5,
    })
    order_dates = pd.date_range("2023-01-01", "2024-06-30", freq="D")
    orders = pd.DataFrame({
        "order_id": [f"ORD-{i:05d}" for i in range(n_orders)],
        "order_date": rng.choice(order_dates, size=n_orders),
        "customer_id": rng.choice(customers["customer_id"], size=n_orders),
        "category": rng.choice(["Fashion & Apparel", "Mobile & Tablet"], size=n_orders),
        "order_amount_usd": rng.uniform(10, 200, size=n_orders),
        "is_returned": rng.random(n_orders) < 0.05,
        "on_time_delivery": rng.random(n_orders) < 0.9,
    })
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    cases = pd.DataFrame({
        "case_id": [], "customer_id": [], "created_date": [], "csat_score": [],
    })
    return customers, orders, cases


def test_churn_panel_has_expected_columns_and_valid_labels():
    customers, orders, cases = _toy_data()
    snapshots = [pd.Timestamp("2023-07-01"), pd.Timestamp("2023-09-01")]
    panel = build_churn_panel(orders, customers, cases, snapshots)
    assert set(FEATURE_COLUMNS).issubset(panel.columns)
    assert set(panel[LABEL_COLUMN].unique()).issubset({True, False})


def test_churn_panel_recency_is_non_negative():
    customers, orders, cases = _toy_data()
    panel = build_churn_panel(orders, customers, cases, [pd.Timestamp("2023-08-01")])
    assert (panel["recency_days"] >= 0).all()


def test_churn_model_predicts_probabilities_in_range():
    customers, orders, cases = _toy_data(n_customers=500, n_orders=6000)
    snapshots = list(pd.date_range("2023-06-01", "2023-12-01", freq="MS"))
    panel = build_churn_panel(orders, customers, cases, snapshots)
    train, test = cm.time_based_split(panel, n_test_snapshots=1)
    result = cm.train_churn_model(train)
    proba = cm.predict_proba(result, test)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_risk_tier_thresholds():
    proba = np.array([0.1, 0.45, 0.75])
    tiers = cm.risk_tier(proba)
    assert list(tiers) == ["Low Risk", "Medium Risk", "High Risk"]


def test_rfm_quintile_scores_are_1_to_5():
    df = pd.DataFrame({
        "recency_days": np.random.default_rng(0).integers(0, 180, 200),
        "frequency_180d": np.random.default_rng(1).integers(1, 20, 200),
        "monetary_180d": np.random.default_rng(2).uniform(10, 1000, 200),
    })
    scored = score_rfm_quintiles(df)
    for col in ["R_score", "F_score", "M_score"]:
        assert scored[col].between(1, 5).all()


def test_assign_segments_returns_known_labels():
    rng = np.random.default_rng(3)
    n = 200
    df = pd.DataFrame({
        "recency_days": rng.integers(0, 180, n),
        "frequency_180d": rng.integers(1, 20, n),
        "monetary_180d": rng.uniform(10, 1000, n),
        "tenure_days": rng.integers(10, 1000, n),
    })
    proba = rng.uniform(0, 1, n)
    segmented = assign_segments(df, proba)
    valid = {"Champions", "At Risk", "New", "Loyal", "Hibernating", "Others"}
    assert set(segmented["segment"].unique()).issubset(valid)
