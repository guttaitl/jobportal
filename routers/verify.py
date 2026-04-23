from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
import psycopg2
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# --------------------------------------------------
# ENV
# --------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.hiringcircle.us").strip()

# Fix postgres:// → postgresql:// for psycopg2 compatibility
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# --------------------------------------------------
# VERIFY EMAIL
# --------------------------------------------------

@router.get("/verify")
def verify_email(token: str):
    """
    Verify a user's email via verification token.
    Redirects to the frontend with ?verified=true|false.
    """
    if not DATABASE_URL:
        logger.error("DATABASE_URL not configured")
        raise HTTPException(status_code=500, detail="Database not configured")

    if not token:
        return RedirectResponse(url=f"{FRONTEND_URL}/?verified=false")

    conn = None
    cur = None

    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()

        # Atomic update: verify user and invalidate token in one query
        cur.execute(
            """
            UPDATE usersdata
            SET verified = true,
                verification_token = NULL
            WHERE verification_token = %s
            RETURNING id;
            """,
            (token,),
        )

        user = cur.fetchone()
        conn.commit()

        if not user:
            logger.warning(f"Invalid or expired verification token attempted: {token[:8]}...")
            return RedirectResponse(url=f"{FRONTEND_URL}/?verified=false")

        logger.info(f"Email verified for user id: {user[0]}")
        return RedirectResponse(url=f"{FRONTEND_URL}/?verified=true")

    except psycopg2.Error as e:
        logger.error(f"Database error during email verification: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/?verified=false")

    except Exception as e:
        logger.error(f"Unexpected error during email verification: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/?verified=false")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()