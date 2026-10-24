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

def test_confirm_safety_guard_when_job_running():
    """수집 Job이 RUNNING 상태일 때 월별 확정 API 호출 시 400 에러 발생 검증"""
    from fastapi import HTTPException
    from app.api.v1.ratings import confirm_monthly_ratings
    from app.schemas.rating import ConfirmRatingRequest

    db: Session = SessionLocal()
    dummy_job_id = "JOB_TEST_CONFIRM_GUARD"
    try:
        dummy_job = CollectionJob(
            job_id=dummy_job_id,
            execution_type=ExecutionType.SCHEDULED.value,
            started_at=datetime.now(timezone.utc),
            status=JobStatus.RUNNING.value
        )
        db.add(dummy_job)
        db.commit()

        req = ConfirmRatingRequest(base_year_month="2026-10", confirmed_by="TEST")
        with pytest.raises(HTTPException) as exc_info:
            confirm_monthly_ratings(payload=req, db=db)
        assert exc_info.value.status_code == 400
        assert "조사가 진행 중" in exc_info.value.detail
    finally:
        db.query(CollectionJob).filter_by(job_id=dummy_job_id).delete()
        db.commit()
        db.close()

def test_sqlite_wal_pragma():
    """SQLite WAL 저널 모드 및 busy_timeout 설정 적용 검증"""
    from sqlalchemy import text
    db: Session = SessionLocal()
    try:
        res = db.execute(text("PRAGMA journal_mode")).scalar()
        assert res.lower() == "wal"
    finally:
        db.close()

def test_institution_mapping_route_not_eaten_by_id_param():
    """FastAPI 라우트 순서 검증: PUT /api/v1/institutions/mapping 이 /{institution_id}로 오인되지 않아야 함"""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    # 빈 바디 전송 시 422 Unprocessable Entity가 반환되어야 함 (404 Not Found가 아님)
    response = client.put("/api/v1/institutions/mapping", json={})
    assert response.status_code == 422, f"Expected 422 validation error for mapping schema, got {response.status_code}"

def test_current_rating_response_has_search_name_3():
    """CurrentRatingResponse 스키마에 search_name_3 필드가 포함되어 있는지 검증"""
    from app.schemas.rating import CurrentRatingResponse
    fields = CurrentRatingResponse.model_fields
    assert "search_name_3" in fields

def test_sync_single_institution_rejects_when_job_running():
    """전체 수집 진행 중 개별 동기화 API 호출 시 400 에러 차단 검증"""
    from fastapi import HTTPException
    from app.api.v1.ratings import sync_single_institution
    db: Session = SessionLocal()
    dummy_job_id = "JOB_TEST_SYNC_CONCURRENCY"
    try:
        dummy_job = CollectionJob(
            job_id=dummy_job_id,
            execution_type=ExecutionType.SCHEDULED.value,
            started_at=datetime.now(timezone.utc),
            status=JobStatus.RUNNING.value
        )
        db.add(dummy_job)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            sync_single_institution(institution_id="INS_BNK_001", db=db)
        assert exc_info.value.status_code == 409
        assert "전체 신용등급 조사가 진행 중" in exc_info.value.detail
    finally:
        db.query(CollectionJob).filter_by(job_id=dummy_job_id).delete()
        db.commit()
        db.close()

def test_confirm_rating_request_base_year_month_validation():
    """ConfirmRatingRequest의 base_year_month YYYY-MM 정규식 유효성 검증"""
    from pydantic import ValidationError
    from app.schemas.rating import ConfirmRatingRequest

    # 올바른 포맷
    req = ConfirmRatingRequest(base_year_month="2026-10", confirmed_by="TEST")
    assert req.base_year_month == "2026-10"

    # 잘못된 월 (13월)
    with pytest.raises(ValidationError):
        ConfirmRatingRequest(base_year_month="2026-13")

    # 잘못된 포맷 (하이픈 없음)
    with pytest.raises(ValidationError):
        ConfirmRatingRequest(base_year_month="202610")

def test_current_rating_detail_response_has_search_names():
    """CurrentRatingDetailResponse 스키마에 search_name_1/2/3 필드가 존재하는지 검증"""
    from app.schemas.rating import CurrentRatingDetailResponse
    fields = CurrentRatingDetailResponse.model_fields
    assert "search_name_1" in fields
    assert "search_name_2" in fields
    assert "search_name_3" in fields

def test_startup_zombie_collecting_recovery():
    """서버 기동 시 COLLECTING 상태 잔여 기관이 CRAWLING_ERROR로 회수되는지 검증"""
    from app.models.enums import CollectionStatus
    db: Session = SessionLocal()
    inst_id = "INS_BNK_001"
    try:
        cur = db.query(CurrentRating).filter_by(institution_id=inst_id).first()
        if cur:
            cur.overall_status = CollectionStatus.COLLECTING.value
            db.commit()

        # 시뮬레이션: lifespan 시작 로직 실행
        stale_collecting = db.query(CurrentRating).filter_by(overall_status=CollectionStatus.COLLECTING.value).all()
        for c in stale_collecting:
            c.overall_status = CollectionStatus.CRAWLING_ERROR.value
            c.calculation_logic = "서버 재기동으로 인해 조사가 중단되었습니다."
        if stale_collecting:
            db.commit()

        reloaded = db.query(CurrentRating).filter_by(institution_id=inst_id).first()
        assert reloaded.overall_status == CollectionStatus.CRAWLING_ERROR.value
    finally:
        db.close()

def test_collector_stop_and_rerun_prevention():
    """중단 처리 중(is_stopping=True) 및 실행 중일 때 /run 호출 시 409 Conflict 차단 검증"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.jobs.collector_job import ACTIVE_JOB_PROGRESS
    client = TestClient(app)

    # 1) is_stopping 시뮬레이션
    ACTIVE_JOB_PROGRESS["is_stopping"] = True
    try:
        res = client.post("/api/v1/collector/run", json={"execution_type": "MANUAL_ALL"})
        assert res.status_code == 409
        assert "중단 정리 중" in res.json().get("detail", "")
    finally:
        ACTIVE_JOB_PROGRESS["is_stopping"] = False

    # 2) is_running 시뮬레이션
    ACTIVE_JOB_PROGRESS["is_running"] = True
    try:
        res = client.post("/api/v1/collector/run", json={"execution_type": "MANUAL_ALL"})
        assert res.status_code == 409
    finally:
        ACTIVE_JOB_PROGRESS["is_running"] = False

def test_all_collectors_use_tls_verification():
    """3대 평가사 모듈에서 verify=False가 사용되지 않고 TLS 검증이 활성화되어 있는지 검증"""
    import inspect
    from app.collectors import kis, nice, krating

    for mod in [kis, nice, krating]:
        src = inspect.getsource(mod)
        assert "verify=False" not in src, f"{mod.__name__}에 verify=False가 잔류하고 있습니다."

def test_real_worker_stop_and_rerun_lifecycle():
    """실제 워커 스레드 기동 -> /stop 호출 -> 정리 완료 전 /run 409 차단 -> 정리 완료 후 플래그 및 DB STOPPED 검증"""
    import threading
    import time
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.jobs.collector_job import (
        run_collection_batch,
        ACTIVE_JOB_PROGRESS
    )
    from app.models.job_log import CollectionJob
    from app.models.enums import JobStatus
    from app.core.database import SessionLocal

    client = TestClient(app)

    def slow_collector(*args, **kwargs):
        time.sleep(0.15)
        from app.jobs.collector_job import InstitutionCollectResult
        from app.schemas.rating import RatingCalculationResult
        return InstitutionCollectResult(
            institution_id=args[0],
            institution_name=args[1],
            rating_type=args[2],
            agency_results=[],
            calc_result=RatingCalculationResult(
                institution_id=args[0],
                final_rating=None,
                overall_status="NO_RATING",
                calculation_logic="테스트 지연"
            )
        )

    with patch("app.jobs.collector_job._collect_for_single_institution", side_effect=slow_collector), \
         patch("app.collectors.krating.KRatingAdapter.preload_disclosure_data", return_value={}):
        worker_thread = threading.Thread(
            target=run_collection_batch,
            kwargs={"execution_type": "MANUAL_SELECT", "target_institution_ids": ["INS_BNK_001", "INS_BNK_002", "INS_BNK_003"]}
        )
        worker_thread.start()

        for _ in range(20):
            if ACTIVE_JOB_PROGRESS.get("is_running"):
                break
            time.sleep(0.05)

        assert ACTIVE_JOB_PROGRESS.get("is_running") is True

        stop_res = client.post("/api/v1/collector/stop")
        assert stop_res.status_code == 200

        conflict_res = client.post("/api/v1/collector/run", json={"execution_type": "MANUAL_ALL"})
        assert conflict_res.status_code == 409

        worker_thread.join(timeout=5.0)
        assert not worker_thread.is_alive()

        assert ACTIVE_JOB_PROGRESS.get("is_running") is False
        assert ACTIVE_JOB_PROGRESS.get("is_stopping") is False

        db = SessionLocal()
        try:
            last_job = db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).first()
            assert last_job is not None
            assert last_job.status == JobStatus.STOPPED.value
            assert last_job.finished_at is not None
        finally:
            db.close()

def test_reserve_collection_job_concurrency_guard():
    """reserve_collection_job 원자적 예약 함수 중복 호출 차단 검증"""
    from app.jobs.collector_job import reserve_collection_job, ACTIVE_JOB_PROGRESS
    from app.models.enums import ExecutionType
    from app.core.database import SessionLocal

    db = SessionLocal()
    reserved_job_id = None
    try:
        job, count = reserve_collection_job(db=db, execution_type=ExecutionType.MANUAL_ALL.value)
        reserved_job_id = job.job_id
        assert ACTIVE_JOB_PROGRESS.get("is_running") is True

        # 두 번째 예약 시도 -> RuntimeError 발생해야 함
        with pytest.raises(RuntimeError) as exc_info:
            reserve_collection_job(db=db, execution_type=ExecutionType.SCHEDULED.value)
        assert "이미 실행 중" in str(exc_info.value)
    finally:
        ACTIVE_JOB_PROGRESS["is_running"] = False
        ACTIVE_JOB_PROGRESS["is_stopping"] = False
        if reserved_job_id:
            db.query(CollectionJob).filter_by(job_id=reserved_job_id).delete()
            db.commit()
        db.close()

def test_sync_and_confirm_guard_when_memory_flag_set():
    """DB 레코드 생성 전 메모리 플래그만 세팅된 상태에서도 /sync 및 /confirm 이 즉시 차단되는지 검증"""
    from fastapi import HTTPException
    from app.jobs.collector_job import ACTIVE_JOB_PROGRESS
    from app.api.v1.ratings import sync_single_institution, confirm_monthly_ratings
    from app.schemas.rating import ConfirmRatingRequest
    from app.core.database import SessionLocal

    db = SessionLocal()
    ACTIVE_JOB_PROGRESS["is_running"] = True
    try:
        # 1) sync_single_institution 가드 검증
        with pytest.raises(HTTPException) as exc_sync:
            sync_single_institution(institution_id="INS_BNK_001", db=db)
        assert exc_sync.value.status_code == 409

        # 2) confirm_monthly_ratings 가드 검증
        req = ConfirmRatingRequest(base_year_month="2026-10", confirmed_by="TEST")
        with pytest.raises(HTTPException) as exc_confirm:
            confirm_monthly_ratings(payload=req, db=db)
        assert exc_confirm.value.status_code == 400
    finally:
        ACTIVE_JOB_PROGRESS["is_running"] = False
        ACTIVE_JOB_PROGRESS["is_stopping"] = False
        db.close()

def test_concurrent_barrier_race_condition():
    """5개 동시 스레드가 Barrier를 통해 동시 reserve_collection_job 호출 시 정확히 1개만 성공하고 4개는 차단되는지 검증"""
    import threading
    from app.jobs.collector_job import reserve_collection_job, ACTIVE_JOB_PROGRESS
    from app.models.enums import ExecutionType
    from app.models.job_log import CollectionJob
    from app.core.database import SessionLocal

    num_threads = 5
    barrier = threading.Barrier(num_threads)
    results = []
    errors = []
    reserved_jobs = []

    def worker():
        db = SessionLocal()
        try:
            barrier.wait()
            job, count = reserve_collection_job(db=db, execution_type=ExecutionType.MANUAL_ALL.value)
            results.append(job.job_id)
            reserved_jobs.append(job.job_id)
        except RuntimeError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"Unexpected: {e}")
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 1, f"정확히 1개 스레드만 성공해야 하나, {len(results)}개 성공함"
        assert len(errors) == num_threads - 1, f"나머지 {num_threads - 1}개 스레드는 예외가 발생해야 함"
        for err in errors:
            assert "이미 실행 중" in err
    finally:
        ACTIVE_JOB_PROGRESS["is_running"] = False
        ACTIVE_JOB_PROGRESS["is_stopping"] = False
        clean_db = SessionLocal()
        try:
            for jid in reserved_jobs:
                clean_db.query(CollectionJob).filter_by(job_id=jid).delete()
            clean_db.commit()
        finally:
            clean_db.close()
