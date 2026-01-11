from __future__ import annotations

import re
import string
from collections import defaultdict
from typing import Any, Dict, List, Tuple


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    table = str.maketrans("", "", string.punctuation)
    return re.sub(r"\s+", " ", text.translate(table)).strip()


def compute_time_metrics(work_context: Dict[str, Any]) -> Tuple[float, float, List[Dict[str, Any]]]:
    rows = work_context.get("rows") or []
    total_minutes = 0.0
    category_minutes: Dict[str, float] = defaultdict(float)
    for row in rows:
        try:
            minutes = float(row.get("estimated_minutes", 0) or 0)
        except Exception:
            minutes = 0.0
        total_minutes += minutes
        cat = row.get("category") or "uncategorized"
        category_minutes[cat] += minutes

    total_hours = total_minutes / 60 if total_minutes else 0.0
    breakdown: List[Dict[str, Any]] = []
    for cat, minutes in sorted(category_minutes.items()):
        share = (minutes / total_minutes * 100) if total_minutes else 0.0
        breakdown.append(
            {
                "category": cat,
                "minutes": round(minutes, 2),
                "hours": round(minutes / 60, 2),
                "share_percent": round(share, 2),
            }
        )
    return round(total_minutes, 2), round(total_hours, 2), breakdown


def compute_confidence(work_context: Dict[str, Any]) -> float:
    rows = work_context.get("rows") or []
    base = 0.6
    if work_context.get("hourly_rate") is not None:
        base += 0.1
    if len(rows) > 5:
        base += 0.05
    categories = {r.get("category") for r in rows if r.get("category")}
    if len(categories) > 1:
        base += 0.05
    missing_estimates = sum(1 for r in rows if r.get("estimated_minutes") in (None, ""))
    if missing_estimates > 2:
        base -= 0.1
    return max(0.0, min(1.0, round(base, 2)))


def compute_costs(total_hours: float, work_context: Dict[str, Any]) -> Dict[str, float]:
    hourly_rate = work_context.get("hourly_rate")
    monthly_cost = total_hours * float(hourly_rate)
    period = work_context.get("period") or {}
    if period.get("type") == "monthly" and period.get("working_days"):
        annual_cost = monthly_cost * 12
    else:
        annual_cost = monthly_cost * 12
    return {
        "hourly_rate": float(hourly_rate),
        "monthly_cost": round(monthly_cost, 2),
        "annual_cost": round(annual_cost, 2),
    }


def compute_friction(work_context: Dict[str, Any]) -> Dict[str, Any]:
    rows = work_context.get("rows") or []
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = normalize_text(row.get("text", ""))[:48]
        buckets[key].append(row)

    recurring = {k: v for k, v in buckets.items() if len(v) > 1 and k}
    recurring_count = sum(len(v) for v in recurring.values())
    total_rows = len(rows)
    recurring_share = (recurring_count / total_rows * 100) if total_rows else 0.0
    avoidable_percent = min(60.0, round(recurring_share * 1.25, 2))

    clusters = [
        {
            "fingerprint": k,
            "count": len(v),
            "sample_text": (v[0].get("text") or "")[:120],
        }
        for k, v in sorted(recurring.items())
    ]

    return {
        "total_rows": total_rows,
        "recurring_count": recurring_count,
        "recurring_share": round(recurring_share, 2),
        "avoidable_percent": avoidable_percent,
        "clusters": clusters,
    }


def compute_scenario(total_hours: float, costs: Dict[str, float], friction: Dict[str, Any]) -> Dict[str, Any]:
    avoidable_percent = friction.get("avoidable_percent", 0.0)
    recovered_hours = total_hours * (avoidable_percent / 100)
    hourly_rate = costs.get("hourly_rate", 0)
    recovered_monthly_cost = recovered_hours * hourly_rate
    summary = (
        f"Recover {round(recovered_hours, 2)}h ({avoidable_percent}% avoidable) "
        f"worth ${round(recovered_monthly_cost, 2)} per month"
    )
    return {
        "avoidable_percent": avoidable_percent,
        "recovered_hours": round(recovered_hours, 2),
        "recovered_monthly_cost": round(recovered_monthly_cost, 2),
        "summary": summary,
    }
