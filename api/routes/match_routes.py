from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from api.db import get_db
from api.utils.security import get_current_user
from services.match_service import match_job_to_candidates

router = APIRouter()


@router.post("/hybrid-match/job/{job_id}")
def match_candidates(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        results = match_job_to_candidates(job_id)

        return {
            "job_id": job_id,
            "count": len(results),
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
