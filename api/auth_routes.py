from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import secrets
import traceback
from pydantic import BaseModel, EmailStr
from typing import Optional

from api.db import get_db
from api.utils.security import verify_password, create_access_token, hash_password
from api.schemas.auth_schema import LoginRequest, EmailCheckRequest
from api.utils.email_sender import send_verification_email as send_verification_email_via_gmail

router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiringcircle.us")

# ==========================================================
# RESEND VERIFICATION
# ==========================================================
@router.post("/resend-verification")
def resend_verification(payload: EmailCheckRequest, db: Session = Depends(get_db)):
    user = db.execute(
        text("SELECT verified FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user[0]:
        return {"status": "already_verified"}

    token = secrets.token_urlsafe(32)

    db.execute(
        text("""
        UPDATE usersdata
        SET verification_token = :token
        WHERE email = :email
        """),
        {"token": token, "email": payload.email}
    )
    db.commit()

    send_verification_email_via_gmail(payload.email, f"{FRONTEND_URL}/verify?token={token}")

    return {"status": "sent"}


# ==========================================================
# CHECK EMAIL
# ==========================================================
@router.post("/register/check")
def check_email_available(payload: EmailCheckRequest, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT 1 FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    return {"status": "EXISTS" if existing else "AVAILABLE"}


# ==========================================================
# LOGIN
# ==========================================================
@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    result = db.execute(
        text("""
        SELECT password_hash, verified, role
        FROM usersdata
        WHERE email = :email
        """),
        {"email": payload.email}
    ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.password, result[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not result[1]:
        raise HTTPException(status_code=401, detail="Email not verified")

    role = (result[2] or "").strip().lower()
    role = "EMPLOYER" if role in ["employer", "employer login"] else "USER"

    token = create_access_token({"email": payload.email, "role": role})

    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none"
    )

    return {"access_token": token, "role": role}


# ==========================================================
# MODELS
# ==========================================================
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    contact: str
    company: Optional[str] = ""
    role: str


# ==========================================================
# REGISTER
# ==========================================================
@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT 1 FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    if existing:
        return {"status": "exists"}

    token = secrets.token_urlsafe(32)
    password_hash = hash_password(payload.password)

    role = (payload.role or "").strip().lower()
    role = "EMPLOYER" if role in ["employer", "employer login"] else "USER"

    db.execute(
        text("""
        INSERT INTO usersdata (
            full_name, email, contact, company, role,
            password_hash, verified, verification_token, created_date
        )
        VALUES (
            :full_name, :email, :contact, :company, :role,
            :password_hash, false, :token, NOW()
        )
        """),
        {
            "full_name": payload.full_name,
            "email": payload.email,
            "contact": payload.contact,
            "company": payload.company or "",
            "role": role,
            "password_hash": password_hash,
            "token": token
        }
    )

    db.commit()

    send_verification_email_via_gmail(payload.email, f"{FRONTEND_URL}/verify?token={token}")

    return {"status": "success"}