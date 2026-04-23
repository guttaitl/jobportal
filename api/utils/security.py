import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from fastapi import Request

def get_current_user_optional(request: Request):
    try:
        return get_current_user(request)
    except Exception:
        return None
# ==========================================================
# CONFIG
# ==========================================================

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

<<<<<<< HEAD
security = HTTPBearer(auto_error=False)
=======
security = HTTPBearer()
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

# ==========================================================
# PASSWORD FUNCTIONS
# ==========================================================

def hash_password(password: str) -> str:
    # bcrypt limit protection
    if len(password.encode("utf-8")) > 72:
        password = password[:72]

    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        password = password[:72]

    return pwd_context.verify(password, password_hash)

# ==========================================================
# JWT TOKEN CREATION
# ==========================================================

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["type"] = "access"

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload["type"] = "refresh"

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ==========================================================
# TOKEN DECODE
# ==========================================================

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


# ==========================================================
# AUTH DEPENDENCY
# ==========================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
<<<<<<< HEAD
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
=======

    token = credentials.credentials
    payload = decode_token(token)
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

    if payload.get("type") != "access":
        raise HTTPException(401, "Invalid token type")

    return payload

<<<<<<< HEAD
=======

>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
# ==========================================================
# ROLE GUARD
# ==========================================================

def require_role(role: str):

    def role_checker(user=Depends(get_current_user)):

        user_role = (user.get("role") or "").upper()

        if user_role != role.upper():
            raise HTTPException(403, "Insufficient permissions")

        return user

    return role_checker


# ==========================================================
# ADMIN GUARD
# ==========================================================

def admin_required(user=Depends(get_current_user)):

    role = (user.get("role") or "").upper()

    if role != "ADMIN":
        raise HTTPException(403, "Admin access required")

<<<<<<< HEAD
    return user
=======
    return user
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
