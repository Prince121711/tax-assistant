"""
utils/itr3_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates a pre-filled ITR-3 PDF for individuals/HUFs having income from
business or profession (NOT under presumptive scheme).

ITR-3 is for:
  • Income from business / profession (books of accounts maintained)
  • Capital gains
  • Multiple heads of income

Structure mirrors official CBDT ITR-3 form:
  PART A   – General Information
  PART A-BS – Balance Sheet (simplified)
  PART A-P&L – Profit & Loss Account
  Schedule BP  – Business Profit Computation
  Schedule OS  – Other Sources
  PART B-TI    – Total Income
  PART B-TTI   – Tax on Total Income
  Schedule TDS / Advance Tax
  Verification
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEPT_BLUE = DEPT_ORANGE = WHITE = BLACK = LIGHT_BLUE = LIGHT_GREY = DARK_GREY = None

def _init_colors():
    global DEPT_BLUE, DEPT_ORANGE, WHITE, BLACK, LIGHT_BLUE, LIGHT_GREY, DARK_GREY
    from reportlab.lib import colors
    DEPT_BLUE   = colors.HexColor("#003580")
    DEPT_ORANGE = colors.HexColor("#FF6600")
    WHITE       = colors.white
    BLACK       = colors.black
    LIGHT_BLUE  = colors.HexColor("#E8F0FA")
    LIGHT_GREY  = colors.HexColor("#F5F5F5")
    DARK_GREY   = colors.HexColor("#555555")


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def generate_itr3(
    file_path: str,
    # ── Personal details ───────────────────────────────────────────────────
    full_name:          str,
    pan:                str  = "XXXXXXXXXX",
    aadhaar:            str  = "",
    dob:                str  = "",
    address:            str  = "",
    city:               str  = "",
    state:              str  = "",
    pincode:            str  = "",
    phone:              str  = "",
    email:              str  = "",
    # ── Business details ───────────────────────────────────────────────────
    business_name:      str  = "",
    business_type:      str  = "Retail Shop",
    gstin:              str  = "",
    # ── Financial figures ─────────────────────────────────────────────────
    gross_turnover:     float = 0.0,
    total_expenses:     float = 0.0,
    net_profit:         float = 0.0,
    gst_collected:      float = 0.0,
    gst_paid:           float = 0.0,
    tds_deducted:       float = 0.0,
    advance_tax_paid:   float = 0.0,
    # ── Assessment year ────────────────────────────────────────────────────
    assessment_year:    str  = "",
    financial_year:     str  = "",
    # ── Category breakdown ─────────────────────────────────────────────────
    category_breakdown: Optional[dict] = None,
) -> None:
    """Generate a pre-filled ITR-3 PDF with P&L and balance sheet."""

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    except ImportError:
        raise ImportError("reportlab required. Run: pip install reportlab")

    _init_colors()

    if not assessment_year:
        y = date.today().year
        assessment_year = f"{y}-{str(y+1)[2:]}"
        financial_year  = f"{y-1}-{str(y)[2:]}"

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.2*cm, bottomMargin=1.5*cm,
    )

    W = 17.4 * cm

    def style(name, **kw):
        return ParagraphStyle(name, fontName="Helvetica", **kw)

    H1   = style("h1", fontSize=13, textColor=WHITE, fontName="Helvetica-Bold",
                 alignment=TA_CENTER, spaceAfter=2)
    H2   = style("h2", fontSize=9,  textColor=WHITE, fontName="Helvetica-Bold",
                 alignment=TA_CENTER, spaceAfter=0)
    H3   = style("h3", fontSize=8,  textColor=DEPT_BLUE, fontName="Helvetica-Bold",
                 spaceBefore=6, spaceAfter=3)
    BODY = style("body", fontSize=7.5, textColor=BLACK, leading=11)
    SMALL = style("small", fontSize=6.5, textColor=DARK_GREY, leading=9)
    NOTE = style("note", fontSize=6.5, textColor=DARK_GREY, alignment=TA_CENTER, leading=9)

    def inr(v): return f"₹ {v:,.2f}" if v else "—"

    story = []

    # ─── Banner ───────────────────────────────────────────────────────────
    hdr = Table(
        [[Paragraph("INCOME TAX DEPARTMENT — GOVERNMENT OF INDIA", H1)],
         [Paragraph(f"ITR-3 — Assessment Year {assessment_year}", H2)],
         [Paragraph(
            "For Individuals and HUFs having income from Business or Profession "
            "(Books of Accounts Maintained — Not eligible for 44AD / 44ADA Presumptive Scheme)", NOTE)]],
        colWidths=[W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,1), DEPT_BLUE),
        ("BACKGROUND",    (0,2),(-1,2), DEPT_ORANGE),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.2*cm))

    disc = Table([[Paragraph(
        "⚠  Pre-filled draft generated by TaxShield — for reference only. "
        "Verify all figures with a CA before official e-filing at https://www.incometax.gov.in",
        style("d", fontSize=6.5, textColor=DEPT_ORANGE, alignment=TA_CENTER)
    )]], colWidths=[W])
    disc.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FFF3E0")),
        ("BOX",(0,0),(-1,-1),0.5,DEPT_ORANGE),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(disc)
    story.append(Spacer(1, 0.3*cm))

    # ── Helper: section header ────────────────────────────────────────────
    def sec(title, sub=""):
        rows = [[Paragraph(title, H2)]]
        if sub: rows.append([Paragraph(sub, NOTE)])
        t = Table(rows, colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),DEPT_BLUE),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        return t

    # ── Helper: 4-col field grid ──────────────────────────────────────────
    def fld(rows_data):
        t = Table(rows_data, colWidths=[5.5*cm,5.8*cm,5.5*cm,5.6*cm])
        t.setStyle(TableStyle([
            ("FONTSIZE",(0,0),(-1,-1),7.5),
            ("TEXTCOLOR",(0,0),(0,-1),DARK_GREY),
            ("TEXTCOLOR",(2,0),(2,-1),DARK_GREY),
            ("FONTNAME",(1,0),(1,-1),"Helvetica-Bold"),
            ("FONTNAME",(3,0),(3,-1),"Helvetica-Bold"),
            ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CCCCCC")),
            ("BACKGROUND",(0,0),(0,-1),LIGHT_GREY),
            ("BACKGROUND",(2,0),(2,-1),LIGHT_GREY),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[WHITE,LIGHT_BLUE]),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),6),
        ]))
        return t

    # ── Helper: schedule money table ─────────────────────────────────────
    def mtbl(rows, cw=None):
        if cw is None: cw = [1.2*cm, 9*cm, 3.5*cm, 3.7*cm]
        t = Table(rows, colWidths=cw)
        t.setStyle(TableStyle([
            ("FONTSIZE",(0,0),(-1,-1),7.5),
            ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CCCCCC")),
            ("BACKGROUND",(0,0),(-1,0),DEPT_BLUE),
            ("TEXTCOLOR",(0,0),(-1,0),WHITE),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("ALIGN",(2,0),(-1,-1),"RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT_GREY]),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),5),
        ]))
        return t

    # ═══ PART A — GENERAL INFO ════════════════════════════════════════════
    story.append(sec("PART A — GENERAL INFORMATION"))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph("A1 — Personal Details", H3))
    story.append(fld([
        ["Name",              full_name or "—",     "Assessment Year", assessment_year],
        ["PAN",               pan,                  "Financial Year",  financial_year],
        ["Aadhaar",           aadhaar or "—",        "Date of Birth",   dob or "—"],
        ["Phone",             phone or "—",          "Email",           email or "—"],
    ]))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph("A2 — Address & Business", H3))
    story.append(fld([
        ["Address",           address or "—",        "City",            city or "—"],
        ["State",             state or "—",          "PIN",             pincode or "—"],
        ["Business Name",     business_name or full_name, "Nature",     business_type],
        ["GSTIN",             gstin or "—",          "Return Type",     "Original"],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══ PART A-P&L — PROFIT & LOSS ══════════════════════════════════════
    story.append(sec("PART A-P&L — PROFIT AND LOSS ACCOUNT",
                     "For the year ending 31st March " + financial_year.split("-")[0][:2] + financial_year.split("-")[1]))
    story.append(Spacer(1, 0.15*cm))

    # Build P&L rows from category breakdown
    pl_debit_rows  = [["Particulars (Dr.)",    "Amount (₹)", "Particulars (Cr.)", "Amount (₹)"]]
    pl_credit_rows = []

    expense_rows = []
    if category_breakdown:
        for cat, amt in category_breakdown.items():
            expense_rows.append([cat, inr(amt)])
    else:
        expense_rows = [["Business Expenses", inr(total_expenses)]]

    # Two-column P&L layout
    cr_items = [
        ("Gross Turnover / Receipts", gross_turnover),
        ("GST Collected (Output)",     gst_collected),
    ]
    dr_items = list((category_breakdown or {"Total Expenses": total_expenses}).items())
    dr_items += [("Net Profit c/d", net_profit)]

    max_rows = max(len(dr_items), len(cr_items))
    dr_items += [("", 0.0)] * (max_rows - len(dr_items))
    cr_items += [("", 0.0)] * (max_rows - len(cr_items))

    pl_data = [["Expenditure / Losses", "Amount (₹)", "Income / Gains", "Amount (₹)"]]
    for (dk, dv), (ck, cv) in zip(dr_items, cr_items):
        pl_data.append([dk, inr(dv) if dv else "—", ck, inr(cv) if cv else "—"])
    pl_data.append(["TOTAL", inr(total_expenses + net_profit), "TOTAL", inr(gross_turnover + gst_collected)])

    pl_tbl = Table(pl_data, colWidths=[6*cm, 3*cm, 6*cm, 2.4*cm])
    pl_tbl.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),7.5),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CCCCCC")),
        ("BACKGROUND",(0,0),(-1,0),DEPT_BLUE),
        ("TEXTCOLOR",(0,0),(-1,0),WHITE),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("BACKGROUND",(0,-1),(-1,-1),LIGHT_BLUE),
        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),("ALIGN",(3,0),(3,-1),"RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-2),[WHITE,LIGHT_GREY]),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(pl_tbl)
    story.append(Spacer(1, 0.3*cm))

    # ═══ PART A-BS — SIMPLIFIED BALANCE SHEET ════════════════════════════
    story.append(sec("PART A-BS — BALANCE SHEET (Simplified)",
                     "As at 31st March " + financial_year.split("-")[0][:2] + financial_year.split("-")[1]))
    story.append(Spacer(1, 0.15*cm))

    bs_data = [
        ["LIABILITIES",             "Amount (₹)",  "ASSETS",               "Amount (₹)"],
        ["Capital Account",          inr(net_profit), "Cash & Bank Balance", "—"],
        ["Reserves & Surplus",       "—",           "Debtors / Receivables","—"],
        ["Bank Loans / Overdraft",   "—",           "Stock / Inventory",    "—"],
        ["Sundry Creditors",         "—",           "Fixed Assets",         "—"],
        ["GST Payable",              inr(max(gst_collected-gst_paid,0)), "Other Assets","—"],
        ["TOTAL",                    inr(net_profit),"TOTAL",               inr(net_profit)],
    ]
    bs_tbl = Table(bs_data, colWidths=[5.8*cm, 2.9*cm, 5.8*cm, 2.9*cm])
    bs_tbl.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),7.5),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CCCCCC")),
        ("BACKGROUND",(0,0),(-1,0),DEPT_BLUE),
        ("TEXTCOLOR",(0,0),(-1,0),WHITE),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("BACKGROUND",(0,-1),(-1,-1),LIGHT_BLUE),
        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),("ALIGN",(3,0),(3,-1),"RIGHT"),
        ("ROWBACKGROUNDS",(0,1),(-1,-2),[WHITE,LIGHT_GREY]),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(bs_tbl)
    story.append(Paragraph(
        "Note: Complete Balance Sheet with all assets and liabilities must be maintained "
        "in books of accounts. Update figures above based on actual books.", SMALL))
    story.append(Spacer(1, 0.3*cm))

    # ═══ SCHEDULE BP ══════════════════════════════════════════════════════
    story.append(sec("SCHEDULE BP — BUSINESS INCOME COMPUTATION (Actual Books)"))
    story.append(Spacer(1, 0.15*cm))
    story.append(mtbl([
        ["Sl.", "Particulars",                               "Reference",      "Amount (₹)"],
        ["1",  "Net Profit as per P&L Account",             "P&L Account",     inr(net_profit)],
        ["2",  "Add: Inadmissible Expenses (if any)",       "Sec 40/40A/43B",  "—"],
        ["3",  "Less: Allowable Expenses not in P&L",       "—",               "—"],
        ["4",  "Depreciation (WDV Method) — if applicable", "Sec 32",          "—"],
        ["5",  "Income from Business (Row 1 + 2 − 3 − 4)", "",                 inr(net_profit)],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══ PART B-TI — TOTAL INCOME ═════════════════════════════════════════
    story.append(sec("PART B-TI — COMPUTATION OF TOTAL INCOME"))
    story.append(Spacer(1, 0.15*cm))
    total_taxable = max(net_profit, 0.0)

    from utils.itr4_generator import _compute_tax_new_regime
    tax_liability    = _compute_tax_new_regime(total_taxable)
    rebate_87a       = min(tax_liability, 25000.0) if total_taxable <= 700000 else 0.0
    tax_after_rebate = max(tax_liability - rebate_87a, 0.0)
    cess             = round(tax_after_rebate * 0.04, 2)
    total_tax        = round(tax_after_rebate + cess, 2)
    self_assess      = max(total_tax - tds_deducted - advance_tax_paid, 0.0)
    refund_due       = max(tds_deducted + advance_tax_paid - total_tax, 0.0)

    story.append(mtbl([
        ["Sl.", "Head of Income",                                  "Section",    "Amount (₹)"],
        ["1",  "Income from Business / Profession (Schedule BP)", "Sec 28-44",  inr(net_profit)],
        ["2",  "Income from Capital Gains",                       "—",           "—"],
        ["3",  "Income from Other Sources",                       "—",           "—"],
        ["4",  "GROSS TOTAL INCOME",                              "",            inr(total_taxable)],
        ["5",  "Less: Deductions (Chapter VI-A)",                 "80C/80D etc.","—"],
        ["6",  "TOTAL TAXABLE INCOME",                            "",            inr(total_taxable)],
    ]))
    story.append(Spacer(1, 0.2*cm))

    # ═══ PART B-TTI — TAX ON TOTAL INCOME ════════════════════════════════
    story.append(sec("PART B-TTI — TAX ON TOTAL INCOME (New Regime FY 2024-25)"))
    story.append(Spacer(1, 0.15*cm))
    story.append(mtbl([
        ["Sl.", "Particulars",                                    "Rate",          "Amount (₹)"],
        ["1",  "Tax on Total Income",                            "New Regime",    inr(tax_liability)],
        ["2",  "Less: Rebate u/s 87A",                          "If income ≤ ₹7L",inr(rebate_87a)],
        ["3",  "Tax after Rebate",                               "",               inr(tax_after_rebate)],
        ["4",  "Health & Education Cess @ 4%",                  "4% of Row 3",    inr(cess)],
        ["5",  "TOTAL TAX PAYABLE",                             "",               inr(total_tax)],
        ["6",  "Less: TDS / TCS Credit",                        "Form 26AS",      inr(tds_deducted)],
        ["7",  "Less: Advance Tax Paid",                        "Schedule IT",    inr(advance_tax_paid)],
        ["8",  "Self-Assessment Tax Payable",                   "",               inr(self_assess)],
        ["9",  "Refund Due",                                    "",               inr(refund_due) if refund_due > 0 else "Nil"],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══ VERIFICATION ═════════════════════════════════════════════════════
    story.append(sec("VERIFICATION DECLARATION"))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"I, <b>{full_name or '_______________'}</b>, declare that to the best of my knowledge "
        f"and belief, the information given in this return for Assessment Year "
        f"<b>{assessment_year}</b> is correct, complete and truly stated in accordance with "
        "the provisions of the Income Tax Act, 1961.", BODY))
    story.append(Spacer(1, 0.5*cm))
    sig = Table([
        ["Place: ___________________", "Signature: ___________________________"],
        ["Date:  ___________________", full_name or "_______________"],
    ], colWidths=[7*cm, 10.4*cm])
    sig.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,-1),8),
                              ("TOPPADDING",(0,0),(-1,-1),5),
                              ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.append(sig)
    story.append(Spacer(1, 0.3*cm))

    footer = Table([[Paragraph(
        f"Generated by TaxShield on {date.today().strftime('%d %B %Y')}  |  "
        "Pre-filled draft — NOT an officially filed return  |  "
        "E-file at: https://www.incometax.gov.in",
        style("ft", fontSize=6.5, textColor=WHITE, alignment=TA_CENTER)
    )]], colWidths=[W])
    footer.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),DEPT_BLUE),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(footer)

    doc.build(story)
    logger.info("ITR-3 PDF generated: %s", path)
