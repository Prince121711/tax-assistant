"""
insights_service.py – Spending pattern analysis and financial insights.
"""

from collections import Counter
from typing import TypedDict


class SpendingPatternResult(TypedDict):
    top_category:          str
    category_distribution: dict[str, float]
    total_spent:           float
    category_totals:       dict[str, float]


def analyze_spending_pattern(expenses: list) -> SpendingPatternResult:
    """
    Analyse expense records to surface spending patterns.

    Args:
        expenses: List of Expense ORM objects with `.category` and `.amount` attributes.

    Returns:
        A SpendingPatternResult with category breakdown, totals, and the top category.
    """
    if not expenses:
        return SpendingPatternResult(
            top_category="None",
            category_distribution={},
            total_spent=0.0,
            category_totals={},
        )

    # ── Aggregate by category ─────────────────────────────────────────────────
    category_totals: dict[str, float] = {}
    for expense in expenses:
        cat = expense.category or "Others"
        category_totals[cat] = category_totals.get(cat, 0.0) + (expense.amount or 0.0)

    total_spent = sum(category_totals.values())

    # ── Percentage distribution ───────────────────────────────────────────────
    category_distribution: dict[str, float] = {
        cat: round((amount / total_spent) * 100, 2)
        for cat, amount in category_totals.items()
    } if total_spent > 0 else {}

    top_category = max(category_totals, key=category_totals.get) if category_totals else "None"

    return SpendingPatternResult(
        top_category=top_category,
        category_distribution=category_distribution,
        total_spent=round(total_spent, 2),
        category_totals={k: round(v, 2) for k, v in category_totals.items()},
    )
