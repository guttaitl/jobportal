from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from datetime import datetime
from typing import Optional
import uuid
from api.db import Base

Base = declarative_base()

class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    resume_id: Mapped[Optional[int]] = mapped_column(Integer)
    candidate_name: Mapped[Optional[str]] = mapped_column(Text)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    resume_text: Mapped[Optional[str]] = mapped_column(Text)

    # ✅ This maps to job_postings.jobid
    job_id: Mapped[Optional[str]] = mapped_column(Text)
    job_title: Mapped[Optional[str]] = mapped_column(Text)
    job_description: Mapped[Optional[str]] = mapped_column(Text)

    # AI scoring
    match_score: Mapped[Optional[float]] = mapped_column(Float)
    semantic_similarity: Mapped[Optional[float]] = mapped_column(Float)
    score_breakdown: Mapped[Optional[str]] = mapped_column(Text)
    fit_summary: Mapped[Optional[str]] = mapped_column(Text)
    confidence_band: Mapped[Optional[str]] = mapped_column(String(20))
    final_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    skill_matrix: Mapped[Optional[str]] = mapped_column(Text)
    fabrication_observations: Mapped[Optional[str]] = mapped_column(Text)
    scoring_status: Mapped[Optional[str]] = mapped_column(String(50))
    report_path: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(Integer, primary_key=True, index=True)
    jobid = Column(String(10), unique=True, index=True, nullable=False)  # 🔥 matches DB
    job_title = Column(Text, nullable=False)
    job_description = Column(Text)
    location = Column(Text)
    experience = Column(Text)
    skills = Column(Text)
    employment_type = Column(Text)
    salary = Column(Text)
    client_name = Column(Text)
    work_authorization = Column(Text, default="Any")
    visa_transfer = Column(Text, default="No")
    posted_by = Column(Text)
    applicants_count = Column(Integer, default=0)
    responsibilities = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime)