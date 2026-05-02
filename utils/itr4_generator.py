"""
utils/itr4_generator.py
─────────────────────────────────────────────────────────────────────────────
Generates a pre-filled ITR-4 SUGAM PDF for small Indian businesses using the
presumptive taxation scheme (Section 44AD / 44ADA / 44AE).

ITR-4 is for:
  • Individuals / HUF / Firms (other than LLP)
  • Business income under Section 44AD  (turnover ≤ ₹2 Cr)
  • Professional income under Section 44ADA (receipts ≤ ₹50 L)
  • Transport business under Section 44AE

Structure mirrors the official CBDT ITR-4 Sugam form:
  PART A  – General Information
  PART B  – Gross Total Income & Tax Computation
  Schedule BP   – Presumptive Business Income
  Schedule TDS  – TDS (if any)
  Schedule IT   – Advance Tax & Self-Assessment Tax
  PART C  – Deductions (80C etc.)
  Verification Declaration
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Colour palette (matches Income Tax dept blue/white theme) ─────────────────
DEPT_BLUE   = None   # set after reportlab import
DEPT_ORANGE = None
WHITE       = None
BLACK       = None
LIGHT_BLUE  = None
LIGHT_GREY  = None
DARK_GREY   = None


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

def generate_itr4(
    file_path: str,
    # ── User / merchant details ────────────────────────────────────────────
    full_name:     str,
    pan:           str = "XXXXXXXXXX",
    aadhaar:       str = "",
    dob:           str = "",
    address:       str = "",
    city:          str = "",
    state:         str = "",
    pincode:       str = "",
    phone:         str = "",
    email:         str = "",
    # ── Business details ───────────────────────────────────────────────────
    business_name: str = "",
    business_type: str = "Retail Shop",
    gstin:         str = "",
    # ── Financial figures (from TaxShield DB) ─────────────────────────────
    gross_turnover:     float = 0.0,
    total_expenses:     float = 0.0,
    net_profit:         float = 0.0,
    gst_collected:      float = 0.0,
    gst_paid:           float = 0.0,
    tds_deducted:       float = 0.0,
    advance_tax_paid:   float = 0.0,
    # ── Assessment year ────────────────────────────────────────────────────
    assessment_year:    str = "",
    financial_year:     str = "",
    # ── Category breakdown ─────────────────────────────────────────────────
    category_breakdown: Optional[dict] = None,
) -> None:
    """Generate a pre-filled ITR-4 Sugam PDF."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable, PageBreak,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise ImportError("reportlab is required. Run: pip install reportlab")

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
        topMargin=1.2*cm,  bottomMargin=1.5*cm,
    )

    # ── Style definitions ─────────────────────────────────────────────────
    S = getSampleStyleSheet()
    W = 17.4 * cm   # usable page width

    def style(name, **kw):
        kw.setdefault("fontName", "Helvetica")
        return ParagraphStyle(name, **kw)

    H1 = style("h1", fontSize=13, textColor=WHITE,       fontName="Helvetica-Bold",
               alignment=TA_CENTER, spaceAfter=2)
    H2 = style("h2", fontSize=9,  textColor=WHITE,       fontName="Helvetica-Bold",
               alignment=TA_CENTER, spaceAfter=0)
    H3 = style("h3", fontSize=8,  textColor=DEPT_BLUE,   fontName="Helvetica-Bold",
               spaceBefore=6, spaceAfter=3)
    BODY = style("body", fontSize=7.5, textColor=BLACK,  leading=11)
    SMALL = style("small", fontSize=6.5, textColor=DARK_GREY, leading=9)
    NOTE = style("note", fontSize=6.5, textColor=DARK_GREY,
                 alignment=TA_CENTER, leading=9)
    RIGHT = style("right", fontSize=7.5, textColor=BLACK,
                  alignment=TA_RIGHT)

    story = []

    # ═══════════════════════════════════════════════════════════════════════
    # HEADER BANNER
    # ═══════════════════════════════════════════════════════════════════════
    def _header_banner():
        hdr = Table(
            [[Paragraph("INCOME TAX DEPARTMENT — GOVERNMENT OF INDIA", H1)],
             [Paragraph(f"ITR-4 SUGAM — Assessment Year {assessment_year}", H2)],
             [Paragraph("For Individuals, HUFs and Firms (other than LLP) having income from business"
                        " / profession computed under Sections 44AD, 44ADA or 44AE", NOTE)]],
            colWidths=[W],
        )
        hdr.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,1), DEPT_BLUE),
            ("BACKGROUND",    (0,2), (-1,2), DEPT_ORANGE),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        return hdr

    story.append(_header_banner())
    story.append(Spacer(1, 0.3*cm))

    # ── Disclaimer banner ─────────────────────────────────────────────────
    disc = Table([[Paragraph(
        "⚠  This is an AI-generated pre-filled ITR-4 draft for reference only. "
        "Verify all figures with a Chartered Accountant before official e-filing on the "
        "Income Tax e-Filing portal (https://www.incometax.gov.in). "
        "Figures are auto-populated from your TaxShield transaction records.",
        style("disc", fontSize=6.5, textColor=DEPT_ORANGE, alignment=TA_CENTER, leading=9)
    )]], colWidths=[W])
    disc.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#FFF3E0")),
        ("BOX",           (0,0), (-1,-1), 0.5, DEPT_ORANGE),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(disc)
    story.append(Spacer(1, 0.4*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # SECTION HEADER helper
    # ═══════════════════════════════════════════════════════════════════════
    def section_hdr(title, subtitle=""):
        rows = [[Paragraph(title, H2)]]
        if subtitle:
            rows.append([Paragraph(subtitle, NOTE)])
        t = Table(rows, colWidths=[W])
        style_commands = [
            ("BACKGROUND",    (0,0), (-1,0), DEPT_BLUE),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]
        if subtitle:
            style_commands.append(
                ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#1a4a8a"))
            )
        t.setStyle(TableStyle(style_commands))
        return t

    # ═══════════════════════════════════════════════════════════════════════
    # FIELD TABLE helper  (label | value)
    # ═══════════════════════════════════════════════════════════════════════
    def field_table(rows_data, col_widths=None):
        if col_widths is None:
            col_widths = [5.5*cm, 6.2*cm, 5.5*cm, 6.2*cm] if len(rows_data[0])==4 \
                         else [5.5*cm, 11.9*cm]
        tbl = Table(rows_data, colWidths=col_widths)
        tbl.setStyle(TableStyle([
            ("FONTNAME",     (0,0),  (-1,-1), "Helvetica"),
            ("FONTSIZE",     (0,0),  (-1,-1), 7.5),
            ("TEXTCOLOR",    (0,0),  (0,-1),  DARK_GREY),
            ("TEXTCOLOR",    (2,0),  (2,-1),  DARK_GREY),
            ("FONTNAME",     (1,0),  (1,-1),  "Helvetica-Bold"),
            ("FONTNAME",     (3,0),  (3,-1),  "Helvetica-Bold"),
            ("GRID",         (0,0),  (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
            ("BACKGROUND",   (0,0),  (0,-1),  LIGHT_GREY),
            ("BACKGROUND",   (2,0),  (2,-1),  LIGHT_GREY),
            ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, LIGHT_BLUE]),
            ("TOPPADDING",   (0,0),  (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),  (-1,-1), 4),
            ("LEFTPADDING",  (0,0),  (-1,-1), 6),
        ]))
        return tbl

    # ═══════════════════════════════════════════════════════════════════════
    # MONEY TABLE helper  (schedule rows)
    # ═══════════════════════════════════════════════════════════════════════
    def money_table(rows_data, header=True):
        tbl = Table(rows_data, colWidths=[1.2*cm, 8.5*cm, 3.5*cm, 4.2*cm])
        style_cmds = [
            ("FONTNAME",     (0,0),  (-1,-1), "Helvetica"),
            ("FONTSIZE",     (0,0),  (-1,-1), 7.5),
            ("GRID",         (0,0),  (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING",   (0,0),  (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),  (-1,-1), 4),
            ("LEFTPADDING",  (0,0),  (-1,-1), 5),
            ("ALIGN",        (2,0),  (-1,-1), "RIGHT"),
        ]
        if header:
            style_cmds += [
                ("BACKGROUND",   (0,0), (-1,0), DEPT_BLUE),
                ("TEXTCOLOR",    (0,0), (-1,0), WHITE),
                ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ]
        tbl.setStyle(TableStyle(style_cmds))
        return tbl

    def inr(v): return f"₹ {v:,.2f}" if v else "—"
    def val(v): return str(v) if v else "—"

    # ═══════════════════════════════════════════════════════════════════════
    # PART A — GENERAL INFORMATION
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("PART A — GENERAL INFORMATION",
                             "Personal and Business Details of the Assessee"))
    story.append(Spacer(1, 0.15*cm))

    story.append(Paragraph("A1 — Personal Details", H3))
    story.append(field_table([
        ["Name of Assessee",    full_name or "—",
         "Assessment Year",     assessment_year],
        ["PAN",                 pan or "XXXXXXXXXX",
         "Financial Year",      financial_year],
        ["Aadhaar Number",      aadhaar or "— (Update in e-Filing portal)",
         "Date of Birth",       dob or "—"],
        ["Mobile / Phone",      phone or "—",
         "Email Address",       email or "—"],
    ]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("A2 — Address", H3))
    story.append(field_table([
        ["Flat / Door / Block",  address or "—",
         "City / Town",         city or "—"],
        ["State",                state or "—",
         "PIN Code",            pincode or "—"],
    ]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("A3 — Business / Profession Details", H3))
    story.append(field_table([
        ["Nature of Business",   business_type or "—",
         "Business / Trade Name",business_name or full_name],
        ["GSTIN",                gstin or "— (Not registered / Exempt)",
         "Section under which\npresumptive income\nis computed",
         "44AD — Business (Turnover ≤ ₹2 Cr)"],
        ["Status of Assessee",   "Individual",
         "Residential Status",   "Resident"],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # SCHEDULE BP — PRESUMPTIVE BUSINESS INCOME (Sec 44AD)
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("SCHEDULE BP — COMPUTATION OF PRESUMPTIVE BUSINESS INCOME",
                             "Under Section 44AD (For businesses with turnover ≤ ₹2 Crore)"))
    story.append(Spacer(1, 0.15*cm))

    # Compute presumptive profit (8% of turnover as per 44AD; 6% for digital receipts)
    presumptive_rate = 0.08
    presumptive_profit = round(gross_turnover * presumptive_rate, 2)
    # Use actual profit if higher (required under 44AD)
    declared_profit = max(net_profit, presumptive_profit)
    gross_from_expenses = round(gross_turnover - total_expenses, 2)

    story.append(money_table([
        ["Sl.", "Particulars", "Rate / Note", "Amount (₹)"],
        ["1",  "Gross Turnover / Gross Receipts from Business",
         "As per records", inr(gross_turnover)],
        ["2",  "Total Business Expenditure",
         "As per records", inr(total_expenses)],
        ["3",  "Net Profit as per Books (Turnover − Expenses)",
         "Col 1 − Col 2", inr(gross_from_expenses)],
        ["",   "", "", ""],
        ["4",  "Presumptive Income @ 8% of Gross Turnover (Sec 44AD)",
         "8% of Row 1", inr(presumptive_profit)],
        ["5",  "Presumptive Income @ 6% (for amounts received digitally)",
         "6% of digital receipts — update if applicable", "—"],
        ["6",  "Income Declared under Presumptive Scheme",
         "Higher of Row 3 or Row 4", inr(declared_profit)],
    ]))
    story.append(Spacer(1, 0.15*cm))

    # Note box
    note_txt = (
        "Note: Under Section 44AD, if actual profit is less than 8% of turnover, "
        "the assessee must declare income at 8% (or 6% for digital receipts) "
        "OR maintain books of accounts and get them audited under Sec 44AB. "
        "Row 6 shows the higher of actual profit vs. presumptive minimum."
    )
    n = Table([[Paragraph(note_txt, SMALL)]], colWidths=[W])
    n.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), colors.HexColor("#FFF8E1")),
        ("BOX",        (0,0),(-1,-1), 0.5, DEPT_ORANGE),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(n)
    story.append(Spacer(1, 0.3*cm))

    # ─── Expense Breakdown ────────────────────────────────────────────────
    if category_breakdown:
        story.append(Paragraph("Expense Category Breakdown (from TaxShield Records)", H3))
        rows = [["Sl.", "Category", "Amount (₹)", "% of Total Expenses"]]
        for i, (cat, amt) in enumerate(category_breakdown.items(), 1):
            pct = f"{(amt/total_expenses*100):.1f}%" if total_expenses else "—"
            rows.append([str(i), cat, inr(amt), pct])
        rows.append(["", "TOTAL", inr(total_expenses), "100%"])

        cat_tbl = Table(rows, colWidths=[1.2*cm, 8.5*cm, 4*cm, 3.7*cm])
        cat_tbl.setStyle(TableStyle([
            ("FONTSIZE",     (0,0),(-1,-1), 7.5),
            ("GRID",         (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
            ("BACKGROUND",   (0,0),(-1,0),  DEPT_BLUE),
            ("TEXTCOLOR",    (0,0),(-1,0),  WHITE),
            ("FONTNAME",     (0,0),(-1,0),  "Helvetica-Bold"),
            ("BACKGROUND",   (0,-1),(-1,-1),LIGHT_BLUE),
            ("FONTNAME",     (0,-1),(-1,-1),"Helvetica-Bold"),
            ("ALIGN",        (2,0),(-1,-1), "RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[WHITE, LIGHT_GREY]),
            ("TOPPADDING",   (0,0),(-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
            ("LEFTPADDING",  (0,0),(-1,-1), 5),
        ]))
        story.append(cat_tbl)
        story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # PART B — GROSS TOTAL INCOME & TAX COMPUTATION
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("PART B — GROSS TOTAL INCOME AND TAX COMPUTATION"))
    story.append(Spacer(1, 0.15*cm))

    story.append(Paragraph("B1 — Income Computation", H3))

    # Standard deduction & 80C assumptions (user should update)
    std_deduction    = 50000.0   # ₹50,000 standard deduction for salaried; 0 for business
    income_from_biz  = declared_profit
    gross_total      = income_from_biz
    deduction_80c    = 0.0
    total_deductions = deduction_80c
    total_taxable    = max(gross_total - total_deductions, 0.0)

    story.append(money_table([
        ["Sl.", "Head of Income / Deduction", "Reference", "Amount (₹)"],
        ["B1",  "Income from Business / Profession (Schedule BP Row 6)",
         "Sec 44AD", inr(income_from_biz)],
        ["B2",  "Income from House Property", "—", "—"],
        ["B3",  "Income from Capital Gains",  "—", "—"],
        ["B4",  "Income from Other Sources",  "—", "—"],
        ["B5",  "GROSS TOTAL INCOME (B1 + B2 + B3 + B4)", "", inr(gross_total)],
        ["",    "", "", ""],
        ["B6",  "Deduction under Chapter VI-A (80C / 80D etc.)", "Update manually", inr(deduction_80c)],
        ["B7",  "TOTAL TAXABLE INCOME (B5 − B6)", "", inr(total_taxable)],
    ]))
    story.append(Spacer(1, 0.2*cm))

    # Tax computation (New Regime default for FY 2024-25)
    story.append(Paragraph("B2 — Tax Computation (New Tax Regime — FY 2024-25)", H3))

    tax_liability = _compute_tax_new_regime(total_taxable)
    rebate_87a    = min(tax_liability, 25000.0) if total_taxable <= 700000 else 0.0
    tax_after_rebate = max(tax_liability - rebate_87a, 0.0)
    surcharge     = 0.0
    cess          = round(tax_after_rebate * 0.04, 2)
    total_tax_payable = round(tax_after_rebate + surcharge + cess, 2)
    tds_credit    = tds_deducted
    advance_tax   = advance_tax_paid
    self_assess_tax = max(total_tax_payable - tds_credit - advance_tax, 0.0)
    refund_due    = max(tds_credit + advance_tax - total_tax_payable, 0.0)

    story.append(money_table([
        ["Sl.", "Particulars",                                    "Rate",          "Amount (₹)"],
        ["1",  "Tax on Total Taxable Income (New Regime slabs)", "As applicable", inr(tax_liability)],
        ["2",  "Less: Rebate u/s 87A (if taxable income ≤ ₹7L)", "Up to ₹25,000", inr(rebate_87a)],
        ["3",  "Tax after Rebate",                               "",               inr(tax_after_rebate)],
        ["4",  "Surcharge",                                      "Nil (income < ₹50L)", inr(surcharge)],
        ["5",  "Health & Education Cess",                        "4% of Row 3",   inr(cess)],
        ["6",  "TOTAL TAX PAYABLE (Row 3 + 4 + 5)",             "",               inr(total_tax_payable)],
        ["",   "", "", ""],
        ["7",  "Less: TDS Deducted (from Schedule TDS)",        "",               inr(tds_credit)],
        ["8",  "Less: Advance Tax Paid (from Schedule IT)",     "",               inr(advance_tax)],
        ["9",  "Self-Assessment Tax Payable (Row 6 − 7 − 8)",   "",               inr(self_assess_tax)],
        ["10", "Refund Due (if Row 7+8 > Row 6)",               "",               inr(refund_due) if refund_due > 0 else "Nil"],
    ]))
    story.append(Spacer(1, 0.15*cm))

    # New regime slab reference
    slab_note = (
        "New Tax Regime Slabs (FY 2024-25): Up to ₹3L → Nil | ₹3L–₹7L → 5% | "
        "₹7L–₹10L → 10% | ₹10L–₹12L → 15% | ₹12L–₹15L → 20% | Above ₹15L → 30%. "
        "Rebate u/s 87A: Full tax rebate if total income ≤ ₹7 Lakh."
    )
    n2 = Table([[Paragraph(slab_note, SMALL)]], colWidths=[W])
    n2.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), LIGHT_BLUE),
        ("BOX",        (0,0),(-1,-1), 0.5, DEPT_BLUE),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("LEFTPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(n2)
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # SCHEDULE TDS — TAX DEDUCTED AT SOURCE
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("SCHEDULE TDS — TAX DEDUCTED AT SOURCE"))
    story.append(Spacer(1, 0.15*cm))
    story.append(money_table([
        ["Sl.", "Deductor Name / TAN",
         "Amount on which\nTDS Deducted (₹)",
         "TDS Amount (₹)"],
        ["1",  "— Update from Form 26AS on IT portal —",
         "—", inr(tds_deducted) if tds_deducted else "—"],
    ]))
    story.append(Paragraph(
        "Please verify TDS details from your Form 26AS / AIS on the IT e-Filing portal. "
        "Enter TAN of deductor and amount of income from which TDS was deducted.",
        SMALL))
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # SCHEDULE IT — ADVANCE TAX & SELF ASSESSMENT TAX
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("SCHEDULE IT — ADVANCE TAX AND SELF-ASSESSMENT TAX PAYMENTS"))
    story.append(Spacer(1, 0.15*cm))
    story.append(money_table([
        ["Sl.", "BSR Code / Challan Details", "Date of Deposit", "Amount (₹)"],
        ["1",  "Advance Tax — Update challan details from bank",
         "— / — / —", inr(advance_tax_paid) if advance_tax_paid else "—"],
        ["2",  "Self-Assessment Tax — To be paid before filing",
         "— / — / —", inr(self_assess_tax) if self_assess_tax > 0 else "Nil"],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # PART C — DEDUCTIONS (80C, 80D etc.)
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("PART C — DEDUCTIONS UNDER CHAPTER VI-A",
                             "Update these figures manually based on your actual investments"))
    story.append(Spacer(1, 0.15*cm))
    story.append(money_table([
        ["Sl.", "Section", "Eligible Investments / Payments", "Amount (₹)"],
        ["1",  "80C",  "LIC / PPF / ELSS / EPF / NSC / Tuition Fees (Max ₹1.5L)", "—"],
        ["2",  "80CCD(1B)", "NPS Self Contribution (Additional ₹50,000)", "—"],
        ["3",  "80D",  "Health Insurance Premium (Self/Family — Max ₹25,000)", "—"],
        ["4",  "80E",  "Interest on Education Loan", "—"],
        ["5",  "80G",  "Donations to Approved Funds / Charities", "—"],
        ["6",  "80TTA","Interest on Savings Bank Account (Max ₹10,000)", "—"],
        ["",   "",     "TOTAL DEDUCTIONS (Update manually)", inr(0.0)],
    ]))
    story.append(Paragraph(
        "Note: Deductions under Chapter VI-A are NOT available under the New Tax Regime "
        "except 80CCD(2) [employer NPS contribution] and 80CCH [Agnipath scheme]. "
        "Switch to Old Regime if deductions make it beneficial — consult your CA.",
        SMALL))
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # GST SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("GST SUMMARY (From TaxShield Records — Cross-check with GSTR)"))
    story.append(Spacer(1, 0.15*cm))
    gst_payable = max(gst_collected - gst_paid, 0.0)
    story.append(field_table([
        ["GSTIN",              gstin or "Not Registered",
         "GST Collected (Output)", inr(gst_collected)],
        ["Turnover (as filed\nin GSTR-1)",
         inr(gross_turnover),
         "GST Paid (Input Credit)", inr(gst_paid)],
        ["Net GST Payable\n(Output − Input)",
         inr(gst_payable),
         "GST Filing Status",       "Verify in GSTN Portal"],
    ]))
    story.append(Spacer(1, 0.3*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # SUMMARY SNAPSHOT
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("SUMMARY SNAPSHOT — KEY FIGURES"))
    story.append(Spacer(1, 0.15*cm))

    snap = Table([
        ["Gross Turnover",        inr(gross_turnover),
         "Total Tax Payable",     inr(total_tax_payable)],
        ["Declared Profit (44AD)",inr(declared_profit),
         "TDS Credit",            inr(tds_credit)],
        ["Total Expenses",        inr(total_expenses),
         "Self-Assessment Tax",   inr(self_assess_tax)],
        ["GST Payable",           inr(gst_payable),
         "Refund Due",            inr(refund_due) if refund_due > 0 else "Nil"],
    ], colWidths=[4.5*cm, 4*cm, 4.5*cm, 4.4*cm])
    snap.setStyle(TableStyle([
        ("FONTSIZE",     (0,0),(-1,-1), 8),
        ("FONTNAME",     (1,0),(1,-1),  "Helvetica-Bold"),
        ("FONTNAME",     (3,0),(3,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",    (0,0),(0,-1),  DARK_GREY),
        ("TEXTCOLOR",    (2,0),(2,-1),  DARK_GREY),
        ("TEXTCOLOR",    (1,0),(1,-1),  DEPT_BLUE),
        ("TEXTCOLOR",    (3,0),(3,-1),  DEPT_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[WHITE, LIGHT_BLUE]),
        ("TOPPADDING",   (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("LEFTPADDING",  (0,0),(-1,-1), 8),
    ]))
    story.append(snap)
    story.append(Spacer(1, 0.4*cm))

    # ═══════════════════════════════════════════════════════════════════════
    # VERIFICATION DECLARATION
    # ═══════════════════════════════════════════════════════════════════════
    story.append(section_hdr("VERIFICATION DECLARATION"))
    story.append(Spacer(1, 0.2*cm))

    ver_text = (
        "I, <b>{name}</b>, son/daughter of _________________, solemnly declare that to the best "
        "of my knowledge and belief, the information given in this return and the schedules "
        "thereto is correct and complete and that the amount of total income and other "
        "particulars shown therein are truly stated and are in accordance with the provisions "
        "of the Income Tax Act, 1961, in respect of income and other matters for the "
        "previous year relevant to the Assessment Year {ay}."
    ).format(name=full_name or "_______________", ay=assessment_year)

    story.append(Paragraph(ver_text, BODY))
    story.append(Spacer(1, 0.5*cm))

    sig_tbl = Table([
        ["Place:  ___________________",
         "Signature of Assessee / Authorised Representative"],
        ["Date:   ___________________",
         full_name or "_______________"],
        ["", "(Full Name)"],
    ], colWidths=[7*cm, 10.4*cm])
    sig_tbl.setStyle(TableStyle([
        ("FONTSIZE",    (0,0),(-1,-1), 8),
        ("TOPPADDING",  (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("ALIGN",       (1,0),(-1,-1), "CENTER"),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 0.3*cm))

    # ─── Footer ───────────────────────────────────────────────────────────
    footer = Table([[Paragraph(
        f"Generated by TaxShield on {date.today().strftime('%d %B %Y')}  |  "
        "This is a pre-filled draft — NOT an officially filed return  |  "
        "E-file at: https://www.incometax.gov.in",
        style("footer", fontSize=6.5, textColor=WHITE, alignment=TA_CENTER, leading=9)
    )]], colWidths=[W])
    footer.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), DEPT_BLUE),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
    ]))
    story.append(footer)

    # ── Build PDF ─────────────────────────────────────────────────────────
    doc.build(story)
    logger.info("ITR-4 PDF generated: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# TAX SLAB CALCULATION — NEW REGIME FY 2024-25
# ══════════════════════════════════════════════════════════════════════════════

def _compute_tax_new_regime(income: float) -> float:
    """
    Compute income tax under the New Tax Regime (FY 2024-25 / AY 2025-26).
    Slabs: 0-3L→0%, 3-7L→5%, 7-10L→10%, 10-12L→15%, 12-15L→20%, >15L→30%
    """
    slabs = [
        (300_000,  0.00),
        (700_000,  0.05),
        (1_000_000,0.10),
        (1_200_000,0.15),
        (1_500_000,0.20),
        (float("inf"), 0.30),
    ]
    tax = 0.0
    prev = 0.0
    for limit, rate in slabs:
        if income <= prev:
            break
        taxable = min(income, limit) - prev
        tax += taxable * rate
        prev = limit
    return round(tax, 2)
