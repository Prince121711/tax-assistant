# TaxShield API

A FastAPI backend for financial tracking, GST management, and tax estimation — built for small business owners.

---

## Features

- **Income & Expense tracking** — full CRUD with pagination
- **GST summary** — input/output GST and net payable
- **Tax estimation** — presumptive scheme (5% on profit)
- **Bill scanning** — OCR via EasyOCR
- **Voice expenses** — transcription via OpenAI Whisper
- **Bank statement import** — PDF parsing via pdfplumber
- **Financial analysis** — rule-based risk scoring and alerts
- **AI insights** — spending pattern breakdown by category
- **PDF reports** — downloadable financial reports

---

## Project Structure

```
taxshield/
├── Main.py               # FastAPI app and all route handlers
├── models.py             # SQLAlchemy ORM models
├── schemas.py            # Pydantic request/response schemas
├── crud.py               # Database access layer (full CRUD)
├── database.py           # Engine, session, and dependency
├── analysis_service.py   # Rule-based financial health analysis
├── insights_service.py   # Spending pattern analytics
├── categorizer.py        # Keyword-based expense categorisation
├── bank_parser.py        # Bank statement PDF parser
├── voice.py              # Whisper voice transcription
├── ocr.py                # EasyOCR bill scanning
├── .env                  # Environment variables (never commit this)
└── utils/
    ├── image_preprocess.py
    └── report_generator.py
```

---

## Setup

### 1. Install dependencies

```bash
pip install fastapi uvicorn sqlalchemy pymysql pdfplumber easyocr \
            openai-whisper python-multipart python-dotenv
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
DATABASE_URL=mysql+pymysql://root:yourpassword@localhost/taxshield
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### 3. Run the server

```bash
uvicorn Main:app --reload
```

Open the interactive API docs at: **http://localhost:8000/docs**

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| POST | `/income` | Add income |
| GET | `/income` | List income (paginated) |
| PUT | `/income/{id}` | Update income |
| DELETE | `/income/{id}` | Delete income |
| POST | `/expense` | Add expense |
| GET | `/expense` | List expenses (paginated) |
| PUT | `/expense/{id}` | Update expense |
| DELETE | `/expense/{id}` | Delete expense |
| POST | `/scan-bill` | Upload bill image (OCR) |
| POST | `/voice-expense` | Upload voice recording |
| POST | `/upload-bank-statement` | Import bank statement PDF |
| GET | `/profit-summary` | Income, expense, profit |
| GET | `/tax-estimate` | Estimated tax (5% presumptive) |
| GET | `/gst-summary` | GST input/output/payable |
| GET | `/analyze` | Rule-based financial analysis |
| GET | `/ai-insights` | Spending patterns + analysis |
| GET | `/dashboard` | Full dashboard summary |
| GET | `/generate-report` | Generate PDF report |
| GET | `/download-report` | Download PDF report |

---

## Security Notes

- **Never commit `.env`** — add it to `.gitignore`
- Passwords in `User` model should be stored **hashed** (use `passlib` with bcrypt)
- Add JWT authentication before deploying to production
