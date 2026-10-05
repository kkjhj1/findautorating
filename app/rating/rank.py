from typing import Optional, Dict

# PRD 제19조: 내부 등급 순위표 (숫자가 클수록 낮은 등급)
RATING_RANKS: Dict[str, int] = {
    "AAA": 1,
    "AA+": 2,
    "AA": 3,
    "AA-": 4,
    "A+": 5,
    "A": 6,
    "A-": 7,
    "BBB+": 8,
    "BBB": 9,
    "BBB-": 10,
    "BB+": 11,
    "BB": 12,
    "BB-": 13,
    "B+": 14,
    "B": 15,
    "B-": 16,
    "CCC+": 17,
    "CCC": 18,
    "CCC-": 19,
    "CC": 20,
    "C": 21,
    "D": 22,
}

def get_rating_rank(rating: Optional[str]) -> Optional[int]:
    """등급 문자열의 숫자 Rank 반환 (알 수 없거나 None인 경우 None)"""
    if not rating:
        return None
    clean = rating.strip().upper()
    return RATING_RANKS.get(clean, None)

def compare_ratings(rating_a: Optional[str], rating_b: Optional[str]) -> int:
    """
    두 등급 비교:
    - rating_a가 더 우수하면(rank가 작으면) -1
    - 같으면 0
    - rating_a가 더 열위면(rank가 크면) 1
    """
    rank_a = get_rating_rank(rating_a)
    rank_b = get_rating_rank(rating_b)

    if rank_a is None and rank_b is None:
        return 0
    if rank_a is None:
        return 1
    if rank_b is None:
        return -1

    if rank_a < rank_b:
        return -1
    elif rank_a > rank_b:
        return 1
    return 0

def get_lower_rating(rating_a: Optional[str], rating_b: Optional[str]) -> Optional[str]:
    """두 등급 중 더 낮은(열위) 등급 반환 (보수적 원칙)"""
    if not rating_a:
        return rating_b
    if not rating_b:
        return rating_a

    rank_a = get_rating_rank(rating_a)
    rank_b = get_rating_rank(rating_b)

    if rank_a is None:
        return rating_b
    if rank_b is None:
        return rating_a

    # 숫자가 클수록 낮은 등급
    return rating_a if rank_a >= rank_b else rating_b
