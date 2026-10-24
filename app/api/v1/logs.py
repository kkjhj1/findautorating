from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.job_log import CollectionJob, CollectionLog
from app.models.institution import Institution
from app.schemas.job import JobResponse, LogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("/jobs", response_model=List[JobResponse])
def get_jobs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).limit(limit).all()

@router.get("/{job_id}/details", response_model=List[LogResponse])
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    logs = db.query(CollectionLog).filter_by(job_id=job_id).order_by(CollectionLog.started_at).all()
    if not logs:
        raise HTTPException(status_code=404, detail="해당 작업의 로그를 찾을 수 없습니다.")

    inst_map = {i.institution_id: i.institution_name for i in db.query(Institution).all()}
    enriched = []
    for log in logs:
        enriched.append(LogResponse(
            log_id=log.log_id,
            job_id=log.job_id,
            institution_id=log.institution_id,
            institution_name=inst_map.get(log.institution_id, log.institution_id),
            agency_code=log.agency_code,
            status=log.status,
            message=log.message,
            source_url=log.source_url,
            started_at=log.started_at,
            finished_at=log.finished_at
        ))
    return enriched

