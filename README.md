# 🏢 신용등급 자동조사 시스템 (Credit Rating Collector)

> 국내 3대 신용평가사(한국기업평가, 한국신용평가, NICE신용평가)의 공시 신용등급을 실시간 자동 수집하고, 가장 보수적인 최저등급을 기준으로 최종 등급 및 전월대비 변동을 자동 산출하는 고성능 금융기관 신용등급 관리 시스템입니다.

---

## ✨ 핵심 기능

1. **3대 평가사 실시간 자동 스크래핑 & 매핑**
   - 한국기업평가(KR), 한국신용평가(KIS), NICE신용평가(NICE) 웹 공시 데이터 실시간 수집
   - 업권별(은행, 저축은행, 증권, 생명보험, 손해보험) 적합 평가 상품 자동 매핑
   - 법인격 제거 및 1·2·3순위 검색어 기반 정밀 기업 식별

2. **최종 등급 결정 & 변동 분석 엔진**
   - 3대 신용평가사 유효 등급 중 가장 보수적인 **최저등급(Lowest Rating)**을 최종 등급으로 자동 채택
   - 전월 공식 확정 이력 대비 **유지, 상향, 하향, 신규** 상태 자동 판정

3. **100vh 반응형 모던 대시보드 (Vanilla UI)**
   - 브라우저 외부 종스크롤 0px 최적화 (테이블 내부 유동 스크롤)
   - 원클릭 미니 KPI 통계 바 & 실시간 인터랙티브 필터링
   - 수집 오류 / 확인필요 대상 기관 원클릭 선별 재조회(⚡) 지원

4. **월별 공식 확정 및 이력 관리**
   - 당월 조사 결과를 검토한 후 [당월 등급 최종 확정] 버튼으로 공식 영구 기록
   - 과거 월별 확정 데이터 조회 및 시계열 변동 분석

5. **상품제공기관 마스터 실시간 CRUD 관리**
   - 사명 변경, M&A(합병/인수), 신설 법인을 웹 화면에서 실시간 등록/수정/비활성화
   - `자료/전산요건.xlsx` 엑셀 기반 초기 마스터 자동 동기화(SSOT)

6. **Excel 보고서 다운로드 (윈도우 탐색기 연동)**
   - Web File System Access API 연동으로 원하는 폴더("다른 이름으로 저장") 직접 지정 지원
   - 화면 그리드와 100% 일치하는 4개 시트 정밀 규격 엑셀 보고서 생성

---

## 🛠️ 기술 스택

- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy, APScheduler
- **Database**: SQLite3
- **Scraping / Network**: HTTPX, BeautifulSoup4
- **Excel Processing**: openpyxl
- **Frontend**: HTML5, Vanilla CSS (Modern Dark Theme), Vanilla JavaScript (ES6+)
- **Testing**: pytest

---

## 🚀 빠른 시작 (Getting Started)

### 1. 환경 설정 및 패키지 설치

```bash
# 가상환경 생성 (선택)
python -m venv venv
venv\Scripts\activate  # Windows

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2. 서버 실행

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 서버 구동 시 `자료/전산요건.xlsx` 마스터 데이터를 기반으로 SQLite 데이터베이스가 자동 초기화됩니다.
- 웹 브라우저에서 `http://127.0.0.1:8000`에 접속하여 대시보드를 이용할 수 있습니다.

### 3. 단위 테스트 실행

```bash
python -m pytest tests/
```

---

## 📁 프로젝트 구조

```text
신용등급조회/
├── app/                      # 백엔드 애플리케이션 모듈
│   ├── api/                  # REST API 라우터 (v1)
│   ├── collectors/           # 3대 신용평가사 수집기 (KR, KIS, NICE)
│   ├── core/                 # DB 연결, 설정, 초기화
│   ├── engine/               # 최저등급 산출 및 변동 판정 엔진
│   ├── institution/          # 기관 마스터 및 엑셀 동기화
│   ├── jobs/                 # 배치 작업 및 스케줄러
│   ├── models/               # SQLAlchemy ORM 모델
│   └── schemas/              # Pydantic 데이터 검증 스키마
├── frontend/                 # 프론트엔드 정적 에셋
│   ├── css/style.css         # 다크 테마 및 100vh 뷰포트 CSS
│   ├── js/app.js             # 대시보드 인터랙션 및 API 통신
│   └── index.html            # 메인 대시보드 뷰
├── tests/                    # pytest 회귀 검증 단위 테스트
├── 자료/                     # 마스터 데이터 소스 (전산요건.xlsx)
├── requirements.txt          # 패키지 의존성 명세
└── README.md                 # 프로젝트 문서
```
