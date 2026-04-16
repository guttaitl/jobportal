import os
import asyncio
from sqlalchemy import text
from api.db import engine
from api.utils.embedding_utils import generate_embedding

def match_job_to_candidates(job_id: str):
    with engine.connect() as conn:

        # 1. Fetch job
        job_query = text("""
            SELECT 
                jobid AS id,
                job_title AS title,
                job_description AS description
            FROM job_postings
            WHERE jobid = :job_id
        """)

        job_result = conn.execute(job_query, {"job_id": job_id}).fetchone()

        if not job_result:
            raise Exception("Job not found")

        job_text = f"""
        Title: {job_result.title}
        Description: {job_result.description}
        """

        job_embedding = asyncio.run(generate_embedding(job_text))

        # 2. Query pattern
        query_pattern = f"%{job_result.title}%"

        # 3. Load SQL file (from src/db)
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        PROJECT_ROOT = os.path.dirname(BASE_DIR)

        sql_path = os.path.join(
            PROJECT_ROOT,
            "src",
            "db",
            "queries",
            "matchJobToCandidates.sql"
        )

        with open(sql_path, "r") as f:
            match_query = f.read()

        # 4. Execute
        job_text = f"{job_result.title} {job_result.description}"

        result = conn.execute(
            text(match_query),
            {
                "job_embedding": job_embedding,
                "job_text": job_text
            }
        )

        return [dict(row._mapping) for row in result]