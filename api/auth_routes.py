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

# ==========================================================
# CONFIG
# ==========================================================
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiringcircle.us")
EMAIL_FROM_NAME = "HiringCircle"
    
@router.post("/resend-verification")
def resend_verification(payload: EmailCheckRequest, db: Session = Depends(get_db)):

    print("🔁 RESEND VERIFICATION:", payload.email)

    user = db.execute(
        text("""
        SELECT verified FROM usersdata WHERE email = :email
        """),
        {"email": payload.email}
    ).fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user[0]:  # already verified
        return {
            "status": "already_verified",
            "message": "Email is already verified"
        }

    # 🔑 generate new token
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

    print("📧 Sending new verification email...")
    email_sent = _do_send_verification_email(payload.email, token)

    return {
        "status": "sent" if email_sent else "email_failed",
        "message": "Verification email resent successfully" if email_sent else "Failed to send verification email. Please try again."
    }


def _do_send_verification_email(email: str, token: str) -> bool:
    """Send verification email using the reliable email_sender module."""
    try:
        print("===== EMAIL DEBUG START =====")
        print("TARGET EMAIL:", email)
        print("TOKEN:", token[:10] + "...")

        verify_link = f"{FRONTEND_URL}/verify?token={token}"
        print("🔗 VERIFY LINK:", verify_link)

        success = send_verification_email_via_gmail(email, verify_link)

        if success:
            print("✅ Email sent successfully")
        else:
            print("❌ Email sender returned False")
        print("===== EMAIL DEBUG END =====")
        return success

    except Exception as e:
        print("❌ EMAIL ERROR:", str(e))
        traceback.print_exc()
        print("===== EMAIL DEBUG END =====")
        return False

# ==========================================================
# CHECK EMAIL AVAILABILITY
# ==========================================================
@router.post("/register/check")
def check_email_available(payload: EmailCheckRequest, db: Session = Depends(get_db)):
    existing = db.execute(
        text("SELECT 1 FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    if existing:
        return {
            "status": "EXISTS",
            "message": "Email already registered"
        }

    return {
        "status": "AVAILABLE",
        "message": "Email is available"
    }

# ==========================================================
# LOGIN (UNCHANGED)
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

    password_hash = result[0]
    verified = result[1]
    role = result[2]

    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verified:
        raise HTTPException(status_code=401, detail="Email not verified")

    role = (role or "").strip().lower()

    if role in ["employer", "employer login"]:
        role = "EMPLOYER"
    else:
        role = "USER"

    token = create_access_token({
        "email": payload.email,
        "role": role
    })

    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none"
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role
    }


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    contact: str
    company: Optional[str] = ""
    role: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    
# ==========================================================
# REGISTER (UPDATED TO USE GMAIL API)
# ==========================================================
@router.post("/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):

    print("📥 REGISTER REQUEST RECEIVED:", payload.email)

    existing = db.execute(
        text("SELECT 1 FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    if existing:
        return {
            "status": "exists",
            "message": "Email already registered"
        }

    token = secrets.token_urlsafe(32)
    password_hash = hash_password(payload.password)

    role = (payload.role or "").strip().lower()
    role = "EMPLOYER" if role in ["employer", "employer login"] else "USER"

    try:
        print("📝 Creating user in DB...")

        db.execute(
            text("""
            INSERT INTO usersdata
            (
                full_name,
                email,
                contact,
                company,
                role,
                password_hash,
                verified,
                verification_token,
                created_date
            )
            VALUES
            (
                :full_name,
                :email,
                :contact,
                :company,
                :role,
                :password_hash,
                false,
                :token,
                NOW()
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
        print("✅ User created successfully")

        print("📧 Sending verification email...")
        email_sent = _do_send_verification_email(payload.email, token)

        return {
            "status": "success",
            "message": "Verification email sent" if email_sent else "User created but email failed"
        }

    except Exception as e:
        db.rollback()
        print("❌ REGISTRATION ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Registration failed")
