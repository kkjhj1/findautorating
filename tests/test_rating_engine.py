import pytest
from app.schemas.rating import StandardRating
from app.models.enums import CollectionStatus
from app.rating.calculator import calculate_final_rating
from app.rating.validator import is_rating_valid, select_latest_rating_by_date
from app.rating.normalizer import normalize_rating

def test_tc_01_three_agencies_lowest_wins():
    """TC-01: KR = AA, KIS = AA-, NICE = AA -> Expected: 최종 = AA-"""
    kr = StandardRating(institution_id="INS001", agency_code="KR", rating_type="SENIOR_BOND", rating="AA", status="VALID")
    kis = StandardRating(institution_id="INS001", agency_code="KIS", rating_type="SENIOR_BOND", rating="AA-", status="VALID")
    nice = StandardRating(institution_id="INS001", agency_code="NICE", rating_type="SENIOR_BOND", rating="AA", status="VALID")

    result = calculate_final_rating("INS001", kr=kr, kis=kis, nice=nice)
    assert result.final_rating == "AA-"
    assert result.overall_status == CollectionStatus.SUCCESS.value

def test_tc_02_single_agency_recognized():
    """TC-02: KR = AA, KIS = NULL, NICE = NULL -> Expected: 최종 = AA"""
    kr = StandardRating(institution_id="INS001", agency_code="KR", rating_type="CORPORATE_CREDIT", rating="AA", status="VALID")
    kis = StandardRating(institution_id="INS001", agency_code="KIS", rating_type="CORPORATE_CREDIT", rating=None, status="NO_RATING")
    nice = StandardRating(institution_id="INS001", agency_code="NICE", rating_type="CORPORATE_CREDIT", rating=None, status="NO_RATING")

    result = calculate_final_rating("INS001", kr=kr, kis=kis, nice=nice)
    assert result.final_rating == "AA"
    assert result.overall_status == CollectionStatus.SUCCESS.value

def test_tc_03_all_no_rating():
    """TC-03: KR = NULL, KIS = NULL, NICE = NULL -> Expected: 최종 = NULL"""
    kr = StandardRating(institution_id="INS001", agency_code="KR", rating_type="CORPORATE_CREDIT", rating=None, status="NO_RATING")
    kis = StandardRating(institution_id="INS001", agency_code="KIS", rating_type="CORPORATE_CREDIT", rating=None, status="NO_RATING")
    nice = StandardRating(institution_id="INS001", agency_code="NICE", rating_type="CORPORATE_CREDIT", rating=None, status="NO_RATING")

    result = calculate_final_rating("INS001", kr=kr, kis=kis, nice=nice)
    assert result.final_rating is None
    assert result.overall_status == CollectionStatus.NO_RATING.value

def test_tc_04_expired_rating_excluded():
    """TC-04: AA, valid_to = 과거 -> Expected: 등급 제외"""
    rating = StandardRating(
        institution_id="INS001",
        agency_code="KR",
        rating_type="CORPORATE_CREDIT",
        rating="AA",
        valid_to="2026-06-30"
    )
    # 기준일 2026-10-01
    assert is_rating_valid(rating, execution_date="2026-10-01") is False

def test_tc_05_no_validity_date_is_valid():
    """TC-05: AA, valid_to = NULL -> Expected: 유효등급"""
    rating = StandardRating(
        institution_id="INS001",
        agency_code="KR",
        rating_type="CORPORATE_CREDIT",
        rating="AA",
        valid_to=None
    )
    assert is_rating_valid(rating, execution_date="2026-10-01") is True

def test_tc_06_same_type_latest_date_selected():
    """TC-06: AA- (2026-03-01) vs AA (2026-09-01) -> Expected: AA"""
    r1 = StandardRating(institution_id="INS001", agency_code="KR", rating_type="CORPORATE_CREDIT", rating="AA-", rating_date="2026-03-01")
    r2 = StandardRating(institution_id="INS001", agency_code="KR", rating_type="CORPORATE_CREDIT", rating="AA", rating_date="2026-09-01")

    selected = select_latest_rating_by_date([r1, r2])
    assert selected is not None
    assert selected.rating == "AA"
    assert selected.rating_date == "2026-09-01"

def test_tc_07_no_rating_date_still_recognized():
    """TC-07: rating = AA, rating_date = NULL -> Expected: AA, 확정일 = None"""
    kr = StandardRating(institution_id="INS001", agency_code="KR", rating_type="CORPORATE_CREDIT", rating="AA", rating_date=None, status="VALID")
    result = calculate_final_rating("INS001", kr=kr)
    assert result.final_rating == "AA"
    assert kr.rating_date is None

def test_tc_08_crawling_error_handling():
    """TC-08: NICE Crawling Error -> Expected: NICE=CRAWLING_ERROR, 전체상태 MANUAL_CHECK, 최종=AA"""
    kr = StandardRating(institution_id="INS001", agency_code="KR", rating_type="SENIOR_BOND", rating="AA", status="SUCCESS")
    kis = StandardRating(institution_id="INS001", agency_code="KIS", rating_type="SENIOR_BOND", rating=None, status="NO_RATING")
    nice = StandardRating(institution_id="INS001", agency_code="NICE", rating_type="SENIOR_BOND", rating=None, status="CRAWLING_ERROR", error_message="Timeout")

    result = calculate_final_rating("INS001", kr=kr, kis=kis, nice=nice)
    assert result.final_rating == "AA"
    assert result.overall_status == CollectionStatus.MANUAL_CHECK.value

def test_tc_09_rating_normalizer():
    """등급 문자열 정규화 테스트 (전망 분리)"""
    norm, outlook = normalize_rating("AA (안정적)")
    assert norm == "AA"
    assert outlook == "안정적"

    norm2, outlook2 = normalize_rating("AA-(하향검토)")
    assert norm2 == "AA-"
    assert outlook2 == "하향검토"
