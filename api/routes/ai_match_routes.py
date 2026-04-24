from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from openai import AsyncOpenAI
from datetime import datetime
import os
import json
import re
import logging
import hashlib
import asyncio

# ─── SOFT IMPORTS: FAISS + Embeddings ────────────────────
VECTOR_SEARCH_AVAILABLE = False
_faiss = None
_SentenceTransformer = None
_np = None

try:
    import numpy as _np
    import faiss as _faiss
    from sentence_transformers import SentenceTransformer as _SentenceTransformerClass

    _SentenceTransformer = _SentenceTransformerClass
    VECTOR_SEARCH_AVAILABLE = True
    logging.getLogger(__name__).info("✅ FAISS vector search enabled")
except ImportError as _import_err:
    logging.getLogger(__name__).warning(
        f"⚠️  FAISS vector search disabled (missing deps: {_import_err}). "
        "Install: pip install faiss-cpu sentence-transformers numpy"
    )

from api.db import get_db
from api.utils.security import get_current_user
from api.schemas.ai_match_schema import TopCandidatesResponse, CandidateMatch

router = APIRouter()
logger = logging.getLogger(__name__)

# =========================================================
# OPENAI CLIENT (optional enrichment for top-k only)
# =========================================================
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# =========================================================
# VECTOR SEARCH SERVICE (FAISS singleton)
# =========================================================

class VectorSearchService:
    """
    Singleton FAISS index manager.
    - IndexFlatIP + normalized embeddings = cosine similarity search
    - Lazy-built from DB on first request
    - Thread-safe via asyncio.Lock
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if self._initialized:
            return
        if not VECTOR_SEARCH_AVAILABLE:
            raise RuntimeError(
                "FAISS vector search requires: pip install faiss-cpu sentence-transformers numpy"
            )

        logger.info(f"Loading embedding model: {model_name}")
        self.model = _SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

        # IndexFlatIP with normalized vectors == cosine similarity
        self.resume_index = _faiss.IndexFlatIP(self.dim)
        self.job_index = _faiss.IndexFlatIP(self.dim)

        self.resume_ids: List[str] = []   # faiss_idx -> submission_id
        self.job_ids: List[str] = []      # faiss_idx -> jobid

        self._resume_built = False
        self._job_built = False
        self._lock = asyncio.Lock()
        self._initialized = True

    def encode(self, texts: List[str]):
        """L2-normalized embeddings for cosine-similarity search."""
        return self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    # ── text builders ─────────────────────────────────────

    @staticmethod
    def _build_job_text(row) -> str:
        return "\n".join(
            [
                f"Title: {row.job_title or ''}",
                f"Description: {row.job_description or ''}",
                f"Skills: {row.skills or ''}",
                f"Experience: {row.experience or ''}",
                f"Location: {row.location or ''}",
            ]
        ).strip()

    @staticmethod
    def _build_resume_text(row) -> str:
        return "\n".join(
            [
                f"Name: {row.full_name or ''}",
                f"Skills: {row.skills or ''}",
                f"Experience: {row.experience or ''}",
                f"Location: {row.location or ''}",
                f"Resume: {row.resume_text or ''}",
            ]
        ).strip()

    # ── index builders ────────────────────────────────────

    async def build_resume_index(self, db: Session):
        async with self._lock:
            rows = db.execute(
                text(
                    """
                    SELECT submission_id, full_name, resume_text, skills, experience, location
                    FROM submissions
                    WHERE resume_text IS NOT NULL
                    """
                )
            ).fetchall()

            self.resume_ids = []
            self.resume_index = _faiss.IndexFlatIP(self.dim)

            if not rows:
                self._resume_built = True
                return

            texts = [self._build_resume_text(r) for r in rows]
            self.resume_ids = [str(r.submission_id) for r in rows]

            embs = self.encode(texts)
            self.resume_index.add(embs)
            self._resume_built = True
            logger.info(f"Resume FAISS index built: {len(rows)} vectors")

    async def build_job_index(self, db: Session):
        async with self._lock:
            rows = db.execute(
                text(
                    """
                    SELECT jobid, job_title, job_description, skills, experience, location
                    FROM job_postings
                    """
                )
            ).fetchall()

            self.job_ids = []
            self.job_index = _faiss.IndexFlatIP(self.dim)

            if not rows:
                self._job_built = True
                return

            texts = [self._build_job_text(r) for r in rows]
            self.job_ids = [str(r.jobid) for r in rows]

            embs = self.encode(texts)
            self.job_index.add(embs)
            self._job_built = True
            logger.info(f"Job FAISS index built: {len(rows)} vectors")

    # ── search ────────────────────────────────────────────

    async def search_resumes(self, query_text: str, top_k: int = 20) -> List[dict]:
        async with self._lock:
            if not self._resume_built or self.resume_index.ntotal == 0:
                return []

            emb = self.encode([query_text])
            k = min(top_k, self.resume_index.ntotal)
            scores, indices = self.resume_index.search(emb, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self.resume_ids):
                    continue
                cosine = float(score)
                pct = max(0.0, cosine) * 100.0
                results.append(
                    {
                        "resume_id": self.resume_ids[idx],
                        "vector_score": round(pct, 2),
                        "raw_cosine": round(cosine, 4),
                    }
                )
            return results

    async def search_jobs(self, query_text: str, top_k: int = 20) -> List[dict]:
        async with self._lock:
            if not self._job_built or self.job_index.ntotal == 0:
                return []

            emb = self.encode([query_text])
            k = min(top_k, self.job_index.ntotal)
            scores, indices = self.job_index.search(emb, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self.job_ids):
                    continue
                cosine = float(score)
                pct = max(0.0, cosine) * 100.0
                results.append(
                    {
                        "job_id": self.job_ids[idx],
                        "vector_score": round(pct, 2),
                        "raw_cosine": round(cosine, 4),
                    }
                )
            return results


# Global singleton — only instantiated if deps are available
vector_service: Optional[VectorSearchService] = None
if VECTOR_SEARCH_AVAILABLE:
    try:
        vector_service = VectorSearchService()
    except Exception as e:
        logger.error(f"Failed to initialize VectorSearchService: {e}")
        vector_service = None


async def ensure_indices(db: Session):
    """Lazy-load FAISS indices on first matching request."""
    if vector_service is None:
        raise HTTPException(
            status_code=503,
            detail="Vector search unavailable. Install faiss-cpu sentence-transformers numpy",
        )
    if not vector_service._resume_built:
        await vector_service.build_resume_index(db)
    if not vector_service._job_built:
        await vector_service.build_job_index(db)


# =========================================================
# PYDANTIC MODELS
# =========================================================

class JobResumeMatchRequest(BaseModel):
    job_id: str
    top_k: Optional[int] = 10


class CandidateMatchRequest(BaseModel):
    resume_id: str
    top_k: Optional[int] = 10


class MatchResult(BaseModel):
    match_id: str
    job_id: Optional[str]
    resume_id: Optional[str]
    match_score: float
    match_reasons: List[str]
    skill_match: dict
    experience_match: dict
    overall_fit: str


# =========================================================
# OPTIONAL AI ENRICHMENT (top-k only)
# =========================================================

async def enrich_match_with_ai(job_text: str, resume_text: str) -> dict:
    """
    Lightweight OpenAI call to generate human-readable reasoning
    and structured sub-scores for the final shortlist.
    """
    if not openai_client.api_key:
        return {
            "overall_fit": "Good",
            "reasoning": "FAISS vector semantic match.",
            "skill_match_score": 0,
            "experience_match_score": 0,
            "key_matching_skills": [],
            "missing_skills": [],
        }

    try:
        prompt = f"""You are an expert recruiter AI. Analyze this job-resume pair briefly.

JOB:
{job_text[:2000]}

RESUME:
{resume_text[:2000]}

Return STRICT JSON:
{{
    "overall_fit": "Excellent" | "Good" | "Fair" | "Poor",
    "reasoning": "One sentence explanation.",
    "skill_match_score": 0-100,
    "experience_match_score": 0-100,
    "key_matching_skills": ["skill1", "skill2"],
    "missing_skills": ["skill3"]
}}"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=350,
        )

        content = response.choices[0].message.content.strip()
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                result = json.loads(m.group(0))
            else:
                raise ValueError("No JSON found")

        return {
            "overall_fit": result.get("overall_fit", "Good"),
            "reasoning": result.get("reasoning", ""),
            "skill_match_score": result.get("skill_match_score", 0),
            "experience_match_score": result.get("experience_match_score", 0),
            "key_matching_skills": result.get("key_matching_skills", []),
            "missing_skills": result.get("missing_skills", []),
        }

    except Exception as e:
        logger.error(f"AI enrichment failed: {e}")
        return {
            "overall_fit": "Good",
            "reasoning": "FAISS vector semantic match.",
            "skill_match_score": 0,
            "experience_match_score": 0,
            "key_matching_skills": [],
            "missing_skills": [],
        }


# =========================================================
# ROUTES
# =========================================================

@router.post("/ai-match/job-to-candidates")
async def match_job_to_candidates(
    request: JobResumeMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Find best matching candidates for a job.
    1. FAISS vector retrieval (semantic similarity)
    2. Optional OpenAI enrichment on the shortlist only
    3. Persist results to ai_matches table
    """
    await ensure_indices(db)

    # ── fetch job ─────────────────────────────────────────
    job_row = db.execute(
        text(
            """
            SELECT jobid, job_title, job_description, skills, experience, location
            FROM job_postings
            WHERE jobid = :job_id
            """
        ),
        {"job_id": request.job_id},
    ).fetchone()

    if not job_row:
        raise HTTPException(status_code=404, detail="Job not found")

    job_text = vector_service._build_job_text(job_row)

    # ── FAISS vector search ───────────────────────────────
    vector_results = await vector_service.search_resumes(job_text, top_k=20)
    if not vector_results:
        return {
            "success": True,
            "job_id": request.job_id,
            "job_title": job_row.job_title,
            "total_candidates": vector_service.resume_index.ntotal,
            "processed_candidates": 0,
            "matches_found": 0,
            "matches": [],
        }

    # ── fetch resume rows ─────────────────────────────────
    resume_ids = [r["resume_id"] for r in vector_results]
    placeholders = ", ".join([f":id{i}" for i in range(len(resume_ids))])
    params = {f"id{i}": rid for i, rid in enumerate(resume_ids)}

    resume_rows = db.execute(
        text(
            f"""
            SELECT submission_id, full_name, resume_text, skills, experience, location
            FROM submissions
            WHERE submission_id IN ({placeholders})
            """
        ),
        params,
    ).fetchall()
    resume_map = {str(r.submission_id): r for r in resume_rows}

    # ── enrich + build response (parallel, limited) ───────
    semaphore = asyncio.Semaphore(5)

    async def process(vec_res: dict):
        async with semaphore:
            rid = vec_res["resume_id"]
            resume = resume_map.get(rid)
            if not resume:
                return None

            r_text = vector_service._build_resume_text(resume)
            ai = await enrich_match_with_ai(job_text, r_text)

            match_id = hashlib.md5(
                f"{request.job_id}_{rid}".encode()
            ).hexdigest()[:20]

            v_score = vec_res["vector_score"]
            return {
                "match_id": match_id,
                "job_id": request.job_id,
                "resume_id": rid,
                "candidate_name": resume.full_name,
                "candidate_email": None,
                "match_score": v_score,
                "skill_match_score": round(ai.get("skill_match_score") or v_score, 2),
                "experience_match_score": round(
                    ai.get("experience_match_score") or v_score, 2
                ),
                "experience_years_match": (ai.get("experience_match_score") or 0) > 60,
                "key_matching_skills": ai.get("key_matching_skills", []),
                "missing_skills": ai.get("missing_skills", []),
                "overall_fit": ai.get("overall_fit", "Good"),
                "reasoning": ai.get("reasoning", "FAISS vector similarity match"),
            }

    matches = [m for m in await asyncio.gather(*[process(r) for r in vector_results]) if m]
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    top_matches = matches[: request.top_k]

    # ── persist ───────────────────────────────────────────
    for m in top_matches:
        db.execute(
            text(
                """
                INSERT INTO ai_matches (
                    match_id, job_id, resume_id, match_score,
                    skill_match_score, experience_match_score, overall_fit,
                    reasoning, created_at, created_by
                ) VALUES (
                    :match_id, :job_id, :resume_id, :match_score,
                    :skill_match_score, :experience_match_score, :overall_fit,
                    :reasoning, NOW(), :created_by
                )
                ON CONFLICT (match_id) DO UPDATE SET
                    match_score = EXCLUDED.match_score,
                    skill_match_score = EXCLUDED.skill_match_score,
                    experience_match_score = EXCLUDED.experience_match_score,
                    overall_fit = EXCLUDED.overall_fit,
                    reasoning = EXCLUDED.reasoning,
                    updated_at = NOW()
                """
            ),
            {
                "match_id": m["match_id"],
                "job_id": m["job_id"],
                "resume_id": m["resume_id"],
                "match_score": m["match_score"],
                "skill_match_score": m["skill_match_score"],
                "experience_match_score": m["experience_match_score"],
                "overall_fit": m["overall_fit"],
                "reasoning": m["reasoning"],
                "created_by": current_user.get("email", "system"),
            },
        )
    db.commit()

    return {
        "success": True,
        "job_id": request.job_id,
        "job_title": job_row.job_title,
        "total_candidates": vector_service.resume_index.ntotal,
        "processed_candidates": len(vector_results),
        "matches_found": len(top_matches),
        "matches": top_matches,
    }


@router.post("/ai-match/candidate-to-jobs")
async def match_candidate_to_jobs(
    request: CandidateMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Find best matching jobs for a candidate using FAISS vector search.
    """
    await ensure_indices(db)

    # ── fetch resume ──────────────────────────────────────
    resume_row = db.execute(
        text(
            """
            SELECT submission_id, full_name, resume_text, skills, experience, location
            FROM submissions
            WHERE submission_id = :resume_id
            """
        ),
        {"resume_id": request.resume_id},
    ).fetchone()

    if not resume_row:
        raise HTTPException(status_code=404, detail="Resume not found")

    resume_text = vector_service._build_resume_text(resume_row)

    # ── FAISS vector search ───────────────────────────────
    vector_results = await vector_service.search_jobs(resume_text, top_k=20)
    if not vector_results:
        return {
            "success": True,
            "resume_id": request.resume_id,
            "candidate_name": resume_row.full_name,
            "total_jobs": vector_service.job_index.ntotal,
            "processed_jobs": 0,
            "matches_found": 0,
            "matches": [],
        }

    # ── fetch job rows ────────────────────────────────────
    job_ids = [r["job_id"] for r in vector_results]
    placeholders = ", ".join([f":id{i}" for i in range(len(job_ids))])
    params = {f"id{i}": jid for i, jid in enumerate(job_ids)}

    job_rows = db.execute(
        text(
            f"""
            SELECT jobid, job_title, job_description, skills, experience, location, client_name
            FROM job_postings
            WHERE jobid IN ({placeholders})
            """
        ),
        params,
    ).fetchall()
    job_map = {str(r.jobid): r for r in job_rows}

    semaphore = asyncio.Semaphore(5)

    async def process(vec_res: dict):
        async with semaphore:
            jid = vec_res["job_id"]
            job = job_map.get(jid)
            if not job:
                return None

            j_text = vector_service._build_job_text(job)
            ai = await enrich_match_with_ai(j_text, resume_text)

            match_id = hashlib.md5(
                f"{jid}_{request.resume_id}".encode()
            ).hexdigest()[:20]

            v_score = vec_res["vector_score"]
            return {
                "match_id": match_id,
                "job_id": jid,
                "job_title": job.job_title,
                "client_name": job.client_name,
                "resume_id": request.resume_id,
                "candidate_name": resume_row.full_name,
                "match_score": v_score,
                "skill_match_score": round(ai.get("skill_match_score") or v_score, 2),
                "experience_match_score": round(
                    ai.get("experience_match_score") or v_score, 2
                ),
                "experience_years_match": (ai.get("experience_match_score") or 0) > 60,
                "key_matching_skills": ai.get("key_matching_skills", []),
                "missing_skills": ai.get("missing_skills", []),
                "overall_fit": ai.get("overall_fit", "Good"),
                "reasoning": ai.get("reasoning", "FAISS vector similarity match"),
            }

    matches = [m for m in await asyncio.gather(*[process(r) for r in vector_results]) if m]
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    top_matches = matches[: request.top_k]

    return {
        "success": True,
        "resume_id": request.resume_id,
        "candidate_name": resume_row.full_name,
        "total_jobs": vector_service.job_index.ntotal,
        "processed_jobs": len(vector_results),
        "matches_found": len(top_matches),
        "matches": top_matches,
    }


@router.get("/ai-match/history")
def get_match_history(
    job_id: Optional[str] = None,
    resume_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Paginated AI match history."""
    offset = (page - 1) * limit

    query = """
        SELECT
            m.match_id,
            m.job_id,
            j.job_title,
            m.resume_id,
            s.full_name as candidate_name,
            m.match_score,
            m.skill_match_score,
            m.experience_match_score,
            m.overall_fit,
            m.reasoning,
            m.created_at
        FROM ai_matches m
        LEFT JOIN job_postings j ON m.job_id = j.jobid
        LEFT JOIN submissions s ON m.resume_id = s.submission_id
        WHERE 1=1
    """
    params: dict = {"limit": limit, "offset": offset}

    if job_id:
        query += " AND m.job_id = :job_id"
        params["job_id"] = job_id
    if resume_id:
        query += " AND m.resume_id = :resume_id"
        params["resume_id"] = resume_id

    query += " ORDER BY m.created_at DESC LIMIT :limit OFFSET :offset"

    rows = db.execute(text(query), params).fetchall()

    matches = []
    for r in rows:
        matches.append(
            {
                "match_id": r.match_id,
                "job_id": r.job_id,
                "job_title": r.job_title,
                "resume_id": r.resume_id,
                "candidate_name": r.candidate_name,
                "match_score": r.match_score,
                "skill_match_score": r.skill_match_score,
                "experience_match_score": r.experience_match_score,
                "overall_fit": r.overall_fit,
                "reasoning": r.reasoning,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {"success": True, "page": page, "limit": limit, "matches": matches}


@router.get("/ai-match/stats")
def get_match_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI matching statistics."""
    total_matches = db.execute(text("SELECT COUNT(*) FROM ai_matches")).fetchone()[0]
    avg_score = db.execute(text("SELECT AVG(match_score) FROM ai_matches")).fetchone()[0] or 0

    fit_distribution = [
        {"fit": row[0], "count": row[1]}
        for row in db.execute(
            text(
                """
                SELECT overall_fit, COUNT(*) as count
                FROM ai_matches
                GROUP BY overall_fit
                ORDER BY count DESC
                """
            )
        ).fetchall()
    ]

    recent_matches = db.execute(
        text(
            """
            SELECT COUNT(*) FROM ai_matches
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        )
    ).fetchone()[0]

    return {
        "success": True,
        "total_matches": total_matches,
        "average_match_score": round(float(avg_score), 2),
        "fit_distribution": fit_distribution,
        "recent_matches_7d": recent_matches,
    }


@router.get("/ai-match/top-candidates/{job_id}", response_model=TopCandidatesResponse)
def get_top_candidates(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return top 5 stored candidates for a job."""
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    m.resume_id,
                    COALESCE(s.full_name, 'Unknown Candidate') AS candidate_name,
                    m.match_score,
                    m.reasoning
                FROM ai_matches m
                LEFT JOIN submissions s ON m.resume_id = s.submission_id
                WHERE m.job_id = :job_id
                ORDER BY m.match_score DESC
                LIMIT 5
                """
            ),
            {"job_id": job_id},
        ).fetchall()

        if not rows:
            return TopCandidatesResponse(job_id=job_id, total_returned=0, candidates=[])

        candidates = [
            CandidateMatch(
                candidate_id=str(r.resume_id),
                candidate_name=r.candidate_name or "Unknown Candidate",
                email=None,
                match_score=round(float(r.match_score), 2),
                summary=r.reasoning,
            )
            for r in rows
        ]

        return TopCandidatesResponse(
            job_id=job_id, total_returned=len(candidates), candidates=candidates
        )

    except Exception as e:
        logger.error(f"Error in get_top_candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-match/admin/rebuild-indices")
async def rebuild_indices(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Admin endpoint to rebuild FAISS indices from the database.
    Call this after bulk imports or when embeddings drift.
    """
    if vector_service is None:
        raise HTTPException(
            status_code=503,
            detail="Vector search unavailable. Install faiss-cpu sentence-transformers numpy",
        )
    await vector_service.build_resume_index(db)
    await vector_service.build_job_index(db)
    return {
        "success": True,
        "resumes_indexed": vector_service.resume_index.ntotal,
        "jobs_indexed": vector_service.job_index.ntotal,
    }