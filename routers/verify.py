from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
import psycopg2
import os

router = APIRouter()

<<<<<<< HEAD
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
=======
DATABASE_URL = os.getenv("DATABASE_URL")
FRONTEND_LOGIN_URL = os.getenv("FRONTEND_URL", "https://www.hiringcircle.us")
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

@router.get("/verify")
def verify_email(token: str):

    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
<<<<<<< HEAD
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE usersdata
            SET verified = true,
                verification_token = NULL
            WHERE verification_token = %s
            RETURNING id;
=======
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 🔍 Check token
        cur.execute(
            """
            SELECT id FROM usersdata
            WHERE verification_token = %s
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
            """,
            (token,)
        )

        user = cur.fetchone()

        if not user:
<<<<<<< HEAD
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
=======
            raise HTTPException(status_code=400, detail="Invalid or expired verification link")

        # ✅ Update user
        cur.execute(
            """
            UPDATE usersdata
            SET verified = true,
                verification_token = NULL
            WHERE verification_token = %s
            """,
            (token,)
        )

        conn.commit()

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()
<<<<<<< HEAD
=======

    # 🚀 Redirect to frontend login page after verification
    return {"success": True, "message": "Email verified successfully"}
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
