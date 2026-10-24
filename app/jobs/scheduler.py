import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
from app.models.enums import ExecutionType

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def scheduled_job():
    logger.info("Executing daily scheduled credit rating collection batch...")
    from app.jobs.collector_job import (
        reserve_collection_job,
        run_collection_batch
    )
    from app.api.v1.collector import _JOB_TRIGGER_LOCK
    from app.core.database import SessionLocal

    db = SessionLocal()
    job_id = None
    try:
        with _JOB_TRIGGER_LOCK:
            try:
                job, _ = reserve_collection_job(
                    db=db,
                    execution_type=ExecutionType.SCHEDULED.value
                )
                job_id = job.job_id
            except RuntimeError as e:
                logger.warning(f"스케줄 수집 작업 스킵: {e}")
                return
    finally:
        db.close()

    try:
        run_collection_batch(
            execution_type=ExecutionType.SCHEDULED.value,
            existing_job_id=job_id
        )
        logger.info(f"Daily collection batch completed. Job ID: {job_id}")
    except Exception as exc:
        logger.error(f"Daily collection batch failed: {str(exc)}")

def start_scheduler():
    cron_parts = settings.CRON_SCHEDULE.split()
    if len(cron_parts) == 5:
        minute, hour, day, month, day_of_week = cron_parts
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week
        )
    else:
        # Default: 06:00 AM daily
        trigger = CronTrigger(hour=6, minute=0)

    scheduler.add_job(scheduled_job, trigger=trigger, id="daily_rating_collection", replace_existing=True)
    if not scheduler.running:
        scheduler.start()
        logger.info(f"Scheduler started with cron: {settings.CRON_SCHEDULE}")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
