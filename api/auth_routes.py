from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import text

import os
import secrets
import traceback
import base64

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from pydantic import BaseModel, EmailStr
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from api.db import get_db
from api.utils.security import verify_password, create_access_token, hash_password
from api.schemas.auth_schema import LoginRequest, EmailCheckRequest
from api.gmail_service import get_gmail_service

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
    send_verification_email(payload.email, token)

    return {
        "status": "sent",
        "message": "Verification email resent successfully"
    }


# ==========================================================
# EMAIL FUNCTION (UPDATED - GMAIL API TOKEN FLOW)
# ==========================================================
def send_verification_email(email: str, token: str):
    print("===== EMAIL DEBUG START =====")
    print("TARGET EMAIL:", email)
    print("TOKEN:", token[:10] + "...")

    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
    verify_link = f"{BACKEND_URL}/verify?token={token}"
    
    subject = "Verify your email - HiringCircle"

    # HTML email
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
          <h1 style="margin: 0;">{EMAIL_FROM_NAME}</h1>
        </div>
        <div style="background-color: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
          <h2 style="color: #1f2937;">Verify Your Email</h2>
          <p>Hello,</p>
          <p>Please verify your email by clicking below:</p>

          <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_link}" 
               style="background-color: #2563eb; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 6px;">
              Verify Email
            </a>
          </div>

          <p style="font-size: 14px;">
            Or copy this link:<br>
            {verify_link}
          </p>

          <hr>
          <p style="font-size: 12px;">
            If you didn’t create this account, ignore this email.
          </p>
        </div>
      </body>
    </html>
    """

    plain_body = f"""
Hello,

Verify your email:
{verify_link}

If you didn’t create this account, ignore this email.
"""

    try:
        print("🚀 Initializing Gmail API...")
        service = get_gmail_service()
        print("✅ Gmail API ready")

        message = MIMEMultipart("alternative")
        message["to"] = email
        message["subject"] = subject

        message.attach(MIMEText(plain_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        print("📧 Sending email...")
        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()

        print("✅ Email sent:", sent["id"])
        print("===== EMAIL DEBUG END =====")
        return True

    except Exception as e:
        print(f"❌ EMAIL ERROR: {str(e)}")
        print(traceback.format_exc())
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
        email_sent = send_verification_email(payload.email, token)

        return {
            "status": "success",
            "message": "Verification email sent" if email_sent else "User created but email failed"
        }

    except Exception as e:
        db.rollback()
        print("❌ REGISTRATION ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Registration failed")
