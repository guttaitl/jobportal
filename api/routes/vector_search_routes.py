"""
Vector Search Routes - Semantic AI Search with pgvector
Replaces slow ILIKE searches with fast vector similarity
"""
print("⚡Vector Search Route Loaded......")
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

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
# MODELS
# =========================================================

class VectorSearchRequest(BaseModel):
    query: str = Field(..., description="Search query (job description, skills, etc.)")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
    min_similarity: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum similarity threshold")


class VectorSearchResponse(BaseModel):
    success: bool
    query: str
    results: List[dict]
    total: int
    search_time_ms: float


class JobMatchRequest(BaseModel):
    job_id: str = Field(..., description="Job ID to find matching candidates for")
    top_k: int = Field(default=10, ge=1, le=50)
    min_similarity: float = Field(default=0.65, ge=0.0, le=1.0)


class HybridSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=10, ge=1, le=100)
    vector_weight: float = Field(default=0.7, ge=0.0, le=1.0, description="Weight for vector similarity")
    text_weight: float = Field(default=0.3, ge=0.0, le=1.0, description="Weight for text matching")


# =========================================================
# VECTOR SEARCH ENDPOINTS
# =========================================================

@router.post("/resumes/vector-search", response_model=VectorSearchResponse)
async def vector_search_resumes(
    request: VectorSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Semantic search for resumes using vector embeddings.
    
    This is 10-50x faster than ILIKE search and understands meaning, not just keywords.
    
    Example queries:
    - "Senior Python developer with Django experience"
    - "Machine learning engineer with TensorFlow"
    - "DevOps engineer AWS Kubernetes"
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Generate embedding
        query_embedding = await generate_embedding(request.query)

        if not query_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")

        # 3. EXECUTE QUERY  ✅ (this was missing)
        result = db.execute(text("""
        SELECT 
            s.submission_id,
            s.candidate_name,
            1 - (s.embedding <=> :query_embedding) AS similarity
        FROM submissions s
        WHERE s.embedding IS NOT NULL
        ORDER BY s.embedding <=> :query_embedding
        LIMIT :top_k;
        """), {
            "query_embedding": query_embedding,
            "top_k": request.top_k
        })

        # 4. Fetch rows
        rows = result.fetchall()

        # 5. Format response
        results = []
        for row in rows:
            results.append({
                "submission_id": row.submission_id,
                "full_name": row.full_name,
                "job_id": row.job_id,
                "job_title": row.job_title,
                "match_score": row.match_score,
                "scoring_status": row.scoring_status,
                "similarity": round(row.similarity, 4),
                "similarity_percent": round(row.similarity * 100, 1),
                "resume_preview": (row.resume_text[:500] + "...") if row.resume_text and len(row.resume_text) > 500 else row.resume_text
            })
        search_time_ms = round((time.time() - start_time) * 1000, 2)
        
        return VectorSearchResponse(
            success=True,
            query=request.query,
            results=results,
            total=len(results),
            search_time_ms=search_time_ms
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/ai-match/job-to-candidates-vector")
async def match_job_to_candidates_vector(
    request: JobMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Find best matching candidates for a job using vector similarity.
    
    This replaces the slow AI-based matching with fast semantic search.
    Results are ranked by semantic similarity to the job description.
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Get job details
        job_result = db.execute(text("""
            SELECT 
                jobid,
                job_title,
                job_description,
                skills,
                experience,
                location
            FROM job_postings
            WHERE jobid = :job_id
        """), {"job_id": request.job_id})
        
        job = job_result.fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 2. Generate job embedding
        job_embedding = await generate_job_embedding(
            job_title=job.job_title,
            job_description=job.job_description or "",
            skills_required=job.skills,
            experience_required=job.experience
        )

        if not job_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate job embedding")

        print("✅ job_embedding generated:", len(job_embedding))
        job_embedding_str = "[" + ",".join(map(str, job_embedding)) + "]"

        # 3. Vector search for matching candidates
        result = db.execute(text("""
        SELECT 
            s.submission_id,
            s.candidate_name,
            1 - (s.embedding <=> :job_embedding) AS similarity
        FROM submissions s
        WHERE s.embedding IS NOT NULL
        ORDER BY s.embedding <=> :job_embedding
        LIMIT :top_k;
        """), {
            "job_embedding": job_embedding_str,
            "min_similarity": request.min_similarity,
            "top_k": request.top_k
        })   

        rows = result.fetchall()
        
        # 4. Format matches
        matches = []
        for row in rows:
            matches.append({
                "submission_id": row.submission_id,
                "candidate_name": row.full_name,
                "similarity": round(row.similarity, 4),
                "similarity_percent": round(row.similarity * 100, 1),
                "match_score": row.match_score,
                "scoring_status": row.scoring_status,
                "skills": row.skill_matrix,
                "resume_preview": (row.resume_text[:300] + "...") if row.resume_text and len(row.resume_text) > 300 else row.resume_text
            })
        
        search_time_ms = round((time.time() - start_time) * 1000, 2)
        
        return {
            "success": True,
            "job_id": request.job_id,
            "job_title": job.job_title,
            "matches_found": len(matches),
            "search_time_ms": search_time_ms,
            "matches": matches
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Job matching failed: {e}")
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")

@router.post("/resumes/hybrid-search")
async def hybrid_search_resumes(
    request: HybridSearchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    import time
    start_time = time.time()

    try:
        # 1. Generate query embedding
        query_embedding = await generate_embedding(request.query)

        if not query_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate query embedding")

        # 🔥 Improve text matching (multi-keyword pattern)
        keywords = request.query.split()
        query_pattern = "%{}%".format("%".join(keywords))

        # 🔥 HNSW tuning (safe)
        db.execute(text("SET LOCAL hnsw.ef_search = 100;"))

        # 2. Hybrid search
        result = db.execute(text("""
        WITH vector_scores AS (
            SELECT 
                s.submission_id,
                s.full_name,
                s.job_id,
                s.job_title,
                s.resume_text,
                s.match_score,
                s.scoring_status,
                s.skill_matrix,
                1 - (s.embedding <=> CAST(:query_embedding AS vector)) AS vector_similarity
            FROM submissions s
            WHERE s.embedding IS NOT NULL
            ORDER BY s.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :top_k * 5
        ),

        text_scores AS (
            SELECT 
                s.submission_id,
                (
                    CASE 
                    WHEN to_tsvector('english', s.resume_text) @@ plainto_tsquery(:query)
                    THEN 1.0 ELSE 0 
                    END
                    CASE WHEN s.skill_matrix ILIKE :query_pattern THEN 1.2 ELSE 0 END +
                    CASE WHEN s.full_name ILIKE :query_pattern THEN 0.5 ELSE 0 END
                ) AS text_match
            FROM vector_scores vs
            JOIN submissions s 
                ON s.submission_id = vs.submission_id
        )

        SELECT 
            vs.submission_id,
            vs.full_name,
            vs.job_id,
            vs.job_title,
            vs.resume_text,
            vs.match_score,
            vs.scoring_status,
            vs.skill_matrix,
            vs.vector_similarity,
            COALESCE(ts.text_match, 0) AS text_match,
            (
                vs.vector_similarity * :vector_weight +
                COALESCE(ts.text_match, 0) * :text_weight
            ) AS combined_score

        FROM vector_scores vs
        LEFT JOIN text_scores ts 
            ON vs.submission_id = ts.submission_id

        ORDER BY combined_score DESC
        LIMIT :top_k
        """), {
            "query_embedding": query_embedding,
            "query_pattern": query_pattern,
            "vector_weight": request.vector_weight,
            "text_weight": request.text_weight,
            "top_k": request.top_k
        })

        rows = result.fetchall()

        # 3. Format results
        results = []
        for row in rows:
            results.append({
                "submission_id": row.submission_id,
                "full_name": row.full_name,
                "job_id": row.job_id,
                "job_title": row.job_title,
                "match_score": row.match_score,
                "scoring_status": row.scoring_status,
                "similarity": round(row.vector_similarity, 4),
                "text_match": round(row.text_match, 4),
                "combined_score": round(row.combined_score, 4),
                "combined_percent": round(row.combined_score * 100, 1),
                "resume_preview": (
                    row.resume_text[:500] + "..."
                    if row.resume_text and len(row.resume_text) > 500
                    else row.resume_text
                )
            })

        search_time_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "success": True,
            "query": request.query,
            "vector_weight": request.vector_weight,
            "text_weight": request.text_weight,
            "results": results,
            "total": len(results),
            "search_time_ms": search_time_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# =========================================================
# BACKGROUND TASKS
# =========================================================

@router.post("/admin/backfill-embeddings")
async def trigger_embedding_backfill(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(default=50, ge=10, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger background job to generate embeddings for all resumes without them.
    
    This is a one-time operation to populate the vector column.
    """
    async def run_backfill():
        stats = await backfill_embeddings_for_submissions(db, batch_size)
        logging.info(f"Embedding backfill completed: {stats}")
    
    background_tasks.add_task(run_backfill)
    
    return {
        "success": True,
        "message": "Embedding backfill started in background",
        "batch_size": batch_size
    }


@router.get("/admin/embedding-stats")
async def get_embedding_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get statistics about embeddings in the database."""
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
        "without_embeddings": row.without_embeddings,
        "coverage_percent": row.coverage_percent or 0
    }


# =========================================================
# SINGLE EMBEDDING GENERATION (for new uploads)
# =========================================================

@router.post("/resumes/{submission_id}/generate-embedding")
async def generate_single_embedding(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Generate embedding for a single submission (use after upload)."""
    try:
        # Get submission
        result = db.execute(text("""
            SELECT submission_id, resume_text, full_name, skill_matrix
            FROM submissions
            WHERE submission_id = :submission_id
        """), {"submission_id": submission_id})
        
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        # Generate embedding
        embedding = await generate_resume_embedding(
            resume_text=row.resume_text or "",
            full_name=row.full_name,
            skills=row.skill_matrix
        )
        
        if not embedding:
            raise HTTPException(status_code=500, detail="Failed to generate embedding")
        
        # Save to database
        db.execute(text("""
            UPDATE submissions
            SET embedding = :embedding
            WHERE submission_id = :submission_id
        """), {
            "submission_id": submission_id,
            "embedding": embedding
        })
        db.commit()
        
        return {
            "success": True,
            "submission_id": submission_id,
            "message": "Embedding generated and saved"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")
