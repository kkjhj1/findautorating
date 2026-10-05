from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base

class Institution(Base):
    __tablename__ = "institutions"

    institution_id = Column(String(50), primary_key=True, index=True) # 불변 식별자 (예: INS_BNK_001)
    institution_name = Column(String(100), nullable=False, index=True) # 표준 기관명
    original_name = Column(String(100), nullable=False) # 엑셀 원본 기관명
    industry_type = Column(String(30), nullable=False, index=True) # BANK, SAVINGS_BANK 등
    rating_type = Column(String(50), nullable=False) # CORPORATE_CREDIT, SENIOR_BOND 등
    search_name_1 = Column(String(100), nullable=True) # 전산요건 검색1 (1순위 검색어)
    search_name_2 = Column(String(100), nullable=True) # 전산요건 검색2 (2순위 검색어)
    search_name_3 = Column(String(100), nullable=True) # 추가 확장 검색3 (3순위 검색어)
    kr_target_rating = Column(String(50), nullable=True) # 한국기업평가 조사항목 (ICR, IFSR, 회사채)
    kis_target_rating = Column(String(50), nullable=True) # 한국신용평가 조사항목 (Issuer Rating, 보험금지급 능력평가, 회사채(선순위))
    nice_target_rating = Column(String(50), nullable=True) # NICE신용평가 조사항목 (기업신용평가, 채권, 보험금지급능력)
    dart_corp_code = Column(String(20), nullable=True)
    business_no = Column(String(20), nullable=True)
    use_yn = Column(String(1), default="Y", nullable=False)
    user_modified = Column(Boolean, default=False, nullable=False) # 웹에서 수정한 기관 (서버 재기동 시 엑셀 덮어쓰기 방지)
    memo = Column(String(500), nullable=True) # M&A / 사명변경 사유 메모
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    mappings = relationship("AgencyInstitutionMapping", back_populates="institution", cascade="all, delete-orphan")
    current_rating = relationship("CurrentRating", back_populates="institution", uselist=False, cascade="all, delete-orphan")
    raw_ratings = relationship("CreditRatingRaw", back_populates="institution", cascade="all, delete-orphan")
    histories = relationship("CreditRatingHistory", back_populates="institution", cascade="all, delete-orphan")

class AgencyInstitutionMapping(Base):
    __tablename__ = "rating_agency_institution"

    mapping_id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(String(50), ForeignKey("institutions.institution_id"), nullable=False, index=True)
    agency_code = Column(String(10), nullable=False, index=True) # KR, KIS, NICE
    agency_institution_id = Column(String(100), nullable=True) # 평가사 고유 ID/코드
    search_name = Column(String(100), nullable=False) # 평가사 검색에 사용할 키워드
    alias_name = Column(String(100), nullable=True) # 평가사 실제 등록 공식명
    mapping_status = Column(String(30), default="AUTO_MAPPED", nullable=False) # AUTO_MAPPED, MANUAL_CONFIRMED, MAPPING_REQUIRED
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    institution = relationship("Institution", back_populates="mappings")
