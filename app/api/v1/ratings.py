from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.institution import Institution
from app.models.current_rating import CurrentRating
from app.models.rating_raw import CreditRatingRaw
from app.models.monthly_confirmation import MonthlyConfirmedRating
from app.schemas.rating import (
    CurrentRatingResponse,
    CurrentRatingDetailResponse,
    AgencyDetailInfo,
    ConfirmRatingRequest,
    MonthlyHistoryResponse,
    MonthlyHistorySummary,
    MonthlyConfirmedRatingItem
)

router = APIRouter(prefix="/ratings", tags=["Ratings"])

RATING_TYPE_MAP = {
    "CORPORATE_CREDIT": "기업신용평가 (Issuer)",
    "SENIOR_BOND": "선순위 회사채 (Senior Bond)",
    "INSURANCE_FINANCIAL_STRENGTH": "보험금지급능력 (IFSR)",
}

AGENCY_NAMES = {
    "KR": "한국기업평가",
    "KIS": "한국신용평가",
    "NICE": "NICE신용평가"
}

@router.post("/confirm")
def confirm_monthly_ratings(payload: ConfirmRatingRequest, db: Session = Depends(get_db)):
    """
    당월 신용등급 최종 확정 API (Last-Win 적용)
    - 사용자가 화면에서 검토 후 최종 확정을 누를 때 호출됨
    - 동월(base_year_month)에 여러 번 확정 시 기존 내역을 최신 내역으로 덮어씀 (Last-Win)
    """
    now = datetime.now()
    target_ym = payload.base_year_month or now.strftime("%Y-%m")

    # 1. 현재 조사된 활성 기관 전체 목록 조회
    current_ratings = db.query(CurrentRating).join(
        Institution, CurrentRating.institution_id == Institution.institution_id
    ).filter(Institution.use_yn == "Y").all()

    if not current_ratings:
        raise HTTPException(status_code=400, detail="확정할 조사 내역이 없습니다. 먼저 조사를 실행해주세요.")

    # 2. 동월(base_year_month) 기존 확정 데이터가 있다면 일괄 삭제 (Last-Win: 덮어쓰기)
    deleted_count = db.query(MonthlyConfirmedRating).filter_by(base_year_month=target_ym).delete()

    # 3. 신규 스냅샷 저장
    new_records = []
    for cr in current_ratings:
        inst = cr.institution
        rec = MonthlyConfirmedRating(
            base_year_month=target_ym,
            institution_id=cr.institution_id,
            institution_name=inst.institution_name,
            original_name=inst.original_name,
            industry_type=inst.industry_type,
            rating_type=inst.rating_type,
            rating_type_name=RATING_TYPE_MAP.get(inst.rating_type, inst.rating_type),
            final_rating=cr.final_rating,
            prev_final_rating=cr.prev_final_rating,
            rating_change_status=cr.rating_change_status or "NEW",
            rating_change_notch=cr.rating_change_notch or 0,
            rating_change_label=cr.rating_change_label or "신규",
            calculation_logic=cr.calculation_logic,
            overall_status=cr.overall_status,
            kr_rating=cr.kr_rating,
            kr_date=cr.kr_date,
            kr_status=cr.kr_status,
            kis_rating=cr.kis_rating,
            kis_date=cr.kis_date,
            kis_status=cr.kis_status,
            nice_rating=cr.nice_rating,
            nice_date=cr.nice_date,
            nice_status=cr.nice_status,
            confirmed_at=now,
            confirmed_by=payload.confirmed_by or "USER"
        )
        new_records.append(rec)
        db.add(rec)

    db.commit()

    return {
        "status": "success",
        "message": f"{target_ym} 신용등급이 최종 확정되었습니다.",
        "base_year_month": target_ym,
        "confirmed_count": len(new_records),
        "previous_overwritten": deleted_count > 0,
        "confirmed_at": now.isoformat(),
        "confirmed_by": payload.confirmed_by or "USER"
    }

@router.get("/history/months")
def get_confirmed_months(db: Session = Depends(get_db)):
    """확정 이력이 존재하는 년월 목록 반환 (최신순)"""
    months = db.query(MonthlyConfirmedRating.base_year_month).distinct().order_by(
        desc(MonthlyConfirmedRating.base_year_month)
    ).all()
    return {"months": [m[0] for m in months]}

@router.get("/history", response_model=MonthlyHistoryResponse)
def get_monthly_history(
    base_year_month: str = Query(..., description="기준년월 (예: 2026-10)"),
    industry: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """특정 년월의 확정 이력 상세 조회 및 변동 요약 반환"""
    query = db.query(MonthlyConfirmedRating).filter_by(base_year_month=base_year_month)
    
    if industry and industry != "ALL":
        query = query.filter(MonthlyConfirmedRating.industry_type == industry)
    if status and status != "ALL":
        query = query.filter(MonthlyConfirmedRating.overall_status == status)
    if search:
        query = query.filter(
            (MonthlyConfirmedRating.institution_name.ilike(f"%{search}%")) |
            (MonthlyConfirmedRating.original_name.ilike(f"%{search}%"))
        )

    records = query.all()
    if not records:
        # 비어있는 경우
        return MonthlyHistoryResponse(
            base_year_month=base_year_month,
            confirmed_at=None,
            confirmed_by=None,
            total_count=0,
            summary=MonthlyHistorySummary(),
            items=[]
        )

    # 서머리 계산
    maintain_cnt = 0
    upgrade_cnt = 0
    downgrade_cnt = 0
    new_cnt = 0
    err_cnt = 0

    confirmed_at = records[0].confirmed_at
    confirmed_by = records[0].confirmed_by

    items = []
    for r in records:
        st = r.rating_change_status
        if st == "MAINTAIN":
            maintain_cnt += 1
        elif st == "UPGRADE":
            upgrade_cnt += 1
        elif st == "DOWNGRADE":
            downgrade_cnt += 1
        elif st == "NEW":
            new_cnt += 1

        if r.overall_status in ["CRAWLING_ERROR", "PARSING_ERROR", "MANUAL_CHECK"]:
            err_cnt += 1

        items.append(MonthlyConfirmedRatingItem.model_validate(r))

    return MonthlyHistoryResponse(
        base_year_month=base_year_month,
        confirmed_at=confirmed_at,
        confirmed_by=confirmed_by,
        total_count=len(records),
        summary=MonthlyHistorySummary(
            total=len(records),
            maintain=maintain_cnt,
            upgrade=upgrade_cnt,
            downgrade=downgrade_cnt,
            new=new_cnt,
            error=err_cnt
        ),
        items=items
    )

@router.get("", response_model=List[CurrentRatingResponse])
def get_current_ratings(
    industry: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(CurrentRating).join(Institution, CurrentRating.institution_id == Institution.institution_id)
    query = query.filter(Institution.use_yn == "Y")

    if industry and industry != "ALL":
        query = query.filter(Institution.industry_type == industry)
    if status and status != "ALL":
        query = query.filter(CurrentRating.overall_status == status)
    if search:
        query = query.filter(
            (Institution.institution_name.ilike(f"%{search}%")) |
            (Institution.original_name.ilike(f"%{search}%"))
        )

    ratings = query.all()
    results = []
    for r in ratings:
        inst = r.institution
        results.append(CurrentRatingResponse(
            institution_id=r.institution_id,
            institution_name=inst.institution_name,
            original_name=inst.original_name,
            industry_type=inst.industry_type,
            rating_type=inst.rating_type,
            rating_type_name=RATING_TYPE_MAP.get(inst.rating_type, inst.rating_type),
            final_rating=r.final_rating,
            prev_final_rating=r.prev_final_rating,
            rating_change_status=r.rating_change_status or "NEW",
            rating_change_notch=r.rating_change_notch or 0,
            rating_change_label=r.rating_change_label or "신규",
            is_ambiguous=r.is_ambiguous or False,
            overall_status=r.overall_status,
            calculation_logic=r.calculation_logic,
            kr_rating=r.kr_rating,
            kr_date=r.kr_date,
            kr_status=r.kr_status,
            kr_url=r.kr_url,
            kr_rating_type=r.kr_rating_type,
            kr_outlook=r.kr_outlook,
            kis_rating=r.kis_rating,
            kis_date=r.kis_date,
            kis_status=r.kis_status,
            kis_url=r.kis_url,
            kis_rating_type=r.kis_rating_type,
            kis_outlook=r.kis_outlook,
            nice_rating=r.nice_rating,
            nice_date=r.nice_date,
            nice_status=r.nice_status,
            nice_url=r.nice_url,
            nice_rating_type=r.nice_rating_type,
            nice_outlook=r.nice_outlook,
            search_name_1=inst.search_name_1,
            search_name_2=inst.search_name_2,
            kr_target_rating=inst.kr_target_rating,
            kis_target_rating=inst.kis_target_rating,
            nice_target_rating=inst.nice_target_rating,
            evaluated_at=r.evaluated_at
        ))
    return results

@router.get("/{institution_id}", response_model=CurrentRatingResponse)
def get_institution_rating(institution_id: str, db: Session = Depends(get_db)):
    r = db.query(CurrentRating).filter_by(institution_id=institution_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="신용등급 정보를 찾을 수 없습니다.")
    inst = r.institution
    return CurrentRatingResponse(
        institution_id=r.institution_id,
        institution_name=inst.institution_name,
        original_name=inst.original_name,
        industry_type=inst.industry_type,
        rating_type=inst.rating_type,
        rating_type_name=RATING_TYPE_MAP.get(inst.rating_type, inst.rating_type),
        final_rating=r.final_rating,
        prev_final_rating=r.prev_final_rating,
        rating_change_status=r.rating_change_status or "NEW",
        rating_change_notch=r.rating_change_notch or 0,
        rating_change_label=r.rating_change_label or "신규",
        is_ambiguous=r.is_ambiguous or False,
        overall_status=r.overall_status,
        calculation_logic=r.calculation_logic,
        kr_rating=r.kr_rating,
        kr_date=r.kr_date,
        kr_status=r.kr_status,
        kr_url=r.kr_url,
        kr_rating_type=r.kr_rating_type,
        kr_outlook=r.kr_outlook,
        kis_rating=r.kis_rating,
        kis_date=r.kis_date,
        kis_status=r.kis_status,
        kis_url=r.kis_url,
        kis_rating_type=r.kis_rating_type,
        kis_outlook=r.kis_outlook,
        nice_rating=r.nice_rating,
        nice_date=r.nice_date,
        nice_status=r.nice_status,
        nice_url=r.nice_url,
        nice_rating_type=r.nice_rating_type,
        nice_outlook=r.nice_outlook,
        search_name_1=inst.search_name_1,
        search_name_2=inst.search_name_2,
        kr_target_rating=inst.kr_target_rating,
        kis_target_rating=inst.kis_target_rating,
        nice_target_rating=inst.nice_target_rating,
        evaluated_at=r.evaluated_at
    )

@router.get("/{institution_id}/detail", response_model=CurrentRatingDetailResponse)
def get_institution_rating_detail(institution_id: str, db: Session = Depends(get_db)):
    """신용등급 검증용 3사 원본 공시 상세 내역 반환"""
    r = db.query(CurrentRating).filter_by(institution_id=institution_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="신용등급 정보를 찾을 수 없습니다.")
    inst = r.institution

    agencies = []
    # KR, KIS, NICE 순
    for code, name in [("KR", "한국기업평가"), ("KIS", "한국신용평가"), ("NICE", "NICE신용평가")]:
        raw_rec = db.query(CreditRatingRaw).filter_by(
            institution_id=institution_id,
            agency_code=code
        ).order_by(CreditRatingRaw.collected_at.desc()).first()

        rating_val = getattr(r, f"{code.lower()}_rating", None)
        date_val = getattr(r, f"{code.lower()}_date", None)
        status_val = getattr(r, f"{code.lower()}_status", "NO_RATING")
        url_val = getattr(r, f"{code.lower()}_url", None)

        agencies.append(AgencyDetailInfo(
            agency_code=code,
            agency_name=name,
            rating=rating_val,
            raw_rating=raw_rec.raw_rating if raw_rec else rating_val,
            rating_type_raw=getattr(r, f"{code.lower()}_rating_type", None) or (raw_rec.rating_type if raw_rec else None),
            outlook=getattr(r, f"{code.lower()}_outlook", None),
            rating_date=date_val,
            valid_to=raw_rec.valid_to if raw_rec else None,
            status=status_val,
            source_url=url_val or (raw_rec.source_url if raw_rec else None),
            error_message=raw_rec.error_message if raw_rec else None
        ))

    return CurrentRatingDetailResponse(
        institution_id=r.institution_id,
        institution_name=inst.institution_name,
        original_name=inst.original_name,
        industry_type=inst.industry_type,
        rating_type=inst.rating_type,
        rating_type_name=RATING_TYPE_MAP.get(inst.rating_type, inst.rating_type),
        final_rating=r.final_rating,
        overall_status=r.overall_status,
        calculation_logic=r.calculation_logic,
        agencies=agencies,
        evaluated_at=r.evaluated_at
    )

@router.post("/{institution_id}/sync", response_model=CurrentRatingResponse)
def sync_single_institution(institution_id: str, db: Session = Depends(get_db)):
    """
    단일 기관 즉시 실시간 재조회/동기화 API
    - 전체 85개 조사를 기다릴 필요 없이 해당 기관 1건만 즉시 크롤링 및 최저등급 산출
    - CurrentRating 테이블 및 변동 분석 즉시 갱신
    """
    inst = db.query(Institution).filter_by(institution_id=institution_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="해당 기관을 찾을 수 없습니다.")

    from app.jobs.collector_job import _collect_for_single_institution
    from app.rating.change_analyzer import analyze_rating_change
    from app.models.current_rating import CurrentRating
    from app.models.rating_raw import CreditRatingRaw
    from datetime import date

    today_str = date.today().isoformat()
    targets_dict = {
        "KR": inst.kr_target_rating or "",
        "KIS": inst.kis_target_rating or "",
        "NICE": inst.nice_target_rating or ""
    }

    # 전월 확정 이력 조회
    from app.models.monthly_confirmation import MonthlyConfirmedRating
    from datetime import timedelta
    today = date.today()
    first_day_of_month = today.replace(day=1)
    last_month_date = first_day_of_month - timedelta(days=1)
    prev_ym = last_month_date.strftime("%Y-%m")
    prev_conf = db.query(MonthlyConfirmedRating).filter(
        MonthlyConfirmedRating.institution_id == inst.institution_id,
        MonthlyConfirmedRating.base_year_month == prev_ym
    ).first()
    prev_rating = prev_conf.final_rating if prev_conf else None

    # 1. 단일 기관 3대 평가사 즉시 수집
    inst_res = _collect_for_single_institution(
        inst_id=inst.institution_id,
        inst_name=inst.institution_name,
        rating_type=inst.rating_type,
        search_1=inst.search_name_1 or inst.institution_name,
        search_2=inst.search_name_2 or "",
        targets_dict=targets_dict,
        execution_date_str=today_str,
        prev_final_rating=prev_rating
    )

    # 2. Raw 결과 저장
    for ag_res in inst_res.agency_results:
        raw_rec = CreditRatingRaw(
            institution_id=inst.institution_id,
            agency_code=ag_res.agency_code,
            rating_type=inst.rating_type,
            raw_rating=ag_res.rating_res.raw_rating,
            normalized_rating=ag_res.rating_res.rating,
            rating_date=ag_res.rating_res.rating_date,
            valid_from=ag_res.rating_res.valid_from,
            valid_to=ag_res.rating_res.valid_to,
            collection_status=ag_res.rating_res.status,
            source_url=ag_res.rating_res.source_url,
            raw_data=ag_res.rating_res.raw_data,
            error_message=ag_res.rating_res.error_message,
            collected_at=datetime.utcnow()
        )
        db.add(raw_rec)

    # 3. CurrentRating 업데이트
    curr = db.query(CurrentRating).filter_by(institution_id=inst.institution_id).first()
    if not curr:
        curr = CurrentRating(institution_id=inst.institution_id)
        db.add(curr)

    # 평가사별 수집 결과 매핑
    agency_map = {ag.agency_code: ag.rating_res for ag in inst_res.agency_results}
    kr_res = agency_map.get("KR")
    kis_res = agency_map.get("KIS")
    nice_res = agency_map.get("NICE")

    if kr_res:
        curr.kr_rating = kr_res.rating
        curr.kr_date = kr_res.rating_date
        curr.kr_status = kr_res.status
        curr.kr_url = kr_res.source_url
        curr.kr_rating_type = kr_res.rating_type_raw
        curr.kr_outlook = kr_res.outlook
    if kis_res:
        curr.kis_rating = kis_res.rating
        curr.kis_date = kis_res.rating_date
        curr.kis_status = kis_res.status
        curr.kis_url = kis_res.source_url
        curr.kis_rating_type = kis_res.rating_type_raw
        curr.kis_outlook = kis_res.outlook
    if nice_res:
        curr.nice_rating = nice_res.rating
        curr.nice_date = nice_res.rating_date
        curr.nice_status = nice_res.status
        curr.nice_url = nice_res.source_url
        curr.nice_rating_type = nice_res.rating_type_raw
        curr.nice_outlook = nice_res.outlook

    curr.final_rating = inst_res.calc_result.final_rating
    curr.overall_status = inst_res.calc_result.overall_status
    curr.calculation_logic = inst_res.calc_result.calculation_logic
    curr.evaluated_at = datetime.utcnow()

    # 4. 전월 대비 변동 분석 (prev_final_rating 기준)
    change_status, notch_delta, change_label = analyze_rating_change(
        prev_rating=curr.prev_final_rating,
        curr_rating=curr.final_rating
    )
    curr.rating_change_status = change_status
    curr.rating_change_notch = notch_delta
    curr.rating_change_label = change_label

    db.commit()
    db.refresh(curr)

    return CurrentRatingResponse(
        institution_id=curr.institution_id,
        institution_name=inst.institution_name,
        original_name=inst.original_name,
        industry_type=inst.industry_type,
        rating_type=inst.rating_type,
        rating_type_name=RATING_TYPE_MAP.get(inst.rating_type, inst.rating_type),
        final_rating=curr.final_rating,
        prev_final_rating=curr.prev_final_rating,
        rating_change_status=curr.rating_change_status or "NEW",
        rating_change_notch=curr.rating_change_notch or 0,
        rating_change_label=curr.rating_change_label or "신규",
        is_ambiguous=curr.is_ambiguous or False,
        overall_status=curr.overall_status,
        calculation_logic=curr.calculation_logic,
        kr_rating=curr.kr_rating,
        kr_date=curr.kr_date,
        kr_status=curr.kr_status,
        kr_url=curr.kr_url,
        kr_rating_type=curr.kr_rating_type,
        kr_outlook=curr.kr_outlook,
        kis_rating=curr.kis_rating,
        kis_date=curr.kis_date,
        kis_status=curr.kis_status,
        kis_url=curr.kis_url,
        kis_rating_type=curr.kis_rating_type,
        kis_outlook=curr.kis_outlook,
        nice_rating=curr.nice_rating,
        nice_date=curr.nice_date,
        nice_status=curr.nice_status,
        nice_url=curr.nice_url,
        nice_rating_type=curr.nice_rating_type,
        nice_outlook=curr.nice_outlook,
        search_name_1=inst.search_name_1,
        search_name_2=inst.search_name_2,
        kr_target_rating=inst.kr_target_rating,
        kis_target_rating=inst.kis_target_rating,
        nice_target_rating=inst.nice_target_rating,
        evaluated_at=curr.evaluated_at
    )

