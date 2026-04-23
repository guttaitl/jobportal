<<<<<<< HEAD
from fastapi import APIRouter, Query, HTTPException, Depends, status, BackgroundTasks
=======
from fastapi import APIRouter, Query, HTTPException, Depends, status
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
<<<<<<< HEAD
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
=======

from api.db import get_db
from api.models import JobPosting
from api.utils.email_sender import send_job_notification

router = APIRouter(prefix="/api", tags=["Jobs"])


# =========================
# 📦 REQUEST MODEL (matches frontend)
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
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
<<<<<<< HEAD
# 🔥 GET RECENT JOBS
# =========================

@router.get("/recent")
def get_recent_jobs(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    jobs = db.query(JobPosting).order_by(JobPosting.created_at.desc()).limit(limit).all()

    return {
        "success": True,
        "jobs": [serialize_job(j) for j in jobs],
        "total": len(jobs)
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    }


# =========================
<<<<<<< HEAD
# 🔵 GET ALL JOBS
# =========================

@router.get("/")
def get_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    total = db.query(JobPosting).count()
    jobs = db.query(JobPosting).offset(skip).limit(limit).all()

    return {
<<<<<<< HEAD
        "success": True,
        "jobs": [serialize_job(j) for j in jobs],
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        "total": total,
        "skip": skip,
        "limit": limit
    }


# =========================
<<<<<<< HEAD
# 🟡 GET JOB BY ID
# =========================

@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
=======
# 🟡 GET JOB BY ID (MUST BE AFTER /jobs/recent)
# =========================

@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """
    Get a specific job by ID
    """
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    job = db.query(JobPosting).filter(JobPosting.jobid == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
<<<<<<< HEAD
        "success": True,
        "job": serialize_job(job)
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    }


# =========================
<<<<<<< HEAD
# 🟢 CREATE JOB (AI + EMAIL)
# =========================

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_job(
    job: JobBase,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
=======
# 🟢 CREATE JOB
# =========================

@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(job: JobBase, db: Session = Depends(get_db)):
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
    timestamp = str(int(datetime.utcnow().timestamp()))[-7:]
    job_id = f"JOB{timestamp}"

    new_job = JobPosting(
        jobid=job_id,
        job_title=job.title,
        job_description=job.description,
        location=job.location,
        experience=job.requirements,
<<<<<<< HEAD
=======
        skills=None,
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        employment_type=job.job_type,
        salary=str(job.salary_min) if job.salary_min else None,
        client_name=job.company,
        created_at=datetime.utcnow()
    )

    db.add(new_job)
    db.commit()
    db.refresh(new_job)

<<<<<<< HEAD
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

=======
    # Send email notification
    email_sent = False
    try:
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
        job_dict = {
            "jobid": job_id,
            "job_title": job.title,
            "user_company": job.company,
            "location": job.location,
            "employment_type": job.job_type,
            "job_description": job.description,
            "skills": "",
            "responsibilities": "",
<<<<<<< HEAD
            "user_name": job.company or "Employer"
        }

        send_job_notification(job_dict, structured)

    except Exception as e:
        logger.error(f"Email error: {e}")
=======
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
>>>>>>> 5d2a440b29f790bcaf0987af11c53518ac88b3e2
