"""
bank_parser.py – Extracts income transactions from a bank statement PDF.
Looks for UPI credits and general credit entries.
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns for credit lines in a bank statement
CREDIT_KEYWORDS = ("upi", "credit", "neft", "imps", "rtgs", "credited")

# Match currency amounts like 1,23,456.78 or 12345 or 1234.56
AMOUNT_PATTERN = re.compile(r"[\d,]+(?:\.\d{1,2})?")


def extract_bank_income(pdf_path: str) -> list[float]:
    """
    Parse a bank statement PDF and return a list of credit amounts.

    Args:
        pdf_path: Path to the bank statement PDF file.

    Returns:
        List of detected credit amounts (float). Returns empty list on failure.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber is not installed. Run: pip install pdfplumber")
        return []

    path = Path(pdf_path)
    if not path.exists():
        logger.error("Bank statement file not found: %s", pdf_path)
        return []

    transactions: list[float] = []

    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if not text:
                    logger.debug("Page %d: no text extracted", page_num)
                    continue

                for line in text.split("\n"):
                    if _is_credit_line(line):
                        amount = _extract_largest_amount(line)
                        if amount and amount > 0:
                            transactions.append(amount)
                            logger.debug("Credit detected: ₹%.2f — %s", amount, line.strip())

    except Exception as exc:
        logger.exception("Failed to parse bank statement %s: %s", pdf_path, exc)

    logger.info("Extracted %d credit transactions from %s", len(transactions), path.name)
    return transactions


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_credit_line(line: str) -> bool:
    """Return True if the line appears to describe a credit/income entry."""
    lower = line.lower()
    return any(keyword in lower for keyword in CREDIT_KEYWORDS)


def _extract_largest_amount(line: str) -> float | None:
    """Extract the largest numeric value from a line (assumed to be the amount)."""
    raw_matches = AMOUNT_PATTERN.findall(line)
    amounts: list[float] = []

    for raw in raw_matches:
        try:
            value = float(raw.replace(",", ""))
            if 1.0 <= value <= 10_000_000:  # filter out obviously wrong values
                amounts.append(value)
        except ValueError:
            continue

    return max(amounts) if amounts else None
