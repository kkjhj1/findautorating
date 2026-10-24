import re
import httpx
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from app.collectors.base import RatingAgencyAdapter
from app.schemas.rating import StandardRating, RawCompany, RawRatingRecord
from app.models.enums import AgencyCode, CollectionStatus, RatingType
from app.institution.search_candidates import generate_search_candidates, is_exact_corp_match
from app.rating.finalizer import finalize_rating

import threading
import logging

logger = logging.getLogger(__name__)

class KRatingWAFBlockedError(Exception):
    """한국기업평가 WAF IP 차단 (Too many requests) 에러"""
    pass

class KRatingAdapter(RatingAgencyAdapter):
    """
    한국기업평가 (Korea Ratings - KR) 실서비스 연동 어댑터
    - [전역 캐시 최적화]: 공시 피드를 1회만 다운로드하여 전체 기관에 공유 (WAF 차단 원천 방지)
    - [1단계: 기업 식별] 공시 피드 및 기업 목록에서 1순위 -> 2순위 -> 3순위 탐색, 기업 식별 시 즉시 STOP
    - [2단계: 상세 수집] COMP_CD 확정 후 해당 기업의 모든 평가종류 및 평가일자 수집 (5년 범위 확대)
    - [3단계: 최종 확정] RatingFinalizer: 대상 평가종류 필터링, 최신일 선택, 유효성 검증
    """
    _disclosure_cache: Optional[Dict[str, Any]] = None
    _cache_time: Optional[datetime] = None
    _cache_lock: threading.Lock = threading.Lock()

    def __init__(self):
        super().__init__(
            agency_code=AgencyCode.KR.value,
            agency_name="한국기업평가",
            base_url="https://www.korearatings.com"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.korearatings.com/cms/frCmnCon/index.do?MENU_ID=360",
        }

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0, headers=self.headers, verify=True) as client:
                res = client.get(self.base_url)
                return res.status_code == 200
        except Exception:
            return False

    @classmethod
    def preload_disclosure_data(cls, headers: dict, base_url: str) -> Dict[str, Any]:
        """배치 시작 전 1회 사전 다운로드 (Zero-Traffic 보장)"""
        with cls._cache_lock:
            now = datetime.now()
            if cls._disclosure_cache and cls._cache_time and (now - cls._cache_time).total_seconds() < 3600:
                return cls._disclosure_cache

            try:
                with httpx.Client(timeout=25.0, headers=headers, verify=True) as client:
                    client.get(f"{base_url}/cms/frCmnCon/index.do?MENU_ID=360")
                    today = date.today()
                    five_years_ago = today - timedelta(days=1825)

                    payload = {
                        "MENU_ID": "360",
                        "CONTENTS_NO": "1",
                        "SITE_NO": "2",
                        "COMP_CD": "",
                        "STDT": five_years_ago.strftime("%Y-%m-%d"),
                        "ENDT": today.strftime("%Y-%m-%d"),
                        "CHNG_ONLY_YN": "N",
                        "checkAll": "Y",
                        "SVCTY_CD": ["01", "07", "02", "03", "10", "11", "05", "09", "04", "06", "08"]
                    }

                    resp = client.post(f"{base_url}/ajaxf/frDisclosureSvc/getRatingDisclosureList.do", data=payload)
                    text_resp = resp.text
                    if "Too many requests" in text_resp or "blocked" in text_resp:
                        raise KRatingWAFBlockedError("한국기업평가 WAF IP 차단이 감지되었습니다 (Too many requests).")

                    if resp.status_code == 200:
                        d = resp.json().get("data", {})
                        if d:
                            cls._disclosure_cache = d
                            cls._cache_time = now
                            return d
            except Exception as e:
                logger.error(f"[KRating] Failed to preload disclosure data: {e}")
                if isinstance(e, KRatingWAFBlockedError):
                    raise
            return cls._disclosure_cache or {}

    def _get_disclosure_data(self, client: httpx.Client, comp_cd: str = "") -> Dict[str, Any]:
        """공시 목록 캐싱 (스레드 락 적용)"""
        now = datetime.now()
        if not comp_cd and self.__class__._disclosure_cache and self.__class__._cache_time:
            if (now - self.__class__._cache_time).total_seconds() < 3600:
                return self.__class__._disclosure_cache

        with self.__class__._cache_lock:
            # 락 획득 후 캐시 재확인 (Double-Checked Locking)
            if not comp_cd and self.__class__._disclosure_cache and self.__class__._cache_time:
                if (now - self.__class__._cache_time).total_seconds() < 3600:
                    return self.__class__._disclosure_cache

            client.get(f"{self.base_url}/cms/frCmnCon/index.do?MENU_ID=360")
            today = date.today()
            five_years_ago = today - timedelta(days=1825)

            payload = {
                "MENU_ID": "360",
                "CONTENTS_NO": "1",
                "SITE_NO": "2",
                "COMP_CD": comp_cd or "",
                "STDT": five_years_ago.strftime("%Y-%m-%d"),
                "ENDT": today.strftime("%Y-%m-%d"),
                "CHNG_ONLY_YN": "N",
                "checkAll": "Y",
                "SVCTY_CD": ["01", "07", "02", "03", "10", "11", "05", "09", "04", "06", "08"]
            }

            resp = client.post(f"{self.base_url}/ajaxf/frDisclosureSvc/getRatingDisclosureList.do", data=payload)
            text_resp = resp.text
            if "Too many requests" in text_resp or "blocked" in text_resp:
                raise KRatingWAFBlockedError("한국기업평가 WAF IP 차단이 감지되었습니다 (Too many requests).")

            if resp.status_code == 200:
                d = resp.json().get("data", {})
                if not comp_cd and d:
                    self.__class__._disclosure_cache = d
                    self.__class__._cache_time = now
                return d
            return self.__class__._disclosure_cache or {}

    def search_company(
        self,
        keyword: str,
        priority: int = 1,
        client: Optional[httpx.Client] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[RawCompany]:
        """
        [1단계: 기업 검색]
        공시 피드의 모든 그리드를 검사하여 keyword와 정확히 일치하는 기업(COMP_CD) 식별
        """
        if data is None:
            if client is None:
                with httpx.Client(timeout=35.0, headers=self.headers, verify=True) as c:
                    data = self._get_disclosure_data(c)
            else:
                data = self._get_disclosure_data(client)

        for grid_key, grid_val in data.items():
            if isinstance(grid_val, dict) and "Data" in grid_val:
                for item in grid_val["Data"]:
                    comp_nm = item.get("COMP_NM", "")
                    comp_abbr = item.get("COMP_ABBR_NM", "")
                    comp_cd = item.get("COMP_CD")
                    if comp_cd and (is_exact_corp_match(keyword, comp_nm) or (comp_abbr and is_exact_corp_match(keyword, comp_abbr))):
                        return RawCompany(
                            company_name=comp_nm or comp_abbr,
                            company_id=str(comp_cd),
                            matched_keyword=keyword,
                            search_priority=priority,
                            source_url=f"{self.base_url}/cms/frDisclosureCon/compView.do?COMP_CD={comp_cd}"
                        )
        return None

    def fetch_raw_ratings(
        self,
        company: RawCompany,
        client: Optional[httpx.Client] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> List[RawRatingRecord]:
        """
        [2단계: 기업 상세 수집]
        확정된 COMP_CD의 모든 공시 기록 수집 (data34: 기업신용, data35: 보험, data32: 회사채 등)
        """
        if data is None:
            if client is None:
                with httpx.Client(timeout=15.0, headers=self.headers, verify=True) as c:
                    data = self._get_disclosure_data(c)
            else:
                data = self._get_disclosure_data(client)

        records: List[RawRatingRecord] = []
        target_comp_cd = str(company.company_id)

        # 그리드별 기본 평가종류 매핑
        grid_type_map = {
            "data34": "기업신용평가",
            "data35": "보험금지급능력평가",
            "data32": "회사채(선순위)",
            "data33": "조건부자본증권/후순위",
            "data31": "기업어음"
        }

        for grid_key, grid_val in data.items():
            if not (isinstance(grid_val, dict) and "Data" in grid_val):
                continue

            default_type_name = grid_type_map.get(grid_key, "기타평가")

            for item in grid_val["Data"]:
                comp_cd = str(item.get("COMP_CD", ""))
                if comp_cd != target_comp_cd:
                    continue

                raw_grd = item.get("GRD") or item.get("CUR_GRD_NM_ORG") or item.get("GRD_NM")
                if not raw_grd or raw_grd == "취소":
                    continue

                # 날짜 파싱 (datetime.date 객체)
                dt_str = item.get("DSCLS_DT") or item.get("EVAL_DT") or item.get("DSCLS_DTTM")
                parsed_dt = None
                if dt_str:
                    m = re.search(r"(\d{4})[\.\-/](\d{2})[\.\-/](\d{2})", dt_str)
                    if m:
                        try:
                            parsed_dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                        except ValueError:
                            parsed_dt = None

                # 유효기간 파싱
                valid_str = item.get("GRD_VALD_DT")
                parsed_valid_to = None
                if valid_str:
                    m_v = re.search(r"(\d{4})[\.\-/](\d{2})[\.\-/](\d{2})", valid_str)
                    if m_v:
                        try:
                            parsed_valid_to = date(int(m_v.group(1)), int(m_v.group(2)), int(m_v.group(3)))
                        except ValueError:
                            parsed_valid_to = None

                item_nm = item.get("ITEM_NM") or item.get("BOND_NM") or item.get("VAL_PDC_NM") or ""
                bond_kind = item.get("BOND_KIND_KRNM") or item.get("BOND_KIND_ENNM") or ""
                svcty_nm = item.get("SVCTY_NM", "")
                type_raw = svcty_nm or default_type_name

                comp_nm_raw = item.get("COMP_NM", "")
                # 회사채 그리드에서 신종자본증권/후순위/지급보증 등 부가정보 확인
                extra = f"{item_nm} {bond_kind} {comp_nm_raw} {grid_key}".strip()

                outlook_val = item.get("CUR_GRD_DIRC_NM") or item.get("OUTLOOK") or item.get("GRD_DIRC_NM") or ""
                if not outlook_val:
                    m_o = re.search(r"(안정적|긍정적|부정적|유동적)", str(item))
                    if m_o:
                        outlook_val = m_o.group(1)

                records.append(RawRatingRecord(
                    company_id=target_comp_cd,
                    rating_type_raw=type_raw,
                    raw_rating=str(raw_grd).strip(),
                    rating_date=parsed_dt,
                    valid_to=parsed_valid_to,
                    source_url=f"{self.base_url}/cms/frDisclosureCon/compView.do?COMP_CD={target_comp_cd}",
                    extra_info=extra,
                    outlook=str(outlook_val).strip() if outlook_val else None
                ))

        return records

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
        source_url = f"{self.base_url}/cms/frCmnCon/index.do?MENU_ID=360"
        try:
            with httpx.Client(timeout=35.0, headers=self.headers, verify=True) as client:
                data = self._get_disclosure_data(client)

                if search_keywords:
                    candidates = search_keywords
                else:
                    candidates = generate_search_candidates(
                        institution_name=search_name,
                        original_name=original_name,
                        agency_code=self.agency_code,
                        search_name_1=search_name,
                        search_name_2=search_name_2
                    )

                # [핵심 요건]: 1순위에서 기업이 확인되면 2/3순위 탐색을 즉시 중단(STOP)!
                selected_company: Optional[RawCompany] = None
                for priority, cand in enumerate(candidates, start=1):
                    comp = self.search_company(cand, priority=priority, client=client, data=data)
                    if comp:
                        selected_company = comp
                        break  # 기업 식별 즉시 STOP!

                # 기업 미발견 시 NO_RATING 반환
                if not selected_company:
                    return StandardRating(
                        institution_id=institution_id,
                        agency_code=self.agency_code,
                        rating_type=rating_type,
                        status=CollectionStatus.NO_RATING.value,
                        source_url=source_url
                    )

                # [2단계]: 확정된 기업의 상세 레코드 수집
                records = self.fetch_raw_ratings(selected_company, client=client, data=data)

                # [3단계]: RatingFinalizer로 평가종류 매칭, 최신 평가일 선택, 상태값 확정
                return finalize_rating(
                    institution_id=institution_id,
                    agency_code=self.agency_code,
                    rating_type=rating_type,
                    raw_company=selected_company,
                    records=records,
                    target_rating_name=target_rating_name,
                    source_url=selected_company.source_url
                )

        except KRatingWAFBlockedError as exc:
            return StandardRating(
                institution_id=institution_id,
                agency_code=self.agency_code,
                rating_type=rating_type,
                status=CollectionStatus.AUTH_REQUIRED.value,
                error_message=str(exc),
                source_url=source_url
            )
        except httpx.RequestError as exc:
            return StandardRating(
                institution_id=institution_id,
                agency_code=self.agency_code,
                rating_type=rating_type,
                status=CollectionStatus.CRAWLING_ERROR.value,
                error_message=f"Network error: {str(exc)}",
                source_url=source_url
            )
        except Exception as exc:
            return StandardRating(
                institution_id=institution_id,
                agency_code=self.agency_code,
                rating_type=rating_type,
                status=CollectionStatus.PARSING_ERROR.value,
                error_message=f"Parsing error: {str(exc)}",
                source_url=source_url
            )

