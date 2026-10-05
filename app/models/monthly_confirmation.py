from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

class MonthlyConfirmedRating(Base):
    """
    월별 최종 확정 신용등급 이력 스냅샷 (Last-Win 적용)
    - 사용자가 화면에서 검토 후 [최종 확정]을 클릭했을 때 영구 기록
    - 동월(base_year_month)에 여러 번 확정할 경우 가장 마지막에 확정한 내역으로 덮어쓰기(Last-Win)
    """
    __tablename__ = "monthly_confirmed_ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_year_month = Column(String(7), nullable=False, index=True) # "2026-10"
    institution_id = Column(String(50), ForeignKey("institutions.institution_id"), nullable=False, index=True)
    
    institution_name = Column(String(100), nullable=False)
    original_name = Column(String(100), nullable=True)
    industry_type = Column(String(50), nullable=True)
    rating_type = Column(String(50), nullable=True)
    rating_type_name = Column(String(50), nullable=True)

    # 최종 확정 등급 및 전월 대비 변동
    final_rating = Column(String(20), nullable=True) # 당월 최저등급
    prev_final_rating = Column(String(20), nullable=True) # 전월 최저등급
    rating_change_status = Column(String(30), default="NEW", nullable=False) # MAINTAIN, UPGRADE, DOWNGRADE, NEW
    rating_change_notch = Column(Integer, default=0, nullable=False)
    rating_change_label = Column(String(50), default="신규", nullable=True)
    calculation_logic = Column(String(200), nullable=True)
    overall_status = Column(String(30), default="SUCCESS", nullable=False)

    # 3대 신용평가사별 스냅샷
    kr_rating = Column(String(20), nullable=True)
    kr_date = Column(String(10), nullable=True)
    kr_status = Column(String(30), default="NO_RATING", nullable=True)

    kis_rating = Column(String(20), nullable=True)
    kis_date = Column(String(10), nullable=True)
    kis_status = Column(String(30), default="NO_RATING", nullable=True)

    nice_rating = Column(String(20), nullable=True)
    nice_date = Column(String(10), nullable=True)
    nice_status = Column(String(30), default="NO_RATING", nullable=True)

    # 확정 메타데이터
    confirmed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    confirmed_by = Column(String(50), default="USER", nullable=False)

    __table_args__ = (
        UniqueConstraint("base_year_month", "institution_id", name="uq_monthly_confirmed_inst"),
    )

    institution = relationship("Institution")
