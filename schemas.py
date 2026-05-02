"""
schemas.py – Pydantic models for request validation and response serialisation.
Covers registration, login, JWT token, and all financial entities.
"""

from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator, EmailStr


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — REGISTER
# ══════════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    # Auth credentials
    username:      str = Field(..., min_length=3, max_length=50,
                               description="Unique login username (letters, numbers, _)")
    password:      str = Field(..., min_length=6, max_length=64,
                               description="Minimum 6 characters")
    confirm_password: str = Field(..., min_length=6)

    # Personal details
    full_name:     str = Field(..., min_length=2, max_length=100)
    phone:         str = Field(..., min_length=10, max_length=15)
    email:         Optional[str] = Field(None, max_length=120)

    # Business profile
    shop_name:     Optional[str] = Field(None, max_length=150)
    gstin:         Optional[str] = Field(None, max_length=20,
                                         description="GST registration number (optional)")
    income_type:   str = Field(..., description="Business / Salary / Freelance / Rental / Investment / Other")
    business_type: str = Field(..., description="Type of business or employment")
    city:          Optional[str] = Field(None, max_length=100)
    state:         Optional[str] = Field(None, max_length=100)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Username may only contain letters, numbers, and underscores.")
        return v.lower()

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_digits(cls, v: str) -> str:
        digits = v.replace("+", "").replace("-", "").replace(" ", "")
        if not digits.isdigit():
            raise ValueError("Phone number must contain only digits.")
        return v

    @field_validator("gstin")
    @classmethod
    def gstin_format(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) != 15:
            raise ValueError("GSTIN must be exactly 15 characters.")
        return v.upper() if v else v


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — LOGIN
# ══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — RESPONSES
# ══════════════════════════════════════════════════════════════════════════════

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user_id:      int
    username:     str
    full_name:    str
    income_type:  str
    business_type: str
    shop_name:    Optional[str]


class UserProfile(BaseModel):
    id:            int
    username:      str
    full_name:     str
    phone:         str
    email:         Optional[str]
    shop_name:     Optional[str]
    gstin:         Optional[str]
    income_type:   str
    business_type: str
    city:          Optional[str]
    state:         Optional[str]

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
# INCOME
# ══════════════════════════════════════════════════════════════════════════════

class IncomeCreate(BaseModel):
    user_id:  int
    amount:   float  = Field(..., gt=0)
    source:   str    = Field(..., min_length=1, max_length=100)
    date:     date
    gst:      float  = Field(default=0.0, ge=0)
    category: Optional[str] = Field(default=None, max_length=50)


class IncomeUpdate(BaseModel):
    amount:   Optional[float] = Field(None, gt=0)
    source:   Optional[str]   = Field(None, max_length=100)
    date:     Optional[date]  = None
    gst:      Optional[float] = Field(None, ge=0)
    category: Optional[str]   = Field(None, max_length=50)


class IncomeResponse(BaseModel):
    id:       int
    user_id:  int
    amount:   float
    source:   str
    date:     date
    gst:      float
    category: Optional[str]

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

class ExpenseCreate(BaseModel):
    user_id:  int
    item:     str   = Field(..., min_length=1, max_length=100)
    amount:   float = Field(..., gt=0)
    date:     date
    gst:      float = Field(default=0.0, ge=0)
    category: Optional[str] = Field(default=None, max_length=50)


class ExpenseUpdate(BaseModel):
    item:     Optional[str]   = Field(None, max_length=100)
    amount:   Optional[float] = Field(None, gt=0)
    date:     Optional[date]  = None
    gst:      Optional[float] = Field(None, ge=0)
    category: Optional[str]   = Field(None, max_length=50)


class ExpenseResponse(BaseModel):
    id:       int
    user_id:  int
    item:     str
    amount:   float
    date:     date
    gst:      float
    category: Optional[str]

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

class ProfitSummary(BaseModel):
    total_income:  float
    total_expense: float
    profit:        float


class TaxEstimate(BaseModel):
    profit:        float
    tax_rate:      float
    estimated_tax: float


class GSTSummary(BaseModel):
    output_gst:  float
    input_gst:   float
    gst_payable: float


class FinancialAnalysis(BaseModel):
    income:      float
    expense:     float
    profit:      float
    gst_payable: float
    risk_level:  str
    alerts:      list[str]
    suggestions: list[str]


class SpendingPattern(BaseModel):
    top_category:          str
    category_distribution: dict[str, float]


class AIInsights(BaseModel):
    financial_analysis: FinancialAnalysis
    spending_pattern:   SpendingPattern


class DashboardSummary(BaseModel):
    total_income:  float
    total_expense: float
    profit:        float
    tax:           float
