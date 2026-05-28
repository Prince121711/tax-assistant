"""
Main.py – TaxShield FastAPI application entry point.

Run with:
    uvicorn Main:app --reload
"""

import os
import uuid
import shutil
import logging
from datetime import date as calendar_date
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import calendar
import models
import schemas
import crud
from database import engine, get_db
from voice import process_voice_expense
from bank_parser import extract_bank_income
from ocr_engine import process_bill, is_supported_image, get_api_quality_stats, clear_api_cache
from insights_service import analyze_spending_pattern
from analysis_service import analyze_financials
from categorizer import categorize_expense
from auth import hash_password, verify_password, create_access_token
from dotenv import load_dotenv
load_dotenv("api.env")  # Load email config
load_dotenv(".env")     # Then load other config

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("taxshield")

# ── Database setup ────────────────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

# ── Upload / report directories ───────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
AUDIO_DIR  = Path("audio")
REPORT_DIR = Path("reports")

for directory in (UPLOAD_DIR, AUDIO_DIR, REPORT_DIR):
    directory.mkdir(exist_ok=True)

# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="TaxShield API",
    description="Financial tracking, GST management, and tax estimation for small businesses.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Health"])
def root():
    return {"message": "TaxShield API is running", "version": "1.0.0"}


# ══════════════════════════════════════════════════════════════════════════════
# API MONITORING & QUALITY METRICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/quality-stats", tags=["Monitoring"])
def get_quality_stats():
    """
    Get current OCR/Vision API quality metrics.
    Useful for monitoring dashboard to detect when quota is exhausted.
    
    Response:
      - total_requests: Total number of extraction attempts
      - success_rate_pct: Percentage of successful extractions
      - vision_api_failures: Count of API errors (including rate limits)
      - regex_fallbacks: Count of fallbacks to regex (lower quality)
      
    When success_rate_pct drops below 50%, it typically means:
      - Gemini API quota is exhausted
      - Need to switch to cached results or alternative provider
    """
    return get_api_quality_stats()


@app.post("/api/cache/clear", tags=["Admin"])
def clear_cache():
    """
    Manually clear the OCR extraction cache.
    Useful for testing or when quota resets.
    WARNING: This will force re-extraction of all scanned bills.
    """
    return clear_api_cache()


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — REGISTER & LOGIN
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/auth/register",
    response_model=schemas.TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new merchant account.
    Returns a JWT token so the user is logged in immediately after signup.
    """
    # ── Check username uniqueness ─────────────────────────────────────────────
    existing_user = db.query(models.User).filter(
        models.User.username == payload.username
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken. Please choose a different one.",
        )

    # ── Check phone uniqueness ────────────────────────────────────────────────
    existing_phone = db.query(models.User).filter(
        models.User.phone == payload.phone
    ).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already registered.",
        )

    # ── Create user ───────────────────────────────────────────────────────────
    new_user = models.User(
        username      = payload.username,
        password_hash = hash_password(payload.password),
        full_name     = payload.full_name,
        phone         = payload.phone,
        email         = payload.email,
        shop_name     = payload.shop_name,
        gstin         = payload.gstin,
        income_type   = payload.income_type,
        business_type = payload.business_type,
        city          = payload.city,
        state         = payload.state,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info("New merchant registered: %s  (id=%d)", new_user.username, new_user.id)

    token = create_access_token(new_user.id, new_user.username)

    return schemas.TokenResponse(
        access_token  = token,
        user_id       = new_user.id,
        username      = new_user.username,
        full_name     = new_user.full_name,
        income_type   = new_user.income_type,
        business_type = new_user.business_type,
        shop_name     = new_user.shop_name,
    )


@app.post(
    "/auth/login",
    response_model=schemas.TokenResponse,
    tags=["Auth"],
)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Login with username and password.
    Returns a JWT token and merchant profile on success.
    """
    from datetime import datetime, timezone

    user = db.query(models.User).filter(
        models.User.username == payload.username.lower()
    ).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Update last login timestamp
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    logger.info("Login successful: %s  (id=%d)", user.username, user.id)

    token = create_access_token(user.id, user.username)

    return schemas.TokenResponse(
        access_token  = token,
        user_id       = user.id,
        username      = user.username,
        full_name     = user.full_name,
        income_type   = user.income_type,
        business_type = user.business_type,
        shop_name     = user.shop_name,
    )


@app.get(
    "/auth/profile",
    response_model=schemas.UserProfile,
    tags=["Auth"],
)
def get_profile(user_id: int, db: Session = Depends(get_db)):
    """Return the full merchant profile for a given user_id."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


# ══════════════════════════════════════════════════════════════════════════════
# INCOME ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/income",
    response_model=schemas.IncomeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Income"],
)
def add_income(income: schemas.IncomeCreate, db: Session = Depends(get_db)):
    """Record a new income entry."""
    return crud.create_income(db, income)


@app.get(
    "/income",
    response_model=list[schemas.IncomeResponse],
    tags=["Income"],
)
def list_incomes(
    user_id: int,
    skip: int  = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """List all income records for a user with pagination."""
    return crud.get_incomes(db, user_id, skip=skip, limit=limit)


@app.put(
    "/income/{income_id}",
    response_model=schemas.IncomeResponse,
    tags=["Income"],
)
def update_income(income_id: int, updates: schemas.IncomeUpdate, db: Session = Depends(get_db)):
    """Update an existing income record."""
    return crud.update_income(db, income_id, updates)


@app.delete("/income/{income_id}", tags=["Income"])
def delete_income(income_id: int, db: Session = Depends(get_db)):
    """Delete an income record."""
    return crud.delete_income(db, income_id)


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/expense",
    response_model=schemas.ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Expense"],
)
def add_expense(expense: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    """Record a new expense entry."""
    return crud.create_expense(db, expense)


@app.get(
    "/expense",
    response_model=list[schemas.ExpenseResponse],
    tags=["Expense"],
)
def list_expenses(
    user_id: int,
    skip: int  = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """List all expense records for a user with pagination."""
    return crud.get_expenses(db, user_id, skip=skip, limit=limit)


@app.put(
    "/expense/{expense_id}",
    response_model=schemas.ExpenseResponse,
    tags=["Expense"],
)
def update_expense(expense_id: int, updates: schemas.ExpenseUpdate, db: Session = Depends(get_db)):
    """Update an existing expense record."""
    return crud.update_expense(db, expense_id, updates)


@app.delete("/expense/{expense_id}", tags=["Expense"])
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    """Delete an expense record."""
    return crud.delete_expense(db, expense_id)


# ══════════════════════════════════════════════════════════════════════════════
# SCAN & VOICE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/scan-bill", tags=["Upload"])
async def scan_bill(
    user_id: int = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a bill image from either:
      - File upload  (JPEG / PNG / WEBP / BMP / TIFF / GIF)
      - Live camera  (JPEG blob from canvas.toBlob())

    OCR pipeline (auto-routed by script detection):
      • English bills → PaddleOCR           (best Latin/digit accuracy)
      • Tamil bills   → Tesseract tam+eng   (only engine with Tamil support)
      • Mixed bills   → Tesseract + PaddleOCR combined
      • All bills     → Gemini Vision API   (structured field extraction)
      • No Tesseract  → PaddleOCR + Gemini Vision (graceful fallback)

    Saves the detected expense to the database automatically.
    """
    content_type = file.content_type or "application/octet-stream"

    # Accept any image format + octet-stream (canvas blob fallback)
    if not is_supported_image(content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Accepted: JPEG, PNG, WEBP, BMP, TIFF, GIF."
            ),
        )

    # Determine the correct file extension from content-type or filename
    ext = _image_extension(content_type, file.filename)
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info("Bill image saved: %s  type=%s", file_path.name, content_type)

    # Detect source: live camera sends filename "live_capture.jpg"
    source = "live_camera" if (file.filename or "").startswith("live_capture") else "upload"

    # ── OCR engine (PaddleOCR + Gemini Vision) ────────────────────────────
    ocr_result = process_bill(str(file_path), use_vision=True, use_ocr=True)

    # Check for Gemini 429 rate-limit error propagated from ocr_engine
    _ocr_error = ocr_result.get("error", "")
    if isinstance(_ocr_error, str) and "429" in _ocr_error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Gemini Vision API quota exhausted (429). Please retry in a few minutes.",
        )

    # Map new engine output → format expected by the rest of the app
    vendor = (
        ocr_result.get("vendor_name")
        or ocr_result.get("vendor")
        or "Unknown Vendor"
    )
    amount = ocr_result.get("total_amount") or ocr_result.get("amount") or 0.0
    items  = ocr_result.get("items") or []
    gst    = (
        (ocr_result.get("cgst") or 0.0) + (ocr_result.get("sgst") or 0.0)
        + (ocr_result.get("igst") or 0.0)
    )
    detected_date = ocr_result.get("date")
    saved_date = _normalize_scanned_bill_date(detected_date)
    expense_item = _build_scanned_expense_label(vendor, items)
    category = categorize_expense(_build_category_hint(vendor, items))
    accuracy_score = _estimate_scan_accuracy(ocr_result, vendor, amount, detected_date, items, gst)

    result = {
        "vendor":      vendor,
        "item_summary": expense_item,
        "category":    category,
        "amount":      amount,
        "gst":         round(gst, 2),
        "date":        saved_date.isoformat(),
        "detected_date": detected_date,
        "invoice_no":  ocr_result.get("invoice_no"),
        "bill_type":   ocr_result.get("bill_type", "estimate"),
        "items":       items,
        "line_item_count": len(items),
        "ocr_text":    ocr_result.get("ocr_text", ""),
        "ocr_confidence": accuracy_score,
        "accuracy_score": accuracy_score,
        "source":      source,
        "success":     ocr_result.get("success", False),
        "_extraction_quality": ocr_result.get("_validation_warning") or "OK",
        "ocr_engine":  ocr_result.get("_source", "unknown"),
    }

    # ── Save to DB if amount was detected and is valid ─────────────────────────────────
    if amount and amount > 0 and amount < 100_000:  # Sanity check: Indian bills rarely exceed 1 lakh
        new_expense = models.Expense(
            user_id  = user_id,
            item     = expense_item,
            amount   = amount,
            gst      = gst,
            date     = saved_date,
            category = category,
        )
        db.add(new_expense)
        db.commit()
        logger.info(
            "Expense from bill saved: ₹%.2f  vendor=%s  source=%s",
            amount, vendor, source,
        )

    return result


@app.post("/voice-expense", tags=["Upload"])
async def voice_expense(
    user_id: int = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a voice recording from either:
      - File upload      (WAV / MP3 / M4A / OGG / FLAC / AAC)
      - Live microphone  (WebM or OGG blob from MediaRecorder API)

    Converts to WAV automatically, transcribes with Whisper,
    and saves the detected expense.
    """
    from voice import is_supported_audio

    content_type = file.content_type or "application/octet-stream"

    if not is_supported_audio(content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported audio type '{content_type}'. "
                "Accepted: WAV, MP3, M4A, OGG, WEBM, FLAC, AAC."
            ),
        )

    # Preserve the correct extension so pydub knows the format
    ext = _audio_extension(content_type, file.filename)
    audio_path = AUDIO_DIR / f"{uuid.uuid4()}{ext}"

    with audio_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info("Audio saved: %s  type=%s  size=%d bytes",
                audio_path.name, content_type, audio_path.stat().st_size)

    result = process_voice_expense(str(audio_path))

    if result.get("amount"):
        new_expense = models.Expense(
            user_id=user_id,
            item=result["item"] or "Voice Entry",
            amount=result["amount"],
            category=categorize_expense(result.get("item") or ""),
        )
        db.add(new_expense)
        db.commit()
        logger.info("Voice expense saved: %s ₹%.2f  format=%s",
                    result["item"], result["amount"], result.get("source_format"))

    return result


@app.post("/upload-bank-statement", tags=["Upload"])
async def upload_bank_statement(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Parse a bank statement PDF and import detected credits as income."""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF bank statements are accepted.",
        )

    file_path = UPLOAD_DIR / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    amounts = extract_bank_income(str(file_path))
    for amount in amounts:
        db.add(models.Income(user_id=user_id, amount=amount, source="Bank Statement"))
    db.commit()

    logger.info("Imported %d income records from bank statement for user %d", len(amounts), user_id)
    return {"income_detected": amounts, "count": len(amounts)}


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/profit-summary", response_model=schemas.ProfitSummary, tags=["Analytics"])
def profit_summary(user_id: int, db: Session = Depends(get_db)):
    """Return total income, expenses, and profit for a user."""
    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    return schemas.ProfitSummary(
        total_income=total_income,
        total_expense=total_expense,
        profit=total_income - total_expense,
    )


@app.get("/tax-estimate", response_model=schemas.TaxEstimate, tags=["Analytics"])
def tax_estimate(user_id: int, db: Session = Depends(get_db)):
    """Estimate tax liability under the presumptive taxation scheme (5%)."""
    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    profit        = total_income - total_expense
    tax_rate      = 0.05
    return schemas.TaxEstimate(
        profit=profit,
        tax_rate=tax_rate,
        estimated_tax=round(profit * tax_rate, 2),
    )


@app.get("/gst-summary", response_model=schemas.GSTSummary, tags=["Analytics"])
def gst_summary(user_id: int, db: Session = Depends(get_db)):
    """Return GST input, output, and net payable for a user."""
    from sqlalchemy import func as sqlfunc

    output_gst = db.query(sqlfunc.sum(models.Income.gst)).filter(
        models.Income.user_id == user_id
    ).scalar() or 0.0

    input_gst = db.query(sqlfunc.sum(models.Expense.gst)).filter(
        models.Expense.user_id == user_id
    ).scalar() or 0.0

    return schemas.GSTSummary(
        output_gst=output_gst,
        input_gst=input_gst,
        gst_payable=max(output_gst - input_gst, 0.0),
    )


@app.get("/analyze", response_model=schemas.FinancialAnalysis, tags=["Analytics"])
def analyze(user_id: int, db: Session = Depends(get_db)):
    """Run the rule-based financial analysis for a user."""
    income  = crud.get_total_income(db, user_id)
    expense = crud.get_total_expense(db, user_id)
    return analyze_financials(income, expense)


@app.get("/ai-insights", response_model=schemas.AIInsights, tags=["Analytics"])
def ai_insights(user_id: int, db: Session = Depends(get_db)):
    """Return combined financial analysis and spending pattern insights."""
    incomes  = crud.get_incomes(db, user_id, limit=10_000)
    expenses = crud.get_expenses(db, user_id, limit=10_000)

    total_income  = sum(i.amount for i in incomes)
    total_expense = sum(e.amount for e in expenses)
    gst_in        = sum(e.gst or 0.0 for e in expenses)
    gst_out       = sum(i.gst or 0.0 for i in incomes)

    financial = analyze_financials(total_income, total_expense, gst_in, gst_out)
    pattern   = analyze_spending_pattern(expenses)

    return schemas.AIInsights(
        financial_analysis=financial,
        spending_pattern=pattern,
    )


@app.get("/dashboard", response_model=schemas.DashboardSummary, tags=["Analytics"])
def dashboard(user_id: int, db: Session = Depends(get_db)):
    """Return a consolidated dashboard summary for the user."""
    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    profit        = total_income - total_expense
    return schemas.DashboardSummary(
        total_income=total_income,
        total_expense=total_expense,
        profit=profit,
        tax=round(profit * 0.05, 2),
    )


def _format_currency(amount: float) -> str:
    return f"₹{amount:,.2f}"


def _compute_indian_income_tax(taxable_income: float) -> float:
    slabs = [
        (250_000, 0.00),
        (250_000, 0.05),
        (250_000, 0.10),
        (250_000, 0.15),
        (250_000, 0.20),
        (250_000, 0.25),
        (float("inf"), 0.30),
    ]
    remaining = max(0.0, taxable_income)
    tax = 0.0
    for slab_amount, rate in slabs:
        if remaining <= 0:
            break
        amount = min(remaining, slab_amount)
        tax += amount * rate
        remaining -= amount
    return round(tax, 2)


def _build_tax_assistant_response(
    user: models.User,
    total_income: float,
    total_expense: float,
    gst_in: float,
    gst_out: float,
    question: str,
) -> str:
    profit = round(total_income - total_expense, 2)
    estimated_tax = round(max(profit, 0.0) * 0.05, 2)
    q = (question or "").strip().lower()
    if not q:
        return "Please ask a question about your tax, savings, or monthly business trends."

    answers = []
    answers.append(
        f"Your current totals are: income { _format_currency(total_income) }, expenses { _format_currency(total_expense) }, profit { _format_currency(profit) }."
    )

    if any(term in q for term in ["save", "savings", "deduct", "deduction", "reduce tax"]):
        answers.append(
            "Tips to improve tax savings:\n"
            "• Keep strong invoices for all business expenses and claim input GST credit where eligible.\n"
            "• Use the presumptive taxation route if your business qualifies to reduce compliance burden.\n"
            "• Maintain clean books and category-wise expenses to maximize allowable business deductions.\n"
        )

    if any(term in q for term in ["slab", "slabs", "tax rate", "new regime", "old regime"]):
        answers.append(
            "For small business profit, the most relevant comparison is presumptive tax at 5% of profit versus normal income tax slabs. "
            "The current new-regime slabs are: 0% up to ₹2.5L, 5% on next ₹2.5L, 10% on next ₹2.5L, 15% on next ₹2.5L, 20% on next ₹2.5L, 25% on next ₹2.5L, and 30% above ₹15L."
        )

    if any(term in q for term in ["gst", "input gst", "output gst", "gst payable"]):
        answers.append(
            f"GST summary: output GST collected is { _format_currency(gst_out) } and input GST paid is { _format_currency(gst_in) }. "
            f"Net GST payable is { _format_currency(max(gst_out - gst_in, 0.0)) }."
        )

    if any(term in q for term in ["profit", "tax", "estimate", "liable"]):
        answers.append(
            f"Under presumptive taxation, your estimated tax on profit is { _format_currency(estimated_tax) }. "
            "This is a simple estimate based on 5% of profit."
        )

    if len(answers) == 1:
        answers.append(
            "For better guidance, share your exact question: examples include 'How much tax should I pay?', 'Can I save tax with more expenses?', or 'What do my monthly income and expense trends show?'."
        )

    return "\n\n".join(answers)


def _get_month_periods(months: int) -> list[tuple[str, str]]:
    today = calendar_date.today().replace(day=1)
    periods = []
    for i in range(months - 1, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        periods.append((year, month))
    return periods


@app.get("/tax-savings", response_model=schemas.TaxSavings, tags=["Analytics"])
def tax_savings(
    gross_income: float = Query(..., ge=0.0),
    business_expense: float = Query(0.0, ge=0.0),
    deductions: float = Query(0.0, ge=0.0),
):
    taxable_income = max(0.0, gross_income - business_expense - deductions)
    normal_tax = _compute_indian_income_tax(taxable_income)
    presumptive_tax = round(taxable_income * 0.05, 2)
    savings = round(max(normal_tax - presumptive_tax, 0.0), 2)
    return schemas.TaxSavings(
        gross_income=gross_income,
        business_expense=business_expense,
        deductions=deductions,
        taxable_income=taxable_income,
        normal_regime_tax=normal_tax,
        presumptive_scheme_tax=presumptive_tax,
        estimated_savings=savings,
        note=(
            "This is a rough estimate. Presumptive tax is estimated at 5% of profit. "
            "Actual tax may vary by scheme eligibility, business type, and other deductions."
        ),
    )


@app.post("/chat", response_model=schemas.ChatResponse, tags=["AI"])
def chat_assistant(
    user_id: int = Query(...),
    payload: schemas.ChatRequest = None,
    db: Session = Depends(get_db),
):
    user = crud.get_user_by_id(db, user_id)
    incomes = crud.get_total_income(db, user_id)
    expenses = crud.get_total_expense(db, user_id)
    gst_in = db.query(func.sum(models.Expense.gst)).filter(models.Expense.user_id == user_id).scalar() or 0.0
    gst_out = db.query(func.sum(models.Income.gst)).filter(models.Income.user_id == user_id).scalar() or 0.0
    answer = _build_tax_assistant_response(user, incomes, expenses, gst_in, gst_out, payload.message)
    recommendations = [
        "Maintain organized expense invoices",
        "Review monthly income vs expense trends",
        "Claim valid input GST credits",
    ]
    return schemas.ChatResponse(answer=answer, recommendations=recommendations)


@app.get("/monthly-trends", response_model=schemas.MonthlyTrends, tags=["Analytics"])
def monthly_trends(
    user_id: int = Query(...),
    months: int = Query(default=6, ge=3, le=12),
    db: Session = Depends(get_db),
):
    periods = _get_month_periods(months)
    month_keys = [f"{year}-{month:02d}" for year, month in periods]
    labels = [f"{calendar.month_abbr[month]} {str(year)[2:]}" for year, month in periods]

    income_rows = db.query(
        func.date_format(models.Income.date, "%Y-%m").label("period"),
        func.sum(models.Income.amount).label("total"),
    ).filter(
        models.Income.user_id == user_id,
        models.Income.date != None,
    ).group_by("period").all()

    expense_rows = db.query(
        func.date_format(models.Expense.date, "%Y-%m").label("period"),
        func.sum(models.Expense.amount).label("total"),
    ).filter(
        models.Expense.user_id == user_id,
        models.Expense.date != None,
    ).group_by("period").all()

    income_map = {row.period: float(row.total or 0.0) for row in income_rows}
    expense_map = {row.period: float(row.total or 0.0) for row in expense_rows}

    income = [income_map.get(key, 0.0) for key in month_keys]
    expense = [expense_map.get(key, 0.0) for key in month_keys]
    profit = [round(i - e, 2) for (i, e) in zip(income, expense)]

    return schemas.MonthlyTrends(labels=labels, income=income, expense=expense, profit=profit)


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/generate-report", tags=["Reports"])
def generate_report(user_id: int, db: Session = Depends(get_db)):
    """Generate a PDF financial report for the user."""
    try:
        from utils.report_generator import generate_financial_report
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Report generator module not available.",
        )

    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    profit        = total_income - total_expense
    tax           = profit * 0.05

    file_path = REPORT_DIR / f"user_{user_id}_report.pdf"
    generate_financial_report(str(file_path), total_income, total_expense, profit, tax)
    logger.info("Report generated: %s", file_path)
    return {"message": "Report generated successfully", "file": str(file_path)}


@app.get("/download-report", tags=["Reports"])
def download_report(user_id: int):
    """Download the generated PDF report for the user."""
    file_path = REPORT_DIR / f"user_{user_id}_report.pdf"
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found. Please generate it first via /generate-report.",
        )
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename="taxshield_report.pdf",
    )

# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _image_extension(content_type: str, filename: str = "") -> str:
    """
    Derive the correct image file extension from MIME type or filename.
    Defaults to .jpg which works fine for canvas JPEG blobs.
    """
    ct = (content_type or "").lower().split(";")[0].strip()
    mime_to_ext = {
        "image/jpeg": ".jpg",  "image/jpg":  ".jpg",
        "image/png":  ".png",  "image/webp": ".webp",
        "image/bmp":  ".bmp",  "image/tiff": ".tiff",
        "image/gif":  ".gif",
    }
    if ct in mime_to_ext:
        return mime_to_ext[ct]
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"):
            return suffix
    return ".jpg"   # safe default for canvas blobs


def _audio_extension(content_type: str, filename: str = "") -> str:
    """
    Derive the correct audio file extension from MIME type or filename.
    Getting this right is critical so pydub knows which decoder to use.
    """
    ct = (content_type or "").lower().split(";")[0].strip()
    mime_to_ext = {
        "audio/wav":   ".wav",  "audio/wave":  ".wav",  "audio/x-wav": ".wav",
        "audio/mpeg":  ".mp3",  "audio/mp3":   ".mp3",
        "audio/mp4":   ".m4a",  "audio/m4a":   ".m4a",  "audio/x-m4a": ".m4a",
        "audio/ogg":   ".ogg",  "audio/opus":  ".ogg",
        "audio/webm":  ".webm",
        "audio/flac":  ".flac",
        "audio/aac":   ".aac",
    }
    if ct in mime_to_ext:
        return mime_to_ext[ct]
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix in (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".aac", ".opus"):
            return suffix
    return ".webm"  # default for live MediaRecorder output


def _normalize_scanned_bill_date(raw_date: str | None) -> calendar_date:
    """Return a safe bill date for DB storage and dashboard display."""
    if raw_date:
        try:
            return calendar_date.fromisoformat(raw_date)
        except ValueError:
            pass
    return calendar_date.today()


def _build_scanned_expense_label(vendor: str, items: list[dict]) -> str:
    """Create a readable single-line label for scanned bills."""
    vendor = (vendor or "").strip()
    item_names = [str(item.get("name", "")).strip() for item in items if item.get("name")]

    if vendor and vendor != "Unknown Vendor":
        if item_names:
            return f"{vendor} ({len(item_names)} item{'s' if len(item_names) != 1 else ''})"[:100]
        return vendor[:100]

    if item_names:
        preview = ", ".join(item_names[:2])
        if len(item_names) > 2:
            preview += f" +{len(item_names) - 2} more"
        return preview[:100]

    return "Scanned Bill"


def _build_category_hint(vendor: str, items: list[dict]) -> str:
    """Combine vendor and line items so categorisation uses the bill contents."""
    item_names = [str(item.get("name", "")).strip() for item in items if item.get("name")]
    parts = [vendor] + item_names[:6]
    return " ".join(part for part in parts if part and part != "Unknown Vendor")


def _estimate_scan_accuracy(
    ocr_result: dict,
    vendor: str,
    amount: float,
    detected_date: str | None,
    items: list[dict],
    gst: float,
) -> float:
    """Heuristic quality score for UI feedback when the OCR engine has no native confidence."""
    score = 0.0

    if amount and amount > 0:
        score += 35
    if vendor and vendor != "Unknown Vendor":
        score += 20
    if detected_date:
        score += 10
    if items:
        score += 20
    if ocr_result.get("invoice_no"):
        score += 5
    if gst > 0:
        score += 5
    if (ocr_result.get("ocr_text") or "").strip():
        score += 5
    if ocr_result.get("_validation_warning"):
        score -= 10
    if ocr_result.get("error"):
        score -= 25

    return round(max(0.0, min(score, 100.0)), 1)


# ══════════════════════════════════════════════════════════════════════════════
# ITR FORM GENERATION
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/generate-itr4", tags=["ITR Forms"])
def generate_itr4_form(user_id: int, db: Session = Depends(get_db)):
    """
    Generate a pre-filled ITR-4 Sugam PDF.
    For small businesses under presumptive taxation (Sec 44AD, turnover ≤ ₹2 Cr).
    Pulls all financial data from the user's TaxShield records automatically.
    """
    try:
        from utils.itr4_generator import generate_itr4
        from utils.report_generator import generate_financial_report
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"ITR generator not available: {e}")

    # ── Fetch user profile ────────────────────────────────────────────────
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # ── Fetch financial totals ────────────────────────────────────────────
    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    net_profit    = total_income - total_expense

    # GST totals
    from sqlalchemy import func as sqlfunc
    gst_out = db.query(sqlfunc.sum(models.Income.gst)) \
        .filter(models.Income.user_id == user_id).scalar() or 0.0
    gst_in  = db.query(sqlfunc.sum(models.Expense.gst)) \
        .filter(models.Expense.user_id == user_id).scalar() or 0.0

    # Category breakdown for expense schedule
    expenses = crud.get_expenses(db, user_id, limit=100_000)
    category_breakdown = {}
    for e in expenses:
        cat = e.category or "Others"
        category_breakdown[cat] = category_breakdown.get(cat, 0.0) + (e.amount or 0.0)

    # ── Assessment year ────────────────────────────────────────────────────
    y  = __import__("datetime").date.today().year
    ay = f"{y}-{str(y+1)[2:]}"
    fy = f"{y-1}-{str(y)[2:]}"

    # ── Generate PDF ───────────────────────────────────────────────────────
    file_path = REPORT_DIR / f"user_{user_id}_itr4.pdf"

    generate_itr4(
        file_path       = str(file_path),
        full_name       = user.full_name,
        pan             = "XXXXXXXXXX",          # user must update
        aadhaar         = "",
        dob             = "",
        address         = "",
        city            = user.city  or "",
        state           = user.state or "",
        phone           = user.phone or "",
        email           = user.email or "",
        business_name   = user.shop_name   or user.full_name,
        business_type   = user.business_type or "Retail Shop",
        gstin           = user.gstin or "",
        gross_turnover  = total_income,
        total_expenses  = total_expense,
        net_profit      = net_profit,
        gst_collected   = gst_out,
        gst_paid        = gst_in,
        assessment_year = ay,
        financial_year  = fy,
        category_breakdown = category_breakdown if category_breakdown else None,
    )

    logger.info("ITR-4 generated for user %d: %s", user_id, file_path)
    return {
        "message":         "ITR-4 Sugam pre-filled draft generated successfully.",
        "file":            str(file_path),
        "assessment_year": ay,
        "financial_year":  fy,
        "gross_turnover":  total_income,
        "net_profit":      net_profit,
        "note": (
            "This is a pre-filled DRAFT for reference. "
            "Verify all figures with your CA before e-filing on the IT portal."
        ),
    }


@app.get("/generate-itr3", tags=["ITR Forms"])
def generate_itr3_form(user_id: int, db: Session = Depends(get_db)):
    """
    Generate a pre-filled ITR-3 PDF.
    For businesses with maintained books of accounts (turnover > ₹2 Cr
    or not opting for presumptive scheme).
    """
    try:
        from utils.itr3_generator import generate_itr3
    except ImportError as e:
        raise HTTPException(status_code=501, detail=f"ITR generator not available: {e}")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    net_profit    = total_income - total_expense

    from sqlalchemy import func as sqlfunc
    gst_out = db.query(sqlfunc.sum(models.Income.gst)) \
        .filter(models.Income.user_id == user_id).scalar() or 0.0
    gst_in  = db.query(sqlfunc.sum(models.Expense.gst)) \
        .filter(models.Expense.user_id == user_id).scalar() or 0.0

    expenses = crud.get_expenses(db, user_id, limit=100_000)
    category_breakdown = {}
    for e in expenses:
        cat = e.category or "Others"
        category_breakdown[cat] = category_breakdown.get(cat, 0.0) + (e.amount or 0.0)

    y  = __import__("datetime").date.today().year
    ay = f"{y}-{str(y+1)[2:]}"
    fy = f"{y-1}-{str(y)[2:]}"

    file_path = REPORT_DIR / f"user_{user_id}_itr3.pdf"

    generate_itr3(
        file_path       = str(file_path),
        full_name       = user.full_name,
        pan             = "XXXXXXXXXX",
        city            = user.city  or "",
        state           = user.state or "",
        phone           = user.phone or "",
        email           = user.email or "",
        business_name   = user.shop_name   or user.full_name,
        business_type   = user.business_type or "Retail Shop",
        gstin           = user.gstin or "",
        gross_turnover  = total_income,
        total_expenses  = total_expense,
        net_profit      = net_profit,
        gst_collected   = gst_out,
        gst_paid        = gst_in,
        assessment_year = ay,
        financial_year  = fy,
        category_breakdown = category_breakdown if category_breakdown else None,
    )

    logger.info("ITR-3 generated for user %d: %s", user_id, file_path)
    return {
        "message":         "ITR-3 pre-filled draft generated successfully.",
        "file":            str(file_path),
        "assessment_year": ay,
        "gross_turnover":  total_income,
        "net_profit":      net_profit,
        "note": (
            "ITR-3 requires books of accounts. "
            "Complete P&L and Balance Sheet before e-filing."
        ),
    }


@app.get("/download-itr4", tags=["ITR Forms"])
def download_itr4(user_id: int):
    """Download the generated ITR-4 Sugam PDF."""
    file_path = REPORT_DIR / f"user_{user_id}_itr4.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404,
            detail="ITR-4 not found. Call /generate-itr4 first.")
    return FileResponse(str(file_path), media_type="application/pdf",
                        filename=f"ITR4_Sugam_{user_id}.pdf")


@app.get("/download-itr3", tags=["ITR Forms"])
def download_itr3(user_id: int):
    """Download the generated ITR-3 PDF."""
    file_path = REPORT_DIR / f"user_{user_id}_itr3.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404,
            detail="ITR-3 not found. Call /generate-itr3 first.")
    return FileResponse(str(file_path), media_type="application/pdf",
                        filename=f"ITR3_{user_id}.pdf")



# ══════════════════════════════════════════════════════════════════════════════
# EMAIL ROUTES
# ══════════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel as PydanticBase
from typing import Optional as Opt

class EmailRequest(PydanticBase):
    to_email:    str
    to_name:     str  = "Recipient"
    report_type: str  = "financial"   # "financial" | "itr4" | "itr3"
    cc_email:    Opt[str] = None


@app.post("/email/send-report", tags=["Email"])
def email_report(
    user_id: int,
    payload: EmailRequest,
    db: Session = Depends(get_db),
):
    """
    Email a generated report PDF to any address.
    report_type: 'financial' | 'itr4' | 'itr3'
    """
    from email_service import (
        send_report_email,
        build_itr_email_body,
        build_financial_summary_email_body,
    )

    # ── Fetch user ─────────────────────────────────────────────────────────
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # ── Financial figures ──────────────────────────────────────────────────
    total_income  = crud.get_total_income(db, user_id)
    total_expense = crud.get_total_expense(db, user_id)
    net_profit    = total_income - total_expense
    tax           = net_profit * 0.05

    import datetime as _dt
    y  = _dt.date.today().year
    ay = f"{y}-{str(y+1)[2:]}"

    # ── Determine file and email content ───────────────────────────────────
    if payload.report_type == "itr4":
        file_path    = REPORT_DIR / f"user_{user_id}_itr4.pdf"
        attach_name  = f"ITR4_Sugam_{user.full_name}_{ay}.pdf"
        subject      = f"ITR-4 Sugam Pre-Filled Draft — {user.full_name} — AY {ay}"
        body         = build_itr_email_body(
            full_name       = user.full_name,
            report_type     = "ITR-4 Sugam",
            assessment_year = ay,
            gross_turnover  = total_income,
            net_profit      = net_profit,
            shop_name       = user.shop_name or "",
        )

    elif payload.report_type == "itr3":
        file_path    = REPORT_DIR / f"user_{user_id}_itr3.pdf"
        attach_name  = f"ITR3_{user.full_name}_{ay}.pdf"
        subject      = f"ITR-3 Pre-Filled Draft — {user.full_name} — AY {ay}"
        body         = build_itr_email_body(
            full_name       = user.full_name,
            report_type     = "ITR-3",
            assessment_year = ay,
            gross_turnover  = total_income,
            net_profit      = net_profit,
            shop_name       = user.shop_name or "",
        )

    else:  # financial summary
        file_path    = REPORT_DIR / f"user_{user_id}_report.pdf"
        attach_name  = f"TaxShield_Financial_Report_{user.full_name}.pdf"
        subject      = f"TaxShield Financial Summary Report — {user.full_name}"
        body         = build_financial_summary_email_body(
            full_name     = user.full_name,
            total_income  = total_income,
            total_expense = total_expense,
            profit        = net_profit,
            tax           = tax,
            shop_name     = user.shop_name or "",
        )

    # ── Check file exists ──────────────────────────────────────────────────
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Report PDF not found. Please generate the {payload.report_type} report first."
        )

    # ── Send email ─────────────────────────────────────────────────────────
    result = send_report_email(
        to_email        = payload.to_email,
        to_name         = payload.to_name,
        subject         = subject,
        body_html       = body,
        attachment_path = str(file_path),
        attachment_name = attach_name,
        cc_email        = payload.cc_email,
    )

    if result["success"]:
        logger.info("Report emailed to %s for user %d", payload.to_email, user_id)
        return {
            "message":     result["message"],
            "sent_to":     payload.to_email,
            "report_type": payload.report_type,
            "attachment":  attach_name,
        }
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@app.get("/email/govt-addresses", tags=["Email"])
def get_govt_email_addresses():
    """Return official government email addresses for reference."""
    return {
        "addresses": [
            {
                "name":  "Income Tax Department (e-Filing)",
                "email": "efiling@incometax.gov.in",
                "note":  "For ITR-related queries only",
            },
            {
                "name":  "GST Helpdesk",
                "email": "helpdesk@gst.gov.in",
                "note":  "For GST filing queries",
            },
            {
                "name":  "Chartered Accountant (Your CA)",
                "email": "",
                "note":  "Add your CA email manually",
            },
        ],
        "important": (
            "Government portals require official e-filing through "
            "https://www.incometax.gov.in — email is for sharing drafts with "
            "your CA or for personal records only."
        ),
    }
