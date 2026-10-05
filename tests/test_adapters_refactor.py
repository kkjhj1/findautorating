import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.models.enums import CollectionStatus, RatingType, AgencyCode
from app.schemas.rating import RawCompany, RawRatingRecord, StandardRating
from app.rating.finalizer import finalize_rating, is_rating_type_match
from app.collectors.kis import KISAdapter, KISAuthRequiredError
from app.collectors.krating import KRatingAdapter
from app.collectors.nice import NICEAdapter


# ============================================================
# [TC-01 ~ TC-10] 신용평가사 Adapter 전산요건 검증 테스트 스위트
# ============================================================

def test_tc01_priority_1_success():
    """TC-01: 1순위 기업 존재 & 1순위 등급 존재 -> 1순위 성공"""
    company = RawCompany(
        company_name="국민은행",
        company_id="860239",
        matched_keyword="국민은행",
        search_priority=1,
        source_url="https://test.com/overview"
    )
    records = [
        RawRatingRecord(
            company_id="860239",
            rating_type_raw="Issuer Rating",
            raw_rating="AAA",
            rating_date=date(2026, 3, 31)
        )
    ]
    res = finalize_rating(
        institution_id="INST_01",
        agency_code="KIS",
        rating_type=RatingType.CORPORATE_CREDIT.value,
        raw_company=company,
        records=records,
        target_rating_name="Issuer Rating"
    )

    assert res.status == CollectionStatus.SUCCESS.value
    assert res.rating == "AAA"
    assert res.rating_date == "2026-03-31"
    assert res.search_priority == 1


def test_tc02_priority_1_found_but_rating_missing_stop_search():
    """
    TC-02 [최우선 Acceptance Criteria]:
    1순위 기업 존재 확인 시 대상 등급이 없더라도 2순위 검색으로 넘어가지 않고 STOP!
    결과: NO_RATING (기업 확정 완료 상태)
    """
    adapter = KISAdapter()

    # 모의: 1순위 검색어 "아이엠뱅크"에서 기업 발견, 하지만 해당 기업에는 대상 등급이 없음
    # 2순위 검색어 "iM뱅크"는 시도조차 되지 않아야 함!
    search_keywords = ["아이엠뱅크", "iM뱅크"]

    with patch.object(adapter, "search_company") as mock_search, \
         patch.object(adapter, "fetch_raw_ratings") as mock_fetch:

        def fake_search(kw, priority, client=None):
            if kw == "아이엠뱅크":
                return RawCompany(
                    company_name="iM뱅크",
                    company_id="111222",
                    matched_keyword=kw,
                    search_priority=priority
                )
            return None

        mock_search.side_effect = fake_search
        mock_fetch.return_value = []  # 등급 없음

        res = adapter.get_ratings(
            institution_id="INST_IM",
            search_name="아이엠뱅크",
            rating_type=RatingType.CORPORATE_CREDIT.value,
            target_rating_name="Issuer Rating",
            search_keywords=search_keywords
        )

        # 1. 1순위 키워드로 기업이 발견되었으므로 search_company는 정확히 1번만 호출되어야 함 (2순위 탐색 차단)
        assert mock_search.call_count == 1
        assert mock_search.call_args[0][0] == "아이엠뱅크"

        # 2. 기업은 발견되었으나 등급이 없으므로 NO_RATING 반환
        assert res.status == CollectionStatus.NO_RATING.value
        assert res.search_priority == 1
        assert res.company_id == "111222"


def test_tc03_priority_1_not_found_priority_2_found():
    """TC-03: 1순위 기업 없음 & 2순위 기업 존재 -> 2순위 채택"""
    adapter = KISAdapter()
    search_keywords = ["부재기업", "국민은행", "KB"]

    with patch.object(adapter, "search_company") as mock_search, \
         patch.object(adapter, "fetch_raw_ratings") as mock_fetch:

        def fake_search(kw, priority, client=None):
            if kw == "부재기업":
                return None
            if kw == "국민은행":
                return RawCompany(
                    company_name="국민은행",
                    company_id="860239",
                    matched_keyword=kw,
                    search_priority=priority
                )
            return None

        mock_search.side_effect = fake_search
        mock_fetch.return_value = [
            RawRatingRecord(
                company_id="860239",
                rating_type_raw="Issuer Rating",
                raw_rating="AAA",
                rating_date=date(2026, 3, 31)
            )
        ]

        res = adapter.get_ratings(
            institution_id="INST_KB",
            search_name="부재기업",
            rating_type=RatingType.CORPORATE_CREDIT.value,
            target_rating_name="Issuer Rating",
            search_keywords=search_keywords
        )

        # 1순위(실패) -> 2순위(성공) 까지만 호출되고 3순위("KB")는 탐색하지 않음
        assert mock_search.call_count == 2
        assert res.status == CollectionStatus.SUCCESS.value
        assert res.search_priority == 2
        assert res.rating == "AAA"


def test_tc04_priority_1_2_not_found_priority_3_found():
    """TC-04: 1순위 없음 & 2순위 없음 & 3순위 존재 -> 3순위 채택"""
    adapter = KRatingAdapter()
    search_keywords = ["없음1", "없음2", "신한은행"]

    with patch.object(adapter, "search_company") as mock_search, \
         patch.object(adapter, "fetch_raw_ratings") as mock_fetch, \
         patch.object(adapter, "_get_disclosure_data") as mock_data:

        mock_data.return_value = {}

        def fake_search(kw, priority, client=None, data=None):
            if kw == "신한은행":
                return RawCompany(
                    company_name="신한은행",
                    company_id="001122",
                    matched_keyword=kw,
                    search_priority=priority
                )
            return None

        mock_search.side_effect = fake_search
        mock_fetch.return_value = [
            RawRatingRecord(
                company_id="001122",
                rating_type_raw="기업신용평가",
                raw_rating="AAA",
                rating_date=date(2026, 4, 15)
            )
        ]

        res = adapter.get_ratings(
            institution_id="INST_SH",
            search_name="없음1",
            rating_type=RatingType.CORPORATE_CREDIT.value,
            target_rating_name="기업신용평가",
            search_keywords=search_keywords
        )

        assert mock_search.call_count == 3
        assert res.status == CollectionStatus.SUCCESS.value
        assert res.search_priority == 3
        assert res.rating == "AAA"


def test_tc05_different_rating_type_rejected():
    """
    TC-05: 기업 존재 & 다른 평가종류만 존재
    예: 은행에 Issuer Rating은 없고 회사채 AAA만 있을 때, 회사채를 대체값으로 가져오면 안 됨 (NO_RATING)
    """
    company = RawCompany(
        company_name="우리은행",
        company_id="333444",
        matched_keyword="우리은행",
        search_priority=1
    )
    records = [
        RawRatingRecord(
            company_id="333444",
            rating_type_raw="회사채(선순위)",  # 회사채 등급만 있음
            raw_rating="AAA",
            rating_date=date(2026, 5, 20)
        )
    ]
    res = finalize_rating(
        institution_id="INST_WR",
        agency_code="KIS",
        rating_type=RatingType.CORPORATE_CREDIT.value,  # 요청은 은행 기업신용평가(Issuer Rating)
        raw_company=company,
        records=records,
        target_rating_name="Issuer Rating"
    )

    # 회사채 등급을 기업신용평가로 대체하지 않고 NO_RATING 반환해야 함
    assert res.status == CollectionStatus.NO_RATING.value
    assert res.rating is None


def test_tc06_senior_bond_strict_selection():
    """TC-06: 회사채(후순위)와 회사채(선순위) 공존 시 선순위만 선택"""
    company = RawCompany(
        company_name="BNK투자증권",
        company_id="555666",
        matched_keyword="BNK투자증권",
        search_priority=1
    )
    records = [
        RawRatingRecord(
            company_id="555666",
            rating_type_raw="회사채(후순위)",
            raw_rating="A+",
            rating_date=date(2026, 6, 1),
            extra_info="후순위"
        ),
        RawRatingRecord(
            company_id="555666",
            rating_type_raw="회사채(선순위)",
            raw_rating="AA-",
            rating_date=date(2026, 6, 1),
            extra_info="선순위"
        )
    ]
    res = finalize_rating(
        institution_id="INST_BNK",
        agency_code="KR",
        rating_type=RatingType.SENIOR_BOND.value,
        raw_company=company,
        records=records,
        target_rating_name="회사채(선순위)"
    )

    assert res.status == CollectionStatus.SUCCESS.value
    assert res.rating == "AA-"  # 선순위인 AA- 채택 (후순위 A+ 배제)


def test_tc07_latest_date_selection_by_date_object():
    """
    TC-07: 동일 평가종류 복수 기록 존재 시 문자열 정렬이 아닌 Date 객체 기준으로 최신일 선택
    2025-06-01 AA vs 2026-06-01 AA- -> 2026-06-01 AA- 선택
    """
    company = RawCompany(
        company_name="한화생명",
        company_id="777888",
        matched_keyword="한화생명",
        search_priority=1
    )
    records = [
        RawRatingRecord(
            company_id="777888",
            rating_type_raw="보험금지급능력평가",
            raw_rating="AA",
            rating_date=date(2025, 6, 1)
        ),
        RawRatingRecord(
            company_id="777888",
            rating_type_raw="보험금지급능력평가",
            raw_rating="AA-",
            rating_date=date(2026, 6, 1)
        )
    ]
    res = finalize_rating(
        institution_id="INST_HW",
        agency_code="KR",
        rating_type=RatingType.INSURANCE_FINANCIAL_STRENGTH.value,
        raw_company=company,
        records=records,
        target_rating_name="보험금지급능력평가"
    )

    assert res.status == CollectionStatus.SUCCESS.value
    assert res.rating == "AA-"
    assert res.rating_date == "2026-06-01"


def test_tc08_rating_without_date_marked_as_manual_review():
    """TC-08: 등급은 존재하나 확정일자가 없는 경우 -> 등급 인정하되 MANUAL_REVIEW 처리"""
    company = RawCompany(
        company_name="미확정은행",
        company_id="999000",
        matched_keyword="미확정은행",
        search_priority=1
    )
    records = [
        RawRatingRecord(
            company_id="999000",
            rating_type_raw="기업신용평가",
            raw_rating="A",
            rating_date=None  # 일자 없음
        )
    ]
    res = finalize_rating(
        institution_id="INST_NO_DATE",
        agency_code="KIS",
        rating_type=RatingType.CORPORATE_CREDIT.value,
        raw_company=company,
        records=records,
        target_rating_name="기업신용평가"
    )

    assert res.status == CollectionStatus.MANUAL_REVIEW.value
    assert res.rating == "A"
    assert res.rating_date is None


def test_tc09_expired_rating():
    """TC-09: 등급 존재하나 유효기간(valid_to) 만료 -> EXPIRED 상태 판정"""
    past_date = date.today() - timedelta(days=30)
    company = RawCompany(
        company_name="만료증권",
        company_id="444555",
        matched_keyword="만료증권",
        search_priority=1
    )
    records = [
        RawRatingRecord(
            company_id="444555",
            rating_type_raw="회사채(선순위)",
            raw_rating="BBB+",
            rating_date=past_date - timedelta(days=365),
            valid_to=past_date  # 30일 전 만료
        )
    ]
    res = finalize_rating(
        institution_id="INST_EXP",
        agency_code="NICE",
        rating_type=RatingType.SENIOR_BOND.value,
        raw_company=company,
        records=records,
        target_rating_name="회사채"
    )

    assert res.status == CollectionStatus.EXPIRED.value
    assert res.rating == "BBB+"
    assert res.valid_to == past_date.strftime("%Y-%m-%d")


def test_tc10_kis_auth_required_detection():
    """TC-10: KIS 사이트에서 로그인/KCW 인증을 요구할 때 AUTH_REQUIRED 감지"""
    adapter = KISAdapter()
    with patch.object(adapter, "search_company") as mock_search:
        mock_search.side_effect = KISAuthRequiredError("KIS 사이트가 로그인/KCW 인증을 요구합니다.")

        res = adapter.get_ratings(
            institution_id="INST_KIS_BLOCK",
            search_name="국민은행",
            rating_type=RatingType.CORPORATE_CREDIT.value,
            target_rating_name="Issuer Rating"
        )

        assert res.status == CollectionStatus.AUTH_REQUIRED.value
        assert "로그인/KCW" in (res.error_message or "")
