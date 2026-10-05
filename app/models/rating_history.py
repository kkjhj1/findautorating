from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class CreditRatingHistory(Base):
    __tablename__ = "credit_rating_histories"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(String(50), ForeignKey("institutions.institution_id"), nullable=False, index=True)
    agency_code = Column(String(10), nullable=False, index=True) # KR, KIS, NICE
    rating_type = Column(String(50), nullable=False)
    rating = Column(String(20), nullable=False) # AA, AA-
    rating_date = Column(String(10), nullable=True) # YYYY-MM-DD
    valid_from = Column(String(10), nullable=True)
    valid_to = Column(String(10), nullable=True)
    source_url = Column(String(500), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    institution = relationship("Institution", back_populates="histories")
