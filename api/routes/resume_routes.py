"""
Resume Routes - Search, Upload, and Management
"""

from api.utils.resume_parser import (
    extract_text,
    extract_skills,
    extract_location,
    extract_job_title,
    text_to_html
)

from fastapi import (
    APIRouter,
    File,
    UploadFile,
    Form,
    HTTPException,
    Depends,
    Request,
    Query,
    status,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid
import os
import shutil
import re
import json
import logging
import hashlib
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

from api.db import get_db
from api.models import Submission
from api.utils.security import get_current_user
logger = logging.getLogger(__name__)

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

async def process_resume_file(
    file_path: str,
    db: Session,
    job_id: str,
    resume_hash: str = None
):
    """Extract text, generate embedding, and store in submissions table."""
    try:
        # -----------------------------
        # TEXT EXTRACTION (FIXED)
        # -----------------------------
        resume_text = extract_text(file_path) or ""
        resume_text = re.sub(r"[^\x00-\x7F]+", " ", resume_text)

        # -----------------------------
        # STRUCTURED PARSING (NEW)
        # -----------------------------
        skills = extract_skills(resume_text)
        city, state = extract_location(resume_text)
        job_title = extract_job_title(resume_text)
        formatted_html = text_to_html(resume_text)

        # -----------------------------
        # EMBEDDING
        # -----------------------------
        from api.utils.embedding_utils import generate_embedding
        embedding_raw = await generate_embedding(resume_text)
        # Convert to PostgreSQL vector string format
        embedding = "[" + ",".join(str(x) for x in embedding_raw) + "]" if embedding_raw else None

        submission_id = str(uuid.uuid4())

        # -----------------------------
        # INSERT (FIXED + EXTENDED)
        # -----------------------------
        db.execute(
            text(
                """
                INSERT INTO submissions (
                    submission_id,
                    candidate_name,
                    full_name,
                    resume_text,
                    embedding,
                    resume_hash,
                    job_id,
                    skills,
                    city,
                    state,
                    job_title,
                    formatted_html,
                    created_at
                )
                VALUES (
                    :submission_id,
                    :name,
                    :full_name,
                    :text,
                    :embedding,
                    :hash,
                    :job_id,
                    :skills,
                    :city,
                    :state,
                    :job_title,
                    :formatted_html,
                    :created_at
                )
                """
            ),
            {
                "submission_id": submission_id,
                "name": os.path.basename(file_path),
                "full_name": os.path.basename(file_path),
                "text": resume_text,
                "embedding": embedding,
                "hash": resume_hash,
                "job_id": job_id,

                # 🔥 NEW FIELDS
                "skills": skills,
                "city": city,
                "state": state,
                "job_title": job_title,
                "formatted_html": formatted_html,

                "created_at": datetime.utcnow(),
            },
        )

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Failed processing file {file_path}: {e}")
        raise
    
def parse_boolean_query(query: str) -> dict:
    """
    Parse a Boolean search query into components.
    Supports AND, OR, NOT operators.
    Example: "python AND (django OR flask) NOT java"
    """
    query = query.strip()

    terms = {"include": [], "exclude": [], "optional": []}

    # Split by NOT first
    not_parts = re.split(r"\s+NOT\s+", query, flags=re.IGNORECASE)
    main_query = not_parts[0]

    if len(not_parts) > 1:
        for exclude_part in not_parts[1:]:
            exclude_terms = re.findall(r"\b\w+\b", exclude_part)
            terms["exclude"].extend(exclude_terms)

    # Check for OR in main query
    or_parts = re.split(r"\s+OR\s+", main_query, flags=re.IGNORECASE)

    if len(or_parts) > 1:
        terms["optional"] = [p.strip() for p in or_parts]
    else:
        # Check for AND
        and_parts = re.split(r"\s+AND\s+", main_query, flags=re.IGNORECASE)
        if len(and_parts) > 1:
            terms["include"] = [p.strip() for p in and_parts]
        else:
            # Simple space-separated terms (treated as AND)
            terms["include"] = main_query.split()

    return terms


def build_search_conditions(terms: dict, param_prefix: str = "term") -> tuple:
    """
    Build safe SQL search conditions with parameterized queries.

    Returns:
        Tuple of (where_clause_string, params_dict)
    """
    conditions = []
    params = {}
    counter = 0

    # Include terms (AND logic)
    for term in terms.get("include", []):
        key = f"{param_prefix}_inc_{counter}"
        conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key} OR candidate_name ILIKE :{key})")
        params[key] = f"%{term}%"
        counter += 1

    # Optional terms (OR logic)
    if terms.get("optional"):
        or_conditions = []
        for term in terms["optional"]:
            key = f"{param_prefix}_opt_{counter}"
            or_conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key} OR candidate_name ILIKE :{key})")
            params[key] = f"%{term}%"
            counter += 1
        if or_conditions:
            conditions.append(f"({' OR '.join(or_conditions)})")

    # Exclude terms (NOT logic)
    for term in terms.get("exclude", []):
        key = f"{param_prefix}_excl_{counter}"
        conditions.append(f"(resume_text NOT ILIKE :{key} AND full_name NOT ILIKE :{key} AND candidate_name NOT ILIKE :{key})")
        params[key] = f"%{term}%"
        counter += 1

    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params


def build_simple_search_conditions(search_terms: List[str], param_prefix: str = "term") -> tuple:
    """
    Build safe SQL search conditions for simple space-separated terms.
    All terms are combined with AND logic.
    """
    conditions = []
    params = {}

    for i, term in enumerate(search_terms):
        key = f"{param_prefix}_{i}"
        conditions.append(f"(resume_text ILIKE :{key} OR full_name ILIKE :{key} OR candidate_name ILIKE :{key})")
        params[key] = f"%{term}%"

    where_clause = " AND ".join(conditions) if conditions else ""
    return where_clause, params


# ============ AI MATCHING HELPERS ============

def calculate_match_score(job_text: str, resume_text: str) -> dict:
    """Calculate match score between job description and resume."""
    job_lower = (job_text or "").lower()
    resume_lower = (resume_text or "").lower()

    skills = [
        "python", "javascript", "java", "react", "node", "sql", "aws",
        "docker", "kubernetes", "machine learning", "ai", "data analysis",
        "typescript", "next.js", "vue", "angular", "mongodb", "postgresql",
        "redis", "graphql", "rest api", "git", "ci/cd", "jenkins",
        "tensorflow", "pytorch", "pandas", "numpy", "tableau", "spark",
        "hadoop", "scala", "go", "rust", "c++", "c#", "php", "ruby",
        "swift", "kotlin", "flutter", "react native", "android", "ios",
        "linux", "azure", "gcp", "google cloud", "terraform", "ansible",
        "prometheus", "grafana", "elasticsearch", "kafka", "rabbitmq",
    ]

    matching = []
    missing = []

    for skill in skills:
        in_job = skill in job_lower
        in_resume = skill in resume_lower

        if in_job and in_resume:
            matching.append(skill)
        elif in_job and not in_resume:
            missing.append(skill)

    job_skills_found = sum(1 for s in skills if s in job_lower)
    skill_score = (len(matching) / max(job_skills_found, 1)) * 100

    exp_keywords = ["years", "experience", "senior", "lead", "manager", "architect"]
    exp_matches = sum(1 for kw in exp_keywords if kw in job_lower and kw in resume_lower)
    exp_score = (exp_matches / len(exp_keywords)) * 100

    overall = (skill_score * 0.6) + (exp_score * 0.4)

    if overall >= 80:
        fit = "Excellent"
    elif overall >= 60:
        fit = "Good"
    elif overall >= 40:
        fit = "Fair"
    else:
        fit = "Poor"

    return {
        "overall_score": round(overall, 1),
        "skill_score": round(skill_score, 1),
        "experience_score": round(exp_score, 1),
        "matching_skills": matching,
        "missing_skills": missing,
        "fit": fit,
    }


def generate_report_html(candidate_name: str, job_title: str, score_data: dict) -> str:
    """Generate HTML report for candidate assessment."""
    matching_skills_html = "".join(f"<li>{skill}</li>" for skill in score_data["matching_skills"])
    missing_skills_html = "".join(f"<li>{skill}</li>" for skill in score_data["missing_skills"])

    score_color = {
        "excellent": "#22c55e",
        "good": "#3b82f6",
        "fair": "#f59e0b",
        "poor": "#ef4444",
    }.get(score_data["fit"].lower(), "#6b7280")

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Candidate Assessment Report - {candidate_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   color: white; padding: 30px; text-align: center; border-radius: 8px; }}
        .score-box {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; }}
        .score {{ font-size: 48px; font-weight: bold; color: {score_color}; }}
        .skills {{ display: flex; gap: 40px; margin: 20px 0; }}
        .skills-column {{ flex: 1; }}
        .matching {{ color: green; }}
        .missing {{ color: red; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Candidate Assessment Report</h1>
        <p>{candidate_name} for {job_title}</p>
    </div>
    <div class="score-box">
        <div class="score">{score_data['overall_score']}%</div>
        <p>Overall Match Score</p>
        <p><strong>Fit:</strong> {score_data['fit']}</p>
    </div>
    <div class="skills">
        <div class="skills-column">
            <h3 class="matching">Matching Skills ({len(score_data['matching_skills'])})</h3>
            <ul>{matching_skills_html or '<li>None found</li>'}</ul>
        </div>
        <div class="skills-column">
            <h3 class="missing">Missing Skills ({len(score_data['missing_skills'])})</h3>
            <ul>{missing_skills_html or '<li>None found</li>'}</ul>
        </div>
    </div>
    <div style="margin-top: 30px; padding: 20px; background: #f9f9f9; border-radius: 8px;">
        <h3>Score Breakdown</h3>
        <p><strong>Skill Match:</strong> {score_data['skill_score']}%</p>
        <p><strong>Experience Match:</strong> {score_data['experience_score']}%</p>
    </div>
    <p style="text-align: center; margin-top: 30px; color: #666;">
        Generated by HiringCircle AI on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
    </p>
</body>
</html>"""


async def process_application_background(
    submission_id: str,
    job_id: str,
    candidate_name: str,
    candidate_email: str,
    candidate_phone: str,
    candidate_visa: str,
    candidate_city: str,
    candidate_state: str,
    resume_text: str,
):
    """Background task: AI matching, report generation, and email notification."""
    from api.db import SessionLocal
    from api.utils.email_sender import send_application_notification_email

    db = SessionLocal()
    try:
        job_result = db.execute(
            text(
                """
                SELECT jobid, job_title, job_description, skills, experience, location, posted_by
                FROM job_postings
                WHERE jobid = :job_id
                """
            ),
            {"job_id": job_id},
        ).fetchone()

        if not job_result:
            logger.warning(f"Job {job_id} not found for application processing")
            return

        job_title = job_result.job_title or "Unknown Position"
        job_description = job_result.job_description or ""
        job_skills = job_result.skills or ""
        job_experience = job_result.experience or ""
        job_location = job_result.location or ""
        posted_by = job_result.posted_by or ""

        job_text = f"""
        Title: {job_title}
        Description: {job_description}
        Skills Required: {job_skills}
        Experience: {job_experience}
        Location: {job_location}
        """

        score_data = calculate_match_score(job_text, resume_text)

        db.execute(
            text(
                """
                UPDATE submissions SET
                    job_title = :job_title,
                    job_description = :job_description,
                    match_score = :match_score,
                    semantic_similarity = :semantic_similarity,
                    score_breakdown = :score_breakdown,
                    fit_summary = :fit_summary,
                    confidence_band = :confidence_band,
                    final_recommendation = :final_recommendation,
                    skill_matrix = :skill_matrix,
                    scoring_status = 'completed',
                    processed_at = NOW()
                WHERE submission_id = :submission_id
                """
            ),
            {
                "submission_id": submission_id,
                "job_title": job_title,
                "job_description": job_description,
                "match_score": score_data["overall_score"],
                "semantic_similarity": score_data["overall_score"] / 100,
                "score_breakdown": json.dumps(
                    {
                        "skill_score": score_data["skill_score"],
                        "experience_score": score_data["experience_score"],
                    }
                ),
                "fit_summary": f"Candidate has {len(score_data['matching_skills'])} matching skills: {', '.join(score_data['matching_skills'][:5])}",
                "confidence_band": score_data["fit"],
                "final_recommendation": score_data["fit"],
                "skill_matrix": json.dumps(
                    {
                        "matching": score_data["matching_skills"],
                        "missing": score_data["missing_skills"],
                    }
                ),
            },
        )
        db.commit()

        # Generate report
        try:
            report_html = generate_report_html(candidate_name, job_title, score_data)
            reports_dir = os.environ.get("REPORTS_PATH", "/tmp/reports")
            os.makedirs(reports_dir, exist_ok=True)
            report_path = os.path.join(reports_dir, f"report_{submission_id}.html")

            with open(report_path, "w") as f:
                f.write(report_html)

            db.execute(
                text("UPDATE submissions SET report_path = :report_path WHERE submission_id = :submission_id"),
                {"report_path": report_path, "submission_id": submission_id},
            )
            db.commit()
            logger.info(f"Report generated for submission {submission_id}: {report_path}")
        except Exception as e:
            logger.error(f"Report generation failed: {e}")

        # Store match in ai_matches table
        try:
            match_id = hashlib.md5(f"{job_id}_{submission_id}".encode()).hexdigest()[:20]
            db.execute(
                text(
                    """
                    INSERT INTO ai_matches (
                        match_id, job_id, resume_id, match_score,
                        skill_match_score, experience_match_score, overall_fit, reasoning, created_at
                    ) VALUES (
                        :match_id, :job_id, :resume_id, :match_score,
                        :skill_match_score, :experience_match_score, :overall_fit, :reasoning, NOW()
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
                    "match_id": match_id,
                    "job_id": job_id,
                    "resume_id": submission_id[:20],
                    "match_score": score_data["overall_score"],
                    "skill_match_score": score_data["skill_score"],
                    "experience_match_score": score_data["experience_score"],
                    "overall_fit": score_data["fit"],
                    "reasoning": f"Matched {len(score_data['matching_skills'])} skills",
                },
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to store match: {e}")

        # Send email notification to job poster
        if posted_by:
            try:
                applicant_location = (
                    f"{candidate_city}, {candidate_state}"
                    if candidate_city and candidate_state
                    else candidate_city or candidate_state or "Not specified"
                )
                send_application_notification_email(
                    job_poster_email=posted_by,
                    job_title=job_title,
                    job_id=job_id,
                    applicant_name=candidate_name,
                    applicant_email=candidate_email,
                    applicant_phone=candidate_phone or "Not provided",
                    applicant_visa=candidate_visa or "Not specified",
                    applicant_location=applicant_location,
                    match_score=score_data["overall_score"],
                    overall_fit=score_data["fit"],
                )
                logger.info(f"Application notification email sent to {posted_by}")
            except Exception as e:
                logger.error(f"Failed to send application notification email: {e}")

        logger.info(f"Application processing completed for submission {submission_id}")

    except Exception as e:
        logger.error(f"Application processing failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


# ============ UPLOAD ENDPOINTS ============

@router.post("/resumes/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    request: Request,
    background_tasks: BackgroundTasks,
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
    tax_term: Optional[str] = Form(None),
    posted_by: Optional[str] = Form(None),
    employer_company: Optional[str] = Form(None),
    employer_name: Optional[str] = Form(None),
    employer_email: Optional[str] = Form(None),
    employer_phone: Optional[str] = Form(None),
    # Job application fields
    job_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
):
    """
    Upload resume. Can be used for:
    1. Job application (when job_id is provided) — triggers background AI matching + email
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

        if not resolved_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name is required",
            )
        if not resolved_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email is required",
            )

        uploaded_file = file or resume
        if not uploaded_file:
            raise HTTPException(status_code=400, detail="Resume file is required")

        submission_uuid = str(uuid.uuid4())
        resume_id = str(uuid.uuid4())[:8].upper()

        # Save file
        file_url = None
        file_name = None
        file_path = None
        storage_path = os.environ.get("RESUME_STORAGE_PATH", "/tmp/resumes")
        os.makedirs(storage_path, exist_ok=True)

        file_extension = os.path.splitext(uploaded_file.filename)[1]
        file_name = f"{resume_id}{file_extension}"
        file_path = os.path.join(storage_path, file_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)

        file_url = f"/storage/resumes/{file_name}"

        # Extract text
        resume_text = extract_text(file_path) if file_path else ""

        # Get job title if applying
        job_title = ""
        if job_id:
            job_result = db.execute(
                text("SELECT job_title FROM job_postings WHERE jobid = :job_id"),
                {"job_id": job_id},
            ).fetchone()
            if job_result:
                job_title = job_result.job_title or ""

        # Create Submission record
        submission = Submission(
            submission_id=submission_uuid,
            resume_id=int(uuid.uuid4().int % 2147483647),
            candidate_name=resolved_name,
            full_name=resolved_name,
            resume_text=resume_text,
            job_id=job_id,
            job_title=job_title,
            job_description="",
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
            created_at=datetime.utcnow(),
            processed_at=None,
        )

        db.add(submission)
        db.commit()
        db.refresh(submission)

        # Trigger background processing for job applications
        if job_id:
            background_tasks.add_task(
                process_application_background,
                submission_id=submission_uuid,
                job_id=job_id,
                candidate_name=resolved_name,
                candidate_email=resolved_email,
                candidate_phone=resolved_phone or "",
                candidate_visa=resolved_visa or "",
                candidate_city=resolved_city or "",
                candidate_state=resolved_state or "",
                resume_text=resume_text or "",
            )
            message = "Job application submitted successfully — AI review in progress"
        else:
            message = "Resume uploaded successfully to database"

        return ResumeUploadResponse(
            id=resume_id,
            message=message,
            status="pending",
            file_url=file_url,
            job_id=job_id,
            submission_id=submission.submission_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Resume upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload: {str(e)}",
        )


# ============ SEARCH ENDPOINTS ============

@router.get("/resumes/search")
async def search_resumes(
    q: Optional[str] = Query(None, description="Search query"),
    skills: Optional[str] = Query(None),
    experience_min: Optional[int] = Query(None),
    experience_max: Optional[int] = Query(None),
    location: Optional[str] = Query(None),
    boolean_mode: bool = Query(False),
    scoring_status: Optional[str] = Query(None),
    has_score: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        offset = (page - 1) * limit

        base_query = "SELECT * FROM submissions WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM submissions WHERE 1=1"

        params = {}
        conditions = []

        # 🔥 REGEX SAFE BOOLEAN NORMALIZATION
        if q:
            normalized_q = re.sub(
                r"\b(and|or|not)\b",
                lambda m: m.group(0).upper(),
                q,
                flags=re.IGNORECASE
            )

            use_boolean = boolean_mode or any(
                op in normalized_q for op in ["AND", "OR", "NOT"]
            )

            if use_boolean:
                terms = parse_boolean_query(normalized_q)
                search_clause, search_params = build_search_conditions(
                    terms, param_prefix="q"
                )
            else:
                search_terms = normalized_q.split()
                search_clause, search_params = build_simple_search_conditions(
                    search_terms, param_prefix="q"
                )

            if search_clause:
                conditions.append(search_clause)
                params.update(search_params)

        # Skills filter
        if skills:
            skill_list = [s.strip() for s in skills.split(",")]
            for i, skill in enumerate(skill_list):
                key = f"skill_{i}"
                conditions.append(
                    f"(resume_text ILIKE :{key} OR skill_matrix ILIKE :{key})"
                )
                params[key] = f"%{skill}%"

        # Location filter
        if location:
            conditions.append(
                "(resume_text ILIKE :location OR full_name ILIKE :location OR candidate_name ILIKE :location)"
            )
            params["location"] = f"%{location}%"

        # Scoring status
        if scoring_status:
            conditions.append("scoring_status = :scoring_status")
            params["scoring_status"] = scoring_status

        # Score filter
        if has_score is not None:
            conditions.append(
                "match_score IS NOT NULL" if has_score else "match_score IS NULL"
            )

        # Combine conditions
        if conditions:
            where_clause = " AND ".join(conditions)
            base_query += f" AND {where_clause}"
            count_query += f" AND {where_clause}"

        # Pagination
        base_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        # Count
        count_params = {
            k: v for k, v in params.items() if k not in ["limit", "offset"]
        }
        total = db.execute(text(count_query), count_params).scalar()

        # Fetch
        rows = db.execute(text(base_query), params).fetchall()

        resumes = [
            {
                "submission_id": r.submission_id,
                "candidate_name": r.candidate_name,
                "full_name": r.full_name,

                # 🔥 NEW FIELDS (CRITICAL)
                "skills": r.skills,
                "city": r.city,
                "state": r.state,
                "formatted_html": r.formatted_html,

                "job_id": r.job_id,
                "job_title": r.job_title,
                "match_score": r.match_score,
                "semantic_similarity": r.semantic_similarity,
                "scoring_status": r.scoring_status,
                "confidence_band": r.confidence_band,
                "overall_fit": r.final_recommendation,
                "report_path": r.report_path,

                "created_at": r.created_at.isoformat() if r.created_at else None,
                "processed_at": r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in rows
        ]

        return {
            "success": True,
            "resumes": resumes,
            "total": total,
            "page": page,
            "limit": limit,
            "query": q,
            "boolean_mode": use_boolean,
        }

    except Exception as e:
        logger.error(f"Resume search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
    
@router.post("/resumes/search/advanced")
async def advanced_resume_search(
    request: ResumeSearchRequest,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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
        current_user=current_user,
    )

# ============ SUBMISSION QUERY ENDPOINTS ============

@router.get("/submissions")
async def list_submissions(
    skip: int = 0,
    limit: int = 100,
    job_id: Optional[str] = None,
    scoring_status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all submissions with filtering."""
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
                "candidate_name": s.candidate_name,
                "full_name": s.full_name,
                "job_id": s.job_id,
                "job_title": s.job_title,
                "scoring_status": s.scoring_status,
                "match_score": s.match_score,
                "created_at": s.created_at,
                "processed_at": s.processed_at,
            }
            for s in submissions
        ],
        "total": query.count(),
    }


@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get specific submission with AI scoring details."""
    submission = db.query(Submission).filter(Submission.submission_id == submission_id).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {
        "submission_id": submission.submission_id,
        "candidate_name": submission.candidate_name,
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
        "processed_at": submission.processed_at,
    }


@router.get("/submissions/job/{job_id}")
async def get_submissions_by_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all submissions for a specific job."""
    submissions = db.query(Submission).filter(Submission.job_id == job_id).all()

    return {
        "job_id": job_id,
        "submissions": [
            {
                "submission_id": s.submission_id,
                "candidate_name": s.candidate_name,
                "full_name": s.full_name,
                "match_score": s.match_score,
                "scoring_status": s.scoring_status,
                "created_at": s.created_at,
            }
            for s in submissions
        ],
        "total": len(submissions),
    }


# ============ RESUME ENDPOINTS ============

@router.get("/resumes")
async def list_resumes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get all resumes (mapped from submissions)."""
    submissions = db.query(Submission).offset(skip).limit(limit).all()

    return {
        "resumes": [
            {
                "id": s.submission_id[:8].upper(),
                "full_name": s.full_name or s.candidate_name,
                "job_id": s.job_id,
                "status": s.scoring_status,
                "match_score": s.match_score,
                "created_at": s.created_at,
            }
            for s in submissions
        ],
        "total": len(submissions),
    }


@router.get("/resumes/{resume_id}")
async def get_resume(
    resume_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get specific resume (mapped from submission)."""
    submission = (
        db.query(Submission).filter(Submission.submission_id.like(f"{resume_id}%")).first()
    )

    if not submission:
        raise HTTPException(status_code=404, detail="Resume not found")

    return {
        "id": resume_id,
        "full_name": submission.full_name or submission.candidate_name,
        "job_id": submission.job_id,
        "job_title": submission.job_title,
        "status": submission.scoring_status,
        "match_score": submission.match_score,
        "created_at": submission.created_at,
    }