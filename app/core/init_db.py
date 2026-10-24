from sqlalchemy import text
from app.core.database import engine, Base
import app.models # 모든 모델을 Base에 등록

def init_database():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE collection_jobs ADD COLUMN error_message TEXT"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_job_running ON collection_jobs (status) WHERE status = 'RUNNING';"))
            conn.commit()
        except Exception:
            pass
    print("Database tables created successfully.")

if __name__ == "__main__":
    init_database()
