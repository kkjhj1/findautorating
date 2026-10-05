from app.core.database import SessionLocal
from app.models.job_log import CollectionJob

db = SessionLocal()
jobs = db.query(CollectionJob).order_by(CollectionJob.started_at.desc()).limit(10).all()
print(f"Total jobs count: {len(jobs)}")
for j in jobs:
    print(f"Job: {j.job_id}, status: {j.status}, started: {j.started_at}, finished: {j.finished_at}, total: {j.total_count}, succ: {j.success_count}")

running = db.query(CollectionJob).filter_by(status="RUNNING").all()
print(f"\nCurrently RUNNING jobs: {len(running)}")
for r in running:
    print(f"  RUNNING: {r.job_id}")

db.close()
