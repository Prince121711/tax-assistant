"""
database.py – Database engine and session configuration.
Reads credentials from environment variables (never hardcoded).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()  # Load from .env file if present

# ── Connection URL ────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:1234@localhost/taxshield")

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # detects stale connections automatically
    pool_recycle=3600,        # recycle connections every hour
    echo=False,               # set True to log SQL statements during debugging
)

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Declarative base ──────────────────────────────────────────────────────────
Base = declarative_base()


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """Yield a database session and ensure it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
