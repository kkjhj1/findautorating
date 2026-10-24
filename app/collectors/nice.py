import re
import time
import random
from datetime import date, datetime
import httpx
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
from app.collectors.base import RatingAgencyAdapter
from app.schemas.rating import StandardRating, RawCompany, RawRatingRecord
from app.models.enums import AgencyCode, CollectionStatus, RatingType
import threading
from app.institution.search_candidates import generate_search_candidates, is_exact_corp_match
from app.rating.finalizer import finalize_rating

_NICE_SEMAPHORE = threading.Semaphore(2)


class NICEAdapter(RatingAgencyAdapter):
    """
    NICE신용평가 실서비스 연동 어댑터
    - [1단계: 기업 식별] companySearch.do: 1순위 -> 2순위 -> 3순위 탐색, 기업 식별 시 즉시 STOP
    - [2단계: 상세 수집] companyGradeInfo.do: Header 텍스트 동적 매칭으로 rows[2] 하드코딩 제거, 유효기간(valid_to) 파싱
    - [3단계: 최종 확정] RatingFinalizer: 대상 평가종류 필터링(증권사 채권 중 선순위 검증), 최신일 선택, 유효성 검증
    """
    def __init__(self):
        super().__init__(
            agency_code=AgencyCode.NICE.value,
            agency_name="NICE신용평가",
            base_url="https://www.nicerating.com"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.nicerating.com/main.do",
        }

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=5.0, headers=self.headers, verify=True) as client:
                res = client.get(f"{self.base_url}/main.do")
                return res.status_code == 200
        except Exception:
            return False

    def _extract_cmp_cd(self, a_tag) -> Optional[str]:
        """data-cmp-cd -> href 쿼리 파라미터 -> goView 정규식 순서로 안전하게 cmp_cd 추출"""
        if a_tag.get("data-cmp-cd"):
            return str(a_tag["data-cmp-cd"]).strip()

        href = a_tag.get("href", "")
        # href 내 cmpCd= 파라미터 확인
        m_param = re.search(r"cmpCd=(\d+)", href)
        if m_param:
            return m_param.group(1)

        # goView(...) JavaScript 인자 확인
        m_fn = re.search(r"goView\([^,]+,\s*['\"](\d+)['\"]", href)
        if m_fn:
            return m_fn.group(1)

        return None

    def search_company(
        self,
        keyword: str,
        priority: int = 1,
        client: Optional[httpx.Client] = None
    ) -> Optional[RawCompany]:
        """
        [1단계: 기업 검색]
        companySearch.do 호출 -> exact match 확인 -> cmp_cd 확정
        """
        curr_url = f"{self.base_url}/disclosure/companySearch.do?searchText={keyword}"
        should_close = False
        if client is None:
            client = httpx.Client(timeout=12.0, headers=self.headers, follow_redirects=True, verify=True)
            should_close = True

        for retry_idx in range(2):
            try:
                resp = client.get(curr_url)
                if resp.status_code != 200:
                    if retry_idx == 0:
                        time.sleep(0.2)
                        continue
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. 단일 기업으로 즉시 상세 페이지로 리디렉션된 경우 (URL에 cmpCd가 포함되거나 상세 화면일 때)
                if "companyGradeInfo" in str(resp.url):
                    m_url = re.search(r"cmpCd=(\d+)", str(resp.url))
                    if m_url:
                        cmp_code = m_url.group(1)
                        # 첫 번째 테이블(기업개요)의 Row 1 첫 번째 셀에서 정확한 사명 확인
                        comp_txt = ""
                        t0 = soup.find("table")
                        if t0:
                            rows = t0.find_all("tr")
                            if len(rows) >= 2:
                                tds = [td.get_text(strip=True) for td in rows[1].find_all(["th", "td"])]
                                if tds:
                                    comp_txt = tds[0]

                        if not comp_txt:
                            title_elem = soup.find(["h2", "h3", "h4", "strong"])
                            comp_txt = title_elem.get_text(strip=True) if title_elem else keyword

                        if is_exact_corp_match(keyword, comp_txt) or is_exact_corp_match(keyword, soup.text[:1000]):
                            return RawCompany(
                                company_name=comp_txt or keyword,
                                company_id=cmp_code,
                                matched_keyword=keyword,
                                search_priority=priority,
                                source_url=str(resp.url),
                                extra_data={"cached_html": resp.text}
                            )

                # 2. 검색 결과 목록 페이지인 경우
                for a_tag in soup.find_all("a", href=True):
                    txt = a_tag.get_text(strip=True)
                    cmp_cd = self._extract_cmp_cd(a_tag)
                    if cmp_cd and txt and is_exact_corp_match(keyword, txt):
                        return RawCompany(
                            company_name=txt,
                            company_id=cmp_cd,
                            matched_keyword=keyword,
                            search_priority=priority,
                            source_url=f"{self.base_url}/disclosure/companyGradeInfo.do?cmpCd={cmp_cd}"
                        )

                # 일시적 리다이렉트 지연 대비 1회 재시도
                if retry_idx == 0:
                    time.sleep(0.2)
                    continue

                return None
            except Exception:
                if retry_idx == 0:
                    time.sleep(0.2)
                    continue
                return None
            finally:
                if should_close:
                    client.close()

    def fetch_raw_ratings(
        self,
        company: RawCompany,
        client: Optional[httpx.Client] = None
    ) -> Optional[List[RawRatingRecord]]:
        """
        [2단계: 기업 상세 수집]
        companyGradeInfo.do?cmpCd={company.company_id} 조회
        - 요약 테이블: 2중 헤더(대분류/소분류) 건너뛰고 데이터 행(Row 2)에서 등급 및 확정일 추출
        - 공시 상세 테이블: 회사채(선순위), 기업신용평가 등 개별 공시 내역 추가 누적
        """
        detail_url = f"{self.base_url}/disclosure/companyGradeInfo.do?cmpCd={company.company_id}"
        should_close = False
        if client is None:
            client = httpx.Client(timeout=12.0, headers=self.headers, follow_redirects=True, verify=True)
            should_close = True

        html_text = ""
        try:
            # 1단계에서 단일 기업으로 즉시 상세 리다이렉트되어 HTML을 이미 수신한 경우 즉시 재활용 (세션 튕김 원천 방지)
            if company.extra_data and isinstance(company.extra_data, dict) and company.extra_data.get("cached_html"):
                html_text = company.extra_data["cached_html"]
            else:
                for retry_idx in range(2):
                    try:
                        r = client.get(detail_url)
                        if r.status_code == 200 and "companyGradeInfo" in str(r.url):
                            html_text = r.text
                            break
                        if retry_idx == 0:
                            time.sleep(0.3)
                    except Exception:
                        if retry_idx == 0:
                            time.sleep(0.3)

            if not html_text:
                return None

            records: List[RawRatingRecord] = []
            soup = BeautifulSoup(html_text, "html.parser")

            # 1. 유효등급 요약 테이블 파싱
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue

                header_row = rows[0]
                header_cols = [re.sub(r"\s+", "", th.get_text(strip=True)) for th in header_row.find_all(["th", "td"])]
                known_headers = ["채권", "기업어음", "전자단기사채", "기업신용등급", "보험지급능력"]
                matched_header_keys = [h for h in known_headers if h in header_cols]

                if matched_header_keys:
                    for r_idx in range(1, len(rows)):
                        row_cells = rows[r_idx].find_all(["th", "td"])
                        cell_texts = [c.get_text(strip=True) for c in row_cells]
                        # 서브헤더 행('등급', '평가확정일')은 건너뜀
                        if not cell_texts or "평가확정일" in cell_texts or "등급" in cell_texts:
                            continue

                        is_double_cells = len(row_cells) >= len(header_cols) * 2

                        for h_idx, h_name in enumerate(header_cols):
                            if h_name not in known_headers:
                                continue

                            raw_rating_val = ""
                            raw_date_val = ""

                            if is_double_cells:
                                g_i = h_idx * 2
                                d_i = g_i + 1
                                if d_i < len(cell_texts):
                                    raw_rating_val = cell_texts[g_i]
                                    raw_date_val = cell_texts[d_i]
                            elif h_idx < len(cell_texts):
                                cell_val = cell_texts[h_idx]
                                raw_rating_val = cell_val
                                raw_date_val = cell_val

                            # 날짜 파싱
                            parsed_dt = None
                            m_d = re.search(r"(\d{4})[\.\-/](\d{2})[\.\-/](\d{2})", raw_date_val)
                            if m_d:
                                try:
                                    parsed_dt = date(int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3)))
                                except ValueError:
                                    parsed_dt = None

                            norm_r, _ = self.normalize(raw_rating_val)
                            if norm_r:
                                outlook_val = None
                                if "/" in raw_rating_val:
                                    parts = raw_rating_val.split("/")
                                    if len(parts) >= 2:
                                        code = parts[1].strip().upper()
                                        if code.startswith("S"):
                                            outlook_val = "안정적"
                                        elif code.startswith("N"):
                                            outlook_val = "부정적"
                                        elif code.startswith("P"):
                                            outlook_val = "긍정적"

                                records.append(RawRatingRecord(
                                    company_id=str(company.company_id),
                                    rating_type_raw=h_name,
                                    raw_rating=norm_r,
                                    rating_date=parsed_dt,
                                    source_url=detail_url,
                                    extra_info=h_name,
                                    outlook=outlook_val
                                ))

            # 2. 공시 상세 이력 테이블 파싱 (보완 누적)
            today_date = date.today()
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for r in rows:
                    tds = [td.get_text(strip=True) for td in r.find_all(["th", "td"])]
                    if len(tds) >= 4:
                        first_col = tds[0]
                        row_full_text = " ".join(tds)
                        if any(k in row_full_text for k in ["회사채", "선순위", "기업신용", "보험지급", "사채"]):
                            for text_item in tds[1:]:
                                norm_g, _ = self.normalize(text_item)
                                if norm_g:
                                    # 날짜 후보군 추출 (평가일, 확정일, 만기일 등)
                                    dates_found = []
                                    for dt_candidate in tds:
                                        m = re.search(r"(\d{4})[\.\-/](\d{2})[\.\-/](\d{2})", dt_candidate)
                                        if m:
                                            try:
                                                dates_found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                                            except ValueError:
                                                pass

                                    # 발행일/만기일이 있고 만기일이 이미 지난 과거 채권은 배제
                                    if len(dates_found) >= 2 and dates_found[-1] < today_date:
                                        continue

                                    d_obj = dates_found[0] if dates_found else None
                                    valid_to_obj = dates_found[-1] if len(dates_found) >= 2 else None

                                    outlook_val = None
                                    m_o = re.search(r"(안정적|긍정적|부정적|유동적)", row_full_text)
                                    if m_o:
                                        outlook_val = m_o.group(1)

                                    records.append(RawRatingRecord(
                                        company_id=str(company.company_id),
                                        rating_type_raw=first_col,
                                        raw_rating=norm_g,
                                        rating_date=d_obj,
                                        valid_to=valid_to_obj,
                                        source_url=detail_url,
                                        extra_info=row_full_text,
                                        outlook=outlook_val
                                    ))

            return records
        finally:
            if should_close:
                client.close()

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
        source_url = f"{self.base_url}/disclosure/companySearch.do?searchText={search_name}"
        last_error = None
        for attempt in range(2):
            try:
                with _NICE_SEMAPHORE:
                    with httpx.Client(
                        timeout=18.0,
                        headers=self.headers,
                        follow_redirects=True,
                        verify=True,
                        limits=httpx.Limits(max_keepalive_connections=4, max_connections=6)
                    ) as client:
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

                        selected_company: Optional[RawCompany] = None
                        for priority, kw in enumerate(candidates, start=1):
                            time.sleep(random.uniform(0.05, 0.15))
                            comp = self.search_company(kw, priority=priority, client=client)
                            if comp:
                                selected_company = comp
                                break

                        if not selected_company:
                            return StandardRating(
                                institution_id=institution_id,
                                agency_code=self.agency_code,
                                rating_type=rating_type,
                                status=CollectionStatus.NO_RATING.value,
                                source_url=source_url
                            )

                        records = self.fetch_raw_ratings(selected_company, client=client)

                        return finalize_rating(
                            institution_id=institution_id,
                            agency_code=self.agency_code,
                            rating_type=rating_type,
                            raw_company=selected_company,
                            records=records,
                            target_rating_name=target_rating_name,
                            source_url=selected_company.source_url
                        )

            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.0)
                    continue
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

    def _get_target_keyword(self, rating_type: str) -> str:
        if rating_type == RatingType.SENIOR_BOND.value:
            return "채권"
        elif rating_type == RatingType.INSURANCE_FINANCIAL_STRENGTH.value:
            return "보험지급능력"
        return "기업신용등급"

