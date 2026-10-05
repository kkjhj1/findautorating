from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base

class CurrentRating(Base):
    __tablename__ = "current_ratings"

    institution_id = Column(String(50), ForeignKey("institutions.institution_id"), primary_key=True)

    # 한국기업평가 (KR)
    kr_rating = Column(String(20), nullable=True)
    kr_date = Column(String(10), nullable=True) # YYYY-MM-DD
    kr_status = Column(String(30), default="NO_RATING", nullable=False) # SUCCESS, NO_RATING, CRAWLING_ERROR 등
    kr_url = Column(Text, nullable=True)
    kr_rating_type = Column(String(50), nullable=True)
    kr_outlook = Column(String(30), nullable=True)

    # 한국신용평가 (KIS)
    kis_rating = Column(String(20), nullable=True)
    kis_date = Column(String(10), nullable=True)
    kis_status = Column(String(30), default="NO_RATING", nullable=False)
    kis_url = Column(Text, nullable=True)
    kis_rating_type = Column(String(50), nullable=True)
    kis_outlook = Column(String(30), nullable=True)

    # NICE신용평가 (NICE)
    nice_rating = Column(String(20), nullable=True)
    nice_date = Column(String(10), nullable=True)
    nice_status = Column(String(30), default="NO_RATING", nullable=False)
    nice_url = Column(Text, nullable=True)
    nice_rating_type = Column(String(50), nullable=True)
    nice_outlook = Column(String(30), nullable=True)

    # 최종 등급 및 전체 상태
    final_rating = Column(String(20), nullable=True) # 당월 최저등급 (AA, AA- 등, 없을 시 NULL)
    prev_final_rating = Column(String(20), nullable=True) # 전월 최저등급
    rating_change_status = Column(String(30), default="NEW", nullable=False) # MAINTAIN, UPGRADE, DOWNGRADE, NEW
    rating_change_notch = Column(Integer, default=0, nullable=False) # 변동 단계 (+1, -1 등)
    rating_change_label = Column(String(50), default="신규", nullable=True) # "유지", "상향 ▲1", "하향 ▼1"
    
    # 다건 매칭 상태 및 후보군
    is_ambiguous = Column(Boolean, default=False, nullable=False)
    ambiguous_candidates = Column(Text, nullable=True) # JSON 문자열

    overall_status = Column(String(30), default="NO_RATING", nullable=False) # SUCCESS, MANUAL_CHECK, CRAWLING_ERROR 등
    calculation_logic = Column(String(200), nullable=True) # 산출 근거 (예: "KR(AA), KIS(AA-), NICE(AA) 중 최저치 AA-")

    evaluated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    institution = relationship("Institution", back_populates="current_rating")
