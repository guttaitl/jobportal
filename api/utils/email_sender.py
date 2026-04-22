# ==========================================================
# EMAIL SENDER (CLEAN PRODUCTION VERSION)
# ==========================================================

import os
import base64
import logging
from pathlib import Path
from dotenv import load_dotenv

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from openai import OpenAI

# ==========================================================
# LOAD ENV
# ==========================================================

# Try .env.development first, fallback to .env
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env.development"
if not ROOT_ENV.exists():
    ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"

if os.getenv("RAILWAY_ENVIRONMENT") is None and ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)

logger = logging.getLogger("email_service")

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None


# ==========================================================
# CONFIG
# ==========================================================

def get_email_config():
    return {
        "from_email": os.getenv("EMAIL_FROM"),           # jobs@hiringcircle.us
        "from_name": os.getenv("EMAIL_FROM_NAME"),       # HiringCircle Jobs
        "to": os.getenv("JOB_ALERT_TO"),                 # noreply@hiringcircle.us
        "bcc": os.getenv("JOB_ALERT_BCC"),               # guttaitl@yahoo.com,krishna@nytpartners.com,ravi.oneplus2@gmail.com
        "client_id": os.getenv("GMAIL_CLIENT_ID"),
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        "refresh_token": os.getenv("GMAIL_REFRESH_TOKEN"),
    }

# ==========================================================
# SEND EMAIL (GMAIL API)
# ==========================================================

def send_email_gmail_api(to_list, bcc_list, subject, html, plain_text=None):

    config = get_email_config()

    if not config["client_id"] or not config["refresh_token"]:
        logger.error("Gmail API not configured — check GMAIL_CLIENT_ID and GMAIL_REFRESH_TOKEN env vars")
        return False

    try:
        logger.info(f"📧 Sending email: subject='{subject}' to={to_list}")

        creds = Credentials(
            None,
            refresh_token=config["refresh_token"],
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            token_uri="https://oauth2.googleapis.com/token"
        )

        service = build("gmail", "v1", credentials=creds)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config['from_name']} <no-reply@hiringcircle.us>"
        msg["Reply-To"] = "no-reply@hiringcircle.us"
        msg["To"] = ", ".join(to_list or ["no-reply@hiringcircle.us"])

        if bcc_list:
            msg["Bcc"] = ", ".join(bcc_list)

        # Use provided plain text or a default
        plain = plain_text or "Please view this email in an HTML-capable client."
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        logger.info(f"✅ Email sent: message_id={result.get('id')}")
        return True

    except Exception as e:
        logger.error(f"❌ Email failed: {e}")
        return False


# ==========================================================
# EMAIL HTML BUILDER
# ==========================================================

def build_job_email_html(job: dict, structured=None):

    role = job.get("job_title", "")
    company = job.get("user_company") or job.get("poster_company") or "HiringCircle"
    location = job.get("location", "-")
    job_type = job.get("employment_type", "Contract")
    description = job.get("job_description", "")
    poster_name = job.get("user_name") or job.get("poster_company") or "HiringCircle"
    if structured:
        skills = structured.get("skills", [])
        responsibilities = structured.get("responsibilities", [])
        description = structured.get("description", job.get("job_description", ""))
    else:
        skills = job.get("skills", "")
        responsibilities = job.get("responsibilities", "")
        description = job.get("job_description", "")

    apply_url = f"https://www.hiringcircle.us/apply/{job.get('public_id') or job.get('jobid')}"

    if isinstance(skills, list):
        skills_html = "".join(f"<li>{s}</li>" for s in skills if s)
    else:
        skills_html = "".join(f"<li>{s}</li>" for s in skills.split("\n") if s.strip())

    if isinstance(responsibilities, list):
        resp_html = "".join(f"<li>{r}</li>" for r in responsibilities if r)
    else:
        resp_html = "".join(f"<li>{r}</li>" for r in responsibilities.split("\n") if r.strip())

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial; font-size:14px;">

<!-- APPLY LINK (TOP) -->
<p>
<a href="{apply_url}" style="color:#0b57d0; font-weight:bold;">
Apply Now
</a>
</p>

<p><b>Role:</b> {role}</p>
<p><b>Location:</b> {location}</p>
<p><b>Type:</b> {job_type}</p>

<p>{description}</p>

<p><b>Skills:</b></p>
<ul>
{skills_html}
</ul>
"""

    if resp_html:
        html += f"""
<p><b>Responsibilities:</b></p>
<ul>
{resp_html}
</ul>
"""

    html += f"""
<br>
<p>
{poster_name}<br>
{company}
</p>

</body>
</html>
"""

    return html


# ==========================================================
# SEND JOB EMAIL
# ==========================================================

def send_job_notification(job: dict, structured=None):
    config = get_email_config()
    
    # Get TO from env
    to_email = config.get("to")
    if not to_email:
        logger.error("JOB_ALERT_TO not configured")
        return False
    
    # Get BCC list from env
    bcc_raw = config.get("bcc", "")
    bcc_list = [
        email.strip()
        for email in (config.get("bcc") or "").split(",")
        if email.strip()
    ]
    
    if not bcc_list:
        logger.warning("JOB_ALERT_BCC not configured")
    
    subject = f"New Job Opening: {job.get('job_title', '')}"
    html = build_job_email_html(job, structured)
    
    return send_email_gmail_api([to_email], bcc_list, subject, html)

# ==========================================================
# VERIFY EMAIL
# ==========================================================

def send_verification_email(recipient: str, verification_url: str):

    subject = "Verify your email - HiringCircle"

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">
        <div style="background:#2563eb;color:white;padding:20px;text-align:center;border-radius:8px 8px 0 0;">
          <h1 style="margin:0;">HiringCircle</h1>
        </div>

        <div style="background:#f9fafb;padding:30px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px;">
          <h2 style="color:#1f2937;">Verify Your Email</h2>
          <p>Hello,</p>
          <p>Please verify your email by clicking below:</p>

          <div style="text-align:center;margin:30px 0;">
            <a href="{verification_url}"
               style="background:#2563eb;color:white;padding:12px 30px;text-decoration:none;border-radius:6px;">
              Verify Email
            </a>
          </div>

          <p style="font-size:14px;">Or copy this link:<br>{verification_url}</p>

          <hr>
          <p style="font-size:12px;">
            If you didn't create this account, you can safely ignore this email.
          </p>
        </div>
      </body>
    </html>
    """

    plain_text = f"""Hello,

Please verify your email by clicking the link below:
{verification_url}

If you didn't create this account, you can safely ignore this email."""

    return send_email_gmail_api([recipient], [], subject, html, plain_text)
