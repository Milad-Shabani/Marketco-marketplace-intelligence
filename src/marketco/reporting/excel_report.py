"""
Builds the planner-facing Excel workbook (`MarketCo_Ops_CRM_Report.xlsx`)
combining operations forecasting and CRM analytics into one workbook,
with native (editable) Excel charts. Built from the same computed
tables that feed `reporting.html_dashboard`.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

HEADER_FMT = dict(bold=True, bg_color="#5B4FE9", font_color="white", border=1, text_wrap=True, valign="vcenter")


def _write_df(writer, df: pd.DataFrame, sheet_name: str, freeze_header: bool = True, col_widths: dict | None = None):
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1, header=False)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    header_format = workbook.add_format(HEADER_FMT)
    for col_idx, col_name in enumerate(df.columns):
        worksheet.write(0, col_idx, col_name, header_format)
        width = (col_widths or {}).get(col_name, max(12, min(32, len(str(col_name)) + 4)))
        worksheet.set_column(col_idx, col_idx, width)
    if freeze_header:
        worksheet.freeze_panes(1, 0)
    return worksheet


def build_excel_report(
    output_path: Path,
    exec_summary: dict,
    revenue_by_category: pd.DataFrame,
    forecast_by_category_week: pd.DataFrame,
    churn_watchlist: pd.DataFrame,
    seller_scorecard: pd.DataFrame,
    opportunities: pd.DataFrame,
    case_sla_summary: pd.DataFrame,
    order_model_performance: pd.DataFrame,
    churn_model_metrics: dict,
    funnel_stages: list,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook = writer.book

        ws = workbook.add_worksheet("Executive Summary")
        writer.sheets["Executive Summary"] = ws
        title_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#2E1F6B"})
        label_fmt = workbook.add_format({"bold": True, "font_size": 11})
        value_fmt = workbook.add_format({"font_size": 20, "bold": True, "font_color": "#5B4FE9"})
        sub_fmt = workbook.add_format({"italic": True, "font_color": "#7A7A9A"})

        ws.write(0, 0, "MarketCo — Marketplace Operations & CRM Intelligence", title_fmt)
        ws.write(1, 0, "Network-wide report (synthetic demo data, Dynamics 365-style CRM model)", sub_fmt)

        kpi_row = 3
        for i, (label, value) in enumerate(exec_summary.items()):
            col = i * 2
            ws.write(kpi_row, col, label, label_fmt)
            ws.write(kpi_row + 1, col, value, value_fmt)
        ws.set_column(0, 20, 20)

        rev_start_row = kpi_row + 4
        ws.write(rev_start_row, 0, "Revenue (GMV) by Category", label_fmt)
        for i, r in enumerate(revenue_by_category.itertuples(index=False), start=rev_start_row + 1):
            ws.write(i, 0, r.category)
            ws.write(i, 1, float(r.total_gmv))
        chart1 = workbook.add_chart({"type": "bar"})
        n = len(revenue_by_category)
        chart1.add_series({
            "name": "GMV",
            "categories": ["Executive Summary", rev_start_row + 1, 0, rev_start_row + n, 0],
            "values": ["Executive Summary", rev_start_row + 1, 1, rev_start_row + n, 1],
            "fill": {"color": "#5B4FE9"},
        })
        chart1.set_title({"name": "GMV by Category"})
        chart1.set_legend({"none": True})
        ws.insert_chart(rev_start_row, 3, chart1, {"x_scale": 1.3, "y_scale": 1.3})

        funnel_start = rev_start_row + n + 3
        ws.write(funnel_start, 0, "CRM Seller Acquisition Funnel (Lead -> Opportunity -> Won -> High-Performing)", label_fmt)
        funnel_rows = funnel_stages
        for i, (lbl, val) in enumerate(funnel_rows, start=funnel_start + 1):
            ws.write(i, 0, lbl)
            ws.write(i, 1, val)
        chart2 = workbook.add_chart({"type": "column"})
        chart2.add_series({
            "name": "Funnel",
            "categories": ["Executive Summary", funnel_start + 1, 0, funnel_start + len(funnel_rows), 0],
            "values": ["Executive Summary", funnel_start + 1, 1, funnel_start + len(funnel_rows), 1],
            "fill": {"color": "#00C2A8"},
        })
        chart2.set_title({"name": "Seller Acquisition Funnel"})
        chart2.set_legend({"none": True})
        ws.insert_chart(funnel_start, 3, chart2, {"x_scale": 1.3, "y_scale": 1.3})

        _write_df(writer, forecast_by_category_week, "Order Forecast by Category")
        _write_df(writer, churn_watchlist, "Customer Churn Watchlist", col_widths={"customer_id": 16})
        _write_df(writer, seller_scorecard, "Seller Scorecard", col_widths={"account_name": 24})
        _write_df(writer, opportunities, "CRM Pipeline", col_widths={"opportunity_id": 14})
        _write_df(writer, case_sla_summary, "Support Case Analysis")

        model_rows = pd.concat([
            order_model_performance.reset_index().assign(model_type="Order Forecast (LightGBM Quantile)"),
        ], ignore_index=True)
        _write_df(writer, model_rows, "Model Performance - Forecast")

        churn_metrics_df = pd.DataFrame([churn_model_metrics])
        _write_df(writer, churn_metrics_df, "Model Performance - Churn")

    return output_path
