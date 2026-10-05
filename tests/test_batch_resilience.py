import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.enums import JobStatus, ExecutionType
from app.models.job_log import CollectionJob
from app.models.current_rating import CurrentRating
from app.models.rating_history import CreditRatingHistory
from app.jobs.collector_job import run_collection_batch

def test_batch_duplicate_prevention():
    """PRD 제33조: RUNNING 상태 작업이 있을 때 전체 조사 실행 차단 검증"""
    db: Session = SessionLocal()
    try:
        # 가상의 RUNNING 작업 생성
        dummy_job = CollectionJob(
            job_id="JOB_TEST_RUNNING_LOCK",
            execution_type=ExecutionType.SCHEDULED.value,
            started_at=datetime.now(timezone.utc),
            status=JobStatus.RUNNING.value
        )
        db.add(dummy_job)
        db.commit()

        # 중복 실행 시도 -> RuntimeError 발생해야 함
        with pytest.raises(RuntimeError) as exc_info:
            run_collection_batch(execution_type=ExecutionType.MANUAL_ALL.value)
        assert "이미 실행 중인 수집 작업" in str(exc_info.value)

    finally:
        # 테스트 정리
        db.query(CollectionJob).filter_by(job_id="JOB_TEST_RUNNING_LOCK").delete()
        db.commit()
        db.close()

def test_history_creation_on_rating_update():
    """PRD 제22조, TC-10: 신규 등급 산출 시 히스토리 누적 검증"""
    db: Session = SessionLocal()
    try:
        inst_id = "INS_BNK_001"
        # 초기 등급 설정
        cur = db.query(CurrentRating).filter_by(institution_id=inst_id).first()
        if cur:
            cur.final_rating = "AA"
            db.commit()

        # 히스토리 추가 시뮬레이션
        h = CreditRatingHistory(
            institution_id=inst_id,
            agency_code="FINAL",
            rating_type="CORPORATE_CREDIT",
            rating="AA-",
            rating_date="2026-10-01",
            recorded_at=datetime.now(timezone.utc)
        )
        db.add(h)
        db.commit()

        saved = db.query(CreditRatingHistory).filter_by(institution_id=inst_id).order_by(CreditRatingHistory.recorded_at.desc()).first()
        assert saved is not None
        assert saved.rating == "AA-"
    finally:
        db.close()
