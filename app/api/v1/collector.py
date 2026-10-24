import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.enums import JobStatus, ExecutionType
from app.models.job_log import CollectionJob
from app.models.institution import Institution
from app.schemas.job import JobRunRequest, JobResponse
from app.jobs.collector_job import (
    run_collection_batch,
    reserve_collection_job,
    get_active_job_progress,
    request_stop_collection,
    ACTIVE_JOB_PROGRESS,
    STOP_COLLECTION_EVENT,
    _JOB_TRIGGER_LOCK
)

router = APIRouter(prefix="/collector", tags=["Collector"])

@router.post("/stop")
def stop_current_collection(db: Session = Depends(get_db)):
    """실행 중인 신용등급 조사 작업에 안전한 중단 요청 전송 (워커 정리 완료 보장)"""
    with _JOB_TRIGGER_LOCK:
        running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
        is_active = ACTIVE_JOB_PROGRESS.get("is_running", False) or running is not None

        if not is_active:
            return {
                "status": "info",
                "message": "현재 실행 중인 조사 작업이 없습니다."
            }

        request_stop_collection()

        ACTIVE_JOB_PROGRESS.update({
            "is_stopping": True,
            "current_institution": "조사 중단 요청됨 (스레드 정리 중...)"
        })

        return {
            "status": "success",
            "message": "조사 작업 중단이 요청되었습니다. 진행 중인 수집 스레드가 안전하게 종료된 후 완전히 정리됩니다."
        }

@router.post("/run")
def trigger_collection(payload: JobRunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """수동 전체 또는 선택 기관 조사 실행 트리거 (PRD 제32조, 33조)"""
    with _JOB_TRIGGER_LOCK:
        try:
            job, active_count = reserve_collection_job(
                db=db,
                execution_type=payload.execution_type,
                target_institution_ids=payload.institution_ids
            )
        except RuntimeError as e:
            raise HTTPException(
                status_code=409,
                detail=str(e)
            )

        # 비동기 백그라운드 태스크로 실행 (이미 원자적으로 예약된 job_id 전달)
        background_tasks.add_task(
            run_collection_batch,
            execution_type=payload.execution_type,
            target_institution_ids=payload.institution_ids,
            existing_job_id=job.job_id
        )

        return {
            "status": "accepted",
            "message": "수집 작업이 백그라운드에서 시작되었습니다.",
            "execution_type": payload.execution_type,
            "target_count": active_count
        }

@router.get("/status")
def get_current_job_status(db: Session = Depends(get_db)):
    active_progress = get_active_job_progress()
    running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
    last = db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).first()

    is_running = running is not None or active_progress.get("is_running", False) or active_progress.get("is_stopping", False)

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
            "error_message": last.error_message if last else None,
        } if last else None
    }

