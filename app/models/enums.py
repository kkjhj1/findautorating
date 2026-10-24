import enum

class IndustryType(str, enum.Enum):
    BANK = "BANK"                                 # 은행
    SAVINGS_BANK = "SAVINGS_BANK"                 # 저축은행
    SECURITIES = "SECURITIES"                     # 증권
    LIFE_INSURANCE = "LIFE_INSURANCE"             # 생명보험
    NON_LIFE_INSURANCE = "NON_LIFE_INSURANCE"     # 손해보험
    POST = "POST"                                 # 우체국 (제외)

class RatingType(str, enum.Enum):
    CORPORATE_CREDIT = "CORPORATE_CREDIT"                     # 기업신용등급 (은행, 저축은행)
    SENIOR_BOND = "SENIOR_BOND"                               # 회사채(선순위) (증권)
    INSURANCE_FINANCIAL_STRENGTH = "INSURANCE_FINANCIAL_STRENGTH" # 보험지급능력 (생보, 손보)

class AgencyCode(str, enum.Enum):
    KR = "KR"       # 한국기업평가
    KIS = "KIS"     # 한국신용평가
    NICE = "NICE"   # NICE신용평가

class CollectionStatus(str, enum.Enum):
    COLLECTING = "COLLECTING"               # 조사 진행 중 (사전 클렌징 상태)
    SUCCESS = "SUCCESS"                     # 정상 수집
    NO_RATING = "NO_RATING"                 # 무등급 (평가 대상 아님 또는 등급 없음)
    EXPIRED = "EXPIRED"                     # 유효기간 만료
    CRAWLING_ERROR = "CRAWLING_ERROR"       # 네트워크 / HTTP / 접속 오류
    PARSING_ERROR = "PARSING_ERROR"         # 사이트 구조 변경 등 파싱 오류
    MAPPING_REQUIRED = "MAPPING_REQUIRED"   # 기관 매핑 불명확/필요
    MANUAL_CHECK = "MANUAL_CHECK"           # 수동 확인 필요 상태 (기존 호환)
    MANUAL_REVIEW = "MANUAL_REVIEW"         # 수동 확인 필요 상태 (신규 표준)
    INVALID_RATING = "INVALID_RATING"       # 유효하지 않은 등급 형식
    AUTH_REQUIRED = "AUTH_REQUIRED"         # 로그인/인증 요구 감지
    SITE_STRUCTURE_CHANGED = "SITE_STRUCTURE_CHANGED" # 사이트 HTML/API 구조 변경 감지

class JobStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    STOPPED = "STOPPED"

class ExecutionType(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    MANUAL_ALL = "MANUAL_ALL"
    MANUAL_SELECT = "MANUAL_SELECT"
