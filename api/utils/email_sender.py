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

<<<<<<< HEAD
# Try .env.development first, fallback to .env
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env.development"
if not ROOT_ENV.exists():
    ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"

if os.getenv("RAILWAY_ENVIRONMENT") is None and ROOT_ENV.exists():
=======
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env.development"

if os.getenv("RAILWAY_ENVIRONMENT") is None:
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
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

<<<<<<< HEAD
def send_email_gmail_api(to_list, bcc_list, subject, html, plain_text=None):
=======
def send_email_gmail_api(to_list, bcc_list, subject, html):
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

    config = get_email_config()

    if not config["client_id"] or not config["refresh_token"]:
<<<<<<< HEAD
        logger.error("Gmail API not configured — check GMAIL_CLIENT_ID and GMAIL_REFRESH_TOKEN env vars")
        return False

    try:
        logger.info(f"📧 Sending email: subject='{subject}' to={to_list}")

=======
        logger.error("Gmail API not configured")
        return False

    try:
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
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

<<<<<<< HEAD
        # Use provided plain text or a default
        plain = plain_text or "Please view this email in an HTML-capable client."
        msg.attach(MIMEText(plain, "plain"))
=======
        msg.attach(MIMEText("New job opening available.", "plain"))
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

<<<<<<< HEAD
        result = service.users().messages().send(
=======
        service.users().messages().send(
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
            userId="me",
            body={"raw": raw}
        ).execute()

<<<<<<< HEAD
        logger.info(f"✅ Email sent: message_id={result.get('id')}")
        return True

    except Exception as e:
        logger.error(f"❌ Email failed: {e}")
=======
        logger.info(f"Email sent to {len(bcc_list)} users")
        return True

    except Exception as e:
        logger.error(f"Email failed: {e}")
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        return False


# ==========================================================
# EMAIL HTML BUILDER
# ==========================================================

<<<<<<< HEAD
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

    apply_url = f"https://www.hiringcircle.us/jobs/{job.get('public_id') or job.get('jobid')}/apply"

    if isinstance(skills, list):
        skills_html = "".join(f"<li>{s}</li>" for s in skills if s)
    else:
        skills_html = "".join(f"<li>{s}</li>" for s in skills.split("\n") if s.strip())

    if isinstance(responsibilities, list):
        resp_html = "".join(f"<li>{r}</li>" for r in responsibilities if r)
    else:
        resp_html = "".join(f"<li>{r}</li>" for r in responsibilities.split("\n") if r.strip())
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

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

<<<<<<< HEAD
def send_job_notification(job: dict, structured=None):
=======
def send_job_notification(job: dict):
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    config = get_email_config()
    
    # Get TO from env
    to_email = config.get("to")
    if not to_email:
        logger.error("JOB_ALERT_TO not configured")
        return False
    
    # Get BCC list from env
    bcc_raw = config.get("bcc", "")
<<<<<<< HEAD
    bcc_list = [
        email.strip()
        for email in (config.get("bcc") or "").split(",")
        if email.strip()
    ]
=======
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()]
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    
    if not bcc_list:
        logger.warning("JOB_ALERT_BCC not configured")
    
    subject = f"New Job Opening: {job.get('job_title', '')}"
<<<<<<< HEAD
    html = build_job_email_html(job, structured)
=======
    html = build_job_email_html(job)
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    
    return send_email_gmail_api([to_email], bcc_list, subject, html)

# ==========================================================
# VERIFY EMAIL
# ==========================================================

<<<<<<< HEAD
def send_application_notification_email(
    job_poster_email: str,
    job_title: str,
    job_id: str,
    applicant_name: str,
    applicant_email: str,
    applicant_phone: str,
    applicant_visa: str,
    applicant_location: str,
    match_score: float = None,
    overall_fit: str = None
):
    """Send email notification to job poster when a new application is submitted."""

    score_display = f"{match_score:.1f}%" if match_score else "Pending"
    fit_display = overall_fit if overall_fit else "Pending"

    # Score color based on fit
    if overall_fit and overall_fit.lower() == "excellent":
        score_color = "#22c55e"
    elif overall_fit and overall_fit.lower() == "good":
        score_color = "#3b82f6"
    elif overall_fit and overall_fit.lower() == "fair":
        score_color = "#f59e0b"
    elif overall_fit and overall_fit.lower() == "poor":
        score_color = "#ef4444"
    else:
        score_color = "#6b7280"

    applicants_url = f"https://www.hiringcircle.us/employer/applicants/{job_id}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                      color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #ffffff; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; }}
            .applicant-card {{ background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            .score-badge {{ display: inline-block; padding: 8px 16px; border-radius: 20px; font-weight: bold; color: white; background: {score_color}; }}
            .cta-button {{ display: inline-block; background: #4f46e5; color: white; padding: 12px 30px; 
                          text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 20px; }}
            .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1 style="margin: 0; font-size: 24px;">New Job Application</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Someone applied for your job posting</p>
        </div>
        
        <div class="content">
            <h2 style="color: #1f2937; margin-top: 0;">{job_title}</h2>
            <p style="color: #6b7280; font-size: 14px;">Job ID: {job_id}</p>
            
            <div class="applicant-card">
                <h3 style="margin-top: 0; color: #1f2937;">Applicant Details</h3>
                <p><strong>Name:</strong> {applicant_name}</p>
                <p><strong>Email:</strong> {applicant_email}</p>
                <p><strong>Phone:</strong> {applicant_phone}</p>
                <p><strong>Visa Status:</strong> {applicant_visa}</p>
                <p><strong>Location:</strong> {applicant_location}</p>
            </div>
            
            <div style="text-align: center; margin: 25px 0;">
                <p style="margin-bottom: 10px; color: #6b7280; font-size: 14px;">AI Match Score</p>
                <span class="score-badge">{score_display} — {fit_display}</span>
            </div>
            
            <div style="text-align: center;">
                <a href="{applicants_url}" class="cta-button">View All Applicants</a>
            </div>
        </div>
        
        <div class="footer">
            <p>This notification was sent automatically by HiringCircle AI.</p>
            <p>You are receiving this because you posted this job on HiringCircle.</p>
        </div>
=======
def send_verification_email(recipient: str, verification_url: str):

    html = f"""
    <html>
    <body>
        <h2>Welcome to HiringCircle</h2>
        <p>Please verify your email:</p>
        <a href="{verification_url}">Verify Email</a>
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    </body>
    </html>
    """

<<<<<<< HEAD
    plain_text = f"""New Job Application

Job: {job_title}
Job ID: {job_id}

Applicant: {applicant_name}
Email: {applicant_email}
Phone: {applicant_phone}
Visa: {applicant_visa}
Location: {applicant_location}
AI Match Score: {score_display} ({fit_display})

View applicants: {applicants_url}
"""

    config = get_email_config()
    return send_email_gmail_api(
        to_list=[job_poster_email],
        bcc_list=[],
        subject=f"New Application: {applicant_name} applied for {job_title}",
        html=html,
        plain_text=plain_text
    )


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
=======
    return send_email_gmail_api([recipient], [], "Verify your account", html)
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
