import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.institution import Institution, AgencyInstitutionMapping
from app.models.current_rating import CurrentRating
from app.models.rating_history import CreditRatingHistory

router = APIRouter(prefix="/excel", tags=["Excel"])

HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
HEADER_FONT = Font(name="Pretendard", size=10, bold=True, color="FFFFFF")
REGULAR_FONT = Font(name="Pretendard", size=9)
FINAL_FONT = Font(name="Pretendard", size=10, bold=True, color="0284C7")
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")
LEFT_ALIGN = Alignment(horizontal="left", vertical="center")
THIN_BORDER = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)

@router.get("/download")
def download_excel_report(db: Session = Depends(get_db)):
    """PRD 제30조 4개 시트 엑셀 보고서 다운로드"""
    wb = openpyxl.Workbook()

    # Sheet 1: 조사결과 (화면 그리드 100% 일치 2단 헤더)
    ws1 = wb.active
    ws1.title = "당월_신용등급_현황"
    
    # 1행 (대분류)
    ws1.append([
        "업권", "상품제공기관",
        "최종 결정 신용등급 (3사 최저)", None, None,
        "한국기업평가", None,
        "한국신용평가", None,
        "NICE신용평가", None,
        "수집상태"
    ])
    # 2행 (소분류)
    ws1.append([
        None, None,
        "전월등급", "당월등급", "전월대비",
        "등급/전망", "등급확정일",
        "등급/전망", "등급확정일",
        "등급/전망", "등급확정일",
        None
    ])

    # 2단 헤더 셀 병합
    ws1.merge_cells("A1:A2")
    ws1.merge_cells("B1:B2")
    ws1.merge_cells("C1:E1")
    ws1.merge_cells("F1:G1")
    ws1.merge_cells("H1:I1")
    ws1.merge_cells("J1:K1")
    ws1.merge_cells("L1:L2")

    ratings = db.query(CurrentRating).join(Institution).order_by(Institution.institution_id).all()
    for r in ratings:
        inst = r.institution

        kr_fmt = f"{r.kr_rating} ({r.kr_outlook})" if r.kr_rating and r.kr_outlook else (r.kr_rating or "-")
        kis_fmt = f"{r.kis_rating} ({r.kis_outlook})" if r.kis_rating and r.kis_outlook else (r.kis_rating or "-")
        nice_fmt = f"{r.nice_rating} ({r.nice_outlook})" if r.nice_rating and r.nice_outlook else (r.nice_rating or "-")

        ws1.append([
            get_industry_korean(inst.industry_type),
            inst.institution_name,
            r.prev_final_rating or "-",
            r.final_rating or "-",
            r.rating_change_label or "신규",
            kr_fmt,
            r.kr_date or "-",
            kis_fmt,
            r.kis_date or "-",
            nice_fmt,
            r.nice_date or "-",
            get_status_korean(r.overall_status)
        ])

    # Sheet 2: 월별변동분석 (현업 보고용)
    ws_change = wb.create_sheet(title="월별변동분석")
    headers_change = [
        "업권", "상품제공기관", "전월 최종등급", "당월 최종등급", "전월대비 변동",
        "산출근거", "한국기업평가", "한국신용평가", "NICE신용평가"
    ]
    ws_change.append(headers_change)
    for r in ratings:
        inst = r.institution
        kr_str = f"{r.kr_rating or '-'} ({r.kr_date or '-'})" if r.kr_rating else "-"
        kis_str = f"{r.kis_rating or '-'} ({r.kis_date or '-'})" if r.kis_rating else "-"
        nice_str = f"{r.nice_rating or '-'} ({r.nice_date or '-'})" if r.nice_rating else "-"
        ws_change.append([
            get_industry_korean(inst.industry_type),
            inst.institution_name,
            r.prev_final_rating or "-",
            r.final_rating or "-",
            r.rating_change_label or "신규",
            r.calculation_logic or "-",
            kr_str,
            kis_str,
            nice_str
        ])

    # Sheet 3: 수집상태
    ws2 = wb.create_sheet(title="수집상태")
    headers2 = ["기관명", "업권", "평가대상상품", "전체상태", "한기평 상태", "한신평 상태", "NICE 상태", "산출근거"]
    ws2.append(headers2)
    for r in ratings:
        inst = r.institution
        ws2.append([
            inst.institution_name,
            get_industry_korean(inst.industry_type),
            get_rating_type_korean(inst.rating_type),
            r.overall_status,
            r.kr_status,
            r.kis_status,
            r.nice_status,
            r.calculation_logic or "-"
        ])

    # Sheet 3: 등급변경이력
    ws3 = wb.create_sheet(title="등급변경이력")
    headers3 = ["기관명", "평가사", "Rating Type", "등급", "확정일", "기록일시"]
    ws3.append(headers3)
    histories = db.query(CreditRatingHistory).join(Institution).order_by(CreditRatingHistory.recorded_at.desc()).limit(500).all()
    for h in histories:
        inst = h.institution
        ws3.append([
            inst.institution_name,
            h.agency_code,
            h.rating_type,
            h.rating,
            h.rating_date or "-",
            h.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if h.recorded_at else "-"
        ])

    # Sheet 4: 기관Mapping
    ws4 = wb.create_sheet(title="기관Mapping")
    headers4 = ["기관ID", "표준기관명", "엑셀원본명", "업권", "평가사", "검색명", "공식매핑명", "매핑상태"]
    ws4.append(headers4)
    mappings = db.query(AgencyInstitutionMapping).join(Institution).order_by(Institution.institution_id).all()
    for m in mappings:
        inst = m.institution
        ws4.append([
            inst.institution_id,
            inst.institution_name,
            inst.original_name,
            get_industry_korean(inst.industry_type),
            m.agency_code,
            m.search_name,
            m.alias_name or "-",
            m.mapping_status
        ])

    # 스타일 적용 (모든 시트)
    # Sheet 1은 2단 헤더이므로 1~2행에 헤더 스타일 적용
    for col_idx in range(1, ws1.max_column + 1):
        for r_idx in [1, 2]:
            cell = ws1.cell(row=r_idx, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
        ws1.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 16

    for row_idx in range(3, ws1.max_row + 1):
        for col_idx in range(1, ws1.max_column + 1):
            c = ws1.cell(row=row_idx, column=col_idx)
            c.font = REGULAR_FONT
            c.border = THIN_BORDER
            if col_idx == 4: # 당월등급
                c.font = FINAL_FONT
                c.alignment = CENTER_ALIGN
            elif col_idx == 2: # 상품제공기관
                c.alignment = LEFT_ALIGN
            else:
                c.alignment = CENTER_ALIGN

    # Sheet 2, 3, 4, 5 (1단 헤더)
    for ws in [ws_change, ws2, ws3, ws4]:
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 18

        for row_idx in range(2, ws.max_row + 1):
            for col_idx in range(1, ws.max_column + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.font = REGULAR_FONT
                c.border = THIN_BORDER
                if col_idx == 1:
                    c.alignment = LEFT_ALIGN
                else:
                    c.alignment = CENTER_ALIGN

    # 메모리 스트림 출력
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"credit_rating_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/history")
def download_history_excel(base_year_month: str, db: Session = Depends(get_db)):
    """특정 기준년월의 최종 확정 신용등급 보고서 엑셀 다운로드"""
    from app.models.monthly_confirmation import MonthlyConfirmedRating
    
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = f"{base_year_month}_확정결과"

    # 1행 (대분류)
    ws1.append(["업권", "상품제공기관", "전월등급", "당월확정등급", "전월대비", "한국기업평가", None, "한국신용평가", None, "NICE신용평가", None])
    # 2행 (소분류)
    ws1.append([None, None, None, None, None, "신용등급", "등급확정일", "신용등급", "등급확정일", "신용등급", "등급확정일"])

    # 2단 헤더 병합
    ws1.merge_cells("A1:A2")
    ws1.merge_cells("B1:B2")
    ws1.merge_cells("C1:C2")
    ws1.merge_cells("D1:D2")
    ws1.merge_cells("E1:E2")
    ws1.merge_cells("F1:G1")
    ws1.merge_cells("H1:I1")
    ws1.merge_cells("J1:K1")

    records = db.query(MonthlyConfirmedRating).filter_by(base_year_month=base_year_month).all()
    for r in records:
        ws1.append([
            get_industry_korean(r.industry_type),
            r.institution_name,
            r.prev_final_rating or "-",
            r.final_rating or "-",
            r.rating_change_label or "유지",
            r.kr_rating or "-",
            r.kr_date or "-",
            r.kis_rating or "-",
            r.kis_date or "-",
            r.nice_rating or "-",
            r.nice_date or "-"
        ])

    # 헤더 스타일링
    for row in range(1, 3):
        for col in range(1, 12):
            cell = ws1.cell(row=row, column=col)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

    for col_idx in range(1, 12):
        ws1.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 15

    for row_idx in range(3, ws1.max_row + 1):
        for col_idx in range(1, ws1.max_column + 1):
            c = ws1.cell(row=row_idx, column=col_idx)
            c.font = REGULAR_FONT
            c.border = THIN_BORDER
            if col_idx in [3, 4]:
                c.font = FINAL_FONT
                c.alignment = CENTER_ALIGN
            elif col_idx == 2:
                c.alignment = LEFT_ALIGN
            else:
                c.alignment = CENTER_ALIGN

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"credit_rating_confirmed_{base_year_month}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def get_industry_korean(code: str) -> str:
    map = {
        "BANK": "은행",
        "SAVINGS_BANK": "저축은행",
        "SECURITIES": "증권",
        "LIFE_INSURANCE": "생명보험",
        "NON_LIFE_INSURANCE": "손해보험"
    }
    return map.get(code, code)

def get_rating_type_korean(code: str) -> str:
    map = {
        "CORPORATE_CREDIT": "기업신용평가",
        "SENIOR_BOND": "선순위 회사채",
        "INSURANCE_FINANCIAL_STRENGTH": "보험지급능력평가"
    }
    return map.get(code, code)

def get_status_korean(code: str) -> str:
    map = {
        "SUCCESS": "정상",
        "NO_RATING": "미공시",
        "MANUAL_CHECK": "확인필요",
        "MANUAL_REVIEW": "수동확인",
        "CRAWLING_ERROR": "수집오류",
        "PARSING_ERROR": "파싱오류",
        "AUTH_REQUIRED": "인증필요"
    }
    return map.get(code, code or "-")
