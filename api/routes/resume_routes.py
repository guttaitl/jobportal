"""
Resume Routes - Search, Upload, and Management
"""
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends, Request, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

import uuid
import os
import shutil
import re
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_

from api.utils.resume_parser import extract_text
from api.db import get_db
from api.models import Submission
from api.utils.security import get_current_user


router = APIRouter(tags=["Resumes"])

# ============ ENUMS ============

class SearchOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"

# ============ MODELS ============

class ResumeUploadResponse(BaseModel):
    id: str
    message: str
    status: str
    file_url: Optional[str] = None
    job_id: Optional[str] = None
    submission_id: Optional[str] = None

    class Config:
        from_attributes = True


class ResumeSearchRequest(BaseModel):
    query: str = Field(default="", description="Search query string")
    skills: Optional[List[str]] = Field(default=None, description="List of skills to search for")
    experience_min: Optional[int] = Field(default=None, description="Minimum years of experience")
    experience_max: Optional[int] = Field(default=None, description="Maximum years of experience")
    location: Optional[str] = Field(default=None, description="Location filter")
    boolean_mode: bool = Field(default=False, description="Enable Boolean search (AND, OR, NOT)")
    operator: SearchOperator = Field(default=SearchOperator.AND, description="Boolean operator")


class ResumeSearchResponse(BaseModel):
    resumes: List[dict]
    total: int
    page: int
    limit: int
    query: str


# ============ HELPER FUNCTIONS ============

async def process_resume_file(file_path: str, db: Session, resume_hash: str = None):
    try:
        resume_text = extract_text(file_path) or ""
        resume_text = re.sub(r'[^\x00-\x7F]+', ' ', resume_text)

        from ..utils.embedding_utils import generate_embedding
        embedding = await generate_embedding(resume_text)  # ✅ FIXED
        db.execute(
            text("""
                INSERT INTO submissions (
                    submission_id,
                    candidate_name,
                    full_name,
                    resume_text,
                    embedding,
                    resume_hash,
                    created_at
                )
                VALUES (
                    :submission_id,
                    :name,
                    :full_name,
                    :text,
                    :embedding,
                    :hash,
                    :created_at
                )
            """),
            {
                "submission_id": str(uuid.uuid4()),
                "name": os.path.basename(file_path),
                "full_name": os.path.basename(file_path),
                "text": resume_text,
                "embedding": embedding,
                "hash": resume_hash,
                "created_at": datetime.utcnow()
            }
        )
        db.commit()

    except Exception as e:
        db.rollback()
        db.close()
        db = next(get_db())
        print(f"❌ Failed processing file {file_path} → {e}")

def parse_boolean_query(query: str) -> dict:
    """
    Parse a Boolean search query into components.
    Supports AND, OR, NOT operators.
    Example: "python AND (django OR flask) NOT java"
    """
    query = query.strip()
    
    terms = {
        "include": [],
        "exclude": [],
        "optional": []
    }
    
    # Split by NOT first
    not_parts = re.split(r'\s+NOT\s+', query, flags=re.IGNORECASE)
    main_query = not_parts[0]
    
    if len(not_parts) > 1:
        for exclude_part in not_parts[1:]:
            exclude_terms = re.findall(r'\b\w+\b', exclude_part)
            terms["exclude"].extend(exclude_terms)
    
    # Check for OR in main query
    or_parts = re.split(r'\s+OR\s+', main_query, flags=re.IGNORECASE)
    
    if len(or_parts) > 1:
        terms["optional"] = [p.strip() for p in or_parts]
    else:
        # Check for AND
        and_parts = re.split(r'\s+AND\s+', main_query, flags=re.IGNORECASE)
        if len(and_parts) > 1:
            terms["include"] = [p.strip() for p in and_parts]
        else:
            # Simple space-separated terms (treated as AND)
            terms["include"] = main_query.split()
    
    return terms

def build_search_conditions(terms: dict, param_prefix: str = "term") -> tuple:
    """
    Build safe SQL search conditions with parameterized queries.
    
    Args:
        terms: Dict with 'include', 'exclude', 'optional' lists
        param_prefix: Prefix for parameter keys to avoid collisions
    
    Returns:
        Tuple of (where_clause_string, params_dict)
    """
    conditions = []
    params = {}
    counter = 0
    
    # Include terms (AND logic)
    for term in terms.get("include", []):
        key = f"{param_prefix}_inc_{counter}"
        conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key})")
        params[key] = f"%{term}%"
        counter += 1
    
    # Optional terms (OR logic)
    if terms.get("optional"):
        or_conditions = []
        for term in terms["optional"]:
            key = f"{param_prefix}_opt_{counter}"
            # Wrap each OR condition in parentheses to prevent precedence issues
            or_conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key})")
            params[key] = f"%{term}%"
            counter += 1
        if or_conditions:
            conditions.append(f"({' OR '.join(or_conditions)})")
    
    # Exclude terms (NOT logic)
    for term in terms.get("exclude", []):
        key = f"{param_prefix}_excl_{counter}"
        conditions.append(f"(resume_text NOT ILIKE :{key} AND full_name NOT ILIKE :{key})")
        params[key] = f"%{term}%"
        counter += 1
    
    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params

def build_simple_search_conditions(search_terms: List[str], param_prefix: str = "term") -> tuple:
    """
    Build safe SQL search conditions for simple space-separated terms.
    All terms are combined with AND logic.
    
    Args:
        search_terms: List of search terms
        param_prefix: Prefix for parameter keys
    
    Returns:
        Tuple of (where_clause_string, params_dict)
    """
    conditions = []
    params = {}
    
    for i, term in enumerate(search_terms):
        key = f"{param_prefix}_{i}"
        conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key})")
        params[key] = f"%{term}%"
    
    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params

# ============ UPLOAD ENDPOINTS ============
@router.post("/resumes/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    request: Request,
    db: Session = Depends(get_db),
    
    # File
    file: Optional[UploadFile] = File(None),
    resume: Optional[UploadFile] = File(None),
    
    # Candidate info
    full_name: Optional[str] = Form(None),
    applicant_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    applicant_email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    applicant_phone: Optional[str] = Form(None),
    
    # Additional fields
    skill: Optional[str] = Form(None),
    experience: Optional[str] = Form(None),
    visa: Optional[str] = Form(None),
    applicant_visa: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    applicant_city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    applicant_state: Optional[str] = Form(None),
    work_preference: Optional[str] = Form(None),
    
    # Job application fields (optional - if not provided, just uploads resume)
    job_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
):
    """
    Upload resume. Can be used for:
    1. Job application (when job_id is provided)
    2. Resume database upload (when job_id is not provided)
    """
    try:
        # Resolve field names
        resolved_name = applicant_name or full_name
        resolved_email = applicant_email or email
        resolved_phone = applicant_phone or phone
        resolved_visa = applicant_visa or visa
        resolved_city = applicant_city or city
        resolved_state = applicant_state or state
        resolved_skills = skill or ""
        resolved_experience = experience or ""
        
        # Validate required fields
        if not resolved_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name is required"
            )
        if not resolved_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email is required"
            )
        
        # Resolve file
        uploaded_file = file or resume
        if not uploaded_file:
            raise HTTPException(
                status_code=400,
                detail="Resume file is required"
            )
        # Generate IDs
        submission_uuid = str(uuid.uuid4())
        resume_id = str(uuid.uuid4())[:8].upper()
        
        # Save file if provided
        file_url = None
        file_name = None
        file_path = None 
        if uploaded_file:
            storage_path = os.environ.get("RESUME_STORAGE_PATH", "/tmp/resumes")
            os.makedirs(storage_path, exist_ok=True)
            
            file_extension = os.path.splitext(uploaded_file.filename)[1]
            file_name = f"{resume_id}{file_extension}"
            file_path = os.path.join(storage_path, file_name)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            
            file_url = f"/storage/resumes/{file_name}"
        
        resume_text = ""
        if uploaded_file and file_path:
            resume_text = extract_text(file_path)

        # Create Submission record
        submission = Submission(
            submission_id=submission_uuid,
            resume_id=int(uuid.uuid4().int % 2147483647),
            candidate_name=resolved_name,
            full_name=resolved_name,
            resume_text=resume_text,
            resume_hash=file_name or submission_uuid,   # ✅ ADD THIS

            job_id=job_id,
            job_title="",
            job_description="",
                    
            # AI scoring fields
            match_score=None,
            semantic_similarity=None,
            score_breakdown=None,
            fit_summary=None,
            confidence_band=None,
            final_recommendation=None,
            skill_matrix=None,
            fabrication_observations=None,
            scoring_status="pending",
            report_path=None,
            
            # Timestamps
            created_at=datetime.utcnow(),
            processed_at=None
        )
        
        db.add(submission)
        db.commit()
        db.refresh(submission)
        
        # Determine response message
        if job_id:
            message = "Job application submitted successfully - pending AI review"
        else:
            message = "Resume uploaded successfully to database"
        
        return ResumeUploadResponse(
            id=resume_id,
            message=message,
            status="pending",
            file_url=file_url,
            job_id=job_id,
            submission_id=submission.submission_id
            
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload: {str(e)}"
        )

# ============ SEARCH ENDPOINTS ============

@router.get("/resumes/search")
async def search_resumes(
    q: Optional[str] = Query(None, description="Search query"),
    skills: Optional[str] = Query(None, description="Comma-separated skills"),
    experience_min: Optional[int] = Query(None, description="Min years of experience"),
    experience_max: Optional[int] = Query(None, description="Max years of experience"),
    location: Optional[str] = Query(None, description="Location"),
    boolean_mode: bool = Query(False, description="Enable Boolean search"),
    scoring_status: Optional[str] = Query(None, description="Filter by scoring status"),
    has_score: Optional[bool] = Query(None, description="Filter by has match score"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    Search resumes with filters and Boolean search support.
    
    Boolean search examples:
    - "python AND django" - must have both
    - "python OR java" - must have either
    - "python NOT java" - has python but not java
    - "(python OR java) AND react" - complex query
    """
    try:
        offset = (page - 1) * limit
        
        # Build base queries
        base_query = "SELECT * FROM submissions WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM submissions WHERE 1=1"
        params = {}
        conditions = []
        
        # Text search
        if q:
            if boolean_mode:
                terms = parse_boolean_query(q)
                search_clause, search_params = build_search_conditions(terms, param_prefix="q")
                if search_clause:
                    conditions.append(search_clause)
                    params.update(search_params)
            else:
                # Simple search - split by spaces
                search_terms = q.split()
                search_clause, search_params = build_simple_search_conditions(search_terms, param_prefix="q")
                if search_clause:
                    conditions.append(search_clause)
                    params.update(search_params)
        
        # Skills filter
        if skills:
            skill_list = [s.strip() for s in skills.split(",")]
            for i, skill in enumerate(skill_list):
                key = f"skill_{i}"
                conditions.append(f"(resume_text ILIKE :{key} OR skill_matrix ILIKE :{key})")
                params[key] = f"%{skill}%"
        
        # Location filter
        if location:
            conditions.append("(resume_text ILIKE :location OR full_name ILIKE :location)")
            params["location"] = f"%{location}%"
        
        # Scoring status filter
        if scoring_status:
            conditions.append("scoring_status = :scoring_status")
            params["scoring_status"] = scoring_status
        
        # Has score filter
        if has_score is not None:
            if has_score:
                conditions.append("match_score IS NOT NULL")
            else:
                conditions.append("match_score IS NULL")
        
        # Combine conditions
        if conditions:
            where_clause = " AND ".join(conditions)
            base_query += f" AND {where_clause}"
            count_query += f" AND {where_clause}"
        
        # Add pagination
        base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        # Execute count query (exclude limit/offset params)
        count_params = {k: v for k, v in params.items() if k not in ["limit", "offset"]}
        total_result = db.execute(text(count_query), count_params)
        total = total_result.scalar()
        
        # Execute search query
        result = db.execute(text(base_query), params)
        rows = result.fetchall()
        
        # Format results
        resumes = []
        for row in rows:
            resumes.append({
                "submission_id": row.submission_id,
                "full_name": row.full_name,
                "job_id": row.job_id,
                "job_title": row.job_title,
                "match_score": row.match_score,
                "semantic_similarity": row.semantic_similarity,
                "scoring_status": row.scoring_status,
                "confidence_band": row.confidence_band,
                "overall_fit": row.final_recommendation,
                "report_path": row.report_path,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "processed_at": row.processed_at.isoformat() if row.processed_at else None
            })
        
        return {
            "success": True,
            "resumes": resumes,
            "total": total,
            "page": page,
            "limit": limit,
            "query": q,
            "boolean_mode": boolean_mode
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/resumes/search/advanced")
async def advanced_resume_search(
    request: ResumeSearchRequest,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Advanced resume search with structured filters.
    """
    return await search_resumes(
        q=request.query,
        skills=",".join(request.skills) if request.skills else None,
        experience_min=request.experience_min,
        experience_max=request.experience_max,
        location=request.location,
        boolean_mode=request.boolean_mode,
        page=page,
        limit=limit,
        db=db,
        current_user=current_user
    )


# ============ QUERY ENDPOINTS FOR SUBMISSIONS ============

@router.get("/submissions")
async def list_submissions(
    skip: int = 0,
    limit: int = 100,
    job_id: Optional[str] = None,
    scoring_status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submissions with filtering"""
    query = db.query(Submission)
    
    if job_id:
        query = query.filter(Submission.job_id == job_id)
    if scoring_status:
        query = query.filter(Submission.scoring_status == scoring_status)
    
    submissions = query.order_by(Submission.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "submissions": [
            {
                "submission_id": s.submission_id,
                "full_name": s.full_name,
                "job_id": s.job_id,
                "job_title": s.job_title,
                "scoring_status": s.scoring_status,
                "match_score": s.match_score,
                "created_at": s.created_at,
                "processed_at": s.processed_at
            }
            for s in submissions
        ],
        "total": query.count()
    }


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get specific submission with AI scoring details"""
    submission = db.query(Submission).filter(Submission.submission_id == submission_id).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    return {
        "submission_id": submission.submission_id,
        "full_name": submission.full_name,
        "job_id": submission.job_id,
        "job_title": submission.job_title,
        "scoring_status": submission.scoring_status,
        "match_score": submission.match_score,
        "semantic_similarity": submission.semantic_similarity,
        "score_breakdown": submission.score_breakdown,
        "fit_summary": submission.fit_summary,
        "confidence_band": submission.confidence_band,
        "final_recommendation": submission.final_recommendation,
        "skill_matrix": submission.skill_matrix,
        "fabrication_observations": submission.fabrication_observations,
        "report_path": submission.report_path,
        "created_at": submission.created_at,
        "processed_at": submission.processed_at
    }


@router.get("/submissions/job/{job_id}")
async def get_submissions_by_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all submissions for a specific job"""
    submissions = db.query(Submission).filter(Submission.job_id == job_id).all()
    
    return {
        "job_id": job_id,
        "submissions": [
            {
                "submission_id": s.submission_id,
                "full_name": s.full_name,
                "match_score": s.match_score,
                "scoring_status": s.scoring_status,
                "created_at": s.created_at
            }
            for s in submissions
        ],
        "total": len(submissions)
    }


# ============ RESUME ENDPOINTS ============

@router.get("/resumes")
async def list_resumes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all resumes (mapped from submissions)"""
    submissions = db.query(Submission).offset(skip).limit(limit).all()
    
    return {
        "resumes": [
            {
                "id": s.submission_id[:8].upper(),
                "full_name": s.full_name,
                "job_id": s.job_id,
                "status": s.scoring_status,
                "match_score": s.match_score,
                "created_at": s.created_at
            }
            for s in submissions
        ],
        "total": len(submissions)
    }


@router.get("/resumes/{resume_id}")
async def get_resume(
    resume_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get specific resume (mapped from submission)"""
    submission = db.query(Submission).filter(
        Submission.submission_id.like(f"{resume_id}%")
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    return {
        "id": resume_id,
        "full_name": submission.full_name,
        "job_id": submission.job_id,
        "job_title": submission.job_title,
        "status": submission.scoring_status,
        "match_score": submission.match_score,
        "created_at": submission.created_at
    }
