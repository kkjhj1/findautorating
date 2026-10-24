from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.core.config import settings
from app.core.init_db import init_database
from app.api.router import api_router
from app.jobs.scheduler import start_scheduler, stop_scheduler

from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.job_log import CollectionJob
from app.models.enums import JobStatus

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB 초기화
    init_database()

    # 1. 엑셀 전산요건 자동 동기화 (SSOT)
    db = SessionLocal()
    try:
        from app.institution.sync import sync_institutions_from_excel
        sync_institutions_from_excel(db)
    except Exception as exc:
        db.rollback()
        print(f"Startup Excel sync warning: {exc}")
    finally:
        db.close()

    # 2. 이전에 비정상 종료되거나 남아있는 좀비 RUNNING 및 COLLECTING 작업 정리 (완전 독립 세션 보장)
    db2 = SessionLocal()
    try:
        stale_jobs = db2.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).all()
        for j in stale_jobs:
            j.status = JobStatus.FAILED.value
            j.finished_at = datetime.now(timezone.utc)
            j.error_message = "서버 재기동으로 인해 중단됨"

        from app.models.current_rating import CurrentRating
        from app.models.enums import CollectionStatus
        stale_collecting = db2.query(CurrentRating).filter_by(overall_status=CollectionStatus.COLLECTING.value).all()
        for c in stale_collecting:
            c.overall_status = CollectionStatus.CRAWLING_ERROR.value
            c.calculation_logic = "서버 재기동으로 인해 조사가 중단되었습니다."

        if stale_jobs or stale_collecting:
            db2.commit()
    except Exception as exc:
        db2.rollback()
        print(f"Startup zombie cleanup warning: {exc}")
    finally:
        db2.close()

    # 사용자가 원할 때만 자동 스케줄러 실행 (기본 False: 100% 수동 실행 모드)
    if settings.ENABLE_AUTO_SCHEDULER:
        start_scheduler()

    yield

    # Shutdown: 스케줄러 정상 종료
    if settings.ENABLE_AUTO_SCHEDULER:
        stop_scheduler()

app = FastAPI(
    title=settings.APP_TITLE,
    description="금융기관 신용등급 자동조사 시스템 REST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup (보안: 신뢰할 수 있는 로컬 오리진으로 제한)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app_title": settings.APP_TITLE,
        "environment": settings.APP_ENV
    }

# Mount static frontend directory
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
