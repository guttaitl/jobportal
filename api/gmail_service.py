import os
import json
import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def get_gmail_service():
    token_json = os.getenv("GOOGLE_TOKEN_JSON")

    if not token_json:
        raise Exception("❌ GOOGLE_TOKEN_JSON missing")

    creds = Credentials.from_authorized_user_info(
        json.loads(token_json),
        SCOPES
    )

    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        print("🔄 Refreshing expired Gmail token...")
        try:
            creds.refresh(Request())
            print("✅ Token refreshed successfully")
        except Exception as e:
            print(f"❌ Token refresh failed: {e}")
            raise Exception(f"Gmail token refresh failed: {e}")

    return build('gmail', 'v1', credentials=creds)


def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        print("📧 Sending email to:", to_email)

        service = get_gmail_service()

        message = MIMEText(body, "html")
        message["to"] = to_email
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        print("✅ Email sent")
        return True

    except Exception as e:
        print("❌ Email failed:", str(e))
        return False
    
if __name__ == "__main__":
    print("🚀 Running Gmail test...")

    try:
        service = get_gmail_service()
        print("✅ Gmail service created")

        # OPTIONAL: send test email
        send_email(
            to_email="your_email@gmail.com",  # change this
            subject="Test Email",
            body="<h1>It works 🚀</h1>"
        )

    except Exception as e:
        print("❌ ERROR:", str(e))