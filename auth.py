"""
auth.py – Password hashing and JWT token utilities for TaxShield.

Uses:
    bcrypt   → secure password hashing  (via passlib)
    PyJWT    → token generation and verification
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config (read from .env) ───────────────────────────────────────────────────
SECRET_KEY      = os.getenv("SECRET_KEY", "taxshield-dev-secret-change-in-production")
ALGORITHM       = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))


# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING
# ══════════════════════════════════════════════════════════════════════════════

def hash_password(plain_password: str) -> str:
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        # bcrypt has a 72-byte limit — truncate safely
        truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        return pwd_context.hash(truncated)
    except ImportError:
        raise ImportError("Run: pip install passlib[bcrypt]")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        return pwd_context.verify(truncated, hashed_password)
    except ImportError:
        raise ImportError("Run: pip install passlib[bcrypt]")
    except Exception as exc:
        logger.warning("Password verification error: %s", exc)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# JWT TOKEN
# ══════════════════════════════════════════════════════════════════════════════

def create_access_token(user_id: int, username: str) -> str:
    """
    Create a signed JWT access token.

    Args:
        user_id:  Database user ID.
        username: Username string.

    Returns:
        Signed JWT string.
    """
    try:
        import jwt
    except ImportError:
        raise ImportError("PyJWT not installed. Run: pip install PyJWT")

    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)

    payload = {
        "sub":      str(user_id),
        "username": username,
        "exp":      expire,
        "iat":      datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    logger.info("Token issued for user_id=%d  expires=%s", user_id, expire.isoformat())
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT token.

    Returns:
        Payload dict on success, None on failure / expiry.
    """
    try:
        import jwt
    except ImportError:
        raise ImportError("PyJWT not installed. Run: pip install PyJWT")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid token: %s", exc)
        return None
