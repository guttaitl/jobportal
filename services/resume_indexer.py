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


# 🔐 Efficient hash (streaming, no full file load)
def generate_file_hash(file_path: str) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# 🚀 Single async pipeline (PROCESS → COMMIT → EMBEDDINGS)
async def process_files_async(file_jobs):
    db: Session = SessionLocal()
    processed = 0
    failed = 0

    try:
        total = len(file_jobs)
        print(f"⚙️  Processing {total} resume{'s' if total != 1 else ''}...", end="", flush=True)

        for file_path, file_hash in file_jobs:
            try:
                await process_resume_file(
                    file_path=file_path,
                    db=db,
                    job_id=None,
                    resume_hash=file_hash
                )
                processed += 1
                print(".", end="", flush=True)   # one dot per success

            except Exception as e:
                failed += 1
                print("X", end="", flush=True)   # X for failures
                # Log the real error quietly so it doesn't spam the main line
                print(f"\n   ⚠️  {os.path.basename(file_path)}: {e}", end="")

        print()  # newline after dots

        db.commit()
        print(f"💾  DB commit successful ({processed}/{total} saved)")

        # 🔥 Now safely run embeddings
        print("⚡  Generating embeddings...", end="", flush=True)
        await run_indexer()
        print(" ✅")

    except Exception as e:
        db.rollback()
        print(f"\n❌  Async batch error: {e}")

    finally:
        db.close()

    # Final summary
    if failed:
        print(f"⚠️  Completed with {failed} failure(s)")
    else:
        print(f"✅  All {processed} resume(s) processed successfully")

def index_new_resumes():
    db: Session = SessionLocal()

    try:
        print("🚀 Loading Resumes...")

        if not os.path.exists(RESUME_FOLDER):
            print(f"❌ Folder not found: {RESUME_FOLDER}")
            return

        files = os.listdir(RESUME_FOLDER)
        print(f"📂 Found {len(files)} files")

        file_jobs = []
        skipped = 0

        for file_name in files:
            file_path = os.path.join(RESUME_FOLDER, file_name)

            # ✅ Skip non-files
            if not os.path.isfile(file_path):
                continue

            # ✅ Only allow valid resume formats
            if not file_name.lower().endswith((".pdf", ".docx")):
                print(f"⏭️ Skipping unsupported file: {file_name}")
                continue

            try:
                file_hash = generate_file_hash(file_path)

                # ✅ Check if already processed
                exists = db.execute(
                    text("""
                        SELECT 1 FROM candidate_resumes 
                        WHERE resume_hash = :hash
                    """),
                    {"hash": file_hash}
                ).fetchone()

                if exists:
                    skipped += 1
                    continue

                # 🔥 Add to actual processing queue
                file_jobs.append((file_path, file_hash))

            except Exception as e:
                print(f"❌ Failed file check: {file_name} → {e}")

        print(f"📥 Queued {len(file_jobs)} new resumes")
        print(f"⏭️ Skipped {skipped} already processed")

        db.close()

        # 🚀 Run async pipeline if needed
        if file_jobs:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
            except RuntimeError:
                pass
            asyncio.run(process_files_async(file_jobs))
            print(f"✅ New resumes processed: {len(file_jobs)}")
        else:
            print("⚡ No new resumes → skipping processing & embeddings")

    except Exception as e:
        print(f"❌ Indexing error: {e}")


# 🔁 Full pipeline entry
def full_pipeline():
    index_new_resumes()


# 🔁 Run once in background (non-blocking)
def start_pipeline_background():
    threading.Thread(target=full_pipeline, daemon=True).start()


# 🔁 Scheduler (every 5 mins)
def start_scheduler():
    while True:
        time.sleep(300)
        print("🔁 Running scheduled pipeline...")
        full_pipeline()