from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.job_log import CollectionJob
from app.models.enums import JobStatus

db = SessionLocal()
running_jobs = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).all()
for j in running_jobs:
    print(f"Aborting stale job: {j.job_id}")
    j.status = JobStatus.FAILED.value
    j.finished_at = datetime.now(timezone.utc)

db.commit()
print("All stale running jobs cleaned up.")
db.close()
