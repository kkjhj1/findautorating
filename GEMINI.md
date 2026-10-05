# ============================================================
# PROJECT & WORKSPACE DEVELOPMENT AGENT RULES
# Scope: Project Local (신용등급 자동조사 시스템)
# ============================================================

# 🛑 [CORE NEGATIVE CONSTRAINTS - NEVER VIOLATE]
0. [CRITICAL - 절대 준수] TWO-PHASE WORKFLOW: 무조건 계획 보고 후 정지(STOP) ➔ 명시적 승인 후 구현
   - **[Phase 1: 계획/초안 보고 & 반드시 대기(STOP)]**:
     사용자가 "~해줘", "~바꿔줘" 등 어떠한 개발·수정 요청을 하더라도, **첫 번째 턴에서는 코드 수정 도구(`replace_file_content`, `write_to_file`, `multi_replace_file_content`) 사용을 엄격히 금지**한다.
     오직 읽기 전용 도구(`view_file`, `grep_search`, `list_dir`)만 사용하여 분석한 뒤, **"무엇을 어떻게 바꿀 것인지" 변경 계획과 초안을 먼저 제시하고 즉시 턴을 종료(STOP)하여 사용자의 승인을 기다린다.**
   - **[Phase 2: 명시적 승인 후에만 코드 수정]**:
     사용자가 계획을 확인하고 명시적으로 **"개발진행하라", "진행해", "적용해"**라고 승인한 다음 턴에서만 실제 파일 수정 및 코드 작성을 수행한다.
   - **[임의 확대 해석 절대 금지]**:
     단순 요청 문장("~해줘", "~바꿔줘"), 질문에 대한 동의("오케이", "응"), 설정 확인 등을 '개발 착수 승인'으로 임의 확대 해석하여 코드를 바로 수정하는 행위를 엄격히 금지한다.

1. NEVER modify, refactor, or format working code outside the explicitly requested scope without permission.
2. NEVER rewrite an entire file when a targeted patch/diff is sufficient, regardless of file size.
3. NEVER assume, hallucinate, or shallow-guess unverified APIs, data structures, file paths, or business logic.
4. NEVER expose, hardcode, or commit secrets, API keys, passwords, DB credentials, or tokens.
5. NEVER execute destructive or external actions (git push, force push, mass delete, production deploys, remote modifications) without explicit human confirmation.
6. NEVER execute unverified external scripts, curl piped to shell, or untrusted code snippets.
7. NEVER repeat identical tool calls or reload files when information is already present in the active context.

# ============================================================
# ⚙️ 1. 터미널 및 명령어 실행 규칙 (Terminal & Command Execution Rules)
# ============================================================

### [0. Non-Interactive Shell Execution (터미널 입력 대기 방지)]
- **주의 (개발 승인과 엄격 분리)**: 본 항목은 '사용자가 승인하여 개발이 진행 중일 때' 실행하는 순수 터미널 쉘 명령어에만 한정되며, 사용자의 개발 착수 승인(Phase 1 ➔ Phase 2) 절차를 건너뛰는 면죄부가 아니다.
- **인터랙티브 차단 금지**: 승인된 작업 내에서 Python 스크립트 실행, 테스트 실행(`pytest`), DB 조회, 서버 구동 시 불필요한 사용자 입력 대기(`input()`, 확인 모달 등)로 쉘이 멈추지 않도록 비대화형(non-interactive)으로 자동 실행한다.

### [1. Inline Script Execution (인라인 스크립트 금지)]
- `python -c`, `python -c "..."` 등 임의의 복잡한 인라인 스크립트 실행을 엄격히 금지한다.
- 긴 SQL 쿼리, 대량 파일 조작, API 호출, 다단계 자동화 로직을 쉘 명령어에 인라인으로 삽입하지 않는다.
- 모든 분석, 검증, 일회성 작업은 스크립트 파일(scratch/ 또는 scripts/)을 생성한 후 명시적으로 실행한다.
- 쉘 명령어는 항상 짧고, 결정론적(deterministic)이며, 사람이 쉽게 리뷰할 수 있는 형태로 유지한다.

### [2. Script Execution Safety (스크립트 실행 원칙)]
- 신규 스크립트를 생성하기 전에 프로젝트 내 기존 유틸리티, 테스트, 스크립트가 해당 작업을 수행할 수 있는지 먼저 확인한다.
- `scripts/` 또는 임시 폴더에 있다고 해서 무조건 안전하다고 간주하지 않는다.
- 스크립트가 파괴적 작업, DB 변조(Mutation), 대량 파일 변경, 외부 API 쓰기, 배포 작업을 수행하는 경우 반드시 High-Impact(고위험) 명령으로 취급한다.

### [3. Prefer Deterministic Commands (결정론적 고정 명령어 우선)]
매번 동적으로 생성되는 임의 명령어 대신, 사전에 검증된 정형화된 명령어를 우선 사용한다:
- `pytest tests/` / `python -m pytest`
- `python -m uvicorn app.main:app`
- `git status`, `git diff`, `git log`, `git branch`
- `npm test`, `npm run build`

### [4. Read-Only Operations (무승인 안전 작업)]
다음과 같은 영구 데이터 변조가 없는 읽기 전용 작업은 불필요한 확인 창 없이 즉시 수행한다:
- 파일 목록 및 소스 코드 조회 (`view_file`, `list_dir`, `grep_search`)
- `git status`, `git diff`, `git log`
- 영구 데이터를 변조하지 않는 순수 단위 테스트 (`pytest tests/`)
- 환경 및 패키지 정보 확인 (`pip list`, `python --version`)

### [5. High-Impact & Destructive Operations (절대 승인 필수 작업)]
다음 작업은 사용자 명시적 승인 전까지 명령어 입력을 차단한다:
- 파일 대량 삭제 및 영구 변조 (`rm -rf`, `Remove-Item -Force`, `del /f /q`, `rmdir /s /q`)
- Git 파괴적 명령어 (`git reset --hard`, `git clean -fd`, `git push --force`)
- 파괴적 DB 작업 (`DROP`, `TRUNCATE`, 조건 없는 bulk `DELETE`, 파괴적 마이그레이션)
- 프로덕션 배포 및 원격 저장소 변조
- 영구 데이터를 변조하는 외부 API 대량 호출

### [6. Database Safety (데이터베이스 안전)]
- 조사 및 원인 분석 단계에서는 반드시 Read-Only 조회를 수행한다.
- DB 확인(조회)과 DB 변경(Mutation)을 엄격히 분리한다.
- 로컬 DB(`data/credit_rating.db`)는 실제 검증 데이터이므로 사전 승인 없이 초기화하거나 삭제하지 않는다.

# ============================================================
# 🎯 2. 프로젝트 표준 진입점 (Standard Entrypoints)
# ============================================================
- 백엔드 서버 구동: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 단위 테스트 실행: `pytest tests/`
- 프론트엔드 정적 서빙: 백엔드 FastAPI 마운트 (`/` -> `frontend/`)
- 데이터베이스 경로: `data/credit_rating.db` (SQLite3)

# ============================================================
# 🏢 3. 비즈니스 도메인 및 등급 산출 규격 (Domain Business Rules)
# ============================================================

### [1. 3대 신용평가사 및 최저등급 산출]
- 수집 대상: 한국기업평가(KR), 한국신용평가(KIS), NICE신용평가(NICE)
- 산출 공식: 유효 수집된 평가사 등급 중 가장 보수적인 **최저등급(Lowest Rating)**을 최종 등급으로 산출 (예: KR=AA, KIS=AA-, NICE=AA ➔ 최종: AA-)
- 평가사 결과가 1개사만 존재하더라도 해당 등급을 유효 등급으로 채택.

### [2. 업권별 평가 종류 매핑 규격]
- 은행 / 저축은행 / 증권: 기업신용평가(`CORPORATE_CREDIT`), 선순위회사채(`SENIOR_BOND`)
- 생명보험 / 손해보험: 보험금지급능력평가(`INSURANCE_FINANCIAL_STRENGTH`)
- **이종 상품 Fallback 절대 금지**: 보험사에 대해 임의로 회사채 후순위 등 다른 상품군 등급을 매핑하지 않는다.

### [3. 전월 등급 및 변동 분석 규칙]
- **전월 등급의 엄격한 출처**: 전월 등급(`prev_final_rating`)은 오직 **전월 확정 이력(`MonthlyConfirmedRating`)**에 공식 기록된 데이터만 사용한다. 당월 수집 결과를 임의로 전월 등급에 복사/대입하지 않는다.
- **최초 등록 기관 표기**: 전월 확정 이력이 없는 신규 기관은 전월 등급을 `-` (하이픈), 전월대비 상태를 반드시 **"신규"** 배지로 고정 표기한다.

# ============================================================
# 🖥️ 4. 프론트엔드 UI & 인터랙션 규격 (Frontend Rules)
# ============================================================
- 3개 탭 구조 유지:
  1. 당월 신용등급 조사 및 확정 (`tabCurrent`)
  2. 월별 확정 이력 조회 (`tabHistory`)
  3. 상품제공기관 관리 (`tabManage`)
- **버튼 상태 복원 원칙**: 전체 조사(`btnRunAll`) 및 선택 조사(`btnRunSelected`) 완료 시점에는 진행 중 텍스트 및 SVG 아이콘, 카운트 배지(`selectedCount`)를 반드시 초기 상태로 완전 복원한다.
- **기관명 셀 간결성**: 메인 테이블의 기관명 셀에는 불필요한 상품 종류 힌트 배지를 제거하고 기관명만 명확히 단독 출력한다.

