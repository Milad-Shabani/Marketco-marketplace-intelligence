# Methodology

## 1. Data generation

- **Catalog & network** (`catalog.py`, `network.py`, `customers.py`):
  9 categories x ~17 SKUs, 5 regional warehouses, 260 seller Accounts
  (tiered Bronze->Platinum with tier-dependent order share and
  fulfillment reliability), and 36,000 Contacts with registration
  dates spread from 2020 through the end of the study window (biased
  toward later dates, reflecting marketplace growth).
- **Promotional calendar** (`calendar_events.py`): four recurring
  mega-sale events per year - a Nowruz shopping season (mid-March), a
  mid-year flagship sale (early July), a Black-Friday-style "MarketCo
  Friday" (late November, the single biggest spike of the year), and
  a Yalda-night sale (December 20-21) - each category reacting
  according to its own `mega_sale_sensitivity` (electronics and
  digital goods react far more than grocery).
- **Orders** (`orders.py`): ~579,000 rows generated with a fully
  vectorized approach - a single `(day x category)` expected-volume
  grid is flattened and sampled once via `np.random.choice` to assign
  every order's date and category simultaneously, rather than looping
  per day. Customers are sampled per unique order-day (not per order)
  from those already registered by that date, weighted by a lognormal
  purchase-propensity score - this is what makes the RFM/churn
  features later meaningful (some customers are genuinely "big
  spenders", not just noise). Seller, warehouse, delivery, payment,
  and return fields are drawn from realistic conditional
  distributions (seller tier -> order share; seller reliability +
  warehouse region -> on-time delivery; category -> return rate).
- **CRM pipeline** (`crm_pipeline.py`): every onboarded seller traces
  back to a Won Lead -> Opportunity pair with dates that are
  internally consistent (lead created before the opportunity, which
  closes exactly on the onboarding date) - plus lost leads/
  opportunities (funnel drop-off) and Account Expansion opportunities
  against existing top-tier sellers.
- **Cases & Activities** (`cases.py`, `activities.py`): support cases
  are triggered by genuine order-level events (late delivery, return,
  defect, payment risk) rather than sampled independently, so a spike
  in late deliveries during a mega-sale event produces a matching
  spike in support cases a few days later. Activities are derived
  from the lead/opportunity/case tables (a handful of logged touches
  per record), not an arbitrary count.

**Simplification note**: each order row represents one product line
(quantity 1-3) rather than a fully normalized multi-line order/
order-line schema - a deliberate scope decision to keep the fact
table single-grain and directly analyzable, documented here rather
than silently assumed.

## 2. Operations forecasting: order volume

`features/build_features.py` aggregates orders to weekly grain per
category and builds lag (1/2/3/4/8/52 week), rolling mean/std
(4/8/12 week), calendar, and **distance-to-nearest-mega-sale-event**
features - the last one lets the model anticipate a spike before it
happens and recognize the comedown after, rather than only reacting
to lagged history.

A single **global LightGBM model** (`models/order_forecast_model.py`)
is trained across all 9 category series together with two quantile
objectives (P50, P95) - the same "one model, not N per-series models"
architecture used in the companion PharmaPulse project, and the P95
quantile again doubles as a capacity-planning buffer (warehouse
staffing, courier capacity) for exactly the moments - mega-sale weeks
- when capacity planning matters most.

**Backtest results** (held-out final 8 weeks): network-wide WAPE
**9.3%**, R² **0.82**, P95 coverage **90.3%**. Per-category error is
concentrated almost entirely in mega-sale weeks (MarketCo Friday week:
-10% to -14%) while non-event weeks forecast within 1-3.5% - a real
and honestly reported finding: **spike magnitude is inherently harder
to forecast precisely than steady-state demand**, and the P95 band
(not just the P50 point forecast) is what a capacity planner should
actually be sizing against for event weeks.

## 3. CRM analytics: churn prediction

`features/churn_features.py` builds a **multi-snapshot panel**: at
each of 14 monthly snapshots, every customer active in the trailing
180 days becomes one training row, with RFM (recency/frequency/
monetary) features plus CRM engagement signals (support case volume,
average CSAT) computed **only from data before the snapshot** - no
leakage. The label is whether that customer placed zero orders in the
following 90 days (the standard "went quiet" churn definition for a
non-subscription marketplace).

`models/churn_model.py` trains a LightGBM binary classifier, evaluated
with a **time-based split** (train on the first 12 snapshots, test on
the final 2) rather than a random split - a random split would leak
future behavior patterns via customers observed at multiple
snapshots, overstating accuracy.

**Results** (held-out test snapshots, ~52,455 customer-snapshot rows):

| Metric | Value |
|---|---:|
| AUC-ROC | 0.781 |
| Precision @ 0.5 threshold | 0.573 |
| Recall @ 0.5 threshold | 0.158 |
| Base churn rate | 26.1% |

The low recall at the default 0.5 probability threshold is a genuine
and important finding, not a flaw to hide: for a retention-campaign
use case, missing a true churner is usually far more costly than
wasting a discount offer on a customer who wouldn't have churned
anyway, so a real deployment should flag customers by **risk tier**
(the dashboard's High/Medium/Low risk buckets, `models.churn_model.risk_tier`)
or by top-K percentile rather than a fixed 0.5 cutoff. AUC 0.78 means
the model ranks at-risk customers well even though a single threshold
undersells its usefulness.

Top churn drivers by feature importance: `tenure_days`,
`monetary_180d`, `avg_order_value`, `avg_csat_180d`, `recency_days` -
i.e. how long someone has been a customer, how much and how often
they spend, and how well their support experience went, dominate over
raw case-count or marketing-channel features.

## 4. RFM segmentation

`planning/rfm_segmentation.py` combines classic RFM quintile scoring
with the churn model's probability into six named segments
(Champions, Loyal, At Risk, New, Hibernating, Others) - the "customer
health" view used throughout the dashboard, so a churn probability
number becomes an actionable bucket rather than a raw score analysts
have to interpret themselves.

Risk cutoffs are **percentile-based** (the riskiest 20% of this
snapshot's own churn-probability distribution) rather than a fixed
absolute threshold such as "probability >= 0.6". A well-calibrated
classifier trained on an imbalanced ~25% base rate rarely pushes many
raw scores past a high absolute cutoff - in this dataset, probabilities
top out around 0.74, so an absolute 0.6 threshold flagged only 20 of
26,567 customers as "At Risk" the first time this was tried. Ranking
within the snapshot instead guarantees the segment always reflects a
meaningful, actionable cohort (roughly 3-4% of the base, ~890
customers) regardless of where the model's raw probabilities happen
to sit.

## 5. CRM funnel & operations metrics

`planning/crm_funnel.py` computes the standard Lead -> Opportunity ->
Won conversion funnel and win rate by lead source. The funnel is
built to be **strictly monotonic**: an earlier version counted
Account Expansion opportunities (deals against sellers already
onboarded, with no Lead behind them at all) in the same "Opportunities"
total as new-seller-acquisition deals, which could put more
opportunities on the board than there were leads to produce them -
not a valid funnel shape. `compute_acquisition_funnel_stages` fixes
this by restricting every stage to `opportunity_type == "New Seller
Onboarding"`, so each stage is a genuine subset of the one above it:
Leads (754) -> Opportunities (457) -> Won/Onboarded (260) ->
High-Performing, Gold/Platinum tier (56).

`planning/ops_metrics.py` computes warehouse on-time delivery
performance, a seller scorecard (GMV, on-time rate, return rate),
support-case SLA compliance/CSAT by case category, full 2-year
monthly GMV trend with year-over-year growth, seller-tier revenue
contribution (connecting the CRM Account tier field to what each
tier actually produces commercially - Platinum sellers run a
93% on-time rate vs. Bronze's 86%, for example), and lifetime GMV
per customer by acquisition channel (connecting a Contact-level CRM
field to the commercial outcome it's meant to predict).

## 6. Reporting layer

Both `reporting/excel_report.py` (an 8-sheet workbook with native
Excel charts) and `reporting/html_dashboard.py` (a standalone,
interactive Plotly dashboard in an indigo/violet/teal theme, on a
white canvas) are built from exactly the same computed tables in
`scripts/run_pipeline.py` - one source of truth, two presentation
formats.

**A charting lesson worth documenting.** Plotly's native `Funnel`
trace, and its `Pie`/donut legend and outside-label positioning,
both rendered unreliably inside this dashboard's responsive
(`config={"responsive": True}`) flex-card layout - labels and even
entire chart segments would silently fail to appear, in ways that
didn't reproduce in a minimal standalone test page. Rather than
chase a browser/library-version-specific rendering quirk indefinitely,
both charts were rebuilt as horizontal bar charts - the same
proven-reliable rendering path already used by every other chart on
the page - with the stage/segment name, count, and percentage folded
into the y-axis label instead of relying on in-chart text placement.
This is also why the dashboard looks visually consistent (the
original ask): every chart on the page now shares one rendering
pattern instead of mixing bar, funnel, and pie chart types.
