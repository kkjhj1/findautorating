import sys
import httpx

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

print("==================================================")
print("  신용등급 자동조사 시스템 추가 개선기획 종합 검증")
print("==================================================")

client = httpx.Client(base_url=BASE_URL, timeout=20.0)

# 1. 서버 헬스체크
res = client.get("/health")
assert res.status_code == 200, f"Health check failed: {res.status_code}"
print("[PASS 1/6] 서버 헬스체크 정상:", res.json())

# 2. 한국신용평가 (KIS) 직파싱 어댑터 단위 검증
from app.collectors.kis import KISAdapter
adapter = KISAdapter()

# 키움증권 선순위 회사채 (사용자 스크린샷 검증 대상)
res_kw = adapter.get_ratings(
    institution_id="INST_031",
    search_name="키움증권",
    rating_type="SENIOR_BOND",
    target_rating_name="회사채(선순위)"
)
print(f"[PASS 2/6] KIS 키움증권 수집 결과: 등급={res_kw.rating}, 평가일={res_kw.rating_date}, 상태={res_kw.status}")
assert res_kw.rating == "AA", f"Expected AA, got {res_kw.rating}"
assert res_kw.rating_date == "2026-09-16", f"Expected 2026-09-16, got {res_kw.rating_date}"

# 국민은행 선순위 회사채
res_kb = adapter.get_ratings(
    institution_id="INST_001",
    search_name="국민은행",
    rating_type="SENIOR_BOND",
    target_rating_name="회사채(선순위)"
)
print(f"       -> KIS 국민은행 수집 결과: 등급={res_kb.rating}, 평가일={res_kb.rating_date}, 상태={res_kb.status}")
assert res_kb.rating == "AAA", f"Expected AAA, got {res_kb.rating}"

# 삼성생명 보험금지급능력평가
res_ss = adapter.get_ratings(
    institution_id="INST_010",
    search_name="삼성생명",
    rating_type="INSURANCE_FINANCIAL_STRENGTH",
    target_rating_name="보험금지급 능력평가"
)
print(f"       -> KIS 삼성생명 수집 결과: 등급={res_ss.rating}, 평가일={res_ss.rating_date}, 상태={res_ss.status}")
assert res_ss.rating == "AAA", f"Expected AAA, got {res_ss.rating}"

# 3. 당월 최종 확정 (Last-Win 메커니즘 검증)
# 1차 확정
res_c1 = client.post("/api/v1/ratings/confirm", json={"base_year_month": "2026-10", "confirmed_by": "USER_FIRST"})
assert res_c1.status_code == 200, f"1st confirm failed: {res_c1.text}"
c1_data = res_c1.json()
print(f"[PASS 3/6] 당월 1차 최종 확정 성공: {c1_data['confirmed_count']}건 확정 (덮어쓰기={c1_data['previous_overwritten']})")

# 2차 재확정 (동월 내 재확정 -> Last-Win 덮어쓰기 확인)
res_c2 = client.post("/api/v1/ratings/confirm", json={"base_year_month": "2026-10", "confirmed_by": "USER_FINAL"})
assert res_c2.status_code == 200, f"2nd confirm failed: {res_c2.text}"
c2_data = res_c2.json()
assert c2_data["previous_overwritten"] is True, "Expected previous_overwritten to be True for Last-Win"
assert c2_data["confirmed_by"] == "USER_FINAL"
print(f"[PASS 4/6] 동월 재확정 (Last-Win 덮어쓰기) 검증 완료: 덮어쓰기 성공 여부={c2_data['previous_overwritten']}, 최종확정자={c2_data['confirmed_by']}")

# 4. 월별 확정 이력 조회 API 검증
res_months = client.get("/api/v1/ratings/history/months")
assert res_months.status_code == 200
months_data = res_months.json()
assert "2026-10" in months_data["months"], "2026-10 not found in history months"
print(f"[PASS 5/6] 확정 년월 목록 조회 성공: {months_data['months']}")

res_hist = client.get("/api/v1/ratings/history?base_year_month=2026-10")
assert res_hist.status_code == 200
hist_data = res_hist.json()
assert hist_data["total_count"] == 85, f"Expected 85, got {hist_data['total_count']}"
assert hist_data["confirmed_by"] == "USER_FINAL"
print(f"       -> 2026-10 확정 이력 {hist_data['total_count']}건 조회 성공 (서머리: 유지 {hist_data['summary']['maintain']}건, 상향 {hist_data['summary']['upgrade']}건)")

# 5. 이력 엑셀 다운로드 API 검증
res_excel = client.get("/api/v1/excel/history?base_year_month=2026-10")
assert res_excel.status_code == 200
assert len(res_excel.content) > 1000, "Excel content is too small"
print(f"[PASS 6/6] 2026-10 확정본 엑셀 다운로드 성공: {len(res_excel.content)} bytes")

print("\n🎉 모든 핵심 개선 요건 및 API / 크롤러 정밀 검증 100% 통과!")
