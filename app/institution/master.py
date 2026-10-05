import openpyxl
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.core.config import BASE_DIR
from app.core.database import SessionLocal
from app.models.enums import IndustryType, AgencyCode, CollectionStatus
from app.models.institution import Institution, AgencyInstitutionMapping
from app.models.current_rating import CurrentRating
from app.institution.matcher import (
    normalize_institution_name,
    determine_industry_and_rating_type,
    get_agency_search_keyword
)

INDUSTRY_CODE_MAP = {
    IndustryType.BANK.value: "BNK",
    IndustryType.SAVINGS_BANK.value: "SAV",
    IndustryType.SECURITIES.value: "SEC",
    IndustryType.LIFE_INSURANCE.value: "LIF",
    IndustryType.NON_LIFE_INSURANCE.value: "NLI",
}

def load_initial_institutions_from_excel(excel_path: str = None) -> List[Dict[str, Any]]:
    """엑셀 파일에서 상품제공기관 목록을 읽어 정규화 및 마스터 데이터 구조로 변환"""
    if excel_path is None:
        excel_path = str(BASE_DIR / "자료" / "상품제공기관명.xlsx")

    wb = openpyxl.load_workbook(excel_path)
    ws = wb.active

    items = []
    counters: Dict[str, int] = {}

    for row in ws.iter_rows(values_only=True):
        if not row or not row[0]:
            continue
        raw_name = str(row[0]).strip()
        raw_industry = str(row[1]).strip() if len(row) > 1 and row[1] else ""

        # 헤더 건너뛰기
        if raw_name in ["상품제공기관명", "기관명", "회사명"]:
            continue

        industry_type, rating_type = determine_industry_and_rating_type(raw_industry, raw_name)

        # PRD 제3조: 우체국은 조사 대상에서 제외
        if industry_type == IndustryType.POST.value or "우체국" in raw_name:
            continue

        normalized_name = normalize_institution_name(raw_name)

        # 일련번호 부여
        ind_prefix = INDUSTRY_CODE_MAP.get(industry_type, "ETC")
        counters[ind_prefix] = counters.get(ind_prefix, 0) + 1
        inst_id = f"INS_{ind_prefix}_{counters[ind_prefix]:03d}"

        items.append({
            "institution_id": inst_id,
            "institution_name": normalized_name,
            "original_name": raw_name,
            "industry_type": industry_type,
            "rating_type": rating_type,
        })

    return items

def seed_institutions_to_db(db: Session = None) -> int:
    """초기 마스터 및 평가사 매핑, 현재 등급 상태를 DB에 적재"""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        institutions_data = load_initial_institutions_from_excel()
        count = 0

        for item in institutions_data:
            existing = db.query(Institution).filter_by(institution_id=item["institution_id"]).first()
            if not existing:
                inst = Institution(
                    institution_id=item["institution_id"],
                    institution_name=item["institution_name"],
                    original_name=item["original_name"],
                    industry_type=item["industry_type"],
                    rating_type=item["rating_type"],
                    use_yn="Y"
                )
                db.add(inst)

                # 초기 CurrentRating 생성
                current_rt = CurrentRating(
                    institution_id=item["institution_id"],
                    kr_status=CollectionStatus.NO_RATING.value,
                    kis_status=CollectionStatus.NO_RATING.value,
                    nice_status=CollectionStatus.NO_RATING.value,
                    overall_status=CollectionStatus.NO_RATING.value
                )
                db.add(current_rt)

                # 3개 평가사 매핑 기본 생성
                for agency in [AgencyCode.KR.value, AgencyCode.KIS.value, AgencyCode.NICE.value]:
                    search_kw = get_agency_search_keyword(item["institution_name"], agency)
                    mapping = AgencyInstitutionMapping(
                        institution_id=item["institution_id"],
                        agency_code=agency,
                        search_name=search_kw,
                        alias_name=item["original_name"],
                        mapping_status="AUTO_MAPPED",
                        confidence=1.0
                    )
                    db.add(mapping)

                count += 1

        db.commit()
        return count
    finally:
        if should_close:
            db.close()

if __name__ == "__main__":
    seeded = seed_institutions_to_db()
    print(f"Seeded {seeded} institutions into database.")
