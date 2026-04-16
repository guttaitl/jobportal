from fastapi import APIRouter, Query, HTTPException, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from api.db import get_db
from api.models import JobPosting
from api.utils.email_sender import send_job_notification

router = APIRouter(prefix="/jobs")

# =========================
# 📦 REQUEST MODEL (matches frontend)
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
# 🔥 GET RECENT JOBS (MUST BE FIRST - before /jobs/{job_id})
# =========================

@router.get("/jobs/recent")
def get_recent_jobs(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get recently posted jobs (ordered by created_at desc)
    """
    jobs = db.query(JobPosting).order_by(JobPosting.created_at.desc()).limit(limit).all()

    return {
        "jobs": [
            {
                "job_id": j.jobid,
                "job_title": j.job_title,
                "client_name": j.client_name,
                "location": j.location,
                "description": j.job_description,
                "created_at": j.created_at,
                "employment_type": j.employment_type,
                "salary": j.salary
            }
            for j in jobs
        ],
        "total": len(jobs),
        "limit": limit
    }


# =========================
# 🔵 GET ALL JOBS (with optional recent filter via query param)
# =========================

@router.get("/jobs")
def get_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    recent: bool = Query(False),
    recent_limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get all jobs (paginated) OR recent jobs if ?recent=true
    """
    if recent:
        jobs = db.query(JobPosting).order_by(JobPosting.created_at.desc()).limit(recent_limit).all()
        return {
            "jobs": [
                {
                    "job_id": j.jobid,
                    "title": j.job_title,
                    "company": j.client_name,
                    "location": j.location,
                    "description": j.job_description,
                    "created_at": j.created_at,
                    "employment_type": j.employment_type,
                    "salary": j.salary
                }
                for j in jobs
            ],
            "total": len(jobs),
            "limit": recent_limit,
            "recent": True
        }
    
    # Default: paginated list
    total = db.query(JobPosting).count()
    jobs = db.query(JobPosting).offset(skip).limit(limit).all()

    return {
        "jobs": [
            {
                "job_id": j.jobid,
                "title": j.job_title,
                "company": j.client_name,
                "location": j.location,
                "description": j.job_description,
                "created_at": j.created_at,
                "employment_type": j.employment_type,
                "salary": j.salary
            }
            for j in jobs
        ],
        "total": total,
        "skip": skip,
        "limit": limit
    }


# =========================
# 🟡 GET JOB BY ID (MUST BE AFTER /jobs/recent)
# =========================

@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """
    Get a specific job by ID
    """
    job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.jobid,
        "title": job.job_title,
        "company": job.client_name,
        "location": job.location,
        "description": job.job_description,
        "experience": job.experience,
        "skills": job.skills,
        "employment_type": job.employment_type,
        "salary": job.salary,
        "work_authorization": job.work_authorization,
        "visa_transfer": job.visa_transfer,
        "created_at": job.created_at,
        "applicants_count": job.applicants_count
    }


# =========================
# 🟢 CREATE JOB
# =========================

@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(job: JobBase, db: Session = Depends(get_db)):
    timestamp = str(int(datetime.utcnow().timestamp()))[-7:]
    job_id = f"JOB{timestamp}"

    new_job = JobPosting(
        jobid=job_id,
        job_title=job.title,
        job_description=job.description,
        location=job.location,
        experience=job.requirements,
        skills=None,
        employment_type=job.job_type,
        salary=str(job.salary_min) if job.salary_min else None,
        client_name=job.company,
        created_at=datetime.utcnow()
    )

    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Send email notification
    email_sent = False
    try:
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
        email_sent = send_job_notification(job_dict)
    except Exception as e:
        print(f"Email error: {e}")

    return {
        "id": job_id,
        "message": "Job created successfully",
        "email_sent": email_sent
    }

# =========================
# 🟠 UPDATE JOB (PUT)
# =========================

@router.put("/jobs/{job_id}")
def update_job(job_id: str, job: JobBase, db: Session = Depends(get_db)):
    """
    Update an existing job
    """
    existing_job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not existing_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update fields
    existing_job.job_title = job.title
    existing_job.client_name = job.company
    existing_job.location = job.location
    existing_job.job_description = job.description
    existing_job.experience = job.requirements
    existing_job.employment_type = job.job_type
    existing_job.salary = str(job.salary_min) if job.salary_min else None

    db.commit()
    db.refresh(existing_job)

    return {
        "id": job_id,
        "message": "Job updated successfully"
    }


# =========================
# 🔴 DELETE JOB
# =========================

@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    """
    Delete a job posting
    """
    job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.delete(job)
    db.commit()

    return {"message": "Job deleted successfully"}


# =========================
# 🔍 SEARCH JOBS (optional)
# =========================

@router.get("/jobs/search")
def search_jobs(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Search jobs by title, description, or location
    """
    search_term = f"%{q}%"
    
    jobs = db.query(JobPosting).filter(
        (JobPosting.job_title.ilike(search_term)) |
        (JobPosting.job_description.ilike(search_term)) |
        (JobPosting.location.ilike(search_term))
    ).limit(limit).all()

    return {
        "jobs": [
            {
                "job_id": j.jobid,
                "title": j.job_title,
                "company": j.client_name,
                "location": j.location,
                "description": j.job_description,
                "created_at": j.created_at
            }
            for j in jobs
        ],
        "query": q,
        "total": len(jobs)
    }
