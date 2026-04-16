import os
import uuid
import asyncio
from datetime import datetime
from sqlalchemy import text
from api.db import get_db, SessionLocal
from api.utils.resume_parser import extract_text
from api.utils.embedding_utils import generate_embedding

RESUME_FOLDER = "uploads/resumes"

def ingest_resumes():
    db = next(get_db())
    files = os.listdir(RESUME_FOLDER)

    for file in files:
        if not file.endswith(".pdf"):
            continue

        file_path = os.path.join(RESUME_FOLDER, file)

        try:
            print(f"Processing: {file}")
            resume_text = extract_text(file_path)
            submission_id = str(uuid.uuid4())

            db.execute(text("""
                INSERT INTO submissions (
                    submission_id, candidate_name, full_name, resume_text, 
                    job_id, job_title, job_description, scoring_status, created_at
                )
                VALUES (
                    :submission_id, :candidate_name, :full_name, :resume_text,
                    NULL, '', '', 'pending', :created_at
                )
                ON CONFLICT (submission_id) DO NOTHING
            """), {
                "submission_id": submission_id,
                "candidate_name": file.replace(".pdf", ""),
                "full_name": file.replace(".pdf", ""),
                "resume_text": resume_text,
                "created_at": datetime.utcnow()
            })

        except Exception as e:
            print(f"❌ Failed: {file} → {e}")

    db.commit()

# ✅ FIXED: Made this async so we can await generate_embedding
async def run():
    print("⚡ Generating embeddings for new resumes...")

    db = SessionLocal()

    try:
        rows = db.execute(text("""
            SELECT submission_id, resume_text
            FROM submissions
            WHERE embedding IS NULL
        """)).fetchall()

        print(f"🧠 Found {len(rows)} resumes without embeddings")

        for row in rows:
            # ✅ FIXED: Added await here
            embedding = await generate_embedding(row.resume_text)
            
            # ✅ FIXED: Moved INSIDE the loop so each row gets updated
            db.execute(text("""
                UPDATE submissions
                SET embedding = :embedding
                WHERE submission_id = :id
            """), {
                "embedding": embedding,
                "id": row.submission_id
            })

        db.commit()
        print(f"✅ Generated embeddings for {len(rows)} resumes")

    except Exception as e:
        print(f"❌ Embedding error: {e}")
        raise

    finally:
        db.close()
