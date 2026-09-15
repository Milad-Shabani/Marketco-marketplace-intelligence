"""
CRM activity log, modeled as the Dynamics 365 **Activity** entity
(phone calls, emails, tasks) - the record of every touchpoint a sales
or support rep logs against a Lead, Opportunity, or Case. Volume is
derived from the pipeline/case tables already generated (a handful of
activities per lead/opportunity as it's worked, a couple per case as
it's handled), so activity counts are a genuine measure of "how much
CRM work happened" rather than an arbitrary log.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ACTIVITY_TYPES = ["Phone Call", "Email", "Task", "Meeting"]
ACTIVITY_TYPE_PROBS = [0.40, 0.35, 0.15, 0.10]


def generate_activities(
    leads: pd.DataFrame,
    opportunities: pd.DataFrame,
    cases: pd.DataFrame,
    seed: int = 71,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    counter = 0

    for lead in leads.itertuples(index=False):
        n_acts = rng.integers(1, 5)
        base_date = pd.Timestamp(lead.created_date)
        for k in range(n_acts):
            counter += 1
            act_date = base_date + pd.Timedelta(days=int(rng.integers(0, 20)))
            rows.append({
                "activity_id": f"ACT-{counter:07d}", "regarding_type": "Lead", "regarding_id": lead.lead_id,
                "activity_type": rng.choice(ACTIVITY_TYPES, p=ACTIVITY_TYPE_PROBS),
                "activity_date": act_date.strftime("%Y-%m-%d"),
            })

    for opp in opportunities.itertuples(index=False):
        n_acts = rng.integers(2, 7)
        base_date = pd.Timestamp(opp.created_date)
        for k in range(n_acts):
            counter += 1
            act_date = base_date + pd.Timedelta(days=int(rng.integers(0, 45)))
            rows.append({
                "activity_id": f"ACT-{counter:07d}", "regarding_type": "Opportunity", "regarding_id": opp.opportunity_id,
                "activity_type": rng.choice(ACTIVITY_TYPES, p=ACTIVITY_TYPE_PROBS),
                "activity_date": act_date.strftime("%Y-%m-%d"),
            })

    for case in cases.itertuples(index=False):
        n_acts = rng.integers(1, 3)
        base_date = pd.Timestamp(case.created_date)
        for k in range(n_acts):
            counter += 1
            act_date = base_date + pd.Timedelta(days=int(rng.integers(0, 3)))
            rows.append({
                "activity_id": f"ACT-{counter:07d}", "regarding_type": "Case", "regarding_id": case.case_id,
                "activity_type": rng.choice(["Phone Call", "Email"], p=[0.55, 0.45]),
                "activity_date": act_date.strftime("%Y-%m-%d"),
            })

    activities = pd.DataFrame(rows)
    return activities.sort_values("activity_date").reset_index(drop=True)
