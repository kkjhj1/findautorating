import re
from typing import Tuple
from app.models.enums import IndustryType, RatingType

# 한글 음차 -> 영문 약칭 변환 맵
PHONETIC_REPLACEMENTS = [
    (r"에스비아이", "SBI"),
    (r"엔에이치", "NH"),
    (r"케이비", "KB"),
    (r"디비", "DB"),
    (r"비엔케이", "BNK"),
    (r"아이비케이", "IBK"),
    (r"아이엠", "iM"),
]

# 축약어 정규화 맵
ABBREVIATION_REPLACEMENTS = [
    (r"손보$", "손해보험"),
    (r"^국민은행$", "KB국민은행"),
    (r"^농협은행$", "NH농협은행"),
    (r"^메리츠화재$", "메리츠화재해상보험"),
    (r"^삼성화재$", "삼성화재해상보험"),
    (r"^한국스탠다드차타드은행$", "SC제일은행"),
]

def clean_corporate_entity(name: str) -> str:
    """법인 형태 표기((주), ㈜, 주식회사 등) 및 특수문자 제거"""
    cleaned = re.sub(r"[\(（]주[\)）]", "", name)
    cleaned = re.sub(r"㈜", "", cleaned)
    cleaned = re.sub(r"주식회사", "", cleaned)
    cleaned = re.sub(r"[\(（]유[\)）]", "", cleaned)
    cleaned = re.sub(r"유한회사", "", cleaned)
    return cleaned.strip()

def normalize_institution_name(raw_name: str) -> str:
    """기관명을 표준화된 검색/표시 이름으로 변환"""
    name = clean_corporate_entity(raw_name)

    # 1. 음차 변환
    for pattern, repl in PHONETIC_REPLACEMENTS:
        name = re.sub(pattern, repl, name, flags=re.IGNORECASE)

    # 2. 축약어 변환
    for pattern, repl in ABBREVIATION_REPLACEMENTS:
        name = re.sub(pattern, repl, name)

    # 3. 연속 공백 제거
    name = re.sub(r"\s+", " ", name).strip()
    return name

def determine_industry_and_rating_type(raw_industry: str, raw_name: str) -> Tuple[str, str]:
    """엑셀 원본 업권명 및 기관명을 기반으로 PRD 표준 IndustryType 및 RatingType 결정"""
    clean_ind = raw_industry.strip() if raw_industry else ""

    if "은행" in clean_ind and "저축" not in clean_ind and "저축" not in raw_name:
        return IndustryType.BANK.value, RatingType.CORPORATE_CREDIT.value
    elif "저축" in clean_ind or "저축" in raw_name:
        return IndustryType.SAVINGS_BANK.value, RatingType.CORPORATE_CREDIT.value
    elif "증권" in clean_ind or "투자" in raw_name or "증권" in raw_name:
        return IndustryType.SECURITIES.value, RatingType.SENIOR_BOND.value
    elif "보험" in clean_ind:
        # 생명보험 vs 손해보험 분기
        if "생명" in raw_name or "연금" in raw_name or "라이프" in raw_name:
            return IndustryType.LIFE_INSURANCE.value, RatingType.INSURANCE_FINANCIAL_STRENGTH.value
        else:
            return IndustryType.NON_LIFE_INSURANCE.value, RatingType.INSURANCE_FINANCIAL_STRENGTH.value
    elif clean_ind == "-" or "우체국" in raw_name:
        return IndustryType.POST.value, ""
    
    # 기본 폴백
    return IndustryType.BANK.value, RatingType.CORPORATE_CREDIT.value

AGENCY_SEARCH_KEYWORD_MAP = {
    "KB국민은행": {"KR": "국민은행", "KIS": "국민은행", "NICE": "국민은행"},
    "NH농협은행": {"KR": "농협은행", "KIS": "농협은행", "NICE": "농협은행"},
    "SC제일은행": {"KR": "한국스탠다드차타드은행", "KIS": "한국스탠다드차타드은행", "NICE": "한국스탠다드차타드은행"},
    "IBK기업은행": {"KR": "기업은행", "KIS": "중소기업은행", "NICE": "중소기업은행"},
    "메리츠화재해상보험": {"KR": "메리츠화재", "KIS": "메리츠화재", "NICE": "메리츠화재"},
    "삼성화재해상보험": {"KR": "삼성화재", "KIS": "삼성화재", "NICE": "삼성화재"},
    "현대해상화재보험": {"KR": "현대해상", "KIS": "현대해상", "NICE": "현대해상"},
    "KB라이프생명": {"KR": "KB라이프생명", "KIS": "KB라이프", "NICE": "KB라이프"},
    "iM뱅크": {"KR": "대구은행", "KIS": "대구은행", "NICE": "대구은행"},
    "BNK부산은행": {"KR": "부산은행", "KIS": "부산은행", "NICE": "부산은행"},
    "BNK경남은행": {"KR": "경남은행", "KIS": "경남은행", "NICE": "경남은행"},
    "JB전북은행": {"KR": "전북은행", "KIS": "전북은행", "NICE": "전북은행"},
}

def get_agency_search_keyword(normalized_name: str, agency_code: str) -> str:
    """각 신용평가사 검색 엔진에 최적화된 검색 키워드 반환"""
    if normalized_name in AGENCY_SEARCH_KEYWORD_MAP:
        return AGENCY_SEARCH_KEYWORD_MAP[normalized_name].get(agency_code, normalized_name)
    return normalized_name
