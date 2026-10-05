from datetime import date
from typing import Optional, List
from app.schemas.rating import StandardRating
from app.models.enums import CollectionStatus

def is_rating_valid(
    rating_obj: StandardRating,
    execution_date: Optional[str] = None
) -> bool:
    """
    PRD 제15조 등급 유효기간 판정:
    - Case 1: 유효기간 존재 + 현재 유효 (valid_to >= execution_date) -> True
    - Case 2: 유효기간 존재 + 만료 (valid_to < execution_date) -> False
    - Case 3: 유효기간 없음 -> True (유효 인정)
    """
    if not rating_obj.rating:
        return False

    if execution_date is None:
        execution_date = date.today().isoformat()

    if rating_obj.valid_to:
        # 날짜 비교 (YYYY-MM-DD 형식)
        clean_valid_to = rating_obj.valid_to.strip()
        clean_exec = execution_date.strip()
        if clean_valid_to < clean_exec:
            return False

    return True

def select_latest_rating_by_date(ratings: List[StandardRating]) -> Optional[StandardRating]:
    """
    PRD 제14조: 동일 Rating Type이 여러 개 존재하는 경우
    동일 Rating Type에서는 가장 최근 등급확정일의 등급을 선택한다.
    """
    if not ratings:
        return None

    # rating_date 기준 내림차순 정렬 (None인 경우 가장 뒤로)
    def sort_key(item: StandardRating):
        return item.rating_date if item.rating_date else ""

    sorted_ratings = sorted(ratings, key=sort_key, reverse=True)
    return sorted_ratings[0]
