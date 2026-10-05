from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    job_id = Column(String(50), primary_key=True) # 예: JOB_20261001_060000_123
    execution_type = Column(String(30), nullable=False) # SCHEDULED, MANUAL_ALL, MANUAL_SELECT
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    total_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    no_rating_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    manual_check_count = Column(Integer, default=0, nullable=False)
    status = Column(String(30), default="RUNNING", nullable=False) # RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED

    logs = relationship("CollectionLog", back_populates="job", cascade="all, delete-orphan")

class CollectionLog(Base):
    __tablename__ = "collection_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), ForeignKey("collection_jobs.job_id"), nullable=False, index=True)
    institution_id = Column(String(50), nullable=False, index=True)
    agency_code = Column(String(10), nullable=False, index=True) # KR, KIS, NICE
    status = Column(String(30), nullable=False) # SUCCESS, NO_RATING, CRAWLING_ERROR 등
    message = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("CollectionJob", back_populates="logs")

class ManualProcessHistory(Base):
    __tablename__ = "manual_process_histories"

    process_id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(String(50), nullable=False, index=True)
    agency_code = Column(String(10), nullable=False)
    operator = Column(String(50), default="admin", nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    before_status = Column(String(30), nullable=False)
    after_status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    selected_agency_institution = Column(String(100), nullable=True)
