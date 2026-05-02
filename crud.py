"""
crud.py – Database access layer.
All database reads and writes are centralised here, keeping route handlers thin.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

import models
import schemas


# ══════════════════════════════════════════════════════════════════════════════
# USER
# ══════════════════════════════════════════════════════════════════════════════

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    """Return a user by username or None."""
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> models.User:
    """Return a user by ID or raise 404."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    """Return a user by phone or None."""
    return db.query(models.User).filter(models.User.phone == phone).first()


# ══════════════════════════════════════════════════════════════════════════════
# INCOME
# ══════════════════════════════════════════════════════════════════════════════

def create_income(db: Session, income: schemas.IncomeCreate) -> models.Income:
    """Insert a new income record."""
    db_income = models.Income(**income.model_dump())
    db.add(db_income)
    db.commit()
    db.refresh(db_income)
    return db_income


def get_incomes(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Income]:
    """Return paginated income records for a user."""
    return (
        db.query(models.Income)
        .filter(models.Income.user_id == user_id)
        .order_by(models.Income.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_income_by_id(db: Session, income_id: int) -> models.Income:
    """Return a single income record or raise 404."""
    record = db.query(models.Income).filter(models.Income.id == income_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Income record not found")
    return record


def update_income(
    db: Session,
    income_id: int,
    updates: schemas.IncomeUpdate,
) -> models.Income:
    """Partially update an income record."""
    record = get_income_by_id(db, income_id)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


def delete_income(db: Session, income_id: int) -> dict:
    """Delete an income record."""
    record = get_income_by_id(db, income_id)
    db.delete(record)
    db.commit()
    return {"detail": f"Income {income_id} deleted successfully"}


def get_total_income(db: Session, user_id: int) -> float:
    """Return aggregate income for a user."""
    result = (
        db.query(func.sum(models.Income.amount))
        .filter(models.Income.user_id == user_id)
        .scalar()
    )
    return float(result or 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSE
# ══════════════════════════════════════════════════════════════════════════════

def create_expense(db: Session, expense: schemas.ExpenseCreate) -> models.Expense:
    """Insert a new expense record."""
    db_expense = models.Expense(**expense.model_dump())
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense


def get_expenses(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Expense]:
    """Return paginated expense records for a user."""
    return (
        db.query(models.Expense)
        .filter(models.Expense.user_id == user_id)
        .order_by(models.Expense.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_expense_by_id(db: Session, expense_id: int) -> models.Expense:
    """Return a single expense record or raise 404."""
    record = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense record not found")
    return record


def update_expense(
    db: Session,
    expense_id: int,
    updates: schemas.ExpenseUpdate,
) -> models.Expense:
    """Partially update an expense record."""
    record = get_expense_by_id(db, expense_id)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


def delete_expense(db: Session, expense_id: int) -> dict:
    """Delete an expense record."""
    record = get_expense_by_id(db, expense_id)
    db.delete(record)
    db.commit()
    return {"detail": f"Expense {expense_id} deleted successfully"}


def get_total_expense(db: Session, user_id: int) -> float:
    """Return aggregate expense for a user."""
    result = (
        db.query(func.sum(models.Expense.amount))
        .filter(models.Expense.user_id == user_id)
        .scalar()
    )
    return float(result or 0.0)
