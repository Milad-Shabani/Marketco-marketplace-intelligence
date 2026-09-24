"""
Builds `reports/marketco_dashboard.html`: a self-contained, interactive
HTML dashboard (Plotly + a styled KPI/table layout) covering both
marketplace operations and CRM analytics, on a clean white canvas with
indigo/violet/teal accents. Built from the same computed tables that
populate the Excel workbook, so both artifacts show one source of truth.

Design goals: a sticky section nav (highlighting the section in view) so
a stakeholder can jump straight to the part they care about, KPI cards
that show trend direction (not just a snapshot number), an
auto-generated "Key Insights" banner that states the things actually
worth noticing in this run's data, and a title plus a one-line,
data-driven takeaway on every chart so the dashboard reads like an
analyst's briefing rather than a wall of charts.

Layout: charts sit in a CSS grid whose columns are fixed before any
chart is drawn, and a small script refits every chart whenever its card
changes size. Plotly measures a chart once, while the page is still
being parsed; in the earlier flexbox layout the first card of a row was
briefly alone (and full width) at that moment, so on many screens the
chart kept that width and spilled out of its card.
"""
from __future__ import annotations

import html as html_lib
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
FONT = "'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"
ON_TIME_TARGET = 0.90

ICONS = {
    "gmv": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    "aov": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>',
    "truck": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>',
    "forecast": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>',
    "churn": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    "risk": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><path d="M23 11h-6"/></svg>',
    "crm": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    "support": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>',
}


def _fig_to_div(fig: go.Figure, div_id: str, include_js: str | bool = False) -> str:
    # Titles live in the HTML card header, so the plot only needs room at
    # the top for a legend or an annotation drawn above the plot area.
    needs_top = len(fig.data) > 1 or any((a.y or 0) >= 1 for a in fig.layout.annotations)
    fig.update_layout(
        margin=dict(l=8, r=16, t=34 if needs_top else 12, b=8),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family=FONT, size=12, color=PALETTE["ink"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=11.5)),
        hoverlabel=dict(font_family=FONT),
        colorway=CHART_COLORWAY,
        autosize=True,
    )
    # Invisible outside ticks push the x labels down a little, so the first
    # and last dates don't touch the y axes' bottom labels.
    fig.update_xaxes(showgrid=True, gridcolor=PALETTE["grid"], zeroline=False, automargin=True,
                     ticks="outside", ticklen=6, tickcolor="rgba(0,0,0,0)")
    fig.update_yaxes(showgrid=True, gridcolor=PALETTE["grid"], zeroline=False, automargin=True)
    # responsive=True makes Plotly track its container's size - but it
    # does this by setting the graph div's CSS to height:100%/width:100%,
    # which only works if something in the ancestor chain has a REAL,
    # non-auto height. Our chart cards size to content (no fixed height),
    # so without this explicit wrapper the div's height:100% resolves
    # against nothing, the chart is laid out at ~0px tall on first paint,
    # and Plotly's funnel trace in particular renders visibly broken from
    # that bad initial layout. Wrapping in a div with an explicit pixel
    # height (matching the figure's own `height`) gives height:100% a
    # real value to resolve against, and the page script refits the chart
    # to the wrapper's width whenever the wrapper changes size.
    height_px = fig.layout.height or 380
    config = {
        "responsive": True, "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "toImageButtonOptions": {"filename": div_id, "scale": 2},
    }
    inner_html = pio.to_html(fig, full_html=False, include_plotlyjs=include_js, div_id=div_id, config=config)
    return f'<div class="chart-box" style="height:{height_px}px;">{inner_html}</div>'


# --------------------------------------------------------------------------
# Charts: Operations
# --------------------------------------------------------------------------
def _revenue_chart(revenue_by_category: pd.DataFrame) -> go.Figure:
    df = revenue_by_category.sort_values("total_gmv")
    fig = go.Figure(go.Bar(
        x=df["total_gmv"], y=df["category"], orientation="h", marker_color=PALETTE["primary"],
        text=[f"${v / 1e6:,.1f}M" for v in df["total_gmv"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(height=380)
    fig.update_xaxes(range=[0, df["total_gmv"].max() * 1.18], tickprefix="$", tickformat="~s")
    return fig


def _forecast_chart(history: pd.DataFrame, future: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history["week_start"], y=history["weekly_orders"], mode="lines",
                              name="Observed (history)", line=dict(color=PALETTE["ink"], width=2)))
    fig.add_trace(go.Scatter(
        x=pd.concat([future["week_start"], future["week_start"][::-1]]),
        y=pd.concat([future["forecast_p95"], future["forecast_p50"][::-1]]),
        fill="toself", fillcolor=PALETTE["band"], line=dict(color="rgba(0,0,0,0)"),
        name="P50-P95 forecast band", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=future["week_start"], y=future["forecast_p50"], mode="lines+markers",
                              name="Forecast (P50)", line=dict(color=PALETTE["primary"], width=3, dash="dash")))
    # A divider where history ends. Drawn as a shape plus an annotation
    # rather than add_vline(annotation_text=...), which fails on date axes.
    start = future["week_start"].min()
    fig.add_shape(type="line", x0=start, x1=start, y0=0, y1=1, yref="paper",
                  line=dict(color=PALETTE["muted"], width=1, dash="dot"))
    fig.add_annotation(x=start, y=0.98, yref="paper", text="Forecast", showarrow=False,
                       xanchor="left", yanchor="top", xshift=4, font=dict(size=11, color=PALETTE["muted"]))
    fig.update_layout(height=420, hovermode="x unified")
    fig.update_yaxes(title="Orders per week", tickformat=",")
    return fig


def _warehouse_chart(warehouse_perf: pd.DataFrame) -> go.Figure:
    df = warehouse_perf.sort_values("on_time_rate")
    colors = [PALETTE["warn"] if r < 0.85 else PALETTE["secondary"] for r in df["on_time_rate"]]
    # Rates sit inside the bars, at their base: every bar ends near the
    # target line, so labels at the bar ends would collide with it.
    fig = go.Figure(go.Bar(
        x=df["on_time_rate"], y=df["warehouse_name"], orientation="h", marker_color=colors,
        text=[f"{r:.0%}" for r in df["on_time_rate"]], textposition="inside", insidetextanchor="start",
        textfont=dict(color="white", size=12),
        customdata=df[["orders", "avg_delivery_days"]],
        hovertemplate="%{y}<br>On time: %{x:.1%}<br>Orders: %{customdata[0]:,}"
                      "<br>Avg delivery: %{customdata[1]:.1f} days<extra></extra>",
    ))
    fig.add_vline(x=ON_TIME_TARGET, line_dash="dash", line_color=PALETTE["ink"],
                  annotation_text=f"{ON_TIME_TARGET:.0%} target", annotation_position="top",
                  annotation_font=dict(size=11, color=PALETTE["ink"]))
    fig.update_layout(xaxis_tickformat=".0%", height=380)
    fig.update_xaxes(range=[0, 1.02])
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
    fig.update_layout(height=380, yaxis=dict(autorange="reversed"))
    fig.update_xaxes(range=[0, max_val * 1.08])
    return fig


def _win_rate_chart(win_rate_df: pd.DataFrame) -> go.Figure:
    df = win_rate_df.sort_values("win_rate")
    fig = go.Figure(go.Bar(
        x=df["win_rate"], y=df["lead_source"], orientation="h", marker_color=PALETTE["secondary"],
        text=[f"{r:.0%}" for r in df["win_rate"]], textposition="outside", cliponaxis=False,
        customdata=df[["won", "opportunities"]],
        hovertemplate="%{y}: %{x:.1%}<br>%{customdata[0]} won of %{customdata[1]} opportunities<extra></extra>",
    ))
    fig.update_layout(xaxis_tickformat=".0%", height=380)
    fig.update_xaxes(range=[0, df["win_rate"].max() * 1.2])
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
    y_labels = [f"{seg}  —  {cnt:,} ({cnt/total:.0%})" for seg, cnt in ordered.items()]
    colors = [colors_map.get(s, "#CCC") for s in ordered.index]

    fig = go.Figure(go.Bar(
        x=ordered.values, y=y_labels, orientation="h",
        marker_color=colors, showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(height=400)
    fig.update_xaxes(range=[0, ordered.max() * 1.1], title="Customers", tickformat=",")
    return fig


def _case_volume_chart(monthly_cases: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_cases["month"], y=monthly_cases["cases"], name="Case volume",
                          marker_color=PALETTE["primary"], yaxis="y1", hovertemplate="%{y:,} cases"))
    fig.add_trace(go.Scatter(x=monthly_cases["month"], y=monthly_cases["sla_compliance"], name="SLA compliance",
                              line=dict(color=PALETTE["warn"], width=3), yaxis="y2",
                              hovertemplate="%{y:.1%} within SLA"))
    fig.update_layout(
        yaxis=dict(title="Cases", tickformat=","),
        yaxis2=dict(title="SLA compliance", overlaying="y", side="right", tickformat=".0%", range=[0, 1],
                    tickmode="linear", dtick=0.25, showgrid=False),
        height=400, hovermode="x unified",
    )
    return fig


# --------------------------------------------------------------------------
# Charts: Business trends & segmentation deep-dive
# --------------------------------------------------------------------------
def _monthly_gmv_chart(monthly_gmv: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly_gmv["month"], y=monthly_gmv["gmv_usd"], name="Monthly GMV",
                          marker_color=PALETTE["primary"], yaxis="y1", hovertemplate="$%{y:,.0f}"))
    yoy = monthly_gmv.dropna(subset=["yoy_growth"])
    fig.add_trace(go.Scatter(x=yoy["month"], y=yoy["yoy_growth"], name="YoY growth",
                              line=dict(color=PALETTE["warn"], width=3), yaxis="y2",
                              hovertemplate="%{y:+.1%} YoY"))
    fig.update_layout(
        yaxis=dict(title="GMV ($)", tickprefix="$", tickformat="~s"),
        yaxis2=dict(title="YoY growth", overlaying="y", side="right", tickformat=".0%", rangemode="tozero",
                    showgrid=False),
        height=400, hovermode="x unified",
    )
    return fig


def _tier_performance_chart(tier_perf: pd.DataFrame) -> go.Figure:
    colors_map = {"Bronze": "#C9A876", "Silver": "#A8ABC0", "Gold": PALETTE["accent"], "Platinum": PALETTE["primary"]}
    y_labels = [
        f"{r.tier}  —  ${r.gmv_usd/1e6:.1f}M  ({r.on_time_rate:.0%} on-time, {r.sellers} sellers)"
        for r in tier_perf.itertuples()
    ]
    colors = [colors_map.get(t, "#CCC") for t in tier_perf["tier"]]
    fig = go.Figure(go.Bar(
        x=tier_perf["gmv_usd"], y=y_labels, orientation="h", marker_color=colors, showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(height=340)
    fig.update_xaxes(range=[0, tier_perf["gmv_usd"].max() * 1.1], title="GMV ($)", tickprefix="$", tickformat="~s")
    return fig


def _channel_effectiveness_chart(channel_perf: pd.DataFrame) -> go.Figure:
    df = channel_perf.sort_values("gmv_per_customer")
    y_labels = [f"{r.acquisition_channel}  —  ${r.gmv_per_customer:,.0f} / customer" for r in df.itertuples()]
    fig = go.Figure(go.Bar(
        x=df["gmv_per_customer"], y=y_labels, orientation="h", marker_color=PALETTE["secondary"], showlegend=False,
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(height=340)
    fig.update_xaxes(range=[0, df["gmv_per_customer"].max() * 1.15], title="GMV per customer ($)",
                     tickprefix="$", tickformat=",")
    return fig


# --------------------------------------------------------------------------
# One-line takeaways under each chart title, computed from this run's data
# --------------------------------------------------------------------------
def _month_label(month: str) -> str:
    return pd.Period(month, freq="M").strftime("%b %Y")


def _takeaways(
    revenue_by_category: pd.DataFrame,
    future_network: pd.DataFrame,
    warehouse_perf: pd.DataFrame,
    funnel_stages: list,
    win_rate_df: pd.DataFrame,
    segment_counts: pd.Series,
    monthly_cases: pd.DataFrame,
    monthly_gmv: pd.DataFrame,
    tier_perf: pd.DataFrame,
    channel_perf: pd.DataFrame,
) -> dict[str, str]:
    t = {}

    top = revenue_by_category.sort_values("total_gmv", ascending=False).iloc[0]
    t["revenue"] = (f"<strong>{top['category']}</strong> brings in "
                    f"{top['total_gmv'] / revenue_by_category['total_gmv'].sum():.0%} of network GMV.")

    below = int((warehouse_perf["on_time_rate"] < ON_TIME_TARGET).sum())
    t["warehouse"] = (f"<strong>{below} of {len(warehouse_perf)}</strong> fulfillment centers are below the "
                      f"{ON_TIME_TARGET:.0%} on-time target." if below else
                      f"Every fulfillment center meets the {ON_TIME_TARGET:.0%} on-time target.")

    peak = future_network.loc[future_network["forecast_p50"].idxmax()]
    t["forecast"] = (f"Mega-sale events drive the spikes. Busiest forecast week: "
                     f"<strong>{pd.Timestamp(peak['week_start']).strftime('%b %d, %Y')}</strong>, "
                     f"{peak['forecast_p50']:,.0f} orders at P50 and up to {peak['forecast_p95']:,.0f} at P95.")

    yoy = monthly_gmv.dropna(subset=["yoy_growth"])
    if len(yoy):
        last = yoy.iloc[-1]
        t["monthly_gmv"] = (f"{_month_label(last['month'])} GMV is <strong>{last['yoy_growth']:+.0%}</strong> "
                            f"year over year; the last 12 months average {yoy['yoy_growth'].tail(12).mean():+.0%}.")
    else:
        t["monthly_gmv"] = "Monthly GMV over the full history."

    by_seller = tier_perf.sort_values("gmv_per_seller")
    lo, hi = by_seller.iloc[0], by_seller.iloc[-1]
    t["tier"] = (f"A <strong>{hi['tier']}</strong> seller averages ${hi['gmv_per_seller'] / 1e6:,.2f}M in GMV, "
                 f"{hi['gmv_per_seller'] / lo['gmv_per_seller']:.1f}x a {lo['tier']} seller.")

    by_cust = channel_perf.sort_values("gmv_per_customer")
    lo, hi = by_cust.iloc[0], by_cust.iloc[-1]
    t["channel"] = (f"<strong>{hi['acquisition_channel']}</strong> customers are worth the most "
                    f"(${hi['gmv_per_customer']:,.0f} each), "
                    f"{hi['gmv_per_customer'] / lo['gmv_per_customer'] - 1:.0%} more than {lo['acquisition_channel']}.")

    if len(funnel_stages) >= 3 and funnel_stages[0][1]:
        (first, n_first), (won, n_won) = funnel_stages[0], funnel_stages[2]
        t["funnel"] = (f"<strong>{n_won:,} of {n_first:,}</strong> {first.lower()} "
                       f"({n_won / n_first:.0%}) reached “{won}”.")
    else:
        t["funnel"] = "Each stage is a subset of the one above it."

    wr = win_rate_df.sort_values("win_rate")
    t["win_rate"] = (f"<strong>{wr.iloc[-1]['lead_source']}</strong> leads win most often "
                     f"({wr.iloc[-1]['win_rate']:.0%}); {wr.iloc[0]['lead_source']} the least ({wr.iloc[0]['win_rate']:.0%}).")

    total = segment_counts.sum()
    core = segment_counts.get("Champions", 0) + segment_counts.get("Loyal", 0)
    at_risk = segment_counts.get("At Risk", 0)
    t["segments"] = (f"{core / total:.0%} of customers are Champions or Loyal; "
                     f"<strong>{at_risk:,}</strong> ({at_risk / total:.1%}) are At Risk.")

    busiest = monthly_cases.loc[monthly_cases["cases"].idxmax()]
    t["cases"] = (f"Volume peaks at <strong>{busiest['cases']:,}</strong> cases in {_month_label(busiest['month'])}, "
                  f"while SLA compliance stays between {monthly_cases['sla_compliance'].min():.0%} "
                  f"and {monthly_cases['sla_compliance'].max():.0%}.")
    return t


# --------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------
def _delta_html(delta_pct: float | None, good_when_up: bool = True) -> str:
    if delta_pct is None:
        return ""
    if abs(delta_pct) < 0.05:
        return '<span class="kpi-delta delta-flat" title="vs. the previous 90 days">&#9644; 0.0%</span>'
    is_up = delta_pct >= 0
    is_good = is_up if good_when_up else not is_up
    color_class = "delta-good" if is_good else "delta-bad"
    arrow = "&#9650;" if is_up else "&#9660;"
    return f'<span class="kpi-delta {color_class}" title="vs. the previous 90 days">{arrow} {abs(delta_pct):.1f}%</span>'


def _kpi_cards_html(kpis: list[dict]) -> str:
    cards = []
    for kpi in kpis:
        icon = ICONS.get(kpi.get("icon", ""), "")
        delta = _delta_html(kpi.get("delta_pct"), kpi.get("good_when_up", True))
        cards.append(f"""
        <div class="kpi-card">
          <div class="kpi-top"><span class="kpi-icon">{icon}</span><span class="kpi-label">{kpi['label']}</span></div>
          <div class="kpi-value">{kpi['value']}{delta}</div>
          <div class="kpi-sub">{kpi['sub']}</div>
        </div>""")
    return "\n".join(cards)


def _insights_html(insights: list[str]) -> str:
    items = "\n".join(f'<li>{text}</li>' for text in insights)
    return f'<ul class="insights-list">{items}</ul>'


def _chart_card(title: str, takeaway: str, div: str, full_width: bool = False) -> str:
    return f"""
    <div class="card chart-card{' full-width' if full_width else ''}">
      <div class="card-head"><h3>{title}</h3><p>{takeaway}</p></div>
      {div}
    </div>"""


def _table_html(df: pd.DataFrame, num_cols: tuple[str, ...] = (), max_rows: int = 15) -> str:
    # Cells may already hold badge markup, so values are inserted as-is;
    # column names are escaped. Numeric columns are right-aligned.
    def cls(col):
        return ' class="num"' if col in num_cols else ""

    head = "".join(f"<th{cls(c)}>{html_lib.escape(str(c))}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td{cls(c)}>{v}</td>" for c, v in zip(df.columns, row)) + "</tr>"
        for row in df.head(max_rows).itertuples(index=False)
    )
    return f'<table class="data-table"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def _table_card(title: str, subtitle: str, table: str, full_width: bool = False, extra: str = "") -> str:
    return f"""
    <div class="card table-card{' full-width' if full_width else ''}">
      <div class="card-head"><h3>{title}</h3><p>{subtitle}</p></div>
      <div class="table-scroll">{table}</div>{extra}
    </div>"""


def _mini_stats_html(stats: list[tuple[str, str]]) -> str:
    items = "".join(f'<div class="mini-stat"><span>{label}</span><strong>{value}</strong></div>' for label, value in stats)
    return f'<div class="mini-stats">{items}</div>'


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
    t = _takeaways(revenue_by_category, future_network, warehouse_perf, funnel_stages, win_rate_df,
                   segment_counts, monthly_cases, monthly_gmv, tier_perf, channel_perf)

    # Every watchlist row is an At-Risk customer, so the segment column is
    # left out and the card title says it instead.
    watchlist_display = churn_watchlist[[
        "customer_id", "churn_probability", "monetary_180d", "frequency_180d", "recency_days",
    ]].head(10).copy()
    watchlist_display["churn_probability"] = (watchlist_display["churn_probability"] * 100).round(1).astype(str) + "%"
    watchlist_display["monetary_180d"] = watchlist_display["monetary_180d"].round(0).map(lambda v: f"${v:,.0f}")
    watchlist_display = watchlist_display.rename(columns={
        "customer_id": "Customer", "churn_probability": "Churn risk",
        "monetary_180d": "Spend (180d)", "frequency_180d": "Orders (180d)", "recency_days": "Days since last order",
    })

    seller_display = seller_scorecard[[
        "account_name", "tier", "account_manager", "orders", "gmv_usd", "on_time_rate", "return_rate",
    ]].head(12).copy()
    seller_display["tier"] = seller_display["tier"].map(_tier_badge)
    seller_display["orders"] = seller_display["orders"].map(lambda v: f"{v:,}")
    seller_display["gmv_usd"] = seller_display["gmv_usd"].round(0).map(lambda v: f"${v:,.0f}")
    seller_display["on_time_rate"] = (seller_display["on_time_rate"] * 100).round(1).astype(str) + "%"
    seller_display["return_rate"] = (seller_display["return_rate"] * 100).round(1).astype(str) + "%"
    seller_display = seller_display.rename(columns={
        "account_name": "Seller", "tier": "Tier", "account_manager": "Account Manager", "orders": "Orders",
        "gmv_usd": "GMV", "on_time_rate": "On-time %", "return_rate": "Return %",
    })

    n_cases = case_sla_summary["cases"].sum()

    def per_case(col):
        return (case_sla_summary[col] * case_sla_summary["cases"]).sum() / n_cases

    case_stats = _mini_stats_html([
        ("Total cases", f"{n_cases:,}"),
        ("Within SLA", f"{per_case('sla_compliance'):.1%}"),
        ("Avg resolution", f"{per_case('avg_resolution_hours'):.1f} h"),
        ("Avg CSAT", f"{per_case('avg_csat'):.2f} / 5"),
    ])

    case_display = case_sla_summary.copy()
    case_display["cases"] = case_display["cases"].map(lambda v: f"{v:,}")
    case_display["sla_compliance"] = (case_display["sla_compliance"] * 100).round(1).astype(str) + "%"
    case_display["avg_resolution_hours"] = case_display["avg_resolution_hours"].map(lambda v: f"{v:.1f}")
    case_display["avg_csat"] = case_display["avg_csat"].map(lambda v: f"{v:.2f}")
    case_display = case_display.rename(columns={
        "category": "Category", "cases": "Cases", "sla_compliance": "SLA Compliance",
        "avg_resolution_hours": "Avg Resolution (h)", "avg_csat": "Avg CSAT",
    })

    watchlist_table = _table_html(watchlist_display, max_rows=10, num_cols=(
        "Churn risk", "Spend (180d)", "Orders (180d)", "Days since last order"))
    seller_table = _table_html(seller_display, num_cols=("Orders", "GMV", "On-time %", "Return %"))
    case_table = _table_html(case_display, num_cols=("Cases", "SLA Compliance", "Avg Resolution (h)", "Avg CSAT"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MarketCo Inc. — Operations & CRM Intelligence Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<style>
  :root {{
    --ink: #26233F; --muted: #7D799F; --bg: #FFFFFF; --panel: #FBFAFF; --card: #FFFFFF;
    --accent: #5B4FE9; --accent2: #00C2A8; --border: #E9E7F5; --deep: #2E1F6B;
    --shadow: 0 1px 2px rgba(38,35,63,0.04), 0 4px 14px rgba(38,35,63,0.05);
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{ font-family: {FONT}; margin: 0; background: var(--bg); color: var(--ink); line-height: 1.45; }}
  header {{ background: linear-gradient(135deg, #2E1F6B, #5B4FE9 55%, #00C2A8); color: white; }}
  .header-inner {{ max-width: 1320px; margin: 0 auto; padding: 26px 40px 22px; }}
  header h1 {{ margin: 0 0 6px 0; font-size: 25px; line-height: 1.25; }}
  header p {{ margin: 0; color: #E4E1FB; font-size: 13.5px; }}
  .badge-top {{ display: inline-block; vertical-align: middle; background: rgba(255,255,255,0.18); color: white; border-radius: 6px; padding: 3px 9px; font-size: 11px; font-weight: 600; margin-left: 8px; letter-spacing: .02em; }}

  nav.subnav {{
    position: sticky; top: 0; z-index: 50; background: rgba(255,255,255,0.96);
    border-bottom: 1px solid var(--border); backdrop-filter: blur(6px);
  }}
  .subnav-inner {{ max-width: 1320px; margin: 0 auto; padding: 0 28px; display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; }}
  .subnav-inner::-webkit-scrollbar {{ display: none; }}
  nav.subnav a {{
    color: var(--ink); text-decoration: none; font-size: 13px; font-weight: 600;
    padding: 12px 12px 10px; white-space: nowrap; border-bottom: 2px solid transparent;
  }}
  nav.subnav a:hover {{ color: var(--accent); }}
  nav.subnav a.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

  .container {{ max-width: 1320px; margin: 0 auto; padding: 24px 40px 48px; }}
  section {{ scroll-margin-top: 60px; }}
  .section-title {{
    font-size: 18px; font-weight: 700; margin: 36px 0 14px; color: var(--deep);
    border-left: 4px solid var(--accent2); padding-left: 10px; line-height: 1.3;
  }}

  .kpi-row {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }}
  .kpi-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; box-shadow: var(--shadow); min-width: 0;
    transition: box-shadow .15s ease, transform .15s ease;
  }}
  .kpi-card:hover {{ box-shadow: 0 6px 18px rgba(91,79,233,0.12); transform: translateY(-1px); }}
  .kpi-top {{ display: flex; align-items: center; gap: 10px; }}
  .kpi-icon {{ color: var(--accent); background: #EFEDFD; width: 32px; height: 32px; border-radius: 9px; padding: 7px; flex-shrink: 0; }}
  .kpi-icon svg {{ width: 100%; height: 100%; display: block; }}
  .kpi-label {{ font-size: 13px; font-weight: 600; color: var(--ink); }}
  .kpi-value {{ font-size: 26px; font-weight: 700; color: var(--deep); margin-top: 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; letter-spacing: -.01em; }}
  .kpi-delta {{ font-size: 11.5px; font-weight: 700; border-radius: 999px; padding: 2px 8px; letter-spacing: 0; }}
  .delta-good {{ color: #00866F; background: #E1F8F3; }}
  .delta-bad {{ color: #C21E68; background: #FDE7F0; }}
  .delta-flat {{ color: var(--muted); background: #F1EFFB; }}
  .kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .kpi-note {{ font-size: 11.5px; color: var(--muted); margin: 8px 2px 18px; }}

  .insights-card {{
    background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--accent);
    border-radius: 12px; padding: 16px 22px; box-shadow: var(--shadow);
  }}
  .insights-card h3 {{ margin: 0 0 8px 0; font-size: 14px; color: var(--deep); }}
  .insights-list {{ margin: 0; padding-left: 18px; font-size: 13.5px; line-height: 1.7; }}
  .insights-list li {{ margin-bottom: 3px; }}

  /* Two fixed columns: a chart is drawn at its final width even while the
     rest of its row hasn't been parsed yet. min-width:0 lets a card shrink
     below its content's width instead of pushing the grid wider. */
  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }}
  .full-width {{ grid-column: 1 / -1; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 16px 12px;
    box-shadow: var(--shadow); min-width: 0;
  }}
  .chart-card {{ overflow: hidden; }}
  .card-head h3 {{ margin: 0; font-size: 14.5px; font-weight: 700; color: var(--deep); }}
  .card-head p {{ margin: 3px 0 10px; font-size: 12.5px; color: var(--muted); }}
  .card-head p strong {{ color: var(--ink); }}
  .chart-box {{ width: 100%; min-width: 0; position: relative; }}

  .table-scroll {{ overflow-x: auto; }}
  table.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table.data-table th {{ background: #F3F1FD; color: var(--deep); padding: 9px 10px; text-align: left; font-weight: 700; font-size: 12px; white-space: nowrap; border-bottom: 1px solid var(--border); }}
  table.data-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  table.data-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table.data-table tbody tr:hover {{ background: #F7F5FE; }}
  table.data-table tbody tr:last-child td {{ border-bottom: 0; }}
  .mini-stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }}
  .mini-stat {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }}
  .mini-stat span {{ display: block; font-size: 11.5px; color: var(--muted); }}
  .mini-stat strong {{ display: block; font-size: 18px; color: var(--deep); margin-top: 2px; font-variant-numeric: tabular-nums; }}

  .badge {{ display: inline-block; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; font-weight: 700; }}
  .badge-good {{ background: #E3FBF4; color: #00966F; }}
  .badge-secondary {{ background: #E1F8F5; color: #00817A; }}
  .badge-accent {{ background: #FFF4DE; color: #A87400; }}
  .badge-bad {{ background: #FDE7F0; color: #C21E68; }}
  .badge-muted {{ background: #F1EFFB; color: #6C6795; }}

  a {{ color: var(--accent); }}
  .page-end {{ max-width: 1320px; margin: 0 auto; padding: 0 40px 40px; }}
  .signature-box {{
    padding: 16px 24px; background: var(--card); box-shadow: var(--shadow);
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
  footer {{ color: var(--muted); font-size: 12px; margin-top: 18px; }}

  @media (max-width: 1100px) {{
    .kpi-row, .mini-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
  @media (max-width: 900px) {{
    .grid {{ grid-template-columns: minmax(0, 1fr); }}
  }}
  @media (max-width: 640px) {{
    .header-inner {{ padding: 20px 16px 18px; }}
    header h1 {{ font-size: 20px; }}
    .subnav-inner {{ padding: 0 6px; }}
    .container {{ padding: 16px 16px 36px; }}
    .page-end {{ padding: 0 16px 32px; }}
    .kpi-row {{ gap: 10px; }}
    .kpi-card {{ padding: 12px; }}
    .kpi-label {{ font-size: 12px; }}
    .kpi-value {{ font-size: 21px; margin-top: 8px; }}
    .grid {{ gap: 14px; }}
    .card {{ padding: 12px 10px 8px; }}
    .section-title {{ font-size: 16px; margin-top: 28px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    html {{ scroll-behavior: auto; }}
    .kpi-card, .kpi-card:hover {{ transition: none; transform: none; }}
  }}
  @media print {{
    body {{ background: white; }}
    nav.subnav, .sig-link {{ display: none; }}
    .card, .kpi-card, .insights-card {{ box-shadow: none; break-inside: avoid; }}
  }}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <h1>MarketCo Inc. — Operations &amp; CRM Intelligence <span class="badge-top">SYNTHETIC DEMO DATA</span></h1>
    <p>Dynamics 365-style CRM · Network-wide report · Generated {generated_at} · Full detail in <strong>{excel_filename}</strong></p>
  </div>
</header>
<nav class="subnav" aria-label="Sections">
  <div class="subnav-inner">
    <a href="#overview">Overview</a>
    <a href="#operations">Operations</a>
    <a href="#forecast">Forecast</a>
    <a href="#trends">Trends</a>
    <a href="#crm">CRM Pipeline</a>
    <a href="#customers">Customer Health</a>
    <a href="#sellers">Top Sellers</a>
    <a href="#support">Support</a>
  </div>
</nav>
<main class="container">

  <section id="overview">
    <div class="kpi-row">{_kpi_cards_html(kpis)}</div>
    <p class="kpi-note">Arrows compare the last 90 days with the 90 days before.</p>
    <div class="insights-card">
      <h3>&#128161; Key Insights</h3>
      {_insights_html(insights)}
    </div>
  </section>

  <section id="operations">
    <h2 class="section-title">Operations — Revenue &amp; Fulfillment</h2>
    <div class="grid">
      {_chart_card("GMV by Category", t["revenue"], div1)}
      {_chart_card("On-Time Delivery Rate by Warehouse", t["warehouse"], div3)}
    </div>
  </section>

  <section id="forecast">
    <h2 class="section-title">Demand Forecast (Global LightGBM Quantile Model)</h2>
    <div class="grid">
      {_chart_card("Network-wide Weekly Orders: History &amp; 12-Week Forecast", t["forecast"], div2, full_width=True)}
    </div>
  </section>

  <section id="trends">
    <h2 class="section-title">Business Trends &amp; Segmentation Deep-Dive</h2>
    <div class="grid">
      {_chart_card("Monthly GMV &amp; Year-over-Year Growth", t["monthly_gmv"], div8, full_width=True)}
      {_chart_card("Revenue by Seller Tier", t["tier"], div9)}
      {_chart_card("Lifetime GMV per Customer by Acquisition Channel", t["channel"], div10)}
    </div>
  </section>

  <section id="crm">
    <h2 class="section-title">CRM — Seller Acquisition Pipeline</h2>
    <div class="grid">
      {_chart_card("Seller Acquisition Funnel", t["funnel"], div4)}
      {_chart_card("Opportunity Win Rate by Lead Source", t["win_rate"], div5)}
    </div>
  </section>

  <section id="customers">
    <h2 class="section-title">Customer Health &amp; Churn Risk</h2>
    <div class="grid">
      {_chart_card("Customer Segments (RFM x Churn Risk)", t["segments"], div6)}
      {_table_card("Churn Watchlist", "The 10 At-Risk customers with the highest churn probability, latest snapshot.", watchlist_table)}
    </div>
  </section>

  <section id="sellers">
    <h2 class="section-title">Top Sellers</h2>
    <div class="grid">
      {_table_card("Seller Scorecard", "The 12 highest-grossing sellers, with delivery and return performance.", seller_table, full_width=True)}
    </div>
  </section>

  <section id="support">
    <h2 class="section-title">Support Case Analysis</h2>
    <div class="grid">
      {_chart_card("Support Case Volume &amp; SLA Compliance", t["cases"], div7)}
      {_table_card("Cases by Category", "SLA compliance, resolution time and satisfaction per case category.", case_table,
                   extra=case_stats)}
    </div>
  </section>

</main>
<div class="page-end">
  <div class="signature-box">
    <div class="sig-avatar">MS</div>
    <div class="sig-text">
      <div class="sig-name">Milad Shabani</div>
      <div class="sig-role">Data Engineer &amp; Data Scientist — built the data pipeline, forecasting &amp; churn models, and this dashboard, end to end.</div>
    </div>
    <a class="sig-link" href="https://miladshabani.ir/P1/" target="_blank" rel="noopener">View more of my work &rarr;</a>
  </div>
  <footer>
    MarketCo Inc. is a data-engineering / data-science portfolio project. All company, seller, customer, and CRM
    figures are synthetically generated — see <code>docs/data_dictionary.md</code> in the repository for full
    data-provenance notes. Not an official record of any real company.
  </footer>
</div>
<script>
(function () {{
  // Plotly sizes each chart once, when its script runs during parsing, and
  // afterwards only reacts to window resizes. Refit a chart whenever its box
  // changes size (layout settling, fonts loading, zoom, a sidebar opening).
  var boxes = Array.prototype.slice.call(document.querySelectorAll('.chart-box'));
  function fit(box) {{
    var gd = box.querySelector('.plotly-graph-div');
    if (gd && window.Plotly && gd.offsetWidth) Plotly.Plots.resize(gd);
  }}
  if ('ResizeObserver' in window) {{
    var pending = new Set();
    var ro = new ResizeObserver(function (entries) {{
      entries.forEach(function (e) {{ pending.add(e.target); }});
      requestAnimationFrame(function () {{ pending.forEach(fit); pending.clear(); }});
    }});
    boxes.forEach(function (b) {{ ro.observe(b); }});
  }}
  window.addEventListener('load', function () {{ boxes.forEach(fit); }});
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {{ boxes.forEach(fit); }});

  // Highlight the nav link of the section in view.
  var links = Array.prototype.slice.call(document.querySelectorAll('nav.subnav a'));
  if ('IntersectionObserver' in window) {{
    var io = new IntersectionObserver(function (entries) {{
      entries.forEach(function (e) {{
        if (!e.isIntersecting) return;
        links.forEach(function (a) {{ a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id); }});
      }});
    }}, {{ rootMargin: '-40% 0px -55% 0px' }});
    document.querySelectorAll('main > section[id]').forEach(function (s) {{ io.observe(s); }});
  }}
}})();
</script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
