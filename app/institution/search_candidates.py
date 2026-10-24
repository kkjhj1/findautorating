import re
from typing import List

KNOWN_CORP_ALIASES = {
    "SC제일은행": ["한국스탠다드차타드은행", "스탠다드차타드은행", "스탠다드차타드"],
    "제이티친애저축은행": ["JT친애저축은행", "친애저축은행"],
    "NH농협은행": ["농협은행"],
    "중소기업은행": ["기업은행", "IBK기업은행"],
    "한국산업은행": ["산업은행", "KDB산업은행"],
    "수협은행": ["Sh수협은행"],
    "iM증권": ["하이투자증권", "아이엠증권"],
    "iM뱅크": ["대구은행", "아이엠뱅크"],
    "우리투자증권": ["한국포스증권", "포스증권"],
    "메리츠화재해상보험": ["메리츠화재"],
    "삼성화재해상보험": ["삼성화재"],
    "현대해상화재보험": ["현대해상"],
    "KB손해보험": ["케이비손해보험", "LIG손해보험"],
    "DB손해보험": ["동부화재", "동부화재해상보험"],
    "DB생명보험": ["동부생명", "동부생명보험"],
    "KB라이프생명": ["KB라이프", "푸르덴셜생명"],
    "신한라이프생명보험": ["신한라이프", "신한생명", "오렌지라이프"],
    "동양생명보험": ["동양생명"],
    "미래에셋생명보험": ["미래에셋생명"],
    "흥국생명": ["흥국생명보험"],
    "푸본현대생명보험": ["푸본현대생명"],
}

def clean_corporate_affix(name: str) -> str:
    """법인 형태((주), ㈜, 주식회사, 유한회사 등) 완전 제거 및 공백 정규화"""
    if not name:
        return ""
    cleaned = re.sub(r"[\(（]주[\)）]|주식회사|[\(（]유[\)）]|유한회사|㈜", "", name)
    cleaned = re.sub(r"\s+", "", cleaned).strip()
    return cleaned

BRAND_PHONETIC_PAIRS = [
    ("에스케이", "sk"),
    ("케이비", "kb"),
    ("엔에이치", "nh"),
    ("디비", "db"),
    ("아이비케이", "ibk"),
    ("비엔케이", "bnk"),
    ("에스비아이", "sbi"),
    ("에스씨", "sc"),
    ("아이엠", "im"),
    ("에스에이치", "sh"),
    ("케이디비", "kdb"),
]

def normalize_brand_and_terms(name: str) -> str:
    s = name.lower()
    for kor, eng in BRAND_PHONETIC_PAIRS:
        s = s.replace(kor, eng)
    # 업종 접미사 호환
    s = s.replace("해상보험", "화재").replace("손해보험", "화재")
    s = s.replace("생명보험", "생명")
    s = s.replace("투자증권", "증권")
    return s

def is_exact_corp_match(target: str, candidate: str) -> bool:
    """
    법인격을 제외한 기업명이 완전 일치하는지 판정.
    보험/생명/은행/증권 등 필수 업종 접미사 및 브랜드 음차(SK <-> 에스케이 등)의 호환 일치 허용:
    예: '에스케이증권' == 'SK증권'
        '케이비라이프생명' == 'KB라이프생명'
        '신한라이프생명' == '신한라이프생명보험'
        'SC제일은행' == '한국스탠다드차타드은행' (공식 별칭)
    단, 다른 브랜드(신한 != KB, iM != KB)가 섞인 경우 절대 불일치!
    """
    t_clean = clean_corporate_affix(target)
    c_clean = clean_corporate_affix(candidate)

    if not t_clean or not c_clean:
        return False

    if t_clean == c_clean:
        return True

    # 공식 법인명 별칭 매칭 (예: SC제일은행 <-> 한국스탠다드차타드은행)
    for main_name, aliases in KNOWN_CORP_ALIASES.items():
        all_family = [clean_corporate_affix(main_name)] + [clean_corporate_affix(a) for a in aliases]
        if t_clean in all_family and c_clean in all_family:
            return True

    # 브랜드 음차 및 업종 정규화 비교
    t_norm = normalize_brand_and_terms(t_clean)
    c_norm = normalize_brand_and_terms(c_clean)
    if t_norm == c_norm:
        return True

    return False


def generate_search_candidates(
    institution_name: str,
    original_name: str = "",
    agency_code: str = "",
    search_name_1: str = "",
    search_name_2: str = "",
    search_name_3: str = ""
) -> List[str]:
    """
    전산요건 엑셀 기준 순차 기업명 검색:
    1순위: C열 검색1 (우선검색)
    2순위: D열 검색2 (차선검색)
    3순위: 검색3 (추가검색)
    4순위: B열 상품제공기관명 / 정식 법인명 (original_name, institution_name)
    5순위: 특수 공식 법인명 별칭 (SC제일은행 -> 한국스탠다드차타드은행 등)
    """
    candidates = []
    seen = set()

    def add_cand(c: str):
        if not c:
            return
        c_raw = c.strip()
        if c_raw and c_raw not in seen:
            seen.add(c_raw)
            candidates.append(c_raw)

    # 1순위: 전산요건 C열 검색1
    if search_name_1:
        add_cand(search_name_1)

    # 2순위: 전산요건 D열 검색2
    if search_name_2:
        add_cand(search_name_2)

    # 3순위: 추가 지정 검색3
    if search_name_3:
        add_cand(search_name_3)

    # 4순위: 전산요건 B열 상품제공기관명 / 정식 법인명
    if original_name:
        add_cand(original_name)
    if institution_name:
        add_cand(institution_name)

    # 5순위: 특수 공식 법인명 별칭 (SC제일은행 -> 한국스탠다드차타드은행 등)
    for key, aliases in KNOWN_CORP_ALIASES.items():
        if key in [search_name_1, search_name_2, search_name_3, institution_name, original_name]:
            for a in aliases:
                add_cand(a)

    return candidates
