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

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env.development"

if os.getenv("RAILWAY_ENVIRONMENT") is None:
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

def send_email_gmail_api(to_list, bcc_list, subject, html):

    config = get_email_config()

    if not config["client_id"] or not config["refresh_token"]:
        logger.error("Gmail API not configured")
        return False

    try:
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

        msg.attach(MIMEText("New job opening available.", "plain"))
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        logger.info(f"Email sent to {len(bcc_list)} users")
        return True

    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


# ==========================================================
# EMAIL HTML BUILDER
# ==========================================================

def build_job_email_html(job: dict):

    role = job.get("job_title", "")
    company = job.get("user_company") or "HiringCircle"
    location = job.get("location", "-")
    job_type = job.get("employment_type", "Contract")
    description = job.get("job_description", "")
    skills = job.get("skills", "")
    responsibilities = job.get("responsibilities", "")
    poster_name = job.get("user_name", "")

    apply_url = f"https://www.hiringcircle.us/apply/{job.get('jobid')}"

    skills_html = "".join(f"<li>{s}</li>" for s in skills.split("\n") if s.strip())
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

def send_job_notification(job: dict):
    config = get_email_config()
    
    # Get TO from env
    to_email = config.get("to")
    if not to_email:
        logger.error("JOB_ALERT_TO not configured")
        return False
    
    # Get BCC list from env
    bcc_raw = config.get("bcc", "")
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()]
    
    if not bcc_list:
        logger.warning("JOB_ALERT_BCC not configured")
    
    subject = f"New Job Opening: {job.get('job_title', '')}"
    html = build_job_email_html(job)
    
    return send_email_gmail_api([to_email], bcc_list, subject, html)

# ==========================================================
# VERIFY EMAIL
# ==========================================================

def send_verification_email(recipient: str, verification_url: str):

    html = f"""
    <html>
    <body>
        <h2>Welcome to HiringCircle</h2>
        <p>Please verify your email:</p>
        <a href="{verification_url}">Verify Email</a>
    </body>
    </html>
    """

    return send_email_gmail_api([recipient], [], "Verify your account", html)