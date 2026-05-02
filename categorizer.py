"""
categorizer.py – Keyword-based expense categorisation.
Returns a category string from a predefined taxonomy.
"""

from typing import Optional

# ── Category taxonomy ─────────────────────────────────────────────────────────
CATEGORY_RULES: dict[str, list[str]] = {
    "Dairy":        ["milk", "curd", "butter", "cheese", "paneer", "ghee", "cream", "lassi"],
    "Groceries":    ["rice", "wheat", "dal", "flour", "maida", "sugar", "salt", "oil", "atta", "pulses"],
    "Vegetables":   ["onion", "potato", "tomato", "carrot", "spinach", "cabbage", "brinjal"],
    "Fruits":       ["apple", "banana", "mango", "grapes", "orange", "papaya"],
    "Transport":    ["petrol", "diesel", "fuel", "auto", "cab", "bus", "train", "toll", "parking"],
    "Food":         ["tea", "coffee", "snacks", "biscuit", "sweets", "juice", "restaurant", "hotel", "lunch", "dinner", "breakfast"],
    "Utilities":    ["electricity", "water", "gas", "internet", "broadband", "phone", "mobile", "recharge"],
    "Stationery":   ["pen", "paper", "notebook", "printer", "ink", "stapler", "envelope"],
    "Rent":         ["rent", "lease", "shop rent", "office rent"],
    "Salary":       ["salary", "wages", "staff", "employee", "labour"],
    "Repairs":      ["repair", "maintenance", "service", "fix", "plumber", "electrician"],
    "Medical":      ["medicine", "doctor", "hospital", "pharmacy", "clinic", "health"],
    "Marketing":    ["advertisement", "ads", "promotion", "banner", "flyer", "marketing", "social media"],
    "Banking":      ["bank charge", "loan", "emi", "interest", "insurance"],
    "Packaging":    ["packet", "bag", "box", "wrap", "cover", "container"],
}


def categorize_expense(item: str) -> str:
    """
    Return the best-matching category for an expense item description.

    Args:
        item: Raw expense item string (e.g., "2kg rice bag", "petrol ₹500").

    Returns:
        Category name string. Falls back to "Others" when no match is found.
    """
    normalised = item.lower().strip()

    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in normalised for keyword in keywords):
            return category

    return "Others"


def categorize_expenses_bulk(items: list[str]) -> list[tuple[str, str]]:
    """
    Categorise a list of items in bulk.

    Returns:
        List of (item, category) tuples.
    """
    return [(item, categorize_expense(item)) for item in items]
