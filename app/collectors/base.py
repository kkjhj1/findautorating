from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from app.schemas.rating import StandardRating, RawCompany, RawRatingRecord
from app.models.enums import CollectionStatus
from app.rating.normalizer import normalize_rating

class RatingAgencyAdapter(ABC):
    """
    PRD 제6조 및 제7조: 평가사별 수집 Adapter 표준 인터페이스
    공통 Engine에 특정 평가사의 HTML Selector나 URL을 작성하지 않고,
    각 평가사 사이트에 종속되는 로직만 Adapter 계층에서 격리 처리한다.
    """
    def __init__(self, agency_code: str, agency_name: str, base_url: str):
        self.agency_code = agency_code
        self.agency_name = agency_name
        self.base_url = base_url

    def search_company(
        self,
        keyword: str,
        priority: int = 1,
        client: Optional[Any] = None
    ) -> Optional[RawCompany]:
        """
        [1단계: 기업 검색]
        단일 검색 키워드에 대해 해당 평가사에서 대상 기업 존재 여부 및 Company ID 확정
        기업 미발견 시 None 반환
        """
        return None

    def fetch_raw_ratings(
        self,
        company: RawCompany,
        client: Optional[Any] = None
    ) -> List[RawRatingRecord]:
        """
        [2단계: 기업 상세 등급 조회]
        확정된 기업(Company ID)의 상세 페이지/API를 조회하여
        해당 기업이 보유한 모든 Raw 등급 레코드 목록 반환
        """
        return []

    @abstractmethod
    def get_ratings(
        self,
        institution_id: str,
        search_name: str,
        rating_type: str,
        original_name: str = "",
        search_name_2: str = "",
        target_rating_name: str = "",
        search_keywords: Optional[List[str]] = None
    ) -> StandardRating:
        """
        [통합 파이프라인]
        1순위 -> 2순위 -> 3순위 순차 탐색 후 기업 확정 즉시 STOP
        기업 상세 조회 및 RatingFinalizer를 통한 표준 Rating 객체 반환
        """
        pass

    def normalize(self, raw_rating: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """공통 등급 정규화 위임"""
        return normalize_rating(raw_rating)

    @abstractmethod
    def health_check(self) -> bool:
        """평가사 사이트 정상 접근 여부 점검"""
        pass

