"""
Vector Search Routes - Optimized Semantic Search with pgvector
- Full parity with original fields
- Production optimizations applied
"""
print("⚡Vector Search Route Loaded (Optimized)......")

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import time
import hashlib

from api.db import get_db
from api.utils.security import get_current_user
from api.utils.embedding_utils import (
    generate_embedding,
    generate_job_embedding,
    generate_resume_embedding,
    backfill_embeddings_for_submissions
)

router = APIRouter(tags=["Vector Search"])


# =========================================================
# CONFIG / HELPERS
# =========================================================

# Optional: tiny in-process cache (safe fallback if you don't have Redis)
_EMBED_CACHE = {}

def _norm(q: str) -> str:
    return " ".join((q or "").strip().lower().split())

def _cache_get(key: str):
    return _EMBED_CACHE.get(key)

def _cache_set(key: str, val):
    if len(_EMBED_CACHE) > 1000:
        _EMBED_CACHE.clear()
    _EMBED_CACHE[key] = val

async def _get_query_embedding(query: str):
    nq = _norm(query)
    key = hashlib.sha1(nq.encode()).hexdigest()
    cached = _cache_get(key)
    if cached:
        return cached
    emb = await generate_embedding(nq)
    if emb:
        _cache_set(key, emb)
    return emb

def _vec_str(v: List[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


# =========================================================
# MODELS
# =========================================================

class VectorSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=10, ge=1, le=100)
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0)
    probes: int = Field(default=10, ge=1, le=100, description="IVFFLAT probes (higher=better recall, slower)")


class VectorSearchResponse(BaseModel):
    success: bool
    query: str
    results: List[dict]
    total: int
    search_time_ms: float


class JobMatchRequest(BaseModel):
    job_id: str
    top_k: int = Field(default=10, ge=1, le=50)
    min_similarity: float = Field(default=0.65, ge=0.0, le=1.0)
    probes: int = Field(default=10, ge=1, le=100)


class HybridSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=100)
    vector_weight: float = Field(default=0.7)
    text_weight: float = Field(default=0.3)
    probes: int = Field(default=10, ge=1, le=100)


# =========================================================
# VECTOR SEARCH (OPTIMIZED)
# =========================================================

@router.post("/resumes/vector-search", response_model=VectorSearchResponse)
async def vector_search_resumes(
    request: VectorSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    start_time = time.time()

    try:
        emb = await _get_query_embedding(request.query)
        if not emb:
            raise HTTPException(status_code=500, detail="Failed to generate embedding")

        emb_str = _vec_str(emb)

        # Tune IVFFLAT probes for this session (safe no-op if not using ivfflat)
        db.execute(text("SET LOCAL ivfflat.probes = :p"), {"p": request.probes})

        # Compute distance once, then similarity from it; pre-limit in CTE
        result = db.execute(text("""
        WITH ranked AS (
            SELECT 
                s.submission_id,
                s.candidate_name,
                s.full_name,
                s.job_id,
                s.job_title,
                s.skills,
                s.city,
                s.state,
                s.formatted_html,
                s.resume_text,
                s.match_score,
                s.scoring_status,
                (s.embedding <=> (:q)::vector) AS dist
            FROM submissions s
            WHERE s.embedding IS NOT NULL
            ORDER BY s.embedding <=> (:q)::vector
            LIMIT :top_k
        )
        SELECT 
            *,
            (1 - dist) AS vector_similarity
        FROM ranked
        WHERE (1 - dist) >= :min_similarity
        ORDER BY dist ASC
        """), {
            "q": emb_str,
            "top_k": request.top_k,
            "min_similarity": request.min_similarity
        })

        rows = result.fetchall()

        results = []
        for r in rows:
            sim = round(r.vector_similarity, 4)
            results.append({
                "submission_id": r.submission_id,
                "candidate_name": r.candidate_name,
                "full_name": r.full_name,
                "job_id": r.job_id,
                "job_title": r.job_title,
                "skills": r.skills,
                "city": r.city,
                "state": r.state,
                "formatted_html": r.formatted_html,
                "match_score": r.match_score,
                "scoring_status": r.scoring_status,
                "similarity": sim,
                "similarity_percent": round(sim * 100, 1),
                "resume_preview": (
                    r.resume_text[:500] + "..."
                    if r.resume_text and len(r.resume_text) > 500
                    else r.resume_text
                )
            })

        return VectorSearchResponse(
            success=True,
            query=request.query,
            results=results,
            total=len(results),
            search_time_ms=round((time.time() - start_time) * 1000, 2)
        )

    except Exception as e:
        logging.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# JOB MATCHING (OPTIMIZED)
# =========================================================

@router.post("/ai-match/job-to-candidates-vector")
async def match_job_to_candidates_vector(
    request: JobMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    start_time = time.time()

    try:
        job = db.execute(text("""
            SELECT 
                jobid, job_title, job_description, skills, experience, location
            FROM job_postings
            WHERE jobid = :job_id
        """), {"job_id": request.job_id}).fetchone()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job_emb = await generate_job_embedding(
            job_title=job.job_title,
            job_description=job.job_description or "",
            skills_required=job.skills,
            experience_required=job.experience
        )
        if not job_emb:
            raise HTTPException(status_code=500, detail="Embedding failed")

        job_emb_str = _vec_str(job_emb)

        db.execute(text("SET LOCAL ivfflat.probes = :p"), {"p": request.probes})

        result = db.execute(text("""
        WITH ranked AS (
            SELECT 
                s.submission_id,
                s.candidate_name,
                s.full_name,
                s.job_id,
                s.job_title,
                s.skills,
                s.city,
                s.state,
                s.formatted_html,
                s.resume_text,
                s.match_score,
                s.scoring_status,
                (s.embedding <=> (:q)::vector) AS dist
            FROM submissions s
            WHERE s.embedding IS NOT NULL
            ORDER BY s.embedding <=> (:q)::vector
            LIMIT :top_k
        )
        SELECT 
            *,
            (1 - dist) AS similarity
        FROM ranked
        WHERE (1 - dist) >= :min_similarity
        ORDER BY dist ASC
        """), {
            "q": job_emb_str,
            "top_k": request.top_k,
            "min_similarity": request.min_similarity
        })

        rows = result.fetchall()

        matches = []
        for r in rows:
            sim = round(r.similarity, 4)
            matches.append({
                "submission_id": r.submission_id,
                "candidate_name": r.full_name,
                "similarity": sim,
                "similarity_percent": round(sim * 100, 1),
                "match_score": r.match_score,
                "scoring_status": r.scoring_status,
                "skills": r.skills,
                "city": r.city,
                "state": r.state,
                "formatted_html": r.formatted_html,
                "resume_preview": (
                    r.resume_text[:300] + "..."
                    if r.resume_text and len(r.resume_text) > 300
                    else r.resume_text
                )
            })

        return {
            "success": True,
            "job_id": request.job_id,
            "job_title": job.job_title,
            "matches_found": len(matches),
            "search_time_ms": round((time.time() - start_time) * 1000, 2),
            "matches": matches
        }

    except Exception as e:
        logging.error(f"Job matching failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# HYBRID SEARCH (BOUNDED + OPTIMIZED)
# =========================================================

@router.post("/resumes/hybrid-search")
async def hybrid_search_resumes(
    request: HybridSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    start_time = time.time()

    try:
        emb = await _get_query_embedding(request.query)
        if not emb:
            raise HTTPException(status_code=500, detail="Embedding failed")

        emb_str = _vec_str(emb)
        keywords = request.query.split()
        query_pattern = "%{}%".format("%".join(keywords))

        db.execute(text("SET LOCAL ivfflat.probes = :p"), {"p": request.probes})

        result = db.execute(text("""
        WITH vector_scores AS (
            SELECT 
                s.submission_id,
                s.candidate_name,
                s.full_name,
                s.job_id,
                s.job_title,
                s.skills,
                s.city,
                s.state,
                s.formatted_html,
                s.resume_text,
                s.match_score,
                s.scoring_status,
                (s.embedding <=> (:q)::vector) AS dist
            FROM submissions s
            WHERE s.embedding IS NOT NULL
            ORDER BY s.embedding <=> (:q)::vector
            LIMIT :top_k
        ),
        text_scores AS (
            SELECT 
                s.submission_id,
                (
                    CASE 
                        WHEN to_tsvector('english', s.resume_text) @@ plainto_tsquery(:query)
                        THEN 1.0 ELSE 0 
                    END
                    +
                    CASE WHEN s.skills ILIKE :query_pattern THEN 1.2 ELSE 0 END
                    +
                    CASE WHEN s.full_name ILIKE :query_pattern THEN 0.5 ELSE 0 END
                ) AS text_score
            FROM submissions s
        )
        SELECT 
            v.*,
            (1 - v.dist) AS vector_similarity,
            COALESCE(t.text_score, 0) AS text_score,
            (
                (:vector_weight * (1 - v.dist)) +
                (:text_weight * COALESCE(t.text_score, 0))
            ) AS combined_score
        FROM vector_scores v
        LEFT JOIN text_scores t 
            ON v.submission_id = t.submission_id
        ORDER BY combined_score DESC
        LIMIT :top_k
        """), {
            "q": emb_str,
            "query": request.query,
            "query_pattern": query_pattern,
            "vector_weight": request.vector_weight,
            "text_weight": request.text_weight,
            "top_k": request.top_k
        })

        rows = result.fetchall()

        results = []
        for r in rows:
            results.append({
                "submission_id": r.submission_id,
                "full_name": r.full_name,
                "skills": r.skills,
                "city": r.city,
                "state": r.state,
                "formatted_html": r.formatted_html,
                "job_id": r.job_id,
                "job_title": r.job_title,
                "match_score": r.match_score,
                "scoring_status": r.scoring_status,
                "vector_similarity": round(r.vector_similarity, 4),
                "text_score": round(r.text_score, 4),
                "combined_score": round(r.combined_score, 4),
                "combined_percent": round(r.combined_score * 100, 1),
                "resume_preview": (
                    r.resume_text[:500] + "..."
                    if r.resume_text and len(r.resume_text) > 500
                    else r.resume_text
                )
            })

        return {
            "success": True,
            "query": request.query,
            "results": results,
            "total": len(results),
            "search_time_ms": round((time.time() - start_time) * 1000, 2)
        }

    except Exception as e:
        logging.error(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# ADMIN: BACKFILL + STATS
# =========================================================

@router.post("/admin/backfill-embeddings")
async def trigger_embedding_backfill(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    async def run_backfill():
        stats = await backfill_embeddings_for_submissions(db, batch_size)
        logging.info(f"Embedding backfill completed: {stats}")

    background_tasks.add_task(run_backfill)

    return {
        "success": True,
        "message": "Embedding backfill started",
        "batch_size": batch_size
    }


@router.get("/admin/embedding-stats")
async def get_embedding_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    result = db.execute(text("""
        SELECT 
            COUNT(*) AS total_submissions,
            COUNT(embedding) AS with_embeddings,
            COUNT(*) - COUNT(embedding) AS without_embeddings,
            ROUND(COUNT(embedding) * 100.0 / NULLIF(COUNT(*), 0), 2) AS coverage_percent
        FROM submissions
    """))

    row = result.fetchone()

    return {
        "success": True,
        "total_submissions": row.total_submissions,
        "with_embeddings": row.with_embeddings,
        "without_embeddings": row.with_embeddings and (row.total_submissions - row.with_embeddings) or 0,
        "coverage_percent": row.coverage_percent or 0
    }


# =========================================================
# ADMIN: INDEX BOOTSTRAP (RUN ONCE)
# =========================================================

@router.post("/admin/setup-vector-indexes")
async def setup_vector_indexes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Run once to ensure indexes exist.
    Safe to re-run.
    """
    try:
        # IVFFLAT (good default). Adjust lists based on table size.
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c 
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'idx_submissions_embedding_ivfflat'
                ) THEN
                    CREATE INDEX idx_submissions_embedding_ivfflat
                    ON submissions
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                END IF;
            END$$;
        """))

        # Text GIN index for hybrid search
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_submissions_resume_tsv
            ON submissions
            USING GIN (to_tsvector('english', resume_text));
        """))

        db.commit()

        return {
            "success": True,
            "message": "Indexes ensured (ivfflat + GIN)."
        }

    except Exception as e:
        logging.error(f"Index setup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# SINGLE EMBEDDING GENERATION
# =========================================================

@router.post("/resumes/{submission_id}/generate-embedding")
async def generate_single_embedding(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        row = db.execute(text("""
            SELECT submission_id, resume_text, full_name, skill_matrix
            FROM submissions
            WHERE submission_id = :submission_id
        """), {"submission_id": submission_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")

        embedding = await generate_resume_embedding(
            resume_text=row.resume_text or "",
            full_name=row.full_name,
            skills=row.skill_matrix
        )

        if not embedding:
            raise HTTPException(status_code=500, detail="Failed to generate embedding")

        db.execute(text("""
            UPDATE submissions
            SET embedding = (:embedding)::vector
            WHERE submission_id = :submission_id
        """), {
            "submission_id": submission_id,
            "embedding": _vec_str(embedding)
        })
        db.commit()

        return {
            "success": True,
            "submission_id": submission_id,
            "message": "Embedding generated and saved"
        }

    except Exception as e:
        logging.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))