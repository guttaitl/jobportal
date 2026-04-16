from fastapi import APIRouter, HTTPException
from services.match_service import match_job_to_candidates

router = APIRouter()


@router.post("/hybrid-match/job/{job_id}")
def match_candidates(job_id: str):
    try:
        results = match_job_to_candidates(job_id)

        return {
            "job_id": job_id,
            "count": len(results),
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))