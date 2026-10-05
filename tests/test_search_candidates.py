import pytest
from app.institution.search_candidates import generate_search_candidates, clean_corporate_affix

def test_clean_legal_entity_names():
    assert clean_corporate_affix("(주)OK저축은행") == "OK저축은행"
    assert clean_corporate_affix("주식회사 국민은행") == "국민은행"
    assert clean_corporate_affix("㈜DB손해보험") == "DB손해보험"
    assert clean_corporate_affix("신한카드(주)") == "신한카드"
    assert clean_corporate_affix("유한회사 한국지사") == "한국지사"

def test_generate_search_candidates_priority_order():
    # 1순위: C열(우선검색1), 2순위: D열(차선검색2)
    cands = generate_search_candidates(
        institution_name="KB국민은행",
        original_name="KB국민은행",
        agency_code="NICE",
        search_name_1="국민은행",
        search_name_2="KB국민은행"
    )
    assert cands[0] == "국민은행"
    assert cands[1] == "KB국민은행"

def test_generate_search_candidates_sc_bank_alias():
    # 공식 법인명 별칭(SC제일은행 <-> 한국스탠다드차타드은행) 자동 포함 확인
    cands = generate_search_candidates(
        institution_name="SC제일은행",
        original_name="SC제일은행",
        agency_code="KIS",
        search_name_1="SC제일은행"
    )
    assert "SC제일은행" in cands
    assert "한국스탠다드차타드은행" in cands

def test_generate_search_candidates_fallback_to_name():
    # C열, D열이 모두 비어있을 시 기관명 fallback 확인
    cands = generate_search_candidates(
        institution_name="우리은행",
        original_name="우리은행",
        agency_code="KR"
    )
    assert cands == ["우리은행"]

def test_exact_corp_matching():
    from app.institution.search_candidates import is_exact_corp_match
    assert is_exact_corp_match("케이비라이프생명", "케이비라이프생명보험") is True
    assert is_exact_corp_match("국민은행", "국민은행") is True
    assert is_exact_corp_match("SC제일은행", "한국스탠다드차타드은행") is True
    assert is_exact_corp_match("신한은행", "KB국민은행") is False
