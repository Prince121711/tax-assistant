"""
utils/email_service.py
─────────────────────────────────────────────────────────────────────────────
Email service for TaxShield — sends ITR and financial reports via email.

Supports:
  • Gmail (SMTP with App Password)
  • Outlook / Hotmail
  • Yahoo Mail
  • Any custom SMTP server

Setup for Gmail:
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Step Verification
  3. Go to App Passwords → Generate a 16-char password
  4. Put that password in .env as EMAIL_PASSWORD
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# ── Email config from .env ────────────────────────────────────────────────────
EMAIL_HOST     = os.getenv("EMAIL_HOST",     "smtp.gmail.com")
EMAIL_PORT     = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")   # your Gmail address
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")   # Gmail App Password
EMAIL_FROM     = os.getenv("EMAIL_FROM",     EMAIL_USERNAME)
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "TaxShield")


# ── Government / Official email addresses ─────────────────────────────────────
GOVT_EMAILS = {
    "Income Tax Department":   "efiling@incometax.gov.in",
    "GST Portal":              "helpdesk@gst.gov.in",
    "MCA (Ministry of Corporate Affairs)": "mca@mca.gov.in",
}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EMAIL FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def send_report_email(
    to_email:      str,
    to_name:       str,
    subject:       str,
    body_html:     str,
    attachment_path: Optional[str] = None,
    attachment_name: Optional[str] = None,
    cc_email:      Optional[str]   = None,
) -> dict:
    """
    Send an email with an optional PDF attachment.

    Args:
        to_email:        Recipient email address.
        to_name:         Recipient display name.
        subject:         Email subject line.
        body_html:       HTML email body.
        attachment_path: Full path to the PDF file to attach.
        attachment_name: Display name for the attachment file.
        cc_email:        Optional CC email address.

    Returns:
        {"success": True, "message": "..."} or {"success": False, "error": "..."}
    """
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        return {
            "success": False,
            "error": "Email not configured. Add EMAIL_USERNAME and EMAIL_PASSWORD to your .env file."
        }

    try:
        # ── Build message ─────────────────────────────────────────────────────
        msg = MIMEMultipart("mixed")
        msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"]      = f"{to_name} <{to_email}>"
        msg["Subject"] = subject
        if cc_email:
            msg["Cc"] = cc_email

        # ── HTML body ─────────────────────────────────────────────────────────
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        # ── Attach PDF ────────────────────────────────────────────────────────
        if attachment_path:
            path = Path(attachment_path)
            if path.exists():
                with open(path, "rb") as f:
                    part = MIMEBase("application", "pdf")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = attachment_name or path.name
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{filename}"',
                )
                msg.attach(part)
                logger.info("Attached file: %s (%d bytes)", filename, path.stat().st_size)
            else:
                logger.warning("Attachment not found: %s", attachment_path)

        # ── Send via SMTP ─────────────────────────────────────────────────────
        logger.info("Connecting to SMTP: %s:%d", EMAIL_HOST, EMAIL_PORT)
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)

            recipients = [to_email]
            if cc_email:
                recipients.append(cc_email)

            server.sendmail(EMAIL_FROM, recipients, msg.as_string())

        logger.info("Email sent successfully to %s", to_email)
        return {
            "success": True,
            "message": f"Email sent successfully to {to_email}",
        }

    except smtplib.SMTPAuthenticationError:
        error = (
            "Gmail authentication failed. "
            "Make sure you are using an App Password (not your regular Gmail password). "
            "Go to: https://myaccount.google.com/apppasswords"
        )
        logger.error("SMTP auth error: %s", error)
        return {"success": False, "error": error}

    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)
        return {"success": False, "error": f"SMTP error: {str(exc)}"}

    except Exception as exc:
        logger.exception("Email sending failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

def build_itr_email_body(
    full_name:       str,
    report_type:     str,   # "ITR-4 Sugam" or "ITR-3"
    assessment_year: str,
    gross_turnover:  float,
    net_profit:      float,
    shop_name:       str = "",
) -> str:
    """Build a professional HTML email body for ITR report emails."""

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <style>
    body     {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f4f6fb;
               margin:0; padding:0; color:#1c1c2e; }}
    .wrapper {{ max-width:600px; margin:30px auto; background:#fff;
               border-radius:12px; overflow:hidden;
               box-shadow:0 4px 24px rgba(0,0,0,0.10); }}
    .header  {{ background:#003580; padding:32px 32px 24px; text-align:center; }}
    .header h1 {{ color:#e8a020; font-size:22px; margin:0 0 4px; letter-spacing:1px; }}
    .header p  {{ color:#b0bcd4; font-size:13px; margin:0; }}
    .body    {{ padding:28px 32px; }}
    .body h2 {{ color:#003580; font-size:16px; margin:0 0 16px; }}
    .body p  {{ font-size:14px; line-height:1.7; color:#3a3a4a; margin:0 0 12px; }}
    .table   {{ width:100%; border-collapse:collapse; margin:20px 0; }}
    .table th {{ background:#003580; color:#fff; padding:10px 14px;
                text-align:left; font-size:13px; }}
    .table td {{ padding:10px 14px; font-size:13px; border-bottom:1px solid #e8edf5; }}
    .table tr:nth-child(even) td {{ background:#f0f5ff; }}
    .table td.amt {{ font-weight:600; color:#003580; text-align:right; }}
    .badge   {{ display:inline-block; background:#e8f0fa; color:#003580;
               padding:4px 12px; border-radius:20px; font-size:12px;
               font-weight:600; margin-bottom:16px; }}
    .warn    {{ background:#fff8e1; border-left:4px solid #ff6600;
               padding:12px 16px; border-radius:4px; margin:20px 0;
               font-size:13px; color:#7a4a00; }}
    .footer  {{ background:#f4f6fb; padding:20px 32px; text-align:center;
               font-size:12px; color:#8b98b8; border-top:1px solid #e8edf5; }}
    .btn     {{ display:inline-block; background:#e8a020; color:#fff;
               padding:12px 28px; border-radius:6px; text-decoration:none;
               font-weight:600; font-size:14px; margin:16px 0; }}
  </style>
</head>
<body>
<div class="wrapper">

  <!-- Header -->
  <div class="header">
    <h1>🛡 TaxShield</h1>
    <p>Smart Tax Tracking for Indian Merchants</p>
  </div>

  <!-- Body -->
  <div class="body">
    <p>Dear <strong>{full_name}</strong>,</p>

    <span class="badge">📋 {report_type} — Assessment Year {assessment_year}</span>

    <h2>Your Pre-Filled {report_type} Draft is Ready</h2>

    <p>
      Please find attached your <strong>{report_type}</strong> pre-filled draft
      generated by TaxShield for Assessment Year <strong>{assessment_year}</strong>.
      {f"This report covers income and expenses for <strong>{shop_name}</strong>." if shop_name else ""}
    </p>

    <!-- Summary table -->
    <table class="table">
      <tr>
        <th>Particulars</th>
        <th style="text-align:right">Amount</th>
      </tr>
      <tr>
        <td>Gross Turnover / Income</td>
        <td class="amt">₹ {gross_turnover:,.2f}</td>
      </tr>
      <tr>
        <td>Net Profit</td>
        <td class="amt">₹ {net_profit:,.2f}</td>
      </tr>
      <tr>
        <td>Presumptive Profit (8% of Turnover)</td>
        <td class="amt">₹ {gross_turnover * 0.08:,.2f}</td>
      </tr>
      <tr>
        <td>Assessment Year</td>
        <td class="amt">{assessment_year}</td>
      </tr>
    </table>

    <!-- Warning -->
    <div class="warn">
      ⚠ <strong>Important:</strong> This is a pre-filled <strong>draft for reference only</strong>.
      It is NOT an officially filed return. Please verify all figures with your
      Chartered Accountant before e-filing on the official portal.
    </div>

    <!-- CTA -->
    <p style="text-align:center">
      <a class="btn" href="https://www.incometax.gov.in" target="_blank">
        🔗 E-File on Income Tax Portal
      </a>
    </p>

    <p>
      <strong>Steps to e-file:</strong><br/>
      1. Open the PDF attached to this email<br/>
      2. Verify all figures with your CA<br/>
      3. Add your PAN, Aadhaar, and deduction details<br/>
      4. Login to <a href="https://www.incometax.gov.in">incometax.gov.in</a><br/>
      5. File your return online using the pre-filled figures
    </p>

    <p>Regards,<br/><strong>TaxShield Team</strong></p>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>
      Generated by TaxShield on {date.today().strftime("%d %B %Y")} &nbsp;|&nbsp;
      This is an automated email. Do not reply to this address.
    </p>
    <p>
      For official tax queries contact:
      <a href="https://www.incometax.gov.in" style="color:#003580">Income Tax Department</a>
      &nbsp;|&nbsp; Helpline: 1800-103-0025
    </p>
  </div>

</div>
</body>
</html>
"""


def build_financial_summary_email_body(
    full_name:    str,
    total_income: float,
    total_expense:float,
    profit:       float,
    tax:          float,
    shop_name:    str = "",
) -> str:
    """Build HTML email body for financial summary report."""

    profit_color = "#16a34a" if profit >= 0 else "#dc2626"
    profit_label = "Net Profit" if profit >= 0 else "Net Loss"

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <style>
    body     {{ font-family:'Segoe UI',Arial,sans-serif; background:#f4f6fb;
               margin:0; padding:0; color:#1c1c2e; }}
    .wrapper {{ max-width:600px; margin:30px auto; background:#fff;
               border-radius:12px; overflow:hidden;
               box-shadow:0 4px 24px rgba(0,0,0,0.10); }}
    .header  {{ background:#1a2744; padding:28px 32px; text-align:center; }}
    .header h1 {{ color:#e8a020; font-size:20px; margin:0 0 4px; }}
    .header p  {{ color:#8b98b8; font-size:13px; margin:0; }}
    .body    {{ padding:28px 32px; }}
    .body p  {{ font-size:14px; line-height:1.7; color:#3a3a4a; margin:0 0 12px; }}
    .card    {{ background:#f0f5ff; border-radius:8px; padding:16px 20px; margin:8px 0; }}
    .card .label {{ font-size:12px; color:#6b7280; text-transform:uppercase;
                   letter-spacing:0.06em; }}
    .card .value {{ font-size:22px; font-weight:700; margin-top:4px; }}
    .grid    {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:16px 0; }}
    .warn    {{ background:#fff8e1; border-left:4px solid #e8a020; padding:12px 16px;
               border-radius:4px; margin:16px 0; font-size:13px; color:#7a4a00; }}
    .footer  {{ background:#f4f6fb; padding:16px 32px; text-align:center;
               font-size:12px; color:#8b98b8; border-top:1px solid #e8edf5; }}
  </style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>🛡 TaxShield — Financial Summary</h1>
    <p>Generated on {date.today().strftime("%d %B %Y")}</p>
  </div>
  <div class="body">
    <p>Dear <strong>{full_name}</strong>,</p>
    <p>
      Please find attached your TaxShield Financial Summary Report
      {f"for <strong>{shop_name}</strong>" if shop_name else ""}.
    </p>
    <div class="grid">
      <div class="card">
        <div class="label">Total Income</div>
        <div class="value" style="color:#16a34a">₹ {total_income:,.2f}</div>
      </div>
      <div class="card">
        <div class="label">Total Expenses</div>
        <div class="value" style="color:#dc2626">₹ {total_expense:,.2f}</div>
      </div>
      <div class="card">
        <div class="label">{profit_label}</div>
        <div class="value" style="color:{profit_color}">₹ {abs(profit):,.2f}</div>
      </div>
      <div class="card">
        <div class="label">Estimated Tax (5%)</div>
        <div class="value" style="color:#e8a020">₹ {tax:,.2f}</div>
      </div>
    </div>
    <div class="warn">
      ⚠ This report is for internal reference. Consult a CA for official filings.
    </div>
    <p>Regards,<br/><strong>TaxShield</strong></p>
  </div>
  <div class="footer">
    TaxShield Automated Report &nbsp;|&nbsp; Do not reply to this email
  </div>
</div>
</body>
</html>
"""
