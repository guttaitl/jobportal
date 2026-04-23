<<<<<<< HEAD
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import text

import os
import secrets
import traceback

from pydantic import BaseModel, EmailStr
from typing import Optional
=======
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import secrets
import traceback
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail API imports
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

from api.db import get_db
from api.utils.security import verify_password, create_access_token, hash_password
from api.schemas.auth_schema import LoginRequest, EmailCheckRequest
<<<<<<< HEAD
from api.utils.email_sender import send_verification_email as send_verification_email_via_gmail
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

router = APIRouter()

# ==========================================================
# CONFIG
# ==========================================================
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiringcircle.us")
EMAIL_FROM_NAME = "HiringCircle"
<<<<<<< HEAD
    
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
=======

# Gmail API Configuration
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")

# ==========================================================
# GMAIL API SERVICE
# ==========================================================
def get_gmail_service():
    """Build Gmail API service using refresh token"""
    try:
        if not all([GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET]):
            raise ValueError("Missing Gmail API credentials")
            
        creds = Credentials(
            None,  # No access token initially
            refresh_token=GMAIL_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        
        # Refresh to get valid access token
        creds.refresh(Request())
        return build('gmail', 'v1', credentials=creds, cache_discovery=False)
        
    except Exception as e:
        print(f"❌ Error creating Gmail service: {e}")
        raise

# ==========================================================
# EMAIL FUNCTION (GMAIL API)
# ==========================================================
def send_verification_email(email: str, token: str):
    print("===== EMAIL DEBUG START =====")
    print("TARGET EMAIL:", email)
    print("TOKEN:", token[:10] + "...")
    
    # Check for Gmail API credentials
    if not all([GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET]):
        print("❌ EMAIL ERROR: Missing Gmail API credentials")
        print("Make sure GMAIL_REFRESH_TOKEN, GMAIL_CLIENT_ID, and GMAIL_CLIENT_SECRET are set")
        print("===== EMAIL DEBUG END =====")
        return False

    verify_link = f"{FRONTEND_URL}/verify?token={token}"
    subject = "Verify your email - HiringCircle"
    
    # Create HTML email
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
          <h1 style="margin: 0;">{EMAIL_FROM_NAME}</h1>
        </div>
        <div style="background-color: #f9fafb; padding: 30px; border: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
          <h2 style="color: #1f2937; margin-top: 0;">Verify Your Email</h2>
          <p style="color: #4b5563; font-size: 16px;">Hello,</p>
          <p style="color: #4b5563; font-size: 16px;">
            Please verify your email by clicking the link below:
          </p>
          <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_link}" 
               style="background-color: #2563eb; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 6px; display: inline-block;">
              Verify Email
            </a>
          </div>
          <p style="color: #6b7280; font-size: 14px;">
            Or copy and paste this link:<br>
            <span style="color: #2563eb; word-break: break-all;">{verify_link}</span>
          </p>
          <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
          <p style="color: #9ca3af; font-size: 12px; margin: 0;">
            If you did not create this account, please ignore this email.<br>
            Sent by HiringCircle Jobs
          </p>
        </div>
      </body>
    </html>
    """
    
    # Plain text fallback
    plain_body = f"""
Hello,

Please verify your email by clicking the link below:

{verify_link}

If you did not create this account, ignore this email.
    """

    try:
        print("🚀 Initializing Gmail API...")
        service = get_gmail_service()
        print("✅ Gmail API service ready")

        # Create message
        message = MIMEMultipart('alternative')
        message['to'] = email
        message['from'] = f"{EMAIL_FROM_NAME} <jobs@hiringcircle.us>"
        message['subject'] = subject
        
        # Attach both plain and HTML versions
        message.attach(MIMEText(plain_body, 'plain'))
        message.attach(MIMEText(html_body, 'html'))
        
        # Encode to base64
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'raw': raw_message}
        
        print("📧 Sending email via Gmail API...")
        
        # Send via Gmail API
        sent_message = service.users().messages().send(
            userId="me", 
            body=body
        ).execute()
        
        print(f"✅ Email sent successfully! Message Id: {sent_message['id']}")
        print("===== EMAIL DEBUG END =====")
        return True

    except HttpError as e:
        print(f"❌ GMAIL API ERROR: {e}")
        if e.resp.status == 403:
            print("⚠️  Authentication error - check refresh token")
        elif e.resp.status == 400:
            print("⚠️  Bad request - check email format")
        print(traceback.format_exc())
        print("===== EMAIL DEBUG END =====")
        return False
        
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {str(e)}")
        print(traceback.format_exc())
        print("===== EMAIL DEBUG END =====")
        return False


# ==========================================================
# CHECK EMAIL AVAILABILITY (NEW - Required by frontend)
# ==========================================================
@router.post("/register/check")
def check_email_available(payload: EmailCheckRequest, db: Session = Depends(get_db)):
    """Check if email is available for registration"""
    existing = db.execute(
        text("SELECT email FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()
    
    if existing:
        return {"status": "EXISTS", "message": "Email already registered"}
    
    return {"status": "AVAILABLE", "message": "Email is available"}

>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

# ==========================================================
# LOGIN (UNCHANGED)
# ==========================================================
@router.post("/login")
<<<<<<< HEAD
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
=======
def login(payload: LoginRequest, db: Session = Depends(get_db)):
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

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

<<<<<<< HEAD
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none"
    )

=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role
    }


<<<<<<< HEAD
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
    
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
# ==========================================================
# REGISTER (UPDATED TO USE GMAIL API)
# ==========================================================
@router.post("/register")
<<<<<<< HEAD
def register(payload: RegisterRequest, db: Session = Depends(get_db)):

    print("📥 REGISTER REQUEST RECEIVED:", payload.email)

    existing = db.execute(
        text("SELECT 1 FROM usersdata WHERE email = :email"),
        {"email": payload.email}
    ).fetchone()

    if existing:
=======
def register(payload: dict, db: Session = Depends(get_db)):

    print("📥 REGISTER REQUEST RECEIVED:", payload["email"])

    existing = db.execute(
        text("SELECT email FROM usersdata WHERE email = :email"),
        {"email": payload["email"]}
    ).fetchone()

    if existing:
        print("⚠️ Email already exists:", payload["email"])
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        return {
            "status": "exists",
            "message": "Email already registered"
        }

    token = secrets.token_urlsafe(32)
<<<<<<< HEAD
    password_hash = hash_password(payload.password)

    role = (payload.role or "").strip().lower()
    role = "EMPLOYER" if role in ["employer", "employer login"] else "USER"
=======
    password_hash = hash_password(payload["password"])
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

    try:
        print("📝 Creating user in DB...")

        db.execute(
            text("""
<<<<<<< HEAD
                INSERT INTO usersdata (
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
                VALUES (
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
=======
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
                "full_name": payload["full_name"],
                "email": payload["email"],
                "contact": payload["contact"],
                "company": payload.get("company", ""),
                "role": payload["role"],
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
                "password_hash": password_hash,
                "token": token
            }
        )

        db.commit()
        print("✅ User created successfully")

<<<<<<< HEAD
        print("📧 Sending verification email...")
        email_sent = _do_send_verification_email(payload.email, token)
=======
        print("📧 Sending verification email via Gmail API...")
        email_sent = send_verification_email(payload["email"], token)

        if not email_sent:
            print("⚠️ Email sending failed - but user was created")
            # Optionally: You might want to delete the user or mark for retry
            # For now, we just warn but registration succeeds
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

        return {
            "status": "success",
            "message": "Verification email sent" if email_sent else "User created but email failed"
        }

    except Exception as e:
        db.rollback()
        print("❌ REGISTRATION ERROR:", str(e))
<<<<<<< HEAD
=======
        print(traceback.format_exc())

>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        raise HTTPException(status_code=500, detail="Registration failed")