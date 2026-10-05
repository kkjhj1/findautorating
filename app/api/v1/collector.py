from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.enums import JobStatus, ExecutionType
from app.models.job_log import CollectionJob
from app.schemas.job import JobRunRequest, JobResponse
from app.jobs.collector_job import (
    run_collection_batch,
    get_active_job_progress,
    request_stop_collection,
    ACTIVE_JOB_PROGRESS
)

router = APIRouter(prefix="/collector", tags=["Collector"])

@router.post("/stop")
def stop_current_collection(db: Session = Depends(get_db)):
    """실행 중인 신용등급 조사 작업을 즉시 안전하게 중단"""
    request_stop_collection()

    running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
    if running:
        running.status = JobStatus.STOPPED.value
        running.finished_at = datetime.now(timezone.utc)
        running.error_message = "사용자에 의해 조사가 중지되었습니다."
        db.commit()

    ACTIVE_JOB_PROGRESS.update({
        "is_running": False,
        "current_institution": "조사 중지됨"
    })

    return {
        "status": "success",
        "message": "조사 작업이 성공적으로 중지되었습니다."
    }

@router.post("/run")
def trigger_collection(payload: JobRunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """수동 전체 또는 선택 기관 조사 실행 트리거 (PRD 제32조, 33조)"""
    # 중복 실행 방지 확인
    running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"이미 실행 중인 수집 작업({running.job_id})이 있어 새 작업을 시작할 수 없습니다."
        )

    # 선제적 상태 플래그 즉시 세팅 (첫 폴링 시 레이스 컨디션 및 깜빡임 원천 방지)
    ACTIVE_JOB_PROGRESS.update({
        "is_running": True,
        "total_count": len(payload.institution_ids) if payload.institution_ids else 85,
        "processed_count": 0,
        "success_count": 0,
        "no_rating_count": 0,
        "error_count": 0,
        "manual_check_count": 0,
        "current_institution": "조사 엔진 기동 중...",
        "progress_percent": 3.0,
        "started_at": datetime.now(timezone.utc).isoformat()
    })

    # 비동기 백그라운드 태스크로 실행
    background_tasks.add_task(
        run_collection_batch,
        execution_type=payload.execution_type,
        target_institution_ids=payload.institution_ids
    )

    return {
        "status": "accepted",
        "message": "수집 작업이 백그라운드에서 시작되었습니다.",
        "execution_type": payload.execution_type,
        "target_count": len(payload.institution_ids) if payload.institution_ids else "ALL"
    }

@router.get("/status")
def get_current_job_status(db: Session = Depends(get_db)):
    active_progress = get_active_job_progress()
    running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
    last = db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).first()

    is_running = running is not None or active_progress.get("is_running", False)

    current_job_info = None
    if is_running:
        total = running.total_count if running and running.total_count > 0 else active_progress.get("total_count", 0)
        success = running.success_count if running else active_progress.get("success_count", 0)
        no_rating = running.no_rating_count if running else active_progress.get("no_rating_count", 0)
        error = running.error_count if running else active_progress.get("error_count", 0)
        manual = running.manual_check_count if running else active_progress.get("manual_check_count", 0)
        processed = success + no_rating + error + manual
        pct = round((processed / total * 100), 1) if total > 0 else 0.0

        current_job_info = {
            "job_id": running.job_id if running else active_progress.get("job_id"),
            "is_running": True,
            "total_count": total,
            "processed_count": processed,
            "success_count": success,
            "no_rating_count": no_rating,
            "error_count": error,
            "manual_check_count": manual,
            "current_institution": active_progress.get("current_institution") or "조사 진행 중...",
            "progress_percent": pct,
            "started_at": running.started_at.isoformat() if running and running.started_at else active_progress.get("started_at"),
        }

    return {
        "is_running": is_running,
        "current_job_id": running.job_id if running else active_progress.get("job_id"),
        "progress": current_job_info,
        "last_job": {
            "job_id": last.job_id if last else None,
            "started_at": last.started_at.isoformat() if last and last.started_at else None,
            "finished_at": last.finished_at.isoformat() if last and last.finished_at else None,
            "status": last.status if last else None,
            "total_count": last.total_count if last else 0,
            "success_count": last.success_count if last else 0,
            "no_rating_count": last.no_rating_count if last else 0,
            "error_count": last.error_count if last else 0,
            "manual_check_count": last.manual_check_count if last else 0,
        } if last else None
    }

