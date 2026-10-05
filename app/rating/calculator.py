from datetime import date
from typing import Optional, List, Dict
from app.schemas.rating import StandardRating, RatingCalculationResult
from app.models.enums import CollectionStatus, AgencyCode
from app.rating.rank import get_lower_rating, get_rating_rank
from app.rating.validator import is_rating_valid

def calculate_final_rating(
    institution_id: str,
    kr: Optional[StandardRating] = None,
    kis: Optional[StandardRating] = None,
    nice: Optional[StandardRating] = None,
    execution_date: Optional[str] = None
) -> RatingCalculationResult:
    """
    PRD 제18조 & 제24조 최종등급 산출 Engine:
    - 유효성(유효기간 만료 여부 등) 검증 후 유효 등급만 선별
    - 3곳 / 2곳 / 1곳 최저등급 산출
    - 0곳인 경우 final_rating = None
    - CRAWLING_ERROR / PARSING_ERROR가 포함된 경우 overall_status = MANUAL_CHECK 격리
    """
    if execution_date is None:
        execution_date = date.today().isoformat()

    valid_ratings: Dict[str, str] = {}
    has_error = False
    has_mapping_issue = False
    all_no_rating = True

    agency_ratings = [
        (AgencyCode.KR.value, kr),
        (AgencyCode.KIS.value, kis),
        (AgencyCode.NICE.value, nice),
    ]

    for agency_code, rating_obj in agency_ratings:
        if rating_obj is None:
            continue

        status = rating_obj.status

        if status in [CollectionStatus.CRAWLING_ERROR.value, CollectionStatus.PARSING_ERROR.value]:
            has_error = True
            all_no_rating = False
        elif status == CollectionStatus.MAPPING_REQUIRED.value:
            has_mapping_issue = True
            all_no_rating = False
        elif rating_obj.rating:
            # 유효기간 만료 여부 확인
            if is_rating_valid(rating_obj, execution_date):
                valid_ratings[agency_code] = rating_obj.rating
                all_no_rating = False
            else:
                rating_obj.status = CollectionStatus.EXPIRED.value
                all_no_rating = False

    # 최종 최저등급 계산
    final_rating: Optional[str] = None
    for agency_code, r_val in valid_ratings.items():
        if final_rating is None:
            final_rating = r_val
        else:
            final_rating = get_lower_rating(final_rating, r_val)

    # 2노치 이상 등급 격차(오조사 의심) 검증
    ranks = [get_rating_rank(r) for r in valid_ratings.values() if get_rating_rank(r) is not None]
    has_large_gap = False
    max_gap = 0
    if len(ranks) >= 2:
        max_gap = max(ranks) - min(ranks)
        if max_gap >= 2:
            has_large_gap = True

    missing_agencies = [code for code in [AgencyCode.KR.value, AgencyCode.KIS.value, AgencyCode.NICE.value] if code not in valid_ratings]

    # 산출 근거 텍스트 생성
    if valid_ratings:
        parts = [f"{agency}({rating})" for agency, rating in valid_ratings.items()]
        calculation_logic = f"{', '.join(parts)} 중 최저등급: {final_rating}"
        if has_large_gap:
            calculation_logic += f" [⚠️ 평가사간 {max_gap}노치 격차 발생 - 오조사 의심 수동확인 필요]"
        if missing_agencies:
            calculation_logic += f" [미수집: {', '.join(missing_agencies)}]"
    else:
        calculation_logic = "유효한 신용등급 없음"

    # overall_status 판정
    if has_mapping_issue:
        overall_status = CollectionStatus.MAPPING_REQUIRED.value
    elif has_large_gap:
        # 사용자 업무원칙: 2개 이상 차이나는 것은 잘못 조사된 것이므로 수동점검으로 격리
        overall_status = CollectionStatus.MANUAL_CHECK.value
    elif has_error:
        overall_status = CollectionStatus.MANUAL_CHECK.value
    elif final_rating is not None:
        overall_status = CollectionStatus.SUCCESS.value
    elif all_no_rating:
        overall_status = CollectionStatus.NO_RATING.value
    else:
        overall_status = CollectionStatus.MANUAL_CHECK.value

    return RatingCalculationResult(
        institution_id=institution_id,
        final_rating=final_rating,
        overall_status=overall_status,
        calculation_logic=calculation_logic,
        kr=kr,
        kis=kis,
        nice=nice
    )
