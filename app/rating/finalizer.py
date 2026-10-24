import re
from datetime import date
from typing import List, Optional
from app.schemas.rating import RawRatingRecord, RawCompany, StandardRating
from app.models.enums import CollectionStatus, RatingType, AgencyCode
from app.rating.normalizer import normalize_rating

# 평가사별 표준 평가종류 키워드 매핑
RATING_TYPE_KEYWORDS = {
    RatingType.CORPORATE_CREDIT.value: [
        "기업신용평가", "기업신용등급", "issuerrating", "issuer rating", "icr", "기업신용"
    ],
    RatingType.INSURANCE_FINANCIAL_STRENGTH.value: [
        "보험금지급능력평가", "보험금지급능력", "보험지급능력", "ifsr"
    ],
    RatingType.SENIOR_BOND.value: [
        "회사채(선순위)", "무보증사채(선순위)", "선순위회사채", "선순위", "무보증사채", "회사채"
    ]
}

EXCLUDED_BOND_KEYWORDS = [
    "후순위", "조건부", "신종자본", "하이브리드", "파생결합", "지급보증", "보증부",
    "기업어음", "전자단기사채", "cp", "단기사채", "subordinated"
]


def is_rating_type_match(
    target_rating_type: str,
    target_rating_name: str,
    raw_type_name: str,
    extra_info: Optional[str] = None
) -> bool:
    """
    평가종류 1:1 엄격 매칭 검증:
    - target_rating_type (CORPORATE_CREDIT, SENIOR_BOND, INSURANCE_FINANCIAL_STRENGTH)
    - target_rating_name (엑셀 전산요건 정의 명칭: Issuer Rating, 채권, 기업신용평가 등)
    - raw_type_name (수집된 원본 평가종류 명칭)
    """
    if not raw_type_name:
        return False

    clean_raw = re.sub(r"[\s\-_]+", "", raw_type_name).lower()
    combined_info = f"{clean_raw} {extra_info or ''}".lower()

    # 1. 증권사 회사채(선순위) 엄격 검증: 후순위, CP, 전단채 등 불순물 절대 차단
    if (
        target_rating_type == RatingType.SENIOR_BOND.value
        or "선순위" in target_rating_name
        or "회사채" in target_rating_name
        or target_rating_name == "채권"
    ):
        # '무보증'을 '보증'으로 오인하지 않도록 사전 보호
        check_info = combined_info.replace("무보증", "")
        for ex in EXCLUDED_BOND_KEYWORDS:
            if ex in check_info:
                return False

        # 선순위/회사채/채권/무보증사채 키워드 포함 여부 (후순위/CP 등 제외 완료 상태)
        if any(k in clean_raw for k in ["회사채", "무보증사채", "선순위"]):
            return True
        if clean_raw in ["채권", "무보증채권"]:
            return True
        return False

    # 2. 보험금지급능력평가 (IFSR) 엄격 검증
    if (
        target_rating_type == RatingType.INSURANCE_FINANCIAL_STRENGTH.value
        or "보험" in target_rating_name
        or "ifsr" in target_rating_name.lower()
    ):
        return any(k in clean_raw for k in ["보험금지급", "보험지급", "ifsr"])

    # 3. 기업신용평가 (ICR / Issuer Rating) 엄격 검증
    if (
        target_rating_type == RatingType.CORPORATE_CREDIT.value
        or "기업신용" in target_rating_name
        or "issuerrating" in clean_raw
        or "icr" in target_rating_name.lower()
    ):
        # 회사채나 보험 키워드가 들어간 경우 차단
        if any(k in clean_raw for k in ["회사채", "보험", "전단채"]):
            return False
        return any(k in clean_raw for k in ["기업신용", "issuerrating", "icr"])

    # 명시적 전산요건 명칭과의 직접 매칭 시도
    if target_rating_name:
        clean_target = re.sub(r"[\s\-_]+", "", target_rating_name).lower()
        if clean_target in clean_raw or clean_raw in clean_target:
            return True

    return False


def finalize_rating(
    institution_id: str,
    agency_code: str,
    rating_type: str,
    raw_company: Optional[RawCompany],
    records: Optional[List[RawRatingRecord]] = None,
    target_rating_name: str = "",
    source_url: str = ""
) -> StandardRating:
    """
    [Rating Finalizer]
    1. 기업 식별 여부 확인 (raw_company 없으면 NO_RATING)
    2. 수집된 Raw 레코드 중 요청된 평가종류와 일치하는 것 필터링
    3. 정규화 및 유효 등급 검증
    4. 만료 여부 판정 (valid_to)
    5. 동일 평가종류 중 최신 평가일(rating_date) 기준 레코드 선택
    6. 확정일자 누락 시 MANUAL_REVIEW 처리
    """
    base_res = StandardRating(
        institution_id=institution_id,
        agency_code=agency_code,
        rating_type=rating_type,
        source_url=source_url or (raw_company.source_url if raw_company else None),
        company_id=raw_company.company_id if raw_company else None,
        search_priority=raw_company.search_priority if raw_company else None,
        matched_keyword=raw_company.matched_keyword if raw_company else None,
        status=CollectionStatus.NO_RATING.value
    )

    if not raw_company:
        # [케이스 C]: 1~3순위 검색어를 모두 조회했으나 기업 자체가 미등록된 경우 -> 실제 무등급 (NO_RATING)
        base_res.status = CollectionStatus.NO_RATING.value
        return base_res

    if records is None:
        # [비정상 케이스]: 사이트 오류, 세션 튕김, 파싱 불가 등으로 조회가 비정상 중단된 경우 -> 확인필요 (MANUAL_REVIEW)
        base_res.status = CollectionStatus.MANUAL_REVIEW.value
        base_res.error_message = "상세 공시 내역 정상 조회 실패 (확인필요)"
        return base_res

    if len(records) == 0:
        # [정상 조회 완료]: 상세 조회가 정상 완료되었으나 등록된 등급 레코드 자체가 없는 경우 -> 실제 무등급 (NO_RATING)
        base_res.status = CollectionStatus.NO_RATING.value
        return base_res

    # 1. 평가종류 엄격 매칭 레코드 필터링
    matched_records: List[RawRatingRecord] = []
    for rec in records:
        if is_rating_type_match(rating_type, target_rating_name, rec.rating_type_raw, rec.extra_info):
            matched_records.append(rec)

    if not matched_records:
        # [케이스 A]: 상세 공시 목록 확인 완료되었으나 목표 평가종류만 없는 경우 -> 실제 무등급 (NO_RATING) 확정
        base_res.status = CollectionStatus.NO_RATING.value
        return base_res

    # 2. 유효 등급 정규화 검증
    valid_candidates = []
    today = date.today()

    for rec in matched_records:
        norm_rating, outlook = normalize_rating(rec.raw_rating)
        if not norm_rating or norm_rating == "취소":
            continue

        is_expired = False
        if rec.valid_to and rec.valid_to < today:
            is_expired = True

        valid_candidates.append({
            "record": rec,
            "norm_rating": norm_rating,
            "outlook": outlook,
            "is_expired": is_expired,
            "rating_date": rec.rating_date or date.min
        })

    if not valid_candidates:
        return base_res

    # 3. 최신 평가일(rating_date) 기준 레코드 선택 (문자열이 아닌 datetime.date 기반 정렬)
    valid_candidates.sort(key=lambda x: x["rating_date"], reverse=True)
    selected = valid_candidates[0]
    rec: RawRatingRecord = selected["record"]
    base_res.raw_rating = rec.raw_rating
    base_res.rating = selected["norm_rating"]
    base_res.rating_type_raw = rec.rating_type_raw
    base_res.outlook = rec.outlook or selected["outlook"]
    base_res.rating_date = rec.rating_date.strftime("%Y-%m-%d") if rec.rating_date else None
    base_res.valid_from = rec.valid_from.strftime("%Y-%m-%d") if rec.valid_from else None
    base_res.valid_to = rec.valid_to.strftime("%Y-%m-%d") if rec.valid_to else None
    base_res.source_url = rec.source_url or base_res.source_url

    # 4. 상태값 최종 판정
    if selected["is_expired"]:
        base_res.status = CollectionStatus.EXPIRED.value
    elif not rec.rating_date:
        # 등급은 확인되었으나 확정일자가 없는 경우: 등급 유지하되 수동확인 상태 지정
        base_res.status = CollectionStatus.MANUAL_REVIEW.value
    else:
        base_res.status = CollectionStatus.SUCCESS.value

    return base_res
