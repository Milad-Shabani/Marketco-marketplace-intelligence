"""
End-to-end MarketCo pipeline:

1. Load raw synthetic data (run generate_sample_data.py first).
2. Build weekly order-volume features; backtest and forecast with the
   global LightGBM quantile model.
3. Build the churn panel; train and evaluate the LightGBM churn
   classifier with a time-based split.
4. Compute RFM/churn customer segmentation, CRM funnel metrics,
   seller/warehouse operations metrics, and support SLA analysis.
5. Render the Excel workbook and the HTML dashboard from the same
   computed tables.

Usage:
    python scripts/run_pipeline.py
"""
from __future__ import annotations

import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
warnings.filterwarnings("ignore")

from marketco.features.build_features import TARGET, build_feature_dataset  # noqa: E402
from marketco.features.churn_features import build_churn_panel, default_snapshot_dates, FEATURE_COLUMNS as CHURN_FEATURES  # noqa: E402
from marketco.models import evaluate, order_forecast_model as ofm, churn_model as cm  # noqa: E402
from marketco.planning.rfm_segmentation import assign_segments  # noqa: E402
from marketco.planning.crm_funnel import (  # noqa: E402
    compute_funnel_summary, compute_acquisition_funnel_stages, win_rate_by_source, pipeline_by_stage,
)
from marketco.planning.ops_metrics import (  # noqa: E402
    warehouse_performance, seller_scorecard, case_sla_summary, monthly_case_volume,
    monthly_gmv_trend, seller_tier_performance, acquisition_channel_effectiveness,
)
from marketco.reporting.excel_report import build_excel_report  # noqa: E402
from marketco.reporting.html_dashboard import build_dashboard  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
N_TEST_WEEKS = 8
N_FUTURE_WEEKS = 12


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    products = pd.read_csv(RAW_DIR / "products.csv")
    warehouses = pd.read_csv(RAW_DIR / "warehouses.csv")
    sellers = pd.read_csv(RAW_DIR / "accounts.csv")
    customers = pd.read_csv(RAW_DIR / "contacts.csv")
    orders = pd.read_parquet(RAW_DIR / "orders.parquet")
    leads = pd.read_csv(RAW_DIR / "leads.csv")
    opportunities = pd.read_csv(RAW_DIR / "opportunities.csv")
    cases = pd.read_csv(RAW_DIR / "cases.csv")

    # ------------------------------------------------------------------
    # 1. Order-volume forecast: features, backtest, future forecast
    # ------------------------------------------------------------------
    print("[1/6] Building weekly order-volume features...")
    weekly = build_feature_dataset(RAW_DIR)
    weekly.to_parquet(PROCESSED_DIR / "weekly_order_features.parquet", index=False)

    weeks = sorted(weekly["week_start"].unique())
    test_weeks = weeks[-N_TEST_WEEKS:]
    train_df = weekly[~weekly["week_start"].isin(test_weeks)]
    test_df = weekly[weekly["week_start"].isin(test_weeks)].copy()

    print(f"[2/6] Training global LightGBM quantile order-forecast model, "
          f"backtesting on the final {N_TEST_WEEKS} weeks...")
    backtest_models = ofm.train_quantile_models(train_df)
    test_preds = ofm.predict(backtest_models, test_df)
    test_df["forecast_p50"] = test_preds["forecast_p50"].to_numpy()
    test_df["forecast_p95"] = test_preds["forecast_p95"].to_numpy()

    overall_perf = evaluate.summarize(test_df[TARGET].to_numpy(), test_df["forecast_p50"].to_numpy(), "Network overall")
    coverage = float((test_df[TARGET] <= test_df["forecast_p95"]).mean() * 100)
    perf_rows = [overall_perf]
    for cat, g in test_df.groupby("category"):
        perf_rows.append(evaluate.summarize(g[TARGET].to_numpy(), g["forecast_p50"].to_numpy(), cat))
    order_model_performance = evaluate.metrics_table(perf_rows)
    order_model_performance["P95_coverage_%"] = np.nan
    order_model_performance.loc["Network overall", "P95_coverage_%"] = round(coverage, 1)
    order_model_performance.to_csv(REPORTS_DIR / "order_model_performance.csv")
    print(order_model_performance)

    full_models = ofm.train_quantile_models(weekly)
    static_lookup = weekly[["category", "seasonality_profile", "mega_sale_sensitivity"]].drop_duplicates()
    future = ofm.recursive_forecast(full_models, weekly[["category", "week_start", TARGET]], N_FUTURE_WEEKS, static_lookup)
    future.to_parquet(PROCESSED_DIR / "future_order_forecast_12w.parquet", index=False)

    # ------------------------------------------------------------------
    # 2. Churn model: panel, train/test, watchlist
    # ------------------------------------------------------------------
    print("\n[3/6] Building churn panel and training the churn classifier...")
    panel = build_churn_panel(orders, customers, cases, default_snapshot_dates())
    panel.to_parquet(PROCESSED_DIR / "churn_panel.parquet", index=False)

    train_panel, test_panel = cm.time_based_split(panel, n_test_snapshots=2)
    churn_result = cm.train_churn_model(train_panel)
    churn_metrics = cm.evaluate_churn_model(churn_result, test_panel)
    pd.DataFrame([churn_metrics]).to_csv(REPORTS_DIR / "churn_model_performance.csv", index=False)
    print(churn_metrics)

    latest_snapshot = panel["snapshot_date"].max()
    latest_panel = panel[panel["snapshot_date"] == latest_snapshot].copy()
    latest_proba = cm.predict_proba(churn_result, latest_panel)
    segmented = assign_segments(latest_panel, latest_proba)
    segmented = segmented.sort_values("churn_probability", ascending=False)
    segmented.to_csv(REPORTS_DIR / "customer_segments.csv", index=False)

    churn_watchlist = segmented[segmented["segment"] == "At Risk"].head(200)
    segment_counts = segmented["segment"].value_counts()

    # ------------------------------------------------------------------
    # 3. CRM funnel + ops metrics
    # ------------------------------------------------------------------
    print("[4/6] Computing CRM funnel and operations metrics...")
    funnel_summary = compute_funnel_summary(leads, opportunities)
    funnel_stages = compute_acquisition_funnel_stages(leads, opportunities, orders, sellers)
    win_rate_df = win_rate_by_source(leads, opportunities)
    stage_pipeline = pipeline_by_stage(opportunities)

    wh_perf = warehouse_performance(orders, warehouses)
    sellers_perf = seller_scorecard(orders, sellers)
    case_summary = case_sla_summary(cases)
    monthly_cases = monthly_case_volume(cases)
    monthly_gmv = monthly_gmv_trend(orders)
    tier_perf = seller_tier_performance(orders, sellers)
    channel_perf = acquisition_channel_effectiveness(customers, orders)

    # ------------------------------------------------------------------
    # 4. Executive summary tables
    # ------------------------------------------------------------------
    print("[5/6] Assembling executive-summary tables...")
    total_gmv = orders["order_amount_usd"].sum()
    total_orders = len(orders)
    aov = total_gmv / total_orders
    overall_on_time = orders["on_time_delivery"].mean()
    overall_churn_rate = panel.groupby("snapshot_date")["churned"].mean().mean()

    revenue_by_category = orders.groupby("category", as_index=False)["order_amount_usd"].sum().rename(
        columns={"order_amount_usd": "total_gmv"}
    ).sort_values("total_gmv", ascending=False)

    # --- trailing 90-day trend deltas (last 90 days vs the 90 days before that) ---
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    max_date = orders["order_date"].max()
    last90 = orders[orders["order_date"] > max_date - pd.Timedelta(days=90)]
    prior90 = orders[(orders["order_date"] <= max_date - pd.Timedelta(days=90)) &
                      (orders["order_date"] > max_date - pd.Timedelta(days=180))]

    def pct_change(new, old):
        return round((new - old) / old * 100, 1) if old else None

    gmv_delta = pct_change(last90["order_amount_usd"].sum(), prior90["order_amount_usd"].sum())
    ontime_delta = pct_change(last90["on_time_delivery"].mean(), prior90["on_time_delivery"].mean())

    snap_churn = panel.groupby("snapshot_date")["churned"].mean().sort_index()
    churn_delta = pct_change(snap_churn.iloc[-1], snap_churn.iloc[-2]) if len(snap_churn) >= 2 else None

    cases_dated = cases.copy()
    cases_dated["created_date"] = pd.to_datetime(cases_dated["created_date"])
    sla_last90 = cases_dated[cases_dated["created_date"] > max_date - pd.Timedelta(days=90)]["met_sla"].mean()
    sla_prior90 = cases_dated[(cases_dated["created_date"] <= max_date - pd.Timedelta(days=90)) &
                               (cases_dated["created_date"] > max_date - pd.Timedelta(days=180))]["met_sla"].mean()
    sla_delta = pct_change(sla_last90, sla_prior90)

    kpis = [
        {"label": "Network GMV (2Y)", "value": f"${total_gmv/1e6:,.1f}M",
         "sub": f"{total_orders:,} orders across 9 categories", "icon": "gmv",
         "delta_pct": gmv_delta, "good_when_up": True},
        {"label": "Average Order Value", "value": f"${aov:,.0f}",
         "sub": f"{len(sellers):,} active sellers", "icon": "aov"},
        {"label": "On-Time Delivery", "value": f"{overall_on_time:.1%}",
         "sub": "5 fulfillment centers", "icon": "truck",
         "delta_pct": ontime_delta, "good_when_up": True},
        {"label": "Forecast Accuracy (WAPE)", "value": f"{overall_perf['WAPE_%']:.1f}%",
         "sub": f"Held-out {N_TEST_WEEKS}-week backtest", "icon": "forecast"},
        {"label": "90-Day Churn Rate", "value": f"{overall_churn_rate:.1%}",
         "sub": f"Churn model AUC {churn_metrics['AUC_ROC']:.2f}", "icon": "churn",
         "delta_pct": churn_delta, "good_when_up": False},
        {"label": "CRM Win Rate", "value": f"{funnel_summary['win_rate']:.1%}",
         "sub": f"{funnel_summary['leads_total']:,} leads, {funnel_summary['lead_conversion_rate']:.1%} conversion",
         "icon": "crm"},
        {"label": "Support SLA Compliance", "value": f"{cases['met_sla'].mean():.1%}",
         "sub": f"{len(cases):,} cases handled", "icon": "support",
         "delta_pct": sla_delta, "good_when_up": True},
    ]

    exec_summary_cells = {
        "Network GMV (2Y)": f"${total_gmv/1e6:,.1f}M",
        "Average Order Value": f"${aov:,.0f}",
        "On-Time Delivery": f"{overall_on_time:.1%}",
        "Forecast WAPE": f"{overall_perf['WAPE_%']:.1f}%",
        "90-Day Churn Rate": f"{overall_churn_rate:.1%}",
        "CRM Win Rate": f"{funnel_summary['win_rate']:.1%}",
    }

    forecast_by_category_week = future.copy()
    history_network = weekly.groupby("week_start", as_index=False)[TARGET].sum()
    history_network = history_network[history_network["week_start"] >= history_network["week_start"].max() - pd.Timedelta(weeks=30)]
    future_network = future.groupby("week_start", as_index=False).agg(
        forecast_p50=("forecast_p50", "sum"), forecast_p95=("forecast_p95", "sum")
    )

    # --- auto-generated key insights ---
    top_category = revenue_by_category.iloc[0]
    worst_wh = wh_perf.sort_values("on_time_rate").iloc[0]
    best_source = win_rate_df.sort_values("win_rate", ascending=False).iloc[0]
    n_at_risk = int((segmented["segment"] == "At Risk").sum())
    at_risk_value = segmented.loc[segmented["segment"] == "At Risk", "monetary_180d"].sum()
    worst_case_cat = case_summary.sort_values("sla_compliance").iloc[0]
    peak_week = future_network.loc[future_network["forecast_p50"].idxmax()]

    insights = [
        f"<strong>{top_category['category']}</strong> is the top-grossing category at "
        f"${top_category['total_gmv']/1e6:.1f}M GMV — {top_category['total_gmv']/total_gmv:.0%} of network revenue.",
        f"<strong>{worst_wh['warehouse_name']}</strong> has the network's lowest on-time delivery rate "
        f"({worst_wh['on_time_rate']:.0%}, vs. the 90% target) and is the best candidate for a fulfillment review.",
        f"<strong>{n_at_risk:,} customers</strong> are flagged <strong>At Risk</strong> of churning, representing "
        f"~${at_risk_value/1e3:,.0f}K in trailing 180-day spend — a prioritized retention campaign targets real revenue, not just a risk score.",
        f"<strong>{best_source['lead_source']}</strong> leads convert to won deals at the highest rate "
        f"({best_source['win_rate']:.0%}) — worth a larger share of seller-acquisition budget.",
        f"<strong>{worst_case_cat['category']}</strong> cases have the weakest SLA compliance "
        f"({worst_case_cat['sla_compliance']:.0%}) and the support team's biggest improvement opportunity.",
        f"The forecast expects the heaviest order volume of the next 12 weeks in the week of "
        f"<strong>{pd.Timestamp(peak_week['week_start']).strftime('%b %d, %Y')}</strong> "
        f"({peak_week['forecast_p50']:,.0f} orders, P50) — plan warehouse staffing accordingly.",
    ]

    # ------------------------------------------------------------------
    # 5. Excel + HTML dashboard
    # ------------------------------------------------------------------
    print("[6/6] Writing Excel workbook and HTML dashboard...")
    excel_path = REPORTS_DIR / "MarketCo_Ops_CRM_Report.xlsx"
    build_excel_report(
        excel_path,
        exec_summary=exec_summary_cells,
        revenue_by_category=revenue_by_category,
        forecast_by_category_week=forecast_by_category_week,
        churn_watchlist=churn_watchlist[[
            "customer_id", "segment", "churn_probability", "monetary_180d", "frequency_180d",
            "recency_days", "region", "acquisition_channel",
        ]],
        seller_scorecard=sellers_perf,
        opportunities=opportunities,
        case_sla_summary=case_summary,
        order_model_performance=order_model_performance,
        churn_model_metrics=churn_metrics,
        funnel_stages=funnel_stages,
    )

    dashboard_path = REPORTS_DIR / "marketco_dashboard.html"
    build_dashboard(
        dashboard_path,
        kpis=kpis,
        insights=insights,
        revenue_by_category=revenue_by_category,
        history_network=history_network,
        future_network=future_network,
        warehouse_perf=wh_perf,
        funnel_stages=funnel_stages,
        win_rate_df=win_rate_df,
        segment_counts=segment_counts,
        monthly_cases=monthly_cases,
        monthly_gmv=monthly_gmv,
        tier_perf=tier_perf,
        channel_perf=channel_perf,
        churn_watchlist=churn_watchlist,
        seller_scorecard=sellers_perf,
        case_sla_summary=case_summary,
        excel_filename=excel_path.name,
        generated_at=datetime.now().strftime("%Y-%m-%d"),
    )

    print(f"\nDone.\n  Excel report : {excel_path}\n  HTML dashboard: {dashboard_path}")


if __name__ == "__main__":
    main()
