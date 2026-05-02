"""
analysis_service.py – Rule-based financial health analysis for a user's data.
"""

from typing import TypedDict


class FinancialReport(TypedDict):
    income:      float
    expense:     float
    profit:      float
    gst_payable: float
    risk_level:  str
    alerts:      list[str]
    suggestions: list[str]


# Tax rate assumed for small businesses (5% presumptive scheme)
PRESUMPTIVE_TAX_RATE = 0.05

# Threshold: if expenses are less than 30 % of income, flag possible missing records
LOW_EXPENSE_RATIO = 0.30


def analyze_financials(
    income: float,
    expense: float,
    gst_in: float = 0.0,
    gst_out: float = 0.0,
) -> FinancialReport:
    """
    Analyse a user's financial data and return risk level, alerts, and suggestions.

    Args:
        income:  Total income (INR).
        expense: Total recorded expenses (INR).
        gst_in:  Input GST from purchases.
        gst_out: Output GST from sales.

    Returns:
        A FinancialReport dict with profit, GST payable, risk level, alerts, and suggestions.
    """
    profit: float = income - expense
    gst_payable: float = max(gst_out - gst_in, 0.0)

    alerts: list[str] = []
    suggestions: list[str] = []
    risk: str = "LOW"

    # ── Rule 1: Suspiciously low expenses relative to income ─────────────────
    if income > 0 and expense < income * LOW_EXPENSE_RATIO:
        risk = "HIGH"
        alerts.append(
            f"⚠ Income ₹{income:,.2f} but expenses only ₹{expense:,.2f} "
            f"({(expense / income * 100):.1f}% of income). Possible missing records."
        )
        suggestions.append("Upload purchase bills and invoices to capture all deductible expenses.")

    # ── Rule 2: No expenses at all ────────────────────────────────────────────
    if expense == 0:
        risk = "HIGH"
        alerts.append("⚠ No expenses recorded for this period.")
        suggestions.append("Add purchase records and supplier bills to reduce taxable profit.")

    # ── Rule 3: Operating at a loss ───────────────────────────────────────────
    if profit < 0:
        if risk != "HIGH":
            risk = "MEDIUM"
        alerts.append(f"⚠ Operating at a loss of ₹{abs(profit):,.2f}.")
        suggestions.append("Review high-cost expense categories and identify areas to reduce spend.")

    # ── Rule 4: High GST payable ──────────────────────────────────────────────
    if gst_payable > 1_000:
        if risk == "LOW":
            risk = "MEDIUM"
        alerts.append(f"⚠ GST payable of ₹{gst_payable:,.2f} detected.")
        suggestions.append("Record more supplier invoices to increase input GST credit.")

    # ── Rule 5: High estimated tax ────────────────────────────────────────────
    estimated_tax = profit * PRESUMPTIVE_TAX_RATE
    if estimated_tax > 10_000:
        if risk == "LOW":
            risk = "MEDIUM"
        alerts.append(f"⚠ Estimated tax liability of ₹{estimated_tax:,.2f}.")
        suggestions.append("Consult a tax advisor about optimising deductions before the financial year ends.")

    return FinancialReport(
        income=income,
        expense=expense,
        profit=profit,
        gst_payable=gst_payable,
        risk_level=risk,
        alerts=alerts,
        suggestions=suggestions,
    )
