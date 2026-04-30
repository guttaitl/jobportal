"""
Password Reset Routes
Handles forgot password and reset password functionality
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import secrets
import os
import logging

from api.db import get_db
from api.utils.security import get_current_user
from api.utils.email_sender import send_email_gmail_api

router = APIRouter()
logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiringcircle.us").strip()


# =========================================================
# REQUEST MODELS
# =========================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# =========================================================
# FORGOT PASSWORD
# =========================================================

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            text("""
                SELECT id, email, full_name, verified
                FROM usersdata
                WHERE email = :email
            """),
            {"email": request.email},
        ).fetchone()

        if not result:
            return {
                "success": True,
                "message": "If an account exists with this email, a reset link has been sent.",
            }

        if not result.verified:
            raise HTTPException(
                status_code=400,
                detail="Email not verified. Please verify your email first.",
            )

        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        db.execute(
            text("""
                INSERT INTO password_reset_tokens (
                    email, token, expires_at, created_at, used
                ) VALUES (
                    :email, :token, :expires_at, NOW(), false
                )
                ON CONFLICT (email) DO UPDATE SET
                    token = EXCLUDED.token,
                    expires_at = EXCLUDED.expires_at,
                    created_at = EXCLUDED.created_at,
                    used = false
            """),
            {
                "email": request.email,
                "token": reset_token,
                "expires_at": expires_at,
            },
        )
        db.commit()

        reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
        email_sent = _send_password_reset_email(
            request.email, result.full_name, reset_link
        )

        if not email_sent:
            logger.warning(f"Failed to send password reset email to {request.email}")

        return {
            "success": True,
            "message": "If an account exists with this email, a reset link has been sent.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process request")


# =========================================================
# RESET PASSWORD
# =========================================================

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            text("""
                SELECT email, expires_at, used
                FROM password_reset_tokens
                WHERE token = :token
            """),
            {"token": request.token},
        ).fetchone()

        if not result:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        if result.used:
            raise HTTPException(status_code=400, detail="Token already used")
        if result.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Token expired")

        from api.utils.security import hash_password

        password_hash = hash_password(request.new_password)

        db.execute(
            text("""
                UPDATE usersdata
                SET password_hash = :password_hash,
                    updated_at = NOW()
                WHERE email = :email
            """),
            {"password_hash": password_hash, "email": result.email},
        )

        db.execute(
            text("""
                UPDATE password_reset_tokens
                SET used = true
                WHERE token = :token
            """),
            {"token": request.token},
        )

        db.commit()
        return {"success": True, "message": "Password reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to reset password")


# =========================================================
# CHANGE PASSWORD (Authenticated)
# =========================================================

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        from api.utils.security import verify_password, hash_password

        user_email = current_user.get("email")

        result = db.execute(
            text("""
                SELECT password_hash
                FROM usersdata
                WHERE email = :email
            """),
            {"email": user_email},
        ).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(request.current_password, result.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        new_password_hash = hash_password(request.new_password)

        db.execute(
            text("""
                UPDATE usersdata
                SET password_hash = :password_hash,
                    updated_at = NOW()
                WHERE email = :email
            """),
            {"password_hash": new_password_hash, "email": user_email},
        )

        db.commit()
        return {"success": True, "message": "Password changed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change password error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to change password")


# =========================================================
# VERIFY RESET TOKEN
# =========================================================

@router.get("/verify-reset-token")
async def verify_reset_token(token: str, db: Session = Depends(get_db)):
    try:
        result = db.execute(
            text("""
                SELECT email, expires_at, used
                FROM password_reset_tokens
                WHERE token = :token
            """),
            {"token": token},
        ).fetchone()

        if not result or result.used or result.expires_at < datetime.utcnow():
            return {"valid": False}

        return {"valid": True, "email": result.email}

    except Exception as e:
        logger.error(f"Verify token error: {e}")
        return {"valid": False}


# =========================================================
# EMAIL HELPER
# =========================================================

def _send_password_reset_email(email: str, name: str, reset_link: str) -> bool:
    html = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
               color: white; padding: 30px; text-align: center;
               border-radius: 8px 8px 0 0; }}
    .content {{ background: #f9fafb; padding: 30px; border: 1px solid #e5e7eb;
                border-radius: 0 0 8px 8px; }}
    .button {{ display: inline-block; background: #4f46e5; color: white;
               padding: 12px 30px; text-decoration: none; border-radius: 6px;
               margin: 20px 0; }}
    .footer {{ text-align: center; color: #6b7280; font-size: 12px; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>Password Reset Request</h1></div>
    <div class="content">
      <h2>Hello {name or 'User'},</h2>
      <p>We received a request to reset your password for your HiringCircle account.</p>
      <p>Click the button below to reset your password:</p>
      <div style="text-align: center;">
        <a href="{reset_link}" class="button">Reset Password</a>
      </div>
      <p>Or copy and paste this link into your browser:</p>
      <p style="word-break: break-all; color: #4f46e5;">{reset_link}</p>
      <p><strong>This link will expire in 24 hours.</strong></p>
      <p>If you didn't request this password reset, please ignore this email.</p>
    </div>
    <div class="footer">
      <p>Sent by HiringCircle Jobs</p>
    </div>
  </div>
</body>
</html>"""

    plain_text = f"""Hello {name or 'User'},

We received a request to reset your password for your HiringCircle account.

Reset your password: {reset_link}

This link will expire in 24 hours.

If you didn't request this, please ignore this email."""

    return send_email_gmail_api(
        to_list=[email],
        bcc_list=[],
        subject="Password Reset - HiringCircle",
        html=html,
        plain_text=plain_text,
    )