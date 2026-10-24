import re
import time
import threading
from datetime import date, datetime
import httpx
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
from app.collectors.base import RatingAgencyAdapter
from app.schemas.rating import StandardRating, RawCompany, RawRatingRecord
from app.models.enums import AgencyCode, CollectionStatus, RatingType
from app.institution.search_candidates import generate_search_candidates, is_exact_corp_match
from app.rating.finalizer import finalize_rating

_KIS_SEMAPHORE = threading.Semaphore(3)
_KIS_TIMEOUT = 35.0

_KIS_CLIENT: Optional[httpx.Client] = None
_KIS_CLIENT_LOCK = threading.Lock()

def _get_kis_client(headers: dict) -> httpx.Client:
    global _KIS_CLIENT
    if _KIS_CLIENT is None or _KIS_CLIENT.is_closed:
        with _KIS_CLIENT_LOCK:
            if _KIS_CLIENT is None or _KIS_CLIENT.is_closed:
                _KIS_CLIENT = httpx.Client(
                    timeout=_KIS_TIMEOUT,
                    headers=headers,
                    verify=False,
                    limits=httpx.Limits(max_keepalive_connections=8, max_connections=12)
                )
    return _KIS_CLIENT

class KISAuthRequiredError(Exception):
    """KIS KCW 로그인/가입 인증 요구 에러"""
    pass


class KISAdapter(RatingAgencyAdapter):
    """
    한국신용평가 (KIS Rating) 실서비스 연동 어댑터
    - [1단계: 기업 식별] corp_search.do: 1순위 -> 2순위 -> 3순위 탐색, 기업 식별 시 즉시 STOP
    - [2단계: 상세 수집] corp_overview.do: 기업의 모든 평가종류 및 평가일자 수집
    - [3단계: 최종 확정] RatingFinalizer: 대상 평가종류 필터링, 최신일 선택, 유효성 검증
    """
    def __init__(self):
        super().__init__(
            agency_code=AgencyCode.KIS.value,
            agency_name="한국신용평가",
            base_url="https://www.kisrating.com"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.kisrating.com/",
        }

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=_KIS_TIMEOUT, headers=self.headers, verify=False) as client:
                res = client.get(self.base_url)
                return res.status_code == 200
        except Exception:
            return False

    def search_company(
        self,
        keyword: str,
        priority: int = 1,
        client: Optional[httpx.Client] = None
    ) -> Optional[RawCompany]:
        """
        [1단계: 기업 검색]
        corp_search.do 호출 후 exact corp match 확인 -> kiscd 및 기업 확정
        로그인/KCW 차단 페이지 감지 시 KISAuthRequiredError 발생
        """
        source_url = f"{self.base_url}/ratingsSearch/corp_search.do"
        payload = {
            "mainSearchType": "1",
            "keyword": keyword,
            "searchKeyword": keyword,
            "searchYn": "M",
            "searchType": "1"
        }

        should_close = False
        if client is None:
            client = httpx.Client(timeout=_KIS_TIMEOUT, headers=self.headers, verify=False)
            should_close = True

        try:
            # 일시적 타임아웃에 대비해 최대 2회 시도
            resp = None
            for attempt in range(2):
                try:
                    resp = client.post(source_url, data=payload, timeout=_KIS_TIMEOUT)
                    if resp.status_code == 200:
                        break
                except httpx.TimeoutException:
                    if attempt == 1:
                        raise
                    time.sleep(1.0)

            if not resp or resp.status_code != 200:
                return None

            html_text = resp.text
            # KCW 로그인 / 권한 차단 감지 (정상 검색 결과인 fnCorpDetail이 없는 경우에만 판정)
            if "fnCorpDetail" not in html_text:
                if "로그인이 필요한" in html_text or ("KCW" in html_text and "회원가입" in html_text):
                    raise KISAuthRequiredError("KIS 사이트가 로그인/KCW 인증을 요구합니다.")

            soup = BeautifulSoup(html_text, "html.parser")
            candidates = []
            for tr in soup.find_all("tr"):
                a_tag = tr.find("a", href=True)
                if not a_tag:
                    continue
                href = a_tag["href"]
                txt = a_tag.get_text(strip=True)
                m = re.search(r"fnCorpDetail\([^,]+,\s*['\"]([A-Za-z0-9_]+)['\"]", href)
                if m and txt and is_exact_corp_match(keyword, txt):
                    code = m.group(1)
                    # 해당 tr 내에 등급(AA, A, BBB 등)이나 텍스트가 채워져 있는지 확인
                    tds = tr.find_all(["td", "th"])
                    other_text = " ".join(td.get_text(strip=True) for td in tds[1:]) if len(tds) > 1 else ""
                    has_ratings = bool(re.search(r"[A-D][0-9\+\-]*", other_text))
                    candidates.append((has_ratings, RawCompany(
                        company_name=txt,
                        company_id=code,
                        matched_keyword=keyword,
                        search_priority=priority,
                        source_url=f"{self.base_url}/ratingsSearch/corp_overview.do?kiscd={code}"
                    )))

            if candidates:
                # 등급이 존재하는 행(has_ratings=True)을 최우선으로 정렬
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                txt = a_tag.get_text(strip=True)
                m = re.search(r"fnCorpDetail\([^,]+,\s*['\"]([A-Za-z0-9_]+)['\"]", href)
                if m and txt and is_exact_corp_match(keyword, txt):
                    code = m.group(1)
                    return RawCompany(
                        company_name=txt,
                        company_id=code,
                        matched_keyword=keyword,
                        search_priority=priority,
                        source_url=f"{self.base_url}/ratingsSearch/corp_overview.do?kiscd={code}"
                    )
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
        corp_overview.do?kiscd={company.company_id} 상세 카드를 순회하여
        동일 평가종류를 덮어쓰지 않고 모든 레코드 및 전망(outlook) 추출
        """
        overview_url = f"{self.base_url}/ratingsSearch/corp_overview.do?kiscd={company.company_id}"
        should_close = False
        if client is None:
            client = httpx.Client(timeout=_KIS_TIMEOUT, headers=self.headers, verify=False)
            should_close = True

        records: List[RawRatingRecord] = []
        try:
            resp = client.get(overview_url, timeout=_KIS_TIMEOUT)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            for dl in soup.find_all("dl"):
                dt = dl.find("dt")
                if not dt:
                    continue
                p_name = re.sub(r"\s+", " ", dt.get_text(strip=True))
                strong = dl.find("strong")
                r_val = strong.get_text(strip=True) if strong else ""

                outlook = None
                m_out = re.search(r"(안정적|긍정적|부정적|유동적|안정|긍정|부정)", dl.get_text())
                if m_out:
                    outlook = m_out.group(1)

                parsed_date = None
                for dd in dl.find_all("dd"):
                    dd_txt = dd.get_text(strip=True)
                    if "평가일" in dd_txt:
                        m_d = re.search(r"(\d{4})[\.\-/](\d{2})[\.\-/](\d{2})", dd_txt)
                        if m_d:
                            try:
                                parsed_date = date(int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3)))
                            except ValueError:
                                parsed_date = None

                if r_val:
                    records.append(RawRatingRecord(
                        company_id=company.company_id,
                        rating_type_raw=p_name,
                        raw_rating=r_val,
                        rating_date=parsed_date,
                        source_url=overview_url,
                        outlook=outlook
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
        source_url = f"{self.base_url}/ratingsSearch/corp_search.do"
        try:
            with _KIS_SEMAPHORE:
                client = _get_kis_client(self.headers)
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

                # [핵심 요건]: 1순위에서 기업이 발견되면 하위순위는 절대 검색하지 않음!
                selected_company: Optional[RawCompany] = None
                for priority, kw in enumerate(candidates, start=1):
                    comp = self.search_company(kw, priority=priority, client=client)
                    if comp:
                        selected_company = comp
                        break  # 대상 기업 식별 즉시 STOP!

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
                records = self.fetch_raw_ratings(selected_company, client=client)

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

        except KISAuthRequiredError as exc:
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
