"""
Builds `reports/marketco_dashboard.html`: a self-contained, interactive
HTML dashboard (Plotly + a styled KPI/table layout) covering both
marketplace operations and CRM analytics, on a clean white canvas with
indigo/violet/teal accents. Built from the same computed tables that
populate the Excel workbook, so both artifacts show one source of truth.

Design goals (beyond the first version): a sticky section nav so a
stakeholder can jump straight to the part they care about, KPI cards
that show trend direction (not just a snapshot number), an
auto-generated "Key Insights" banner that states the two or three
things actually worth noticing in this run's data, and per-chart
one-line takeaways so the dashboard reads like an analyst's briefing
rather than a wall of charts.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

PALETTE = dict(
    primary="#5B4FE9",     # indigo-violet
    secondary="#00C2A8",   # teal
    accent="#FDCB6E",      # warm amber highlight
    warn="#E84393",        # magenta/pink for alerts
    deep="#2E1F6B",        # deep indigo - headers
    ink="#332F5C",
    muted="#8783A8",
    grid="#EFEDF9",
    band="rgba(91,79,233,0.12)",
    good="#00B894",
    bad="#E84393",
)
CHART_COLORWAY = ["#5B4FE9", "#00C2A8", "#FDCB6E", "#E84393", "#00B894", "#845EC2"]

ICONS = {
    "gmv": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    "aov": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>',
    "truck": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>',
    "forecast": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>',
    "churn": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    "crm": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    "support": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>',
}


def _fig_to_div(fig: go.Figure, div_id: str, include_js: str | bool = False) -> str:
    fig.update_layout(
        margin=dict(l=40, r=20, t=50, b=40),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Segoe UI, Arial, sans-serif", size=12, color=PALETTE["ink"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        colorway=CHART_COLORWAY,
        autosize=True,
    )
    fig.update_xaxes(showgrid=True, gridcolor=PALETTE["grid"])
    fig.update_yaxes(showgrid=True, gridcolor=PALETTE["grid"])
    # responsive=True makes Plotly track its container's size - but it
    # does this by setting the graph div's CSS to height:100%/width:100%,
    # which only works if something in the ancestor chain has a REAL,
    # non-auto height. Our chart cards size to content (no fixed height),
    # so without this explicit wrapper the div's height:100% resolves
    # against nothing, the chart is laid out at ~0px tall on first paint,
    # and Plotly's funnel trace in particular renders visibly broken from
    # that bad initial layout. Wrapping in a div with an explicit pixel
    # height (matching the figure's own `height`) gives height:100% a
    # real value to resolve against while still letting width track the
    # card responsively.
    height_px = fig.layout.height or 380
    config = {"responsive": True, "displaylogo": False}
    inner_html = pio.to_html(fig, full_html=False, include_plotlyjs=include_js, div_id=div_id, config=config)
    return f'<div style="height:{height_px}px; width:100%;">{inner_html}</div>'


# --------------------------------------------------------------------------
# Charts: Operations
# --------------------------------------------------------------------------
def _revenue_chart(revenue_by_category: pd.DataFrame) -> go.Figure:
    df = revenue_by_category.sort_values("total_gmv")
    fig = go.Figure(go.Bar(
        x=df["total_gmv"], y=df["category"], orientation="h", marker_color=PALETTE["primary"],
        text=[f"${v:,.0f}" for v in df["total_gmv"]], textposition="outside",
    ))
    fig.update_layout(title="GMV by Category", height=380)
    fig.update_xaxes(range=[0, df["total_gmv"].max() * 1.22])
    return fig


def _forecast_chart(history: pd.DataFrame, future: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history["week_start"], y=history["weekly_orders"], mode="lines",
                              name="Observed (history)", line=dict(color=PALETTE["ink"], width=2)))
    fig.add_trace(go.Scatter(
        x=pd.concat([future["week_start"], future["week_start"][::-1]]),
        y=pd.concat([future["forecast_p95"], future["forecast_p50"][::-1]]),
        fill="toself", fillcolor=PALETTE["band"], line=dict(color="rgba(0,0,0,0)"),
        name="P50-P95 forecast band",
    ))
    fig.add_trace(go.Scatter(x=future["week_start"], y=future["forecast_p50"], mode="lines+markers",
                              name="Forecast (P50)", line=dict(color=PALETTE["primary"], width=3, dash="dash")))
    fig.update_layout(title="Network-wide Weekly Orders: History & 12-Week Forecast (incl. mega-sale events)", height=420)
    return fig


def _warehouse_chart(warehouse_perf: pd.DataFrame) -> go.Figure:
    df = warehouse_perf.sort_values("on_time_rate")
    colors = [PALETTE["warn"] if r < 0.85 else PALETTE["secondary"] for r in df["on_time_rate"]]
    fig = go.Figure(go.Bar(
        x=df["on_time_rate"], y=df["warehouse_name"], orientation="h", marker_color=colors,
        text=[f"{r:.0%}" for r in df["on_time_rate"]], textposition="outside",
    ))
    fig.add_vline(x=0.90, line_dash="dash", line_color=PALETTE["ink"], annotation_text="90% target")
    fig.update_layout(title="On-Time Delivery Rate by Warehouse", xaxis_tickformat=".0%", height=380)
    fig.update_xaxes(range=[0, max(df["on_time_rate"].max() * 1.18, 1.0)])
    return fig


# --------------------------------------------------------------------------
# Charts: CRM
# --------------------------------------------------------------------------
def _funnel_chart(funnel_stages: list[tuple[str, int]]) -> go.Figure:
    """
    A genuine, strictly-decreasing funnel: each stage is a subset of the
    one above it, so the shape actually narrows the way a real sales
    funnel should (earlier versions mixed in Account Expansion deals
    that don't originate from a Lead at all, which could make a later
    stage's count exceed an earlier one - fixed by only counting
    opportunities/wins that trace back to a Lead).

    Rendered as a simple shared-origin horizontal bar chart (bars
    starting at 0, sorted stage-order top to bottom) rather than
    Plotly's native Funnel trace or a manually-centered "base" bar
    trick - both of those rendered unreliably at small values relative
    to the top stage inside this dashboard's responsive containers.
    A shared-origin bar uses exactly the same proven rendering path as
    every other bar chart on this page, which is also why it looks
    visually consistent with the rest of the dashboard rather than a
    one-off custom shape.
    """
    labels = [s[0] for s in funnel_stages]
    values = [s[1] for s in funnel_stages]
    max_val = max(values) if values else 1
    colors = [PALETTE["primary"], PALETTE["secondary"], PALETTE["accent"], PALETTE["good"]][: len(labels)]
    pcts = [v / max_val if max_val else 0 for v in values]
    # All the information (stage, count, share of top stage) lives in the
    # y-axis label rather than as text drawn on/around each bar - on-bar
    # text (inside, outside, and "auto") each turned out to render
    # invisibly for the two largest bars in this dashboard's responsive
    # container in testing, for reasons that didn't reproduce in
    # isolation. The y-axis label has rendered reliably throughout, so
    # it carries the full story instead.
    y_labels = [f"{lbl}  —  {v:,} ({p:.0%})" for lbl, v, p in zip(labels, values, pcts)]

    fig = go.Figure(go.Bar(
        x=values, y=y_labels, orientation="h",
        marker_color=colors, showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(title="Seller Acquisition Funnel", height=380, yaxis=dict(autorange="reversed"))
    fig.update_xaxes(range=[0, max_val * 1.08])
    return fig


def _win_rate_chart(win_rate_df: pd.DataFrame) -> go.Figure:
    df = win_rate_df.sort_values("win_rate")
    fig = go.Figure(go.Bar(
        x=df["win_rate"], y=df["lead_source"], orientation="h", marker_color=PALETTE["secondary"],
        text=[f"{r:.0%}" for r in df["win_rate"]], textposition="outside",
    ))
    fig.update_layout(title="Opportunity Win Rate by Lead Source", xaxis_tickformat=".0%", height=380)
    fig.update_xaxes(range=[0, df["win_rate"].max() * 1.25])
    return fig


def _churn_risk_chart(segment_counts: pd.Series) -> go.Figure:
    """
    Rendered as a horizontal bar chart rather than a donut/pie: Plotly's
    pie legend and outside/inside slice labels both turned out to
    render unreliably (missing labels, no visible legend) in this
    dashboard's responsive container, the same class of issue the
    funnel chart hit. A bar chart uses the same proven-reliable
    rendering path as every other chart on this page, and a sorted bar
    list is arguably easier to read at a glance than a 6-color donut
    anyway - it's just as easy to see "Champions and Loyal together
    are the majority" from bar lengths as from wedge sizes.
    """
    colors_map = {"Champions": PALETTE["good"], "Loyal": PALETTE["secondary"], "New": PALETTE["accent"],
                  "At Risk": PALETTE["warn"], "Hibernating": "#B2ACD1", "Others": "#C9C6E8"}
    ordered = segment_counts.sort_values(ascending=True)
    total = ordered.sum()
    y_labels = [f"{seg}  \u2014  {cnt:,} ({cnt/total:.0%})" for seg, cnt in ordered.items()]
    colors = [colors_map.get(s, "#CCC") for s in ordered.index]

    fig = go.Figure(go.Bar(
        x=ordered.values, y=y_labels, orientation="h",
        marker_color=colors, showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(title="Customer Segments (RFM x Churn Risk)", height=400)
    fig.update_xaxes(range=[0, ordered.max() * 1.1])
    return fig


def _case_volume_chart(monthly_cases: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_cases["month"], y=monthly_cases["cases"], name="Case volume",
                          marker_color=PALETTE["primary"], yaxis="y1"))
    fig.add_trace(go.Scatter(x=monthly_cases["month"], y=monthly_cases["sla_compliance"], name="SLA compliance",
                              line=dict(color=PALETTE["warn"], width=3), yaxis="y2"))
    fig.update_layout(
        title="Support Case Volume & SLA Compliance",
        yaxis=dict(title="Cases"),
        yaxis2=dict(title="SLA compliance", overlaying="y", side="right", tickformat=".0%", range=[0, 1]),
        height=400,
    )
    return fig


# --------------------------------------------------------------------------
# Charts: Business trends & segmentation deep-dive
# --------------------------------------------------------------------------
def _monthly_gmv_chart(monthly_gmv: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_gmv["month"], y=monthly_gmv["gmv_usd"], name="Monthly GMV",
                          marker_color=PALETTE["primary"], yaxis="y1"))
    yoy = monthly_gmv.dropna(subset=["yoy_growth"])
    fig.add_trace(go.Scatter(x=yoy["month"], y=yoy["yoy_growth"], name="YoY growth",
                              line=dict(color=PALETTE["warn"], width=3), yaxis="y2"))
    fig.update_layout(
        title="Monthly GMV & Year-over-Year Growth (full 2-year history)",
        yaxis=dict(title="GMV ($)"),
        yaxis2=dict(title="YoY growth", overlaying="y", side="right", tickformat=".0%"),
        height=400,
    )
    return fig


def _tier_performance_chart(tier_perf: pd.DataFrame) -> go.Figure:
    colors_map = {"Bronze": "#C9A876", "Silver": "#A8ABC0", "Gold": PALETTE["accent"], "Platinum": PALETTE["primary"]}
    y_labels = [
        f"{r.tier}  \u2014  ${r.gmv_usd/1e6:.1f}M  ({r.on_time_rate:.0%} on-time, {r.sellers} sellers)"
        for r in tier_perf.itertuples()
    ]
    colors = [colors_map.get(t, "#CCC") for t in tier_perf["tier"]]
    fig = go.Figure(go.Bar(
        x=tier_perf["gmv_usd"], y=y_labels, orientation="h", marker_color=colors, showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(title="Revenue by Seller Tier", height=340)
    fig.update_xaxes(range=[0, tier_perf["gmv_usd"].max() * 1.1], title="GMV ($)")
    return fig


def _channel_effectiveness_chart(channel_perf: pd.DataFrame) -> go.Figure:
    df = channel_perf.sort_values("gmv_per_customer")
    y_labels = [f"{r.acquisition_channel}  \u2014  ${r.gmv_per_customer:,.0f} / customer" for r in df.itertuples()]
    fig = go.Figure(go.Bar(
        x=df["gmv_per_customer"], y=y_labels, orientation="h", marker_color=PALETTE["secondary"], showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(title="Lifetime GMV per Customer by Acquisition Channel", height=340)
    fig.update_xaxes(range=[0, df["gmv_per_customer"].max() * 1.15], title="GMV per customer ($)")
    return fig


# --------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------
def _delta_html(delta_pct: float | None, good_when_up: bool = True) -> str:
    if delta_pct is None:
        return ""
    is_up = delta_pct >= 0
    is_good = is_up if good_when_up else not is_up
    color_class = "delta-good" if is_good else "delta-bad"
    arrow = "&#9650;" if is_up else "&#9660;"
    return f'<span class="kpi-delta {color_class}">{arrow} {abs(delta_pct):.1f}%</span>'


def _kpi_cards_html(kpis: list[dict]) -> str:
    cards = []
    for kpi in kpis:
        icon = ICONS.get(kpi.get("icon", ""), "")
        delta = _delta_html(kpi.get("delta_pct"), kpi.get("good_when_up", True))
        cards.append(f"""
        <div class="kpi-card">
          <div class="kpi-icon">{icon}</div>
          <div class="kpi-value">{kpi['value']} {delta}</div>
          <div class="kpi-label">{kpi['label']}</div>
          <div class="kpi-sub">{kpi['sub']}</div>
        </div>""")
    return "\n".join(cards)


def _insights_html(insights: list[str]) -> str:
    items = "\n".join(f'<li>{text}</li>' for text in insights)
    return f'<ul class="insights-list">{items}</ul>'


def _table_html(df: pd.DataFrame, max_rows: int = 15) -> str:
    return df.head(max_rows).to_html(index=False, classes="data-table", border=0, escape=False)


def _risk_badge(segment: str) -> str:
    css = {
        "Champions": "badge-good", "Loyal": "badge-secondary", "New": "badge-accent",
        "At Risk": "badge-bad", "Hibernating": "badge-muted", "Others": "badge-muted",
    }.get(segment, "badge-muted")
    return f'<span class="badge {css}">{segment}</span>'


def _tier_badge(tier: str) -> str:
    css = {"Platinum": "badge-accent", "Gold": "badge-secondary", "Silver": "badge-muted", "Bronze": "badge-muted"}.get(tier, "badge-muted")
    return f'<span class="badge {css}">{tier}</span>'


def build_dashboard(
    output_path: Path,
    kpis: list[dict],
    insights: list[str],
    revenue_by_category: pd.DataFrame,
    history_network: pd.DataFrame,
    future_network: pd.DataFrame,
    warehouse_perf: pd.DataFrame,
    funnel_stages: list,
    win_rate_df: pd.DataFrame,
    segment_counts: pd.Series,
    monthly_cases: pd.DataFrame,
    monthly_gmv: pd.DataFrame,
    tier_perf: pd.DataFrame,
    channel_perf: pd.DataFrame,
    churn_watchlist: pd.DataFrame,
    seller_scorecard: pd.DataFrame,
    case_sla_summary: pd.DataFrame,
    excel_filename: str,
    generated_at: str,
) -> Path:
    div1 = _fig_to_div(_revenue_chart(revenue_by_category), "chart-revenue", include_js=True)
    div2 = _fig_to_div(_forecast_chart(history_network, future_network), "chart-forecast")
    div3 = _fig_to_div(_warehouse_chart(warehouse_perf), "chart-warehouse")
    div4 = _fig_to_div(_funnel_chart(funnel_stages), "chart-funnel")
    div5 = _fig_to_div(_win_rate_chart(win_rate_df), "chart-winrate")
    div6 = _fig_to_div(_churn_risk_chart(segment_counts), "chart-churn")
    div7 = _fig_to_div(_case_volume_chart(monthly_cases), "chart-cases")
    div8 = _fig_to_div(_monthly_gmv_chart(monthly_gmv), "chart-monthly-gmv")
    div9 = _fig_to_div(_tier_performance_chart(tier_perf), "chart-tier-perf")
    div10 = _fig_to_div(_channel_effectiveness_chart(channel_perf), "chart-channel-perf")

    watchlist_display = churn_watchlist[[
        "customer_id", "segment", "churn_probability", "monetary_180d", "frequency_180d", "recency_days",
    ]].head(12).copy()
    watchlist_display["segment"] = watchlist_display["segment"].map(_risk_badge)
    watchlist_display["churn_probability"] = (watchlist_display["churn_probability"] * 100).round(1).astype(str) + "%"
    watchlist_display["monetary_180d"] = watchlist_display["monetary_180d"].round(0).map(lambda v: f"${v:,.0f}")
    watchlist_display = watchlist_display.rename(columns={
        "customer_id": "Customer", "segment": "Segment", "churn_probability": "Churn risk",
        "monetary_180d": "Spend (180d)", "frequency_180d": "Orders (180d)", "recency_days": "Days since last order",
    })

    seller_display = seller_scorecard[[
        "account_name", "tier", "account_manager", "orders", "gmv_usd", "on_time_rate", "return_rate",
    ]].head(12).copy()
    seller_display["tier"] = seller_display["tier"].map(_tier_badge)
    seller_display["gmv_usd"] = seller_display["gmv_usd"].round(0).map(lambda v: f"${v:,.0f}")
    seller_display["on_time_rate"] = (seller_display["on_time_rate"] * 100).round(1).astype(str) + "%"
    seller_display["return_rate"] = (seller_display["return_rate"] * 100).round(1).astype(str) + "%"
    seller_display = seller_display.rename(columns={
        "account_name": "Seller", "tier": "Tier", "account_manager": "Account Manager", "orders": "Orders",
        "gmv_usd": "GMV", "on_time_rate": "On-time %", "return_rate": "Return %",
    })

    case_display = case_sla_summary.copy()
    case_display["sla_compliance"] = (case_display["sla_compliance"] * 100).round(1).astype(str) + "%"
    case_display["avg_resolution_hours"] = case_display["avg_resolution_hours"].round(1)
    case_display["avg_csat"] = case_display["avg_csat"].round(2)
    case_display = case_display.rename(columns={
        "category": "Category", "cases": "Cases", "sla_compliance": "SLA Compliance",
        "avg_resolution_hours": "Avg Resolution (h)", "avg_csat": "Avg CSAT",
    })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MarketCo Inc. — Operations & CRM Intelligence Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --ink: #26233F; --muted: #8783A8; --bg: #FFFFFF; --panel: #FBFAFF; --card: #FFFFFF;
    --accent: #5B4FE9; --accent2: #00C2A8; --border: #ECEAF6; --deep: #2E1F6B;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--ink); }}
  header {{ background: linear-gradient(135deg, #2E1F6B, #5B4FE9 55%, #00C2A8); color: white; padding: 26px 40px 20px; }}
  header h1 {{ margin: 0 0 4px 0; font-size: 25px; }}
  header p {{ margin: 0; color: #E4E1FB; font-size: 13.5px; }}
  nav.subnav {{
    position: sticky; top: 0; z-index: 50; background: rgba(255,255,255,0.96);
    border-bottom: 1px solid var(--border); backdrop-filter: blur(6px);
    display: flex; gap: 4px; padding: 0 40px; overflow-x: auto;
  }}
  nav.subnav a {{
    color: var(--ink); text-decoration: none; font-size: 13px; font-weight: 600;
    padding: 12px 14px; white-space: nowrap; border-bottom: 2px solid transparent;
  }}
  nav.subnav a:hover {{ color: var(--accent); border-bottom-color: var(--accent2); }}
  .container {{ max-width: 1320px; margin: 0 auto; padding: 24px 40px 60px; }}

  .kpi-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 22px; }}
  .kpi-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 20px; flex: 1 1 190px; box-shadow: 0 2px 10px rgba(38,35,63,0.05);
    transition: box-shadow .15s ease, transform .15s ease;
  }}
  .kpi-card:hover {{ box-shadow: 0 6px 18px rgba(91,79,233,0.12); transform: translateY(-1px); }}
  .kpi-icon {{ color: var(--accent2); width: 22px; height: 22px; margin-bottom: 8px; }}
  .kpi-icon svg {{ width: 100%; height: 100%; }}
  .kpi-value {{ font-size: 23px; font-weight: 700; color: var(--accent); display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }}
  .kpi-delta {{ font-size: 12px; font-weight: 700; }}
  .delta-good {{ color: var(--accent2); }}
  .delta-bad {{ color: #E84393; }}
  .kpi-label {{ font-size: 13px; font-weight: 600; margin-top: 6px; }}
  .kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}

  .insights-card {{
    background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--accent);
    border-radius: 12px; padding: 16px 22px; margin-bottom: 30px;
  }}
  .insights-card h3 {{ margin: 0 0 8px 0; font-size: 14px; color: var(--deep, var(--ink)); }}
  .insights-list {{ margin: 0; padding-left: 18px; font-size: 13.5px; line-height: 1.7; }}
  .insights-list li {{ margin-bottom: 3px; }}

  .section-title {{
    font-size: 18px; font-weight: 700; margin: 38px 0 12px; color: var(--ink);
    border-left: 4px solid var(--accent2); padding-left: 10px; scroll-margin-top: 56px;
  }}
  .chart-grid {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }}
  .chart-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px;
    flex: 1 1 45%; min-width: 340px; box-shadow: 0 2px 8px rgba(38,35,63,0.04);
  }}
  .full-width {{ flex: 1 1 100%; }}
  table.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table.data-table th {{ background: var(--accent); color: white; padding: 9px 10px; text-align: left; }}
  table.data-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); }}
  table.data-table tr:nth-child(even) {{ background: var(--panel); }}
  table.data-table tr:hover {{ background: #F1EEFC; }}
  .table-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px; overflow-x: auto; box-shadow: 0 2px 8px rgba(38,35,63,0.04); }}

  .badge {{ display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; font-weight: 700; }}
  .badge-good {{ background: #E3FBF4; color: #00966F; }}
  .badge-secondary {{ background: #E1F8F5; color: #00817A; }}
  .badge-accent {{ background: #FFF4DE; color: #A87400; }}
  .badge-bad {{ background: #FDE7F0; color: #C21E68; }}
  .badge-muted {{ background: #F1EFFB; color: #6C6795; }}

  footer {{ max-width: 1320px; margin: 0 auto; padding: 24px 40px 40px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); }}
  a {{ color: var(--accent); }}
  .badge-top {{ display: inline-block; background: rgba(255,255,255,0.18); color: white; border-radius: 6px; padding: 3px 9px; font-size: 11px; font-weight: 600; margin-left: 8px; }}
  .signature-box {{
    max-width: 1320px; margin: 0 auto 24px; padding: 16px 24px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 12px; display: flex; align-items: center;
    gap: 16px; font-size: 13px; color: var(--ink); flex-wrap: wrap;
  }}
  .sig-avatar {{
    width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: white; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px;
  }}
  .sig-text {{ flex: 1 1 320px; }}
  .sig-name {{ font-weight: 700; font-size: 14px; color: var(--ink); }}
  .sig-role {{ font-size: 12.5px; color: var(--muted); margin-top: 2px; }}
  .sig-link {{
    background: var(--accent); color: white; padding: 9px 18px; border-radius: 8px;
    font-size: 13px; font-weight: 600; text-decoration: none; white-space: nowrap;
    transition: background .15s ease;
  }}
  .sig-link:hover {{ background: var(--deep); }}
</style>
</head>
<body>
<header>
  <h1>MarketCo Inc. — Operations &amp; CRM Intelligence <span class="badge-top">SYNTHETIC DEMO DATA</span></h1>
  <p>Dynamics 365-style CRM · Network-wide report · Generated {generated_at} · Full detail in <strong>{excel_filename}</strong></p>
</header>
<nav class="subnav">
  <a href="#overview">Overview</a>
  <a href="#operations">Operations</a>
  <a href="#forecast">Forecast</a>
  <a href="#trends">Trends</a>
  <a href="#crm">CRM Pipeline</a>
  <a href="#customers">Customer Health</a>
  <a href="#sellers">Top Sellers</a>
  <a href="#support">Support</a>
</nav>
<div class="container">

  <div id="overview" class="kpi-row">{_kpi_cards_html(kpis)}</div>

  <div class="insights-card">
    <h3>&#128161; Key Insights</h3>
    {_insights_html(insights)}
  </div>

  <div id="operations" class="section-title">Operations — Revenue &amp; Fulfillment</div>
  <div class="chart-grid">
    <div class="chart-card">{div1}</div>
    <div class="chart-card">{div3}</div>
  </div>

  <div id="forecast" class="section-title">Demand Forecast (Global LightGBM Quantile Model)</div>
  <div class="chart-grid"><div class="chart-card full-width">{div2}</div></div>

  <div id="trends" class="section-title">Business Trends &amp; Segmentation Deep-Dive</div>
  <div class="chart-grid">
    <div class="chart-card full-width">{div8}</div>
    <div class="chart-card">{div9}</div>
    <div class="chart-card">{div10}</div>
  </div>

  <div id="crm" class="section-title">CRM — Seller Acquisition Pipeline</div>
  <div class="chart-grid">
    <div class="chart-card">{div4}</div>
    <div class="chart-card">{div5}</div>
  </div>

  <div id="customers" class="section-title">Customer Health &amp; Churn Risk</div>
  <div class="chart-grid">
    <div class="chart-card">{div6}</div>
    <div class="chart-card">{div7}</div>
  </div>
  <div class="table-card" style="margin-top:20px;">{_table_html(watchlist_display)}</div>

  <div id="sellers" class="section-title">Top Sellers</div>
  <div class="table-card">{_table_html(seller_display)}</div>

  <div id="support" class="section-title">Support Case Analysis</div>
  <div class="table-card">{_table_html(case_display)}</div>

</div>
<footer>
  MarketCo Inc. is a data-engineering / data-science portfolio project. All company, seller, customer, and CRM
  figures are synthetically generated — see <code>docs/data_dictionary.md</code> in the repository for full
  data-provenance notes. Not an official record of any real company.
</footer>
<div class="signature-box">
  <div class="sig-avatar">MS</div>
  <div class="sig-text">
    <div class="sig-name">Milad Shabani</div>
    <div class="sig-role">Data Engineer &amp; Data Scientist — built the data pipeline, forecasting &amp; churn models, and this dashboard, end to end.</div>
  </div>
  <a class="sig-link" href="https://miladshabani.ir/P1/" target="_blank" rel="noopener">View more of my work &rarr;</a>
</div>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
