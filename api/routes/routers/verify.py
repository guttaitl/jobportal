from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
import psycopg2
import os

router = APIRouter()

# --------------------------------------------------
# ENV
# --------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:3000"  # safe default for local
)

# Fix postgres:// → postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


# --------------------------------------------------
# VERIFY EMAIL
# --------------------------------------------------

@router.get("/verify")
def verify_email(token: str):

    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE usersdata
            SET verified = true,
                verification_token = NULL
            WHERE verification_token = %s
            RETURNING id;
            """,
            (token,)
        )

        user = cur.fetchone()

        if not user:
            # ❌ invalid / expired token
            return RedirectResponse(
                url=f"{FRONTEND_URL}/?verified=false"
            )

        conn.commit()

        # ✅ success
        return RedirectResponse(
            url=f"{FRONTEND_URL}/?verified=true"
        )

    except Exception as e:
        print("❌ VERIFY ERROR:", str(e))

        return RedirectResponse(
            url=f"{FRONTEND_URL}/?verified=false"
        )

    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
