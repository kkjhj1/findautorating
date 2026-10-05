from typing import Optional, Dict, Tuple
from app.rating.rank import get_rating_rank

class RatingChangeStatus:
    MAINTAIN = "MAINTAIN"       # 유지 ➖
    UPGRADE = "UPGRADE"         # 상향 🔺
    DOWNGRADE = "DOWNGRADE"     # 하향 🔻
    NEW = "NEW"                 # 신규 🆕
    UNKNOWN = "UNKNOWN"         # 미평가/비교불가

def analyze_rating_change(
    prev_rating: Optional[str],
    curr_rating: Optional[str]
) -> Tuple[str, int, str]:
    """
    전월 최종등급 vs 당월 최종등급 변동 분석
    반환값: (change_status, notch_delta, display_label)
    - notch_delta: 등급 오른 단계 수 (양수=상향, 음수=하향, 0=동일)
    - display_label: "유지 ➖", "상향 ▲1", "하향 ▼1", "신규 🆕" 등
    """
    if not curr_rating or curr_rating in ["-", "미공시", "NO_RATING"]:
        return RatingChangeStatus.UNKNOWN, 0, "-"

    if not prev_rating or prev_rating in ["-", "미공시", "NO_RATING"]:
        return RatingChangeStatus.NEW, 0, "신규"

    rank_prev = get_rating_rank(prev_rating)
    rank_curr = get_rating_rank(curr_rating)

    if rank_prev is None or rank_curr is None:
        # 텍스트 그대로 비교
        if prev_rating.strip() == curr_rating.strip():
            return RatingChangeStatus.MAINTAIN, 0, "유지"
        return RatingChangeStatus.UNKNOWN, 0, "-"

    # rank 숫자는 작을수록 높은 등급 (AAA=1, AA+=2)
    # 따라서 delta = rank_prev - rank_curr (양수면 상향)
    notch_delta = rank_prev - rank_curr

    if notch_delta == 0:
        return RatingChangeStatus.MAINTAIN, 0, "유지"
    elif notch_delta > 0:
        return RatingChangeStatus.UPGRADE, notch_delta, f"상향 ▲{notch_delta}"
    else:
        return RatingChangeStatus.DOWNGRADE, notch_delta, f"하향 ▼{abs(notch_delta)}"
