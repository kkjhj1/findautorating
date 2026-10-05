from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from app.core.database import Base

class CreditRatingRaw(Base):
    __tablename__ = "credit_rating_raw"

    raw_id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), nullable=True, index=True)
    institution_id = Column(String(50), ForeignKey("institutions.institution_id"), nullable=False, index=True)
    agency_code = Column(String(10), nullable=False, index=True) # KR, KIS, NICE
    raw_rating = Column(String(50), nullable=True) # 원본 등급 문자열
    normalized_rating = Column(String(20), nullable=True) # 표준화된 등급 (AA, AA-)
    rating_type = Column(String(50), nullable=False) # CORPORATE_CREDIT 등
    raw_rating_date = Column(String(50), nullable=True)
    rating_date = Column(String(10), nullable=True) # YYYY-MM-DD
    raw_valid_from = Column(String(50), nullable=True)
    raw_valid_to = Column(String(50), nullable=True)
    valid_from = Column(String(10), nullable=True) # YYYY-MM-DD
    valid_to = Column(String(10), nullable=True) # YYYY-MM-DD
    source_url = Column(Text, nullable=True)
    raw_data = Column(Text, nullable=True) # 원문 JSON 또는 HTML 발췌
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    collection_status = Column(String(30), nullable=False) # SUCCESS, NO_RATING, CRAWLING_ERROR 등
    error_message = Column(Text, nullable=True)

    institution = relationship("Institution", back_populates="raw_ratings")
