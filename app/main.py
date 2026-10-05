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

    # 이전에 비정상 종료되거나 남아있는 좀비 RUNNING 작업 정리 및 엑셀 전산요건 자동 동기화(SSOT)
    db = SessionLocal()
    try:
        from app.institution.sync import sync_institutions_from_excel
        sync_institutions_from_excel(db)

        stale_jobs = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).all()
        for j in stale_jobs:
            j.status = JobStatus.FAILED.value
            j.finished_at = datetime.now(timezone.utc)
        if stale_jobs:
            db.commit()
    except Exception as exc:
        print(f"Startup sync warning: {exc}")
    finally:
        db.close()

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

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
