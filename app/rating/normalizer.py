import re
from typing import Optional, Tuple
from app.rating.rank import RATING_RANKS

# 순서가 긴 문자열(AA+, AA-)이 짧은 문자열(AA)보다 먼저 매치되어야 하며, 뒤에 추가 알파벳/숫자가 없어야 함
RATING_PATTERN = re.compile(
    r"\b(AAA|AA\+|AA\-|AA|A\+|A\-|A|BBB\+|BBB\-|BBB|BB\+|BB\-|BB|B\+|B\-|B|CCC\+|CCC\-|CCC|CC|C|D)(?![A-Za-z0-9\+\-])",
    re.IGNORECASE
)


def normalize_rating(raw_rating: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    원본 등급 문자열을 파싱하여 (정규화된 등급, 전망/기타 부가정보) 튜플 반환.
    예:
      - "AA (안정적)" -> ("AA", "안정적")
      - "AA- (하향검토)" -> ("AA-", "하향검토")
      - "AAA" -> ("AAA", None)
      - None or "" -> (None, None)
    """
    if not raw_rating:
        return None, None

    text = str(raw_rating).strip()
    match = RATING_PATTERN.search(text)
    if not match:
        return None, text

    normalized = match.group(1).upper()
    # 유효한 Rank에 있는지 확인
    if normalized not in RATING_RANKS:
        return None, text

    # 부가 정보 추출 (괄호 안 문구 등)
    outlook_match = re.search(r"[\(（]([^\)）]+)[\)）]", text)
    outlook = outlook_match.group(1).strip() if outlook_match else None

    return normalized, outlook
