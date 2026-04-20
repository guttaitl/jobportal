from fastapi import APIRouter, Query, HTTPException, Depends, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging

from api.utils.ai_job_description import generate_structured_job_content
from api.utils.email_sender import send_job_notification
from api.db import get_db
from api.models import JobPosting
from api.utils.security import require_role

router = APIRouter(prefix="/jobs")
logger = logging.getLogger(__name__)

# =========================
# 📦 REQUEST MODEL
# =========================

class JobBase(BaseModel):
    title: str
    company: str
    location: str
    description: str
    requirements: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_type: Optional[str] = None
    visa_sponsorship: Optional[bool] = False
    remote_allowed: Optional[bool] = False


# =========================
# 🔥 GET RECENT JOBS
# =========================

@router.get("/recent")
def get_recent_jobs(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    jobs = db.query(JobPosting).order_by(JobPosting.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "jobs": [serialize_job(j) for j in jobs],
        "total": len(jobs)
    }


# =========================
# 🔵 GET ALL JOBS
# =========================

@router.get("/")
def get_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    total = db.query(JobPosting).count()
    jobs = db.query(JobPosting).offset(skip).limit(limit).all()

    return {
        "success": True,
        "jobs": [serialize_job(j) for j in jobs],
        "total": total,
        "skip": skip,
        "limit": limit
    }


# =========================
# 🟡 GET JOB BY ID
# =========================

@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "success": True,
        "job": serialize_job(job)
    }


# =========================
# 🟢 CREATE JOB (AI + EMAIL)
# =========================

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_job(
    job: JobBase,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    timestamp = str(int(datetime.utcnow().timestamp()))[-7:]
    job_id = f"JOB{timestamp}"

    new_job = JobPosting(
        jobid=job_id,
        job_title=job.title,
        job_description=job.description,
        location=job.location,
        experience=job.requirements,
        employment_type=job.job_type,
        salary=str(job.salary_min) if job.salary_min else None,
        client_name=job.company,
        created_at=datetime.utcnow()
    )

    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # 🔥 Background AI + Email
    background_tasks.add_task(handle_job_email, job, job_id)

    return {
        "success": True,
        "id": job_id,
        "message": "Job created successfully"
    }


# =========================
# 🟠 UPDATE JOB
# =========================

@router.put("/{job_id}")
def update_job(job_id: str, job: JobBase, db: Session = Depends(get_db)):
    existing_job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found")

    existing_job.job_title = job.title
    existing_job.client_name = job.company
    existing_job.location = job.location
    existing_job.job_description = job.description
    existing_job.experience = job.requirements
    existing_job.employment_type = job.job_type
    existing_job.salary = str(job.salary_min) if job.salary_min else None

    db.commit()

    return {
        "success": True,
        "message": "Job updated successfully"
    }


# =========================
# 🔴 DELETE JOB
# =========================

@router.delete("/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.delete(job)
    db.commit()

    return {
        "success": True,
        "message": "Job deleted successfully"
    }


# =========================
# 🔍 SEARCH JOBS
# =========================

@router.get("/search")
def search_jobs(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    search_term = f"%{q}%"

    jobs = db.query(JobPosting).filter(
        (JobPosting.job_title.ilike(search_term)) |
        (JobPosting.job_description.ilike(search_term)) |
        (JobPosting.location.ilike(search_term))
    ).limit(limit).all()

    return {
        "success": True,
        "jobs": [serialize_job(j) for j in jobs],
        "total": len(jobs),
        "query": q
    }


# =========================
# 🧠 HELPERS
# =========================

def serialize_job(j):
    return {
        "job_id": j.jobid,
        "title": j.job_title,
        "company": j.client_name,
        "location": j.location,
        "description": j.job_description,
        "created_at": j.created_at,
        "employment_type": j.employment_type,
        "salary": j.salary
    }


def handle_job_email(job: JobBase, job_id: str):
    try:
        structured = generate_structured_job_content(
            job_title=job.title,
            experience=job.requirements,
            rate=str(job.salary_min) if job.salary_min else None,
            company_name=job.company,
            location=job.location,
            employment_type=job.job_type,
            industry=None
        )

        job_dict = {
            "jobid": job_id,
            "job_title": job.title,
            "user_company": job.company,
            "location": job.location,
            "employment_type": job.job_type,
            "job_description": job.description,
            "skills": "",
            "responsibilities": "",
            "user_name": ""
        }

        send_job_notification(job_dict, structured)

    except Exception as e:
        logger.error(f"Email error: {e}")