"""
models.py – SQLAlchemy ORM models for TaxShield.
Includes full merchant profile, timestamps, indexes, and FK relationships.
"""

from datetime import date as date_type
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship
from database import Base
import enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class IncomeType(str, enum.Enum):
    BUSINESS        = "Business"
    SALARY          = "Salary"
    FREELANCE       = "Freelance"
    RENTAL          = "Rental"
    INVESTMENT      = "Investment"
    OTHER           = "Other"


class BusinessType(str, enum.Enum):
    RETAIL          = "Retail Shop"
    WHOLESALE       = "Wholesale"
    RESTAURANT      = "Restaurant / Food"
    MANUFACTURING   = "Manufacturing"
    SERVICE         = "Service Provider"
    ECOMMERCE       = "E-Commerce"
    SALARIED        = "Salaried Employee"
    FREELANCER      = "Freelancer"
    OTHER           = "Other"


# ══════════════════════════════════════════════════════════════════════════════
# USER / MERCHANT
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)

    # ── Auth ──────────────────────────────────────────────────────────────────
    username       = Column(String(50),  unique=True, nullable=False, index=True)
    password_hash  = Column(String(256), nullable=False)   # bcrypt hash

    # ── Personal info ─────────────────────────────────────────────────────────
    full_name      = Column(String(100), nullable=False)
    phone          = Column(String(20),  unique=True, nullable=False, index=True)
    email          = Column(String(120), unique=True, nullable=True,  index=True)

    # ── Business / income profile ─────────────────────────────────────────────
    shop_name      = Column(String(150), nullable=True)
    gstin          = Column(String(20),  nullable=True)   # GST registration number
    income_type    = Column(String(30),  nullable=False, default=IncomeType.BUSINESS)
    business_type  = Column(String(50),  nullable=False, default=BusinessType.RETAIL)
    city           = Column(String(100), nullable=True)
    state          = Column(String(100), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at     = Column(DateTime, server_default=func.now())
    last_login     = Column(DateTime, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    incomes  = relationship("Income",  back_populates="owner", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="owner", cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
# INCOME
# ══════════════════════════════════════════════════════════════════════════════

class Income(Base):
    __tablename__ = "income"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount     = Column(Float,  nullable=False)
    source     = Column(String(100), nullable=False, default="Manual Entry")
    date       = Column(Date,   nullable=False, default=date_type.today)
    gst        = Column(Float,  nullable=False, default=0.0)
    category   = Column(String(50),  nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="incomes")


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

class Expense(Base):
    __tablename__ = "expense"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item       = Column(String(100), nullable=False)
    amount     = Column(Float,  nullable=False)
    date       = Column(Date,   nullable=True, default=date_type.today)  # Allow NULL if date extraction fails
    gst        = Column(Float,  nullable=False, default=0.0)
    category   = Column(String(50),  nullable=True,  default="Others")
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="expenses")
