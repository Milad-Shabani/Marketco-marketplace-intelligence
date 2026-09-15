"""
Classic RFM (Recency, Frequency, Monetary) customer segmentation,
combined with the churn model's risk score into named, business-ready
segments - the standard CRM customer-health view.

Segments (in priority order):
  * **Champions**    - low risk, high frequency & monetary value
  * **Loyal**        - low/medium risk, solid repeat purchasing
  * **At Risk**      - high churn-risk score but historically valuable
  * **New**          - short tenure, not enough history to score confidently
  * **Hibernating**  - high recency (long time since last order), low risk score (already effectively gone quiet, not urgent to save)
  * **Others**       - everyone else

Risk cutoffs are **percentile-based** (top/bottom X% of this
snapshot's own churn-probability distribution) rather than fixed
absolute thresholds (e.g. "probability >= 0.6"). A well-calibrated
classifier on an imbalanced label rarely pushes many scores past a
high absolute cutoff - in practice this dataset's probabilities top
out well under 0.75 - so an absolute threshold can silently flag
almost nobody. Ranking within the snapshot guarantees the "At Risk"
segment always reflects a meaningful, actionable cohort (the actual
riskiest fifth of the customer base) regardless of where the model's
raw probabilities happen to sit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def score_rfm_quintiles(panel_latest: pd.DataFrame) -> pd.DataFrame:
    df = panel_latest.copy()
    df["R_score"] = pd.qcut(df["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    df["F_score"] = pd.qcut(df["frequency_180d"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    df["M_score"] = pd.qcut(df["monetary_180d"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    df["RFM_score"] = df["R_score"] + df["F_score"] + df["M_score"]
    return df


def assign_segments(panel_latest: pd.DataFrame, churn_proba: np.ndarray) -> pd.DataFrame:
    df = score_rfm_quintiles(panel_latest)
    df["churn_probability"] = churn_proba
    df["churn_percentile"] = df["churn_probability"].rank(pct=True)

    conditions = [
        (df["RFM_score"] >= 12) & (df["churn_percentile"] < 0.50),
        (df["churn_percentile"] >= 0.80) & (df["M_score"] >= 3),
        (df["tenure_days"] <= 120),
        (df["RFM_score"] >= 8) & (df["churn_percentile"] < 0.70),
        (df["R_score"] <= 2) & (df["churn_percentile"] < 0.60),
    ]
    choices = ["Champions", "At Risk", "New", "Loyal", "Hibernating"]
    df["segment"] = np.select(conditions, choices, default="Others")
    return df
