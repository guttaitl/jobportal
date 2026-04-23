from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
<<<<<<< HEAD
from openai import AsyncOpenAI
from datetime import datetime
import os
import json
import re
import logging
import traceback
import hashlib
import asyncio
from api.db import get_db
from api.utils.security import get_current_user
from api.schemas.ai_match_schema import TopCandidatesResponse, CandidateMatch
=======
import openai
from datetime import datetime
import os
from api.db import get_db
from api.utils.security import get_current_user
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

router = APIRouter()

# =========================================================
<<<<<<< HEAD
# OPENAI CLIENT SETUP (v1.0+)
# =========================================================

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
=======
# OPENAI CLIENT SETUP
# =========================================================

openai.api_key = os.getenv("OPENAI_API_KEY", "")
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2

# =========================================================
# AI MATCH MODELS
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
<<<<<<< HEAD
# AI ANALYSIS FUNCTIONS (FULL AI-BASED VERSION)
# =========================================================

async def analyze_job_resume_match(job_text: str, resume_text: str) -> dict:
    """AI-based job-resume matching using OpenAI (no static skills)"""

    try:
        prompt = f"""
        You are an expert technical recruiter AI.

        Analyze the match between the JOB DESCRIPTION and CANDIDATE RESUME.

        Extract skills dynamically (DO NOT assume predefined skills).

        JOB DESCRIPTION:
        {job_text[:3000]}

        CANDIDATE RESUME:
        {resume_text[:3000]}

        Return STRICT JSON with:
        {{
            "overall_score": number (0-100),
            "skill_match_score": number (0-100),
            "experience_match_score": number (0-100),
            "matched_skills": [list of matching skills],
            "missing_skills": [list of missing skills],
            "experience_years_match": true/false,
            "overall_fit": "Excellent" | "Good" | "Fair" | "Poor",
            "reasoning": "short explanation"
        }}

        Rules:
        - Extract skills from BOTH job and resume dynamically
        - Compare meaning, not just keywords
        - Be realistic (not overly generous)
        - Return ONLY JSON (no text outside JSON)
        """

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a precise hiring intelligence system."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=900
        )

        content = response.choices[0].message.content.strip()

        # Try direct JSON parse
        try:
            result = json.loads(content)
        except:
            # Handle markdown JSON (```json ... ```)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
            else:
                raise ValueError("Invalid JSON from AI")

        # Normalize output (safe defaults)
=======
# AI ANALYSIS FUNCTIONS
# =========================================================

async def analyze_job_resume_match(job_text: str, resume_text: str) -> dict:
    """Use OpenAI to analyze match between job and resume"""
    
    if not openai.api_key:
        # Fallback scoring if no API key
        return fallback_match_analysis(job_text, resume_text)
    
    try:
        prompt = f"""
        Analyze the match between this job description and candidate resume.
        
        JOB DESCRIPTION:
        {job_text[:2000]}
        
        CANDIDATE RESUME:
        {resume_text[:2000]}
        
        Provide a JSON response with:
        1. overall_score (0-100): Overall match percentage
        2. skill_match_score (0-100): How well skills match
        3. experience_match_score (0-100): How well experience matches
        4. key_matching_skills: List of skills that match
        5. missing_skills: List of required skills candidate lacks
        6. experience_years_match: Whether experience level matches
        7. overall_fit: One of "Excellent", "Good", "Fair", "Poor"
        8. reasoning: Brief explanation of the match
        
        Format as valid JSON only.
        """
        
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert recruiter AI that analyzes job-candidate matches."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        import json
        result_text = response.choices[0].message.content
        
        # Extract JSON from response
        try:
            result = json.loads(result_text)
        except:
            # Try to extract JSON from markdown code block
            import re
            json_match = re.search(r'```json\n(.*?)\n```', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                return fallback_match_analysis(job_text, resume_text)
        
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        return {
            "overall_score": result.get("overall_score", 50),
            "skill_match_score": result.get("skill_match_score", 50),
            "experience_match_score": result.get("experience_match_score", 50),
<<<<<<< HEAD
            "matched_skills": result.get("matched_skills", []),
=======
            "key_matching_skills": result.get("key_matching_skills", []),
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
            "missing_skills": result.get("missing_skills", []),
            "experience_years_match": result.get("experience_years_match", False),
            "overall_fit": result.get("overall_fit", "Fair"),
            "reasoning": result.get("reasoning", "")
        }
<<<<<<< HEAD

    except Exception as e:
        logging.error(f"AI matching failed: {e}")
        print(traceback.format_exc())  # Better debugging

        # Minimal fallback (NO static skills)
        return basic_fallback(job_text, resume_text)


# =========================================================
# LIGHTWEIGHT FALLBACK (NO STATIC SKILLS)
# =========================================================

def basic_fallback(job_text: str, resume_text: str) -> dict:
    """Simple fallback using text overlap (no predefined skills)"""

    job_words = set(job_text.lower().split())
    resume_words = set(resume_text.lower().split())

    common = job_words.intersection(resume_words)

    score = int((len(common) / max(len(job_words), 1)) * 100)

    return {
        "overall_score": score,
        "skill_match_score": score,
        "experience_match_score": score,
        "matched_skills": list(common)[:10],
        "missing_skills": [],
        "experience_years_match": False,
        "overall_fit": "Fair" if score > 50 else "Poor",
        "reasoning": "Fallback matching used due to AI error"
    }


# =========================================================
# AI MATCH ROUTES
# =========================================================
=======
        
    except Exception as e:
        print(f"OpenAI analysis error: {e}")
        return fallback_match_analysis(job_text, resume_text)

def fallback_match_analysis(job_text: str, resume_text: str) -> dict:
    """Fallback keyword-based matching when OpenAI is unavailable"""
    
    job_lower = job_text.lower()
    resume_lower = resume_text.lower()
    
    # Common tech skills to check
    common_skills = [
        "python", "javascript", "java", "react", "node", "sql", "aws",
        "docker", "kubernetes", "machine learning", "ai", "data analysis",
        "project management", "agile", "scrum", "leadership", "communication",
        "typescript", "next.js", "vue", "angular", "mongodb", "postgresql",
        "redis", "graphql", "rest api", "git", "ci/cd", "jenkins",
        "tensorflow", "pytorch", "pandas", "numpy", "tableau", "power bi"
    ]
    
    matching_skills = []
    missing_skills = []
    
    for skill in common_skills:
        in_job = skill in job_lower
        in_resume = skill in resume_lower
        
        if in_job and in_resume:
            matching_skills.append(skill)
        elif in_job and not in_resume:
            missing_skills.append(skill)
    
    # Calculate scores
    job_skills_found = sum(1 for s in common_skills if s in job_lower)
    if job_skills_found > 0:
        skill_match_score = (len(matching_skills) / job_skills_found) * 100
    else:
        skill_match_score = 50
    
    # Experience matching (simple keyword check)
    exp_keywords = ["years", "experience", "senior", "junior", "lead", "manager"]
    exp_matches = sum(1 for kw in exp_keywords if kw in job_lower and kw in resume_lower)
    experience_match_score = (exp_matches / len(exp_keywords)) * 100
    
    # Overall score
    overall_score = (skill_match_score * 0.6) + (experience_match_score * 0.4)
    
    # Determine fit
    if overall_score >= 80:
        overall_fit = "Excellent"
    elif overall_score >= 60:
        overall_fit = "Good"
    elif overall_score >= 40:
        overall_fit = "Fair"
    else:
        overall_fit = "Poor"
    
    return {
        "overall_score": round(overall_score, 1),
        "skill_match_score": round(skill_match_score, 1),
        "experience_match_score": round(experience_match_score, 1),
        "key_matching_skills": matching_skills[:10],
        "missing_skills": missing_skills[:10],
        "experience_years_match": experience_match_score > 50,
        "overall_fit": overall_fit,
        "reasoning": f"Matched {len(matching_skills)} skills. Missing {len(missing_skills)} required skills."
    }

# =========================================================
# AI MATCH ROUTES
# =========================================================

>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
@router.post("/ai-match/job-to-candidates")
async def match_job_to_candidates(
    request: JobResumeMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
<<<<<<< HEAD
    """Find best matching candidates for a job (optimized + parallel AI)"""

    # =========================
    # GET JOB
    # =========================
    job_result = db.execute(text("""
=======
    """Find best matching candidates for a job"""
    
    # Get job details
    job_result = db.execute(
        text("""
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        SELECT 
            jobid,
            job_title,
            job_description,
            skills,
            experience,
            location
        FROM job_postings
        WHERE jobid = :job_id
<<<<<<< HEAD
    """), {"job_id": request.job_id})

    job = job_result.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # =========================
    # BUILD JOB TEXT
    # =========================
=======
        """),
        {"job_id": request.job_id}
    )
    
    job = job_result.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Build job text for analysis
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    job_text = f"""
    Title: {job.job_title}
    Description: {job.job_description or ''}
    Skills Required: {job.skills or ''}
    Experience: {job.experience or ''}
    Location: {job.location or ''}
    """
<<<<<<< HEAD

    # =========================
    # FETCH RESUMES
    # =========================
    resumes_result = db.execute(text("""
        SELECT
            submission_id,
            full_name,
            resume_text
        FROM submissions
        WHERE resume_text IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 100
    """))

    resumes = resumes_result.fetchall()

    # =========================
    # STEP 1: QUICK SCORING
    # =========================
    def quick_score(job_text, resume_text):
        job_words = set(job_text.lower().split())
        resume_words = set((resume_text or "").lower().split())
        return len(job_words.intersection(resume_words))

    scored = [
        (resume, quick_score(job_text, resume.resume_text))
        for resume in resumes
    ]

    # =========================
    # STEP 2: SORT + LIMIT
    # =========================
    scored.sort(key=lambda x: x[1], reverse=True)

    TOP_N = 20
    top_resumes = [r[0] for r in scored[:TOP_N]]

    print(f"⚡ Processing only top {TOP_N} resumes out of {len(resumes)}")

    # =========================
    # STEP 3: PARALLEL AI CALLS
    # =========================

    semaphore = asyncio.Semaphore(5)  # prevent rate limit

    async def process_resume(resume):
        async with semaphore:
            resume_text = f"""
            Name: {resume.full_name}
            Resume: {resume.resume_text or ''}
            """

            try:
                analysis = await analyze_job_resume_match(job_text, resume_text)
            except Exception:
                analysis = {}

            match_id = hashlib.md5(
                f"{request.job_id}_{resume.submission_id}".encode()
            ).hexdigest()[:20]

            return {
                "match_id": match_id,
                "job_id": request.job_id,
                "resume_id": resume.submission_id,
                "candidate_name": resume.full_name,
                "candidate_email": None,
                "match_score": analysis.get("overall_score", 0),
                "skill_match_score": analysis.get("skill_match_score", 0),
                "experience_match_score": analysis.get("experience_match_score", 0),
                "experience_years_match": analysis.get("experience_years_match", False),
                "key_matching_skills": analysis.get("matched_skills", []),
                "missing_skills": analysis.get("missing_skills", []),
                "overall_fit": analysis.get("overall_fit", "Unknown"),
                "reasoning": analysis.get("reasoning", "")
            }

    tasks = [process_resume(resume) for resume in top_resumes]
    matches = await asyncio.gather(*tasks)

    # =========================
    # SORT FINAL RESULTS
    # =========================
    matches.sort(key=lambda x: x["match_score"], reverse=True)

    top_matches = matches[:request.top_k]

    # =========================
    # STORE IN DB
    # =========================
=======
    
    # Get all active resumes
    resumes_result = db.execute(
        text("""
        SELECT 
            id,
            full_name,
            email,
            skills,
            experience,
            location,
            resume_text
        FROM resumes
        ORDER BY created_at DESC
        LIMIT 100
        """))
    
    resumes = resumes_result.fetchall()
    
    # Analyze matches
    matches = []
    for resume in resumes:
        resume_text = f"""
        Name: {resume.full_name}
        Skills: {resume.skills or ''}
        Experience: {resume.experience or ''}
        Location: {resume.location or ''}
        Resume: {resume.resume_text or ''}
        """
        
        analysis = await analyze_job_resume_match(job_text, resume_text)
        
        match_id = f"{request.job_id}_{resume.id}"
        
        matches.append({
            "match_id": match_id,
            "job_id": request.job_id,
            "resume_id": resume.id,
            "candidate_name": resume.full_name,
            "candidate_email": resume.email,
            "match_score": analysis["overall_score"],
            "skill_match_score": analysis["skill_match_score"],
            "experience_match_score": analysis["experience_match_score"],
            "key_matching_skills": analysis["key_matching_skills"],
            "missing_skills": analysis["missing_skills"],
            "overall_fit": analysis["overall_fit"],
            "reasoning": analysis["reasoning"]
        })
    
    # Sort by match score
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Return top K matches
    top_matches = matches[:request.top_k]
    
    # Store match results in database
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    for match in top_matches:
        db.execute(
            text("""
            INSERT INTO ai_matches (
                match_id,
                job_id,
                resume_id,
                match_score,
                skill_match_score,
                experience_match_score,
                overall_fit,
                reasoning,
                created_at,
                created_by
            ) VALUES (
                :match_id,
                :job_id,
                :resume_id,
                :match_score,
                :skill_match_score,
                :experience_match_score,
                :overall_fit,
                :reasoning,
                NOW(),
                :created_by
            )
            ON CONFLICT (match_id) DO UPDATE SET
                match_score = EXCLUDED.match_score,
                skill_match_score = EXCLUDED.skill_match_score,
                experience_match_score = EXCLUDED.experience_match_score,
                overall_fit = EXCLUDED.overall_fit,
                reasoning = EXCLUDED.reasoning,
                updated_at = NOW()
            """),
            {
                "match_id": match["match_id"],
                "job_id": match["job_id"],
                "resume_id": match["resume_id"],
                "match_score": match["match_score"],
                "skill_match_score": match["skill_match_score"],
                "experience_match_score": match["experience_match_score"],
                "overall_fit": match["overall_fit"],
                "reasoning": match["reasoning"],
                "created_by": current_user.get("email")
            }
        )
<<<<<<< HEAD

    db.commit()

    # =========================
    # RESPONSE
    # =========================
=======
    
    db.commit()
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    return {
        "success": True,
        "job_id": request.job_id,
        "job_title": job.job_title,
        "total_candidates": len(resumes),
<<<<<<< HEAD
        "processed_candidates": len(top_resumes),
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        "matches_found": len(top_matches),
        "matches": top_matches
    }

<<<<<<< HEAD

=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
@router.post("/ai-match/candidate-to-jobs")
async def match_candidate_to_jobs(
    request: CandidateMatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
<<<<<<< HEAD
    """Find best matching jobs for a candidate (optimized + parallel AI)"""

    # =========================
    # GET RESUME
    # =========================
    resume_result = db.execute(text("""
        SELECT 
            submission_id,
            full_name,
            resume_text
        FROM submissions
        WHERE submission_id = :resume_id
    """), {"resume_id": request.resume_id})

    resume = resume_result.fetchone()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # =========================
    # BUILD RESUME TEXT
    # =========================
    resume_text = f"""
    Name: {resume.full_name}
    Resume: {resume.resume_text or ''}
    """

    # =========================
    # FETCH JOBS
    # =========================
    jobs_result = db.execute(text("""
=======
    """Find best matching jobs for a candidate"""
    
    # Get resume details
    resume_result = db.execute(
        text("""
        SELECT 
            id,
            full_name,
            skills,
            experience,
            location,
            resume_text
        FROM resumes
        WHERE id = :resume_id
        """),
        {"resume_id": request.resume_id}
    )
    
    resume = resume_result.fetchone()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Build resume text for analysis
    resume_text = f"""
    Name: {resume.full_name}
    Skills: {resume.skills or ''}
    Experience: {resume.experience or ''}
    Location: {resume.location or ''}
    Resume: {resume.resume_text or ''}
    """
    
    # Get all active jobs
    jobs_result = db.execute(
        text("""
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        SELECT 
            jobid,
            job_title,
            job_description,
            skills,
            experience,
            location,
            client_name
        FROM job_postings
<<<<<<< HEAD
        LIMIT 100
    """))

    jobs = jobs_result.fetchall()

    # =========================
    # STEP 1: QUICK SCORING
    # =========================
    def quick_score(resume_text, job_text):
        resume_words = set(resume_text.lower().split())
        job_words = set((job_text or "").lower().split())
        return len(resume_words.intersection(job_words))

    scored = []
=======
        ORDER BY created_at DESC
        LIMIT 100
        """))
    
    jobs = jobs_result.fetchall()
    
    # Analyze matches
    matches = []
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    for job in jobs:
        job_text = f"""
        Title: {job.job_title}
        Description: {job.job_description or ''}
        Skills Required: {job.skills or ''}
        Experience: {job.experience or ''}
        Location: {job.location or ''}
        """
<<<<<<< HEAD
        scored.append((job, job_text, quick_score(resume_text, job_text)))

    # =========================
    # STEP 2: SORT + LIMIT
    # =========================
    scored.sort(key=lambda x: x[2], reverse=True)

    TOP_N = 20
    top_jobs = scored[:TOP_N]

    print(f"⚡ Processing only top {TOP_N} jobs out of {len(jobs)}")

    # =========================
    # STEP 3: PARALLEL AI CALLS
    # =========================

    semaphore = asyncio.Semaphore(5)  # prevent rate limit

    async def process_job(job, job_text):
        async with semaphore:
            try:
                analysis = await analyze_job_resume_match(job_text, resume_text)
            except Exception:
                analysis = {}

            match_id = hashlib.md5(
                f"{job.jobid}_{request.resume_id}".encode()
            ).hexdigest()[:20]

            return {
                "match_id": match_id,
                "job_id": job.jobid,
                "job_title": job.job_title,
                "client_name": job.client_name,
                "resume_id": request.resume_id,
                "candidate_name": resume.full_name,
                "match_score": analysis.get("overall_score", 0),
                "skill_match_score": analysis.get("skill_match_score", 0),
                "experience_match_score": analysis.get("experience_match_score", 0),
                "experience_years_match": analysis.get("experience_years_match", False),
                "key_matching_skills": analysis.get("matched_skills", []),
                "missing_skills": analysis.get("missing_skills", []),
                "overall_fit": analysis.get("overall_fit", "Unknown"),
                "reasoning": analysis.get("reasoning", "")
            }

    tasks = [process_job(job, job_text) for job, job_text, _ in top_jobs]
    matches = await asyncio.gather(*tasks)

    # =========================
    # SORT FINAL RESULTS
    # =========================
    matches.sort(key=lambda x: x["match_score"], reverse=True)

    top_matches = matches[:request.top_k]

    # =========================
    # RESPONSE
    # =========================
=======
        
        analysis = await analyze_job_resume_match(job_text, resume_text)
        
        match_id = f"{job.jobid}_{request.resume_id}"
        
        matches.append({
            "match_id": match_id,
            "job_id": job.jobid,
            "job_title": job.job_title,
            "client_name": job.client_name,
            "resume_id": request.resume_id,
            "candidate_name": resume.full_name,
            "match_score": analysis["overall_score"],
            "skill_match_score": analysis["skill_match_score"],
            "experience_match_score": analysis["experience_match_score"],
            "key_matching_skills": analysis["key_matching_skills"],
            "missing_skills": analysis["missing_skills"],
            "overall_fit": analysis["overall_fit"],
            "reasoning": analysis["reasoning"]
        })
    
    # Sort by match score
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Return top K matches
    top_matches = matches[:request.top_k]
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    return {
        "success": True,
        "resume_id": request.resume_id,
        "candidate_name": resume.full_name,
        "total_jobs": len(jobs),
<<<<<<< HEAD
        "processed_jobs": len(top_jobs),
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        "matches_found": len(top_matches),
        "matches": top_matches
    }

<<<<<<< HEAD

=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
@router.get("/ai-match/history")
def get_match_history(
    job_id: Optional[str] = None,
    resume_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get AI match history"""
<<<<<<< HEAD

    offset = (page - 1) * limit

    # Use submissions table instead of resumes
=======
    
    offset = (page - 1) * limit
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    query = """
        SELECT 
            m.match_id,
            m.job_id,
            j.job_title,
            m.resume_id,
<<<<<<< HEAD
            s.full_name as candidate_name,
=======
            r.full_name as candidate_name,
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
            m.match_score,
            m.skill_match_score,
            m.experience_match_score,
            m.overall_fit,
            m.reasoning,
            m.created_at
        FROM ai_matches m
        LEFT JOIN job_postings j ON m.job_id = j.jobid
<<<<<<< HEAD
        LEFT JOIN submissions s ON m.resume_id = s.submission_id
        WHERE 1=1
    """

    params = {"limit": limit, "offset": offset}

    if job_id:
        query += " AND m.job_id = :job_id"
        params["job_id"] = job_id

    if resume_id:
        query += " AND m.resume_id = :resume_id"
        params["resume_id"] = resume_id

    query += " ORDER BY m.created_at DESC LIMIT :limit OFFSET :offset"

    result = db.execute(text(query), params)
    rows = result.fetchall()

=======
        LEFT JOIN resumes r ON m.resume_id = r.id
        WHERE 1=1
    """
    
    params = {"limit": limit, "offset": offset}
    
    if job_id:
        query += " AND m.job_id = :job_id"
        params["job_id"] = job_id
    
    if resume_id:
        query += " AND m.resume_id = :resume_id"
        params["resume_id"] = resume_id
    
    query += " ORDER BY m.created_at DESC LIMIT :limit OFFSET :offset"
    
    result = db.execute(text(query), params)
    rows = result.fetchall()
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    matches = []
    for row in rows:
        matches.append({
            "match_id": row.match_id,
            "job_id": row.job_id,
            "job_title": row.job_title,
            "resume_id": row.resume_id,
            "candidate_name": row.candidate_name,
            "match_score": row.match_score,
            "skill_match_score": row.skill_match_score,
            "experience_match_score": row.experience_match_score,
            "overall_fit": row.overall_fit,
            "reasoning": row.reasoning,
            "created_at": row.created_at
        })
<<<<<<< HEAD

=======
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    return {
        "success": True,
        "page": page,
        "limit": limit,
        "matches": matches
    }

<<<<<<< HEAD

=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
@router.get("/ai-match/stats")
def get_match_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get AI matching statistics"""
<<<<<<< HEAD

    # Total matches
    total_result = db.execute(text("SELECT COUNT(*) FROM ai_matches"))
    total_matches = total_result.fetchone()[0]

    # Average match score
    avg_result = db.execute(text("SELECT AVG(match_score) FROM ai_matches"))
    avg_score = avg_result.fetchone()[0] or 0

=======
    
    # Total matches
    total_result = db.execute(text("SELECT COUNT(*) FROM ai_matches"))
    total_matches = total_result.fetchone()[0]
    
    # Average match score
    avg_result = db.execute(text("SELECT AVG(match_score) FROM ai_matches"))
    avg_score = avg_result.fetchone()[0] or 0
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    # Fit distribution
    fit_result = db.execute(
        text("""
        SELECT overall_fit, COUNT(*) as count
        FROM ai_matches
        GROUP BY overall_fit
        ORDER BY count DESC
        """)
    )
    fit_distribution = [{"fit": row[0], "count": row[1]} for row in fit_result.fetchall()]
<<<<<<< HEAD

=======
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    # Recent matches (last 7 days)
    recent_result = db.execute(
        text("""
        SELECT COUNT(*) FROM ai_matches
        WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
    )
    recent_matches = recent_result.fetchone()[0]
<<<<<<< HEAD

=======
    
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    return {
        "success": True,
        "total_matches": total_matches,
        "average_match_score": round(avg_score, 2),
        "fit_distribution": fit_distribution,
        "recent_matches_7d": recent_matches
    }
<<<<<<< HEAD


@router.get("/ai-match/top-candidates/{job_id}", response_model=TopCandidatesResponse)
def get_top_candidates(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get top 5 candidates for a job (sorted by match_score DESC)
    """

    try:
        result = db.execute(
            text("""
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
            """),
            {"job_id": job_id}
        )

        rows = result.fetchall()

        # Graceful empty response (better than 404)
        if not rows:
            return TopCandidatesResponse(
                job_id=job_id,
                total_returned=0,
                candidates=[]
            )

        candidates = [
            CandidateMatch(
                candidate_id=str(row.resume_id),
                candidate_name=row.candidate_name or "Unknown Candidate",
                email=None,  # not available yet
                match_score=round(row.match_score, 2),
                summary=row.reasoning
            )
            for row in rows
        ]

        return TopCandidatesResponse(
            job_id=job_id,
            total_returned=len(candidates),
            candidates=candidates
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
=======
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
