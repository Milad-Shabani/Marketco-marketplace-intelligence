"""
Binary LightGBM classifier predicting 90-day customer churn from the
RFM + CRM engagement panel built in `features.churn_features`.

Evaluated with a **time-based split** (train on earlier snapshots,
test on the most recent one) rather than a random split - a random
split would leak future customer behavior patterns into training via
overlapping customers observed at multiple snapshots, overstating
accuracy. This mirrors exactly how the model would actually be
deployed: trained on history, scored against the current customer
base going forward.
"""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score, confusion_matrix,
)

from marketco.features.churn_features import FEATURE_COLUMNS, LABEL_COLUMN

CATEGORICAL_FEATURES = ["acquisition_channel_code", "region_code"]

PARAMS = dict(
    n_estimators=400,
    num_leaves=31,
    learning_rate=0.05,
    min_child_samples=40,
    subsample=0.85,
    subsample_freq=1,
    colsample_bytree=0.85,
    reg_lambda=1.0,
    random_state=42,
    verbosity=-1,
)


@dataclass
class ChurnModelResult:
    model: lgb.LGBMClassifier
    feature_importance: pd.Series
    threshold: float


def time_based_split(panel: pd.DataFrame, n_test_snapshots: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshots = sorted(panel["snapshot_date"].unique())
    test_snaps = snapshots[-n_test_snapshots:]
    train = panel[~panel["snapshot_date"].isin(test_snaps)]
    test = panel[panel["snapshot_date"].isin(test_snaps)]
    return train, test


def train_churn_model(train_df: pd.DataFrame, threshold: float = 0.5) -> ChurnModelResult:
    X = train_df[FEATURE_COLUMNS]
    y = train_df[LABEL_COLUMN].astype(int)

    model = lgb.LGBMClassifier(objective="binary", **PARAMS)
    model.fit(X, y, categorical_feature=CATEGORICAL_FEATURES)

    importance = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    return ChurnModelResult(model=model, feature_importance=importance, threshold=threshold)


def predict_proba(result: ChurnModelResult, feature_df: pd.DataFrame) -> np.ndarray:
    return result.model.predict_proba(feature_df[FEATURE_COLUMNS])[:, 1]


def evaluate_churn_model(result: ChurnModelResult, test_df: pd.DataFrame) -> dict:
    y_true = test_df[LABEL_COLUMN].astype(int).to_numpy()
    y_proba = predict_proba(result, test_df)
    y_pred = (y_proba >= result.threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "AUC_ROC": round(roc_auc_score(y_true, y_proba), 4),
        "Precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "Recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "F1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "True_Positives": int(tp), "False_Positives": int(fp),
        "True_Negatives": int(tn), "False_Negatives": int(fn),
        "Base_Churn_Rate_%": round(y_true.mean() * 100, 2),
        "n_test": len(y_true),
    }


def risk_tier(proba: np.ndarray) -> np.ndarray:
    return np.select(
        [proba >= 0.7, proba >= 0.4],
        ["High Risk", "Medium Risk"],
        default="Low Risk",
    )
