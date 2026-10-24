from typing import Optional, List, Any
from datetime import datetime, date, timezone
from pydantic import BaseModel, Field, ConfigDict

class RawCompany(BaseModel):
    """검색 단계에서 식별된 기업 정보"""
    company_name: str
    company_id: str                          # KIS: kiscd, KR: COMP_CD, NICE: cmp_cd
    matched_keyword: str
    search_priority: int                     # 1순위, 2순위, 3순위 등
    source_url: str = ""
    extra_data: Optional[dict] = None

class RawRatingRecord(BaseModel):
    """기업 상세/공시에서 추출된 개별 평가 레코드"""
    company_id: str
    rating_type_raw: str                     # 사이트 원본 평가종류 (예: 'Issuer Rating', '회사채(선순위)')
    raw_rating: str                          # 원본 등급 문자열 (예: 'AAA', 'AA-')
    rating_date: Optional[date] = None       # 파싱된 확정일자 (datetime.date)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None          # 파싱된 유효만료일자 (datetime.date)
    source_url: str = ""
    extra_info: Optional[str] = None         # 부가정보 (후순위 여부, 공시 번호 등)
    outlook: Optional[str] = None            # 등급전망 (안정적, 긍정적, 부정적 등)

class StandardRating(BaseModel):
    """PRD 제8조 표준 Rating 객체"""
    institution_id: str
    agency_code: str # KR, KIS, NICE
    rating_type: str # CORPORATE_CREDIT, SENIOR_BOND, INSURANCE_FINANCIAL_STRENGTH
    rating_type_raw: Optional[str] = None    # 실제 사이트에서 수집된 등급종류 (예: '선순위회사채')
    raw_rating: Optional[str] = None
    rating: Optional[str] = None # 정규화된 등급 (AA, AA- 등)
    outlook: Optional[str] = None            # 등급전망 (안정적, 긍정적, 부정적 등)
    rating_date: Optional[str] = None # YYYY-MM-DD
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    status: str = "VALID" # SUCCESS, EXPIRED, NO_RATING, CRAWLING_ERROR, PARSING_ERROR, MANUAL_CHECK, MANUAL_REVIEW, etc.
    source_url: Optional[str] = None
    raw_data: Optional[str] = None
    error_message: Optional[str] = None
    company_id: Optional[str] = None         # 식별된 기업 코드
    search_priority: Optional[int] = None    # 확정된 검색 키워드 순위 (1, 2, 3...)
    matched_keyword: Optional[str] = None    # 매칭 성공 검색어
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class RatingCalculationResult(BaseModel):
    """최종 등급 계산 결과 DTO"""
    institution_id: str
    final_rating: Optional[str] = None
    overall_status: str # SUCCESS, MANUAL_CHECK, CRAWLING_ERROR, NO_RATING
    calculation_logic: str
    kr: Optional[StandardRating] = None
    kis: Optional[StandardRating] = None
    nice: Optional[StandardRating] = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CurrentRatingResponse(BaseModel):
    institution_id: str
    institution_name: str
    original_name: str
    industry_type: str
    rating_type: str
    rating_type_name: str = ""
    final_rating: Optional[str] = None
    prev_final_rating: Optional[str] = None
    rating_change_status: str = "NEW"
    rating_change_notch: int = 0
    rating_change_label: Optional[str] = "신규"
    is_ambiguous: bool = False
    overall_status: str
    calculation_logic: Optional[str] = None
    kr_rating: Optional[str] = None
    kr_date: Optional[str] = None
    kr_status: str
    kr_url: Optional[str] = None
    kr_rating_type: Optional[str] = None
    kr_outlook: Optional[str] = None
    kis_rating: Optional[str] = None
    kis_date: Optional[str] = None
    kis_status: str
    kis_url: Optional[str] = None
    kis_rating_type: Optional[str] = None
    kis_outlook: Optional[str] = None
    nice_rating: Optional[str] = None
    nice_date: Optional[str] = None
    nice_status: str = "NO_RATING"
    nice_url: Optional[str] = None
    nice_rating_type: Optional[str] = None
    nice_outlook: Optional[str] = None
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None
    kr_target_rating: Optional[str] = None
    kis_target_rating: Optional[str] = None
    nice_target_rating: Optional[str] = None
    evaluated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class AgencyDetailInfo(BaseModel):
    agency_code: str
    agency_name: str
    rating: Optional[str] = None
    raw_rating: Optional[str] = None
    rating_type_raw: Optional[str] = None
    outlook: Optional[str] = None
    rating_date: Optional[str] = None
    valid_to: Optional[str] = None
    status: str
    source_url: Optional[str] = None
    error_message: Optional[str] = None

class CurrentRatingDetailResponse(BaseModel):
    institution_id: str
    institution_name: str
    original_name: str
    industry_type: str
    rating_type: str
    rating_type_name: str
    final_rating: Optional[str] = None
    overall_status: str
    calculation_logic: Optional[str] = None
    search_name_1: Optional[str] = None
    search_name_2: Optional[str] = None
    search_name_3: Optional[str] = None
    agencies: List[AgencyDetailInfo]
    evaluated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ConfirmRatingRequest(BaseModel):
    base_year_month: Optional[str] = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$") # None이면 오늘 기준 YYYY-MM
    confirmed_by: Optional[str] = "USER"

class MonthlyConfirmedRatingItem(BaseModel):
    id: int
    base_year_month: str
    institution_id: str
    institution_name: str
    original_name: Optional[str] = None
    industry_type: Optional[str] = None
    rating_type: Optional[str] = None
    rating_type_name: Optional[str] = None
    final_rating: Optional[str] = None
    prev_final_rating: Optional[str] = None
    rating_change_status: str = "NEW"
    rating_change_notch: int = 0
    rating_change_label: Optional[str] = "신규"
    calculation_logic: Optional[str] = None
    overall_status: str = "SUCCESS"
    kr_rating: Optional[str] = None
    kr_date: Optional[str] = None
    kr_status: Optional[str] = None
    kis_rating: Optional[str] = None
    kis_date: Optional[str] = None
    kis_status: Optional[str] = None
    nice_rating: Optional[str] = None
    nice_date: Optional[str] = None
    nice_status: Optional[str] = None
    confirmed_at: datetime
    confirmed_by: str = "USER"

    model_config = ConfigDict(from_attributes=True)

class MonthlyHistorySummary(BaseModel):
    total: int = 0
    maintain: int = 0
    upgrade: int = 0
    downgrade: int = 0
    new: int = 0
    error: int = 0

class MonthlyHistoryResponse(BaseModel):
    base_year_month: str
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    total_count: int = 0
    summary: MonthlyHistorySummary
    items: List[MonthlyConfirmedRatingItem]

