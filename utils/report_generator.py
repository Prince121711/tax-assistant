"""
utils/report_generator.py – TaxShield Financial Summary Report (non-ITR).
Generates a branded internal report — separate from ITR-3 / ITR-4 forms.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_financial_report(
    file_path: str,
    income:      float,
    expense:     float,
    profit:      float,
    tax:         float,
    gst_payable: float = 0.0,
    alerts:      Optional[list] = None,
    user_name:   str = "Merchant",
) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        raise ImportError("reportlab required. Run: pip install reportlab")

    BRAND_DARK   = colors.HexColor("#1a2744")
    BRAND_ACCENT = colors.HexColor("#e8a020")
    TEXT_DARK    = colors.HexColor("#1c1c2e")
    TEXT_MUTED   = colors.HexColor("#6b7280")
    SUCCESS      = colors.HexColor("#16a34a")
    DANGER       = colors.HexColor("#dc2626")
    ROW_ALT      = colors.HexColor("#f8fafc")

    def style(name, **kw):
        kw.setdefault("fontName", "Helvetica")
        return ParagraphStyle(name, **kw)

    title_style    = style("T", fontSize=22, textColor=colors.white,
                            fontName="Helvetica-Bold", alignment=TA_CENTER)
    subtitle_style = style("S", fontSize=11, textColor=BRAND_ACCENT,
                            fontName="Helvetica", alignment=TA_CENTER)
    section_style  = style("Sec", fontSize=13, textColor=BRAND_DARK,
                            fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=6)
    body_style     = style("B", fontSize=10, textColor=TEXT_DARK, leading=16)
    alert_style    = style("A", fontSize=9, textColor=DANGER, fontName="Helvetica",
                            leftIndent=8, spaceBefore=2)
    footer_style   = style("F", fontSize=8, textColor=TEXT_MUTED, alignment=TA_CENTER)

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.5*cm, bottomMargin=2*cm)
    W = 17 * cm
    story = []

    # Header
    hdr = Table([
        [Paragraph("TaxShield", title_style)],
        [Paragraph("Financial Summary Report", subtitle_style)],
    ], colWidths=[W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),BRAND_DARK),
        ("TOPPADDING",(0,0),(-1,-1),16),("BOTTOMPADDING",(0,0),(-1,-1),16),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.6*cm))

    # Meta
    meta = Table([
        ["Merchant",     user_name],
        ["Report Date",  date.today().strftime("%d %B %Y")],
        ["Period",       "All recorded transactions"],
    ], colWidths=[5*cm, 12*cm])
    meta.setStyle(TableStyle([
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("TEXTCOLOR",(0,0),(0,-1),TEXT_MUTED),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(meta)
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_ACCENT, spaceAfter=12))

    # Summary table
    story.append(Paragraph("Financial Summary", section_style))
    profit_color = SUCCESS if profit >= 0 else DANGER
    sum_data = [
        ["Description", "Amount (INR)"],
        ["Total Income",         f"₹ {income:,.2f}"],
        ["Total Expenses",       f"₹ {expense:,.2f}"],
        ["Net Profit / Loss",    f"₹ {profit:,.2f}"],
        ["Estimated Tax (5%)",   f"₹ {tax:,.2f}"],
    ]
    if gst_payable:
        sum_data.append(["GST Payable", f"₹ {gst_payable:,.2f}"])

    stbl = Table(sum_data, colWidths=[10*cm, 7*cm])
    stbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),BRAND_DARK),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,0),11),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,1),(-1,-1),10),
        ("TEXTCOLOR",(0,1),(-1,-1),TEXT_DARK),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, ROW_ALT]),
        ("TEXTCOLOR",(1,3),(1,3),profit_color),
        ("FONTNAME",(0,3),(-1,3),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),10),
    ]))
    story.append(stbl)
    story.append(Spacer(1, 0.5*cm))

    # Ratios
    story.append(Paragraph("Key Ratios", section_style))
    exp_ratio    = round(expense/income*100,1) if income else 0
    profit_margin = round(profit/income*100,1) if income else 0
    tax_rate_eff = round(tax/income*100,1) if income else 0

    rtbl = Table([
        ["Metric", "Value"],
        ["Expense Ratio",        f"{exp_ratio}%"],
        ["Profit Margin",        f"{profit_margin}%"],
        ["Effective Tax Rate",   f"{tax_rate_eff}%"],
    ], colWidths=[10*cm, 7*cm])
    rtbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),BRAND_DARK),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, ROW_ALT]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),10),
    ]))
    story.append(rtbl)

    if alerts:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("Financial Alerts", section_style))
        for a in alerts:
            story.append(Paragraph(a.replace("⚠","•"), alert_style))

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEXT_MUTED))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "This report is auto-generated by TaxShield for informational purposes. "
        "Tax figures are estimates under the presumptive scheme (5% on profit). "
        "Consult a certified CA for official filings.", footer_style))
    story.append(Paragraph(
        f"Generated on {date.today().strftime('%d %B %Y')} | TaxShield v1.0",
        footer_style))

    doc.build(story)
    logger.info("Financial report saved: %s", path)
