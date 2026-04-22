import os
import threading
import time
import hashlib
import asyncio
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.routes.resume_routes import process_resume_file
from scripts.ingest_resumes import run as run_indexer

RESUME_FOLDER = os.path.join(os.path.dirname(__file__), "..", "uploads")


# 🔥 Efficient hash (no full file load)
def generate_file_hash(file_path):
    hash_md5 = hashlib.md5()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)

    return hash_md5.hexdigest()


def index_new_resumes():
    db: Session = SessionLocal()

    try:
        print("🚀 Loading Resumes...")

        if not os.path.exists(RESUME_FOLDER):
            print(f"❌ Folder not found: {RESUME_FOLDER}")
            return

        files = os.listdir(RESUME_FOLDER)
        print(f"📂 Found {len(files)} files")

        new_count = 0

        for file_name in files:
            file_path = os.path.join(RESUME_FOLDER, file_name)

            if not os.path.isfile(file_path):
                continue

            try:
                # 🔑 Generate hash safely
                file_hash = generate_file_hash(file_path)

                # ✅ Check if already processed (FIXED)
                exists = db.execute(
                    text("SELECT 1 FROM submissions WHERE resume_hash = :hash"),
                    {"hash": file_hash}
                ).fetchone()

                if exists:
                    continue

                print(f"📥 Processing: {file_name}")

                # 🔥 MAIN PROCESS
                process_resume_file(
                    file_path=file_path,
                    db=db,
                    resume_hash=file_hash
                )

                new_count += 1

            except Exception as e:
                print(f"❌ Failed file: {file_name} → {e}")

        print(f"✅ New resumes processed: {new_count}")

        # ⚡ Only run embeddings if new resumes found
        if new_count > 0:
            print("⚡ Generating embeddings...")
            asyncio.run(run_indexer())
        else:
            print("⚡ No new resumes → skipping embeddings")

    except Exception as e:
        print(f"❌ Indexing error: {e}")

    finally:
        db.close()


def index_embeddings():
    print("⚡ Generating embeddings...")
    asyncio.run(run_indexer())


def full_pipeline():
    index_new_resumes()


# 🔁 Run once in background
def start_pipeline_background():
    threading.Thread(target=full_pipeline, daemon=True).start()


# 🔁 Scheduler (every 5 mins)
def start_scheduler():
    while True:
        time.sleep(300)
        print("🔁 Running scheduled pipeline...")
        full_pipeline()