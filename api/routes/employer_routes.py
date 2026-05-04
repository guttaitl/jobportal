from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
import uuid
import hashlib
import logging
import json
import os
from datetime import date, datetime

from api.utils.email_sender import send_job_notification
from api.utils.ai_job_description import generate_structured_job_content
from api.db import get_db
from api.utils.security import require_role

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================================================
# JOB REQUEST MODEL
# =========================================================

class PostJobRequest(BaseModel):
    job_title: str
    client_name: Optional[str] = None
    location: Optional[str] = None
    work_authorization: Optional[str] = "Any"
    experience: Optional[str] = None
    salary: Optional[str] = None
    employment_type: Optional[str] = "Contract"
    visa_transfer: Optional[str] = "No"
    job_description: Optional[str] = None
    skills: Optional[str] = None
    responsibilities: Optional[str] = None


# =========================================================
# GET EMPLOYER JOBS
# =========================================================

@router.get("/employer/jobs")
def get_employer_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")
    offset = (page - 1) * limit

    result = db.execute(
        text("""
            SELECT
                jp.jobid,
                jp.job_title,
                jp.client_name,
                jp.location,
                jp.employment_type,
                jp.created_at,
                COUNT(ja.id) as applicants_count
            FROM job_postings jp
            LEFT JOIN job_applications ja ON ja.job_id = jp.jobid
            WHERE jp.posted_by = :email
            GROUP BY jp.jobid, jp.job_title, jp.client_name, jp.location, jp.employment_type, jp.created_at
            ORDER BY jp.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"email": user_email, "limit": limit, "offset": offset},
    )

    jobs = [
        {
            "jobid": row.jobid,
            "job_title": row.job_title,
            "client_name": row.client_name,
            "location": row.location,
            "employment_type": row.employment_type,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "applicants_count": row.applicants_count or 0,
        }
        for row in result.fetchall()
    ]

    return {"success": True, "jobs": jobs}


# =========================================================
# POST JOB (AI + EMAIL)
# =========================================================

@router.post("/post-job")
async def post_job(
    request: PostJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    # Resolve company name
    user_result = db.execute(
        text("SELECT full_name, company FROM usersdata WHERE email = :email LIMIT 1"),
        {"email": user_email},
    ).fetchone()

    if user_result and user_result.company:
        user_company = user_result.company
    else:
        user_company = request.client_name or "Direct Client"

    # Generate job ID
    job_public_id = str(uuid.uuid4())[:8].upper()

    # AI generation for empty fields
    job_description = (request.job_description or "").strip()
    skills = (request.skills or "").strip()
    responsibilities = (request.responsibilities or "").strip()

    if not job_description or not skills or not responsibilities:
        logger.info(f"AI generation triggered for job: {request.job_title}")
        try:
            ai_json = generate_structured_job_content(
                job_title=request.job_title,
                experience=request.experience,
                company_name=request.client_name,
                location=request.location,
                employment_type=request.employment_type,
                industry="Technology",
            )

            if ai_json:
                if not skills:
                    skills = "\n".join(ai_json.get("required_skills", []))
                if not job_description:
                    job_description = ai_json.get("description", "")
                if not responsibilities:
                    responsibilities = "\n".join(ai_json.get("responsibilities", []))
            else:
                logger.warning("AI generation returned None")

        except Exception as e:
            logger.error(f"AI generation failed: {e}")

    # Hard fallback — never empty
    if not job_description:
        job_description = f"{user_company} is hiring a {request.job_title} with strong experience in enterprise systems."
    if not skills:
        skills = f"{request.job_title}\nAPIs\nSQL\nCloud\nMicroservices"
    if not responsibilities:
        responsibilities = (
            "Develop scalable applications\n"
            "Work with cross-functional teams\n"
            "Design and maintain systems\n"
            "Optimize performance\n"
            "Deliver high-quality code"
        )

    # Insert job
    try:
        db.execute(
            text("""
                INSERT INTO job_postings (
                    jobid, job_title, client_name, location,
                    work_authorization, experience, salary, employment_type,
                    visa_transfer, job_description, skills, responsibilities,
                    posted_by, created_at
                )
                VALUES (
                    :jobid, :job_title, :client_name, :location,
                    :work_authorization, :experience, :salary, :employment_type,
                    :visa_transfer, :job_description, :skills, :responsibilities,
                    :posted_by, NOW()
                )
                RETURNING jobid
            """),
            {
                "jobid": job_public_id,
                "created_date": date.today(),
                "job_title": request.job_title,
                "client_name": user_company,
                "location": request.location or "Remote",
                "work_authorization": request.work_authorization,
                "experience": request.experience or "Not specified",
                "salary": request.salary or "Competitive",
                "employment_type": request.employment_type,
                "visa_transfer": request.visa_transfer,
                "job_description": job_description,
                "skills": skills,
                "responsibilities": responsibilities,
                "posted_by": user_email,
            },
        )
        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Job insert failed: {e}")
        return {"success": False, "error": "Job creation failed"}

    # Background email notification
    try:
        background_tasks.add_task(
            send_job_notification,
            {
                "job_title": request.job_title,
                "poster_company": user_company,
                "location": request.location or "Remote",
                "job_description": job_description,
                "skills": skills,
                "responsibilities": responsibilities,
                "jobid": job_public_id,
                "employment_type": request.employment_type,
            },
        )
    except Exception as e:
        logger.error(f"Email task scheduling failed: {e}")

    return {"success": True, "jobid": job_public_id}


# =========================================================
# GET SINGLE JOB
# =========================================================

@router.get("/employer/jobs/{job_id}")
def get_job_details(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    result = db.execute(
        text("""
            SELECT jobid, job_title, client_name, location, work_authorization,
                   experience, salary, employment_type, visa_transfer,
                   job_description, skills, created_at
            FROM job_postings
            WHERE jobid = :jobid AND posted_by = :email
        """),
        {"jobid": job_id, "email": user_email},
    ).fetchone()

    if not result:
        return {"success": False, "message": "Job not found"}

    return {
        "success": True,
        "job": {
            "jobid": result.jobid,
            "job_title": result.job_title,
            "client_name": result.client_name,
            "location": result.location,
            "work_authorization": result.work_authorization,
            "experience": result.experience,
            "salary": result.salary,
            "employment_type": result.employment_type,
            "visa_transfer": result.visa_transfer,
            "job_description": result.job_description,
            "skills": result.skills,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        },
    }


# =========================================================
# DASHBOARD STATS
# =========================================================

@router.get("/employer/dashboard/stats")
def get_employer_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    total_jobs = db.execute(
        text("SELECT COUNT(*) FROM job_postings WHERE posted_by = :email"),
        {"email": user_email},
    ).scalar()

    active_jobs = db.execute(
        text("""
            SELECT COUNT(*) FROM job_postings
            WHERE posted_by = :email
            AND created_at >= NOW() - INTERVAL '30 days'
        """),
        {"email": user_email},
    ).scalar()

    total_applicants = db.execute(
        text("""
            SELECT COUNT(*)
            FROM job_applications ja
            JOIN job_postings jp ON ja.job_id = jp.jobid
            WHERE jp.posted_by = :email
        """),
        {"email": user_email},
    ).scalar()

    recent_jobs_result = db.execute(
        text("""
            SELECT
                jp.jobid,
                jp.job_title,
                jp.client_name,
                jp.location,
                jp.employment_type,
                jp.created_at,
                COUNT(ja.id) as applicants_count
            FROM job_postings jp
            LEFT JOIN job_applications ja ON ja.job_id = jp.jobid
            WHERE jp.posted_by = :email
            GROUP BY jp.jobid, jp.job_title, jp.client_name, jp.location, jp.employment_type, jp.created_at
            ORDER BY jp.created_at DESC
            LIMIT 10
        """),
        {"email": user_email},
    )

    recent_jobs = [
        {
            "jobid": row.jobid,
            "job_title": row.job_title,
            "client_name": row.client_name,
            "location": row.location,
            "employment_type": row.employment_type,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "applicants_count": row.applicants_count or 0,
        }
        for row in recent_jobs_result.fetchall()
    ]

    return {
        "success": True,
        "stats": {
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "total_applicants": total_applicants,
        },
        "recent_jobs": recent_jobs,
    }


# =========================================================
# DELETE JOB
# =========================================================

@router.delete("/employer/jobs/{job_id}")
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    try:
        check = db.execute(
            text("""
                SELECT jobid FROM job_postings
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {"jobid": job_id, "email": user_email},
        ).fetchone()

        if not check:
            return {"success": False, "message": "Job not found or unauthorized"}

        # Delete related applications first
        db.execute(
            text("DELETE FROM job_applications WHERE job_id = :jobid"),
            {"jobid": job_id},
        )

        result = db.execute(
            text("""
                DELETE FROM job_postings
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {"jobid": job_id, "email": user_email},
        )

        db.commit()

        if result.rowcount == 0:
            return {"success": False, "message": "Job not found"}

        logger.info(f"Job {job_id} deleted by {user_email}")
        return {"success": True, "message": "Job deleted successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Delete error: {e}")
        return {"success": False, "message": f"Failed to delete job: {str(e)}"}


# =========================================================
# BULK DELETE JOBS
# =========================================================

class BulkDeleteRequest(BaseModel):
    job_ids: list

@router.post("/employer/jobs/bulk-delete")
def bulk_delete_jobs(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")
    job_ids = request.job_ids or []

    if not job_ids:
        return {"success": False, "message": "No jobs selected"}

    try:
        # Delete related applications first
        db.execute(
            text("""
                DELETE FROM job_applications
                WHERE job_id = ANY(:job_ids)
                AND job_id IN (
                    SELECT jobid FROM job_postings WHERE posted_by = :email
                )
            """),
            {"job_ids": job_ids, "email": user_email},
        )

        result = db.execute(
            text("""
                DELETE FROM job_postings
                WHERE jobid = ANY(:job_ids) AND posted_by = :email
            """),
            {"job_ids": job_ids, "email": user_email},
        )

        db.commit()

        deleted_count = result.rowcount
        logger.info(f"Bulk deleted {deleted_count} jobs by {user_email}")
        return {
            "success": True,
            "message": f"Deleted {deleted_count} job(s) successfully",
            "deleted_count": deleted_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Bulk delete error: {e}")
        return {"success": False, "message": f"Failed to delete jobs: {str(e)}"}


# =========================================================
# EDIT JOB
# =========================================================

@router.put("/employer/jobs/{job_id}")
async def update_job(
    job_id: str,
    request: PostJobRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    try:
        check = db.execute(
            text("""
                SELECT jobid FROM job_postings
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {"jobid": job_id, "email": user_email},
        ).fetchone()

        if not check:
            return {"success": False, "message": "Job not found or unauthorized"}

        db.execute(
            text("""
                UPDATE job_postings SET
                    job_title = :job_title,
                    client_name = :client_name,
                    location = :location,
                    work_authorization = :work_authorization,
                    experience = :experience,
                    salary = :salary,
                    employment_type = :employment_type,
                    visa_transfer = :visa_transfer,
                    job_description = :job_description,
                    skills = :skills,
                    responsibilities = :responsibilities,
                    updated_at = NOW()
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {
                "jobid": job_id,
                "job_title": request.job_title,
                "client_name": request.client_name or "Direct Client",
                "location": request.location or "Remote",
                "work_authorization": request.work_authorization,
                "experience": request.experience or "Not specified",
                "salary": request.salary or "Competitive",
                "employment_type": request.employment_type,
                "visa_transfer": request.visa_transfer,
                "job_description": request.job_description or "",
                "skills": request.skills or "",
                "responsibilities": request.responsibilities or "",
                "email": user_email,
            },
        )

        db.commit()
        logger.info(f"Job {job_id} updated by {user_email}")
        return {"success": True, "message": "Job updated successfully", "jobid": job_id}

    except Exception as e:
        db.rollback()
        logger.error(f"Update error: {e}")
        return {"success": False, "message": f"Failed to update job: {str(e)}"}


# =========================================================
# RE-POST JOB (CLONE)
# =========================================================

@router.post("/employer/jobs/{job_id}/repost")
async def repost_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    try:
        original = db.execute(
            text("""
                SELECT job_title, client_name, location, work_authorization,
                       experience, salary, employment_type, visa_transfer,
                       job_description, skills, responsibilities
                FROM job_postings
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {"jobid": job_id, "email": user_email},
        ).fetchone()

        if not original:
            return {"success": False, "message": "Job not found or unauthorized"}

        new_job_id = str(uuid.uuid4())[:8].upper()

        db.execute(
            text("""
                INSERT INTO job_postings (
                    jobid, job_title, client_name, location,
                    work_authorization, experience, salary, employment_type,
                    visa_transfer, job_description, skills, responsibilities,
                    posted_by, created_at
                )
                VALUES (
                    :jobid, :job_title, :client_name, :location,
                    :work_authorization, :experience, :salary, :employment_type,
                    :visa_transfer, :job_description, :skills, :responsibilities,
                    :posted_by, NOW()
                )
            """),
            {
                "jobid": new_job_id,
                "created_date": date.today(),
                "job_title": original.job_title,
                "client_name": original.client_name,
                "location": original.location,
                "work_authorization": original.work_authorization,
                "experience": original.experience,
                "salary": original.salary,
                "employment_type": original.employment_type,
                "visa_transfer": original.visa_transfer,
                "job_description": original.job_description,
                "skills": original.skills,
                "responsibilities": original.responsibilities,
                "posted_by": user_email,
            },
        )

        db.commit()

        # Background email
        try:
            background_tasks.add_task(
                send_job_notification,
                {
                    "job_title": original.job_title,
                    "poster_company": original.client_name,
                    "location": original.location or "Remote",
                    "job_description": original.job_description,
                    "skills": original.skills,
                    "responsibilities": original.responsibilities,
                    "jobid": new_job_id,
                    "employment_type": original.employment_type,
                },
            )
        except Exception as e:
            logger.error(f"Email task failed: {e}")

        logger.info(f"Job {job_id} re-posted as {new_job_id} by {user_email}")
        return {
            "success": True,
            "message": "Job re-posted successfully",
            "original_jobid": job_id,
            "new_jobid": new_job_id,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Repost error: {e}")
        return {"success": False, "message": f"Failed to re-post job: {str(e)}"}


# =========================================================
# MATCH TOP PROFILES & EMAIL
# =========================================================

@router.post("/employer/jobs/{job_id}/match-top-profiles")
async def match_top_profiles_and_email(
    job_id: str,
    background_tasks: BackgroundTasks,
    top_k: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    try:
        job_result = db.execute(
            text("""
                SELECT jobid, job_title, job_description, skills, experience, location, posted_by
                FROM job_postings
                WHERE jobid = :jobid AND posted_by = :email
            """),
            {"jobid": job_id, "email": user_email},
        ).fetchone()

        if not job_result:
            return {"success": False, "message": "Job not found or unauthorized"}

        submissions_result = db.execute(
            text("""
                SELECT
                    submission_id,
                    candidate_name,
                    full_name,
                    resume_text,
                    match_score,
                    scoring_status
                FROM submissions
                WHERE resume_text IS NOT NULL AND resume_text != ''
                ORDER BY created_at DESC
                LIMIT 100
            """)
        )

        submissions = submissions_result.fetchall()
        if not submissions:
            return {
                "success": True,
                "message": "No resumes found in database to match",
                "matches": [],
            }

        job_text = f"""
            Title: {job_result.job_title}
            Description: {job_result.job_description or ''}
            Skills Required: {job_result.skills or ''}
            Experience: {job_result.experience or ''}
            Location: {job_result.location or ''}
        """

        def _keyword_match_score(job_text: str, resume_text: str) -> float:
            job_lower = job_text.lower()
            resume_lower = (resume_text or "").lower()

            tech_skills = [
                "python", "javascript", "java", "react", "node", "sql", "aws",
                "docker", "kubernetes", "machine learning", "ai", "data analysis",
                "typescript", "next.js", "vue", "angular", "mongodb", "postgresql",
                "redis", "graphql", "rest api", "git", "ci/cd", "jenkins",
                "tensorflow", "pytorch", "pandas", "numpy", "tableau",
            ]

            matching = sum(
                1 for skill in tech_skills
                if skill in job_lower and skill in resume_lower
            )
            job_count = sum(1 for skill in tech_skills if skill in job_lower)

            return (matching / max(job_count, 1)) * 100 if job_count > 0 else 50.0

        matches = []
        for sub in submissions:
            score = sub.match_score or _keyword_match_score(job_text, sub.resume_text or "")
            matches.append({
                "submission_id": sub.submission_id,
                "candidate_name": sub.candidate_name or sub.full_name,
                "match_score": score,
                "scoring_status": sub.scoring_status,
            })

        matches.sort(key=lambda x: x["match_score"], reverse=True)
        top_matches = matches[:top_k]

        # Store matches
        for match in top_matches:
            match_id = hashlib.md5(
                f"{job_id}_{match['submission_id']}".encode()
            ).hexdigest()[:20]

            db.execute(
                text("""
                    INSERT INTO ai_matches (
                        match_id, job_id, resume_id, match_score, created_at, created_by
                    ) VALUES (
                        :match_id, :job_id, :resume_id, :match_score, NOW(), :created_by
                    )
                    ON CONFLICT (match_id) DO UPDATE SET
                        match_score = EXCLUDED.match_score,
                        updated_at = NOW()
                """),
                {
                    "match_id": match_id,
                    "job_id": job_id,
                    "resume_id": match["submission_id"][:20],
                    "match_score": match["match_score"],
                    "created_by": user_email,
                },
            )

        db.commit()

        # Email top matches
        background_tasks.add_task(
            _send_top_matches_email,
            user_email,
            job_result.job_title,
            job_id,
            top_matches,
        )

        return {
            "success": True,
            "message": f"Top {len(top_matches)} matching candidates found and emailed",
            "job_id": job_id,
            "job_title": job_result.job_title,
            "matches_found": len(top_matches),
            "matches": top_matches,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Match top profiles error: {e}")
        return {"success": False, "message": f"Failed to match profiles: {str(e)}"}


def _send_top_matches_email(
    poster_email: str, job_title: str, job_id: str, matches: list
) -> bool:
    """Send email with top matching candidates to job poster."""
    from api.utils.email_sender import send_email_gmail_api

    rows_html = "".join(
        f"""
        <tr>
            <td style="padding: 10px; border: 1px solid #ddd;">{i}</td>
            <td style="padding: 10px; border: 1px solid #ddd;">{m['candidate_name']}</td>
            <td style="padding: 10px; border: 1px solid #ddd;">{m['match_score']:.1f}%</td>
            <td style="padding: 10px; border: 1px solid #ddd;">{m['scoring_status']}</td>
        </tr>
        """
        for i, m in enumerate(matches, 1)
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   color: white; padding: 20px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #f5f5f5; padding: 10px; border: 1px solid #ddd; text-align: left; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h2>Top Matching Candidates</h2></div>
        <p>Here are the top {len(matches)} matching candidates for your job posting:</p>
        <p><strong>Job:</strong> {job_title}<br><strong>Job ID:</strong> {job_id}</p>
        <table>
            <thead>
                <tr><th>Rank</th><th>Candidate Name</th><th>Match Score</th><th>Status</th></tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        <p style="margin-top: 20px;">
            <a href="https://hiringcircle.us/employer/applicants/{job_id}"
               style="background: #4f46e5; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px;">
               View All Applicants
            </a>
        </p>
    </div>
</body>
</html>"""

    return send_email_gmail_api(
        to_list=[poster_email],
        bcc_list=[],
        subject=f"Top Matching Candidates - {job_title}",
        html=html,
    )


# =========================================================
# GENERATE SCORE & REPORT FOR SUBMISSION
# =========================================================

@router.post("/employer/submissions/{submission_id}/score")
async def generate_submission_score(
    submission_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_role("EMPLOYER")),
):
    user_email = current_user.get("email")

    try:
        sub_result = db.execute(
            text("""
                SELECT s.submission_id, s.candidate_name, s.full_name, s.resume_text,
                       s.job_id, j.job_title, j.job_description, j.skills as job_skills
                FROM submissions s
                LEFT JOIN job_postings j ON s.job_id = j.jobid
                WHERE s.submission_id = :submission_id
            """),
            {"submission_id": submission_id},
        ).fetchone()

        if not sub_result:
            return {"success": False, "message": "Submission not found"}

        job_text = f"""
            Title: {sub_result.job_title or 'N/A'}
            Description: {sub_result.job_description or ''}
            Skills Required: {sub_result.job_skills or ''}
        """

        resume_text = sub_result.resume_text or ""

        def _detailed_score(job_text: str, resume_text: str) -> dict:
            job_lower = job_text.lower()
            resume_lower = resume_text.lower()

            skills = [
                "python", "javascript", "java", "react", "node", "sql", "aws",
                "docker", "kubernetes", "machine learning", "ai", "data analysis",
                "typescript", "next.js", "vue", "angular", "mongodb", "postgresql",
                "redis", "graphql", "rest api", "git", "ci/cd",
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

            exp_keywords = ["years", "experience", "senior", "lead", "manager"]
            exp_matches = sum(
                1 for kw in exp_keywords if kw in job_lower and kw in resume_lower
            )
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

        score_data = _detailed_score(job_text, resume_text)

        db.execute(
            text("""
                UPDATE submissions SET
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
            """),
            {
                "submission_id": submission_id,
                "match_score": score_data["overall_score"],
                "semantic_similarity": score_data["overall_score"] / 100,
                "score_breakdown": json.dumps({
                    "skill_score": score_data["skill_score"],
                    "experience_score": score_data["experience_score"],
                }),
                "fit_summary": f"Candidate has {len(score_data['matching_skills'])} matching skills",
                "confidence_band": score_data["fit"],
                "final_recommendation": score_data["fit"],
                "skill_matrix": json.dumps({
                    "matching": score_data["matching_skills"],
                    "missing": score_data["missing_skills"],
                }),
            },
        )

        db.commit()

        background_tasks.add_task(
            _generate_submission_report,
            submission_id,
            sub_result.candidate_name or sub_result.full_name,
            sub_result.job_title,
            score_data,
        )

        return {
            "success": True,
            "message": "Score generated successfully",
            "submission_id": submission_id,
            "score": score_data["overall_score"],
            "fit": score_data["fit"],
            "matching_skills": score_data["matching_skills"],
            "missing_skills": score_data["missing_skills"],
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Generate score error: {e}")
        return {"success": False, "message": f"Failed to generate score: {str(e)}"}


def _generate_submission_report(
    submission_id: str, candidate_name: str, job_title: str, score_data: dict
) -> str:
    """Generate and save HTML report for a submission."""
    reports_dir = os.environ.get("REPORTS_PATH", "/tmp/reports")
    os.makedirs(reports_dir, exist_ok=True)

    report_path = os.path.join(reports_dir, f"report_{submission_id}.html")

    score_color = {
        "excellent": "#22c55e",
        "good": "#3b82f6",
        "fair": "#f59e0b",
        "poor": "#ef4444",
    }.get(score_data["fit"].lower(), "#6b7280")

    matching_html = "".join(f"<li>{s}</li>" for s in score_data["matching_skills"])
    missing_html = "".join(f"<li>{s}</li>" for s in score_data["missing_skills"])

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Candidate Assessment Report - {candidate_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   color: white; padding: 30px; text-align: center; border-radius: 8px; }}
        .score-box {{ background: #f5f5f5; padding: 20px; border-radius: 8px;
                      margin: 20px 0; text-align: center; }}
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
            <ul>{matching_html or '<li>None found</li>'}</ul>
        </div>
        <div class="skills-column">
            <h3 class="missing">Missing Skills ({len(score_data['missing_skills'])})</h3>
            <ul>{missing_html or '<li>None found</li>'}</ul>
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

    with open(report_path, "w") as f:
        f.write(html)

    # Update submission with report path
    from api.db import SessionLocal

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE submissions SET report_path = :report_path WHERE submission_id = :submission_id"),
            {"report_path": report_path, "submission_id": submission_id},
        )
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save report path: {e}")
    finally:
        db.close()

    return report_path