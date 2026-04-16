from pydantic import BaseModel
from typing import List, Optional


class CandidateMatch(BaseModel):
    candidate_id: str
    candidate_name: str
    email: Optional[str] = None
    match_score: float
    summary: Optional[str] = None


class TopCandidatesResponse(BaseModel):
    job_id: str
    total_returned: int
    candidates: List[CandidateMatch]