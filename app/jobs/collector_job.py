import uuid
import time
import random
import threading
import logging
from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.enums import CollectionStatus, JobStatus, ExecutionType, AgencyCode
from app.models.institution import Institution
from app.models.current_rating import CurrentRating
from app.models.monthly_confirmation import MonthlyConfirmedRating
from app.models.rating_raw import CreditRatingRaw
from app.models.rating_history import CreditRatingHistory
from app.models.job_log import CollectionJob, CollectionLog
from app.collectors import ADAPTERS
from app.rating.calculator import calculate_final_rating
from app.rating.change_analyzer import analyze_rating_change
from app.schemas.rating import StandardRating
from app.institution.search_candidates import generate_search_candidates

logger = logging.getLogger(__name__)

@dataclass
class AgencyCollectResult:
    agency_code: str
    rating_res: StandardRating
    started_at: datetime
    finished_at: datetime

@dataclass
class InstitutionCollectResult:
    institution_id: str
    institution_name: str
    rating_type: str
    agency_results: List[AgencyCollectResult]
    calc_result: Any

# 실시간 진행상태 추적 글로벌 상태 객체 및 중단 이벤트 플래그
STOP_COLLECTION_EVENT = threading.Event()
_JOB_TRIGGER_LOCK = threading.RLock()

ACTIVE_JOB_PROGRESS: Dict[str, Any] = {
    "is_running": False,
    "is_stopping": False,
    "job_id": None,
    "total_count": 0,
    "processed_count": 0,
    "success_count": 0,
    "no_rating_count": 0,
    "error_count": 0,
    "manual_check_count": 0,
    "current_institution": "",
    "progress_percent": 0.0,
    "started_at": None,
}

def get_active_job_progress() -> Dict[str, Any]:
    return dict(ACTIVE_JOB_PROGRESS)

def request_stop_collection() -> bool:
    """진행 중인 일괄 수집 작업에 중단 신호를 전달"""
    STOP_COLLECTION_EVENT.set()
    return True


def _collect_for_single_institution(
    inst_id: str,
    inst_name: str,
    rating_type: str,
    search_1: str,
    search_2: str,
    targets_dict: Dict[str, str],
    execution_date_str: str,
    prev_final_rating: Optional[str] = None,
    search_3: str = ""
) -> InstitutionCollectResult:
    """
    단일 기관에 대한 3대 평가사 병렬 수집 전담 워커 (스레드 안전, DB 의존성 없음)
    """
    def _fetch_agency(agency_code: str):
        # 평가사별 맞춤형 속도 제어 및 WAF 차단 방지 (Rate Limiting)
        if agency_code == AgencyCode.KR.value:
            # 한국기업평가는 메모리 캐시에서 조회하므로 네트워크 지연 없이 즉시 수행
            pass
        elif agency_code == AgencyCode.KIS.value:
            time.sleep(random.uniform(0.15, 0.35))
        else:  # NICE
            time.sleep(random.uniform(0.1, 0.25))

        adapter = ADAPTERS.get(agency_code)
        target_name = targets_dict.get(agency_code, "")
        cands = generate_search_candidates(
            institution_name=inst_name,
            original_name=inst_name,
            agency_code=agency_code,
            search_name_1=search_1,
            search_name_2=search_2,
            search_name_3=search_3
        )
        start_time = datetime.now(timezone.utc)
        try:
            rating_res = adapter.get_ratings(
                institution_id=inst_id,
                search_name=search_1 or inst_name,
                rating_type=rating_type,
                original_name=inst_name,
                search_name_2=search_2 or "",
                target_rating_name=target_name,
                search_keywords=cands
            )
        except Exception as exc:
            rating_res = StandardRating(
                institution_id=inst_id,
                agency_code=agency_code,
                rating_type=rating_type,
                status=CollectionStatus.CRAWLING_ERROR.value,
                error_message=str(exc)
            )

        # 신규 표준 요건: 등급이 조회가 되었으나 등급확정일이 없는 경우 등급을 인정하고 MANUAL_REVIEW(수동확인)로 보존
        if rating_res and rating_res.rating and not rating_res.rating_date:
            if rating_res.status not in [CollectionStatus.MANUAL_REVIEW.value, CollectionStatus.MANUAL_CHECK.value]:
                rating_res.status = CollectionStatus.MANUAL_REVIEW.value

        end_time = datetime.now(timezone.utc)
        return agency_code, rating_res, start_time, end_time

    agency_results = []
    ratings_by_agency = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(_fetch_agency, code)
            for code in [AgencyCode.KR.value, AgencyCode.KIS.value, AgencyCode.NICE.value]
        ]
        for fut in as_completed(futures):
            code, rating_res, start_time, end_time = fut.result()
            ratings_by_agency[code] = rating_res
            agency_results.append(AgencyCollectResult(
                agency_code=code,
                rating_res=rating_res,
                started_at=start_time,
                finished_at=end_time
            ))

    calc_res = calculate_final_rating(
        institution_id=inst_id,
        kr=ratings_by_agency.get(AgencyCode.KR.value),
        kis=ratings_by_agency.get(AgencyCode.KIS.value),
        nice=ratings_by_agency.get(AgencyCode.NICE.value),
        execution_date=execution_date_str,
        prev_final_rating=prev_final_rating
    )

    return InstitutionCollectResult(
        institution_id=inst_id,
        institution_name=inst_name,
        rating_type=rating_type,
        agency_results=agency_results,
        calc_result=calc_res
    )

def reserve_collection_job(
    db: Session,
    execution_type: str,
    target_institution_ids: Optional[List[str]] = None
) -> Tuple[CollectionJob, int]:
    """
    수동 /run 및 자동 scheduler 공통 작업 예약 함수
    - _JOB_TRIGGER_LOCK을 통한 완벽한 다중 스레드 동시성 상호 배제 보장
    - 메모리 및 DB 상태를 검증하고, STOP_COLLECTION_EVENT.clear()
    - CollectionJob 레코드를 DB에 즉시 생성 & commit
    - ACTIVE_JOB_PROGRESS 플래그를 원자적으로 설정하여 반환
    """
    with _JOB_TRIGGER_LOCK:
        if ACTIVE_JOB_PROGRESS.get("is_running") or ACTIVE_JOB_PROGRESS.get("is_stopping"):
            raise RuntimeError("수집 작업이 이미 실행 중이거나 중단 정리 중입니다. 완전히 종료된 후 다시 시도해주세요.")

        running = db.query(CollectionJob).filter_by(status=JobStatus.RUNNING.value).first()
        if running:
            raise RuntimeError(f"이미 실행 중인 수집 작업({running.job_id})이 있어 새 작업을 시작할 수 없습니다.")

        STOP_COLLECTION_EVENT.clear()

        active_count = len(target_institution_ids) if target_institution_ids else db.query(Institution).filter(Institution.use_yn == "Y").count()
        job_id = f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
        job = CollectionJob(
            job_id=job_id,
            execution_type=execution_type,
            started_at=datetime.now(timezone.utc),
            status=JobStatus.RUNNING.value,
            total_count=active_count
        )
        db.add(job)
        db.commit()

        ACTIVE_JOB_PROGRESS.update({
            "is_running": True,
            "is_stopping": False,
            "job_id": job_id,
            "total_count": active_count,
            "processed_count": 0,
            "success_count": 0,
            "no_rating_count": 0,
            "error_count": 0,
            "manual_check_count": 0,
            "current_institution": "조사 엔진 기동 중...",
            "progress_percent": 3.0,
            "started_at": job.started_at.isoformat()
        })

        return job, active_count

def run_collection_batch(
    execution_type: str = ExecutionType.MANUAL_ALL.value,
    target_institution_ids: Optional[List[str]] = None,
    existing_job_id: Optional[str] = None
) -> str:
    """
    신용등급 자동수집 Batch 실행 엔진 (PRD 제31조, 33조, 34조, 35조)
    - ThreadPoolExecutor(max_workers=8)를 적용한 고성능 병렬 수집
    - Network I/O 병렬화 + DB 단일 스레드 안전 기록(Zero DB Lock)
    """
    db: Session = SessionLocal()
    job_id: Optional[str] = None
    target_inst_ids: List[str] = []
    try:
        if existing_job_id:
            job = db.query(CollectionJob).filter_by(job_id=existing_job_id).first()
            if not job:
                raise RuntimeError(f"예약된 작업({existing_job_id})을 찾을 수 없습니다.")
            job_id = existing_job_id
        else:
            job, _ = reserve_collection_job(
                db=db,
                execution_type=execution_type,
                target_institution_ids=target_institution_ids
            )
            job_id = job.job_id

        # 3. 조사 대상 기관 조회
        query = db.query(Institution).filter(Institution.use_yn == "Y")
        if target_institution_ids:
            query = query.filter(Institution.institution_id.in_(target_institution_ids))
        institutions = query.all()

        job.total_count = len(institutions)
        db.commit()

        ACTIVE_JOB_PROGRESS.update({
            "is_running": True,
            "job_id": job_id,
            "total_count": len(institutions),
            "processed_count": 0,
            "success_count": 0,
            "no_rating_count": 0,
            "error_count": 0,
            "manual_check_count": 0,
            "current_institution": "조사 준비 중...",
            "progress_percent": 0.0,
            "started_at": job.started_at.isoformat() if job.started_at else None,
        })

        if STOP_COLLECTION_EVENT.is_set():
            job.status = JobStatus.STOPPED.value
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = "사용자에 의해 조사가 중지되었습니다."
            db.commit()
            ACTIVE_JOB_PROGRESS.update({
                "is_running": False,
                "is_stopping": False,
                "current_institution": "조사 중지됨",
            })
            return job_id

        if not institutions:
            job.finished_at = datetime.now(timezone.utc)
            job.status = JobStatus.SUCCESS.value
            db.commit()
            ACTIVE_JOB_PROGRESS.update({
                "is_running": False,
                "is_stopping": False,
                "current_institution": "조사 완료",
            })
            return job_id

        success_count = 0
        no_rating_count = 0
        error_count = 0
        manual_check_count = 0

        execution_date_str = date.today().isoformat()

        # 4. 한국기업평가(KR) 공시 데이터 사전 1회 다운로드 (Zero-Traffic: 85회 호출을 단 1회로 압축)
        kr_adapter = ADAPTERS.get(AgencyCode.KR.value)
        if kr_adapter and hasattr(kr_adapter, "preload_disclosure_data"):
            try:
                ACTIVE_JOB_PROGRESS["current_institution"] = "한국기업평가 공시 데이터 사전 동기화 중..."
                kr_adapter.preload_disclosure_data(kr_adapter.headers, kr_adapter.base_url)
            except Exception as e:
                logger.warning(f"한국기업평가 사전 로드 실패 (진행 중 자동 대응): {e}")

        # 전월 확정 이력 사전 로드
        today = date.today()
        first_day_of_month = today.replace(day=1)
        last_month_date = first_day_of_month - timedelta(days=1)
        prev_ym = last_month_date.strftime("%Y-%m")

        prev_confirmed_records = db.query(MonthlyConfirmedRating).filter(
            MonthlyConfirmedRating.base_year_month == prev_ym
        ).all()
        prev_confirmed_map = {r.institution_id: r.final_rating for r in prev_confirmed_records if r.final_rating}

        # [사전 클렌징] 조사 대상 기관(전체/선택/오류재조회)의 CurrentRating을 COLLECTING(조사 진행 중)으로 초기화
        # (선택조사 및 오류재조회 시에는 대상 기관들만 초기화되고, 기타 정상 수집 기관 데이터는 100% 보존됨)
        target_inst_ids = [inst.institution_id for inst in institutions]
        target_currents = db.query(CurrentRating).filter(CurrentRating.institution_id.in_(target_inst_ids)).all()
        current_map = {c.institution_id: c for c in target_currents}

        for inst_id in target_inst_ids:
            cur = current_map.get(inst_id)
            if not cur:
                cur = CurrentRating(institution_id=inst_id)
                db.add(cur)

            cur.kr_rating = None
            cur.kr_status = CollectionStatus.COLLECTING.value
            cur.kr_date = None
            cur.kr_url = None
            cur.kr_rating_type = None
            cur.kr_outlook = None

            cur.kis_rating = None
            cur.kis_status = CollectionStatus.COLLECTING.value
            cur.kis_date = None
            cur.kis_url = None
            cur.kis_rating_type = None
            cur.kis_outlook = None

            cur.nice_rating = None
            cur.nice_status = CollectionStatus.COLLECTING.value
            cur.nice_date = None
            cur.nice_url = None
            cur.nice_rating_type = None
            cur.nice_outlook = None

            cur.final_rating = None
            cur.overall_status = CollectionStatus.COLLECTING.value
            cur.calculation_logic = "신용등급 조사 진행 중..."
            cur.rating_change_status = "NEW"
            cur.rating_change_notch = 0
            cur.rating_change_label = "조사 중..."

            # 전월 공식 등급 보존/설정 (이력 없으면 None으로 명시적 초기화하여 stale 등급 잔류 방지)
            if inst_id in prev_confirmed_map:
                cur.prev_final_rating = prev_confirmed_map[inst_id]
            else:
                cur.prev_final_rating = None

        db.commit()

        # 스레드 풀 작업을 위한 독립 튜플 데이터 추출 (전산요건 기반)
        inst_tasks = []
        for inst in institutions:
            targets_dict = {
                AgencyCode.KR.value: inst.kr_target_rating or "",
                AgencyCode.KIS.value: inst.kis_target_rating or "",
                AgencyCode.NICE.value: inst.nice_target_rating or "",
            }
            search_1 = inst.search_name_1 or inst.institution_name
            search_2 = inst.search_name_2 or ""
            search_3 = inst.search_name_3 or ""
            inst_tasks.append((
                inst.institution_id,
                inst.institution_name,
                inst.rating_type,
                search_1,
                search_2,
                targets_dict,
                prev_confirmed_map.get(inst.institution_id),
                search_3
            ))

        # 동시 작업자 수 최적화 (평가사 WAF IP 차단 방지를 위한 안전 4개 스레드)
        max_workers = min(4, len(inst_tasks))

        # 1차 수집 시 실패/누락된 기관 추적 (자동 치유 대상)
        failed_tasks_map = {}

        # 5. 멀티스레드 병렬 크롤링 실행 및 완료 순 DB 적재
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_inst = {
                executor.submit(
                    _collect_for_single_institution,
                    task[0], task[1], task[2], task[3], task[4], task[5], execution_date_str, task[6], task[7]
                ): task
                for task in inst_tasks
            }

            for future in as_completed(future_to_inst):
                if STOP_COLLECTION_EVENT.is_set():
                    logger.info(f"[CollectorJob] 사용자 중단 요청 감지. Job {job_id} 즉시 중지.")
                    for f in future_to_inst:
                        f.cancel()
                    job.status = JobStatus.STOPPED.value
                    job.finished_at = datetime.now(timezone.utc)
                    job.error_message = "사용자에 의해 조사가 중지되었습니다."
                    # 잔여 COLLECTING 기관 상태 정리 (확정 잠김 및 고착 방지)
                    for t_id in target_inst_ids:
                        c_rem = db.query(CurrentRating).filter_by(institution_id=t_id).first()
                        if c_rem and c_rem.overall_status == CollectionStatus.COLLECTING.value:
                            c_rem.overall_status = CollectionStatus.CRAWLING_ERROR.value
                            c_rem.calculation_logic = "사용자에 의해 조사가 중단되었습니다."
                    db.commit()
                    break

                orig_task = future_to_inst[future]
                res: InstitutionCollectResult = future.result()
                inst_id = res.institution_id
                calc_result = res.calc_result

                # (1) Raw Data 및 로그 기록
                for agency_item in res.agency_results:
                    r_res = agency_item.rating_res
                    log_entry = CollectionLog(
                        job_id=job_id,
                        institution_id=inst_id,
                        agency_code=agency_item.agency_code,
                        started_at=agency_item.started_at,
                        finished_at=agency_item.finished_at,
                        status=r_res.status,
                        message=r_res.error_message,
                        source_url=r_res.source_url
                    )
                    db.add(log_entry)

                    raw_record = CreditRatingRaw(
                        job_id=job_id,
                        institution_id=inst_id,
                        agency_code=agency_item.agency_code,
                        raw_rating=r_res.raw_rating,
                        normalized_rating=r_res.rating,
                        rating_type=r_res.rating_type,
                        raw_rating_date=r_res.rating_date,
                        rating_date=r_res.rating_date,
                        valid_to=r_res.valid_to,
                        source_url=r_res.source_url,
                        collection_status=r_res.status,
                        error_message=r_res.error_message,
                        collected_at=agency_item.finished_at
                    )
                    db.add(raw_record)

                # (2) CurrentRating 갱신
                current = db.query(CurrentRating).filter_by(institution_id=inst_id).first()
                if not current:
                    current = CurrentRating(institution_id=inst_id)
                    db.add(current)

                ratings_map = {item.agency_code: item.rating_res for item in res.agency_results}
                kr_obj = ratings_map.get(AgencyCode.KR.value)
                kis_obj = ratings_map.get(AgencyCode.KIS.value)
                nice_obj = ratings_map.get(AgencyCode.NICE.value)

                if kr_obj:
                    current.kr_rating = kr_obj.rating
                    current.kr_date = kr_obj.rating_date
                    current.kr_status = kr_obj.status
                    current.kr_url = kr_obj.source_url
                    current.kr_rating_type = kr_obj.rating_type_raw
                    current.kr_outlook = kr_obj.outlook

                if kis_obj:
                    current.kis_rating = kis_obj.rating
                    current.kis_date = kis_obj.rating_date
                    current.kis_status = kis_obj.status
                    current.kis_url = kis_obj.source_url
                    current.kis_rating_type = kis_obj.rating_type_raw
                    current.kis_outlook = kis_obj.outlook

                if nice_obj:
                    current.nice_rating = nice_obj.rating
                    current.nice_date = nice_obj.rating_date
                    current.nice_status = nice_obj.status
                    current.nice_url = nice_obj.source_url
                    current.nice_rating_type = nice_obj.rating_type_raw
                    current.nice_outlook = nice_obj.outlook

                # (3) 전월 최종등급 엄격 산출 (전월 확정 이력 MonthlyConfirmedRating 기준)
                today = date.today()
                first_day_of_month = today.replace(day=1)
                last_month_date = first_day_of_month - timedelta(days=1)
                prev_ym = last_month_date.strftime("%Y-%m")

                # 전월 공식 확정 이력 조회
                prev_confirmed = db.query(MonthlyConfirmedRating).filter(
                    MonthlyConfirmedRating.institution_id == inst_id,
                    MonthlyConfirmedRating.base_year_month == prev_ym
                ).first()

                if prev_confirmed and prev_confirmed.final_rating:
                    current.prev_final_rating = prev_confirmed.final_rating
                else:
                    # 전월 확정 이력이 없는 신규 기관은 None 유지 (당월 등급을 임의 복사하지 않음!)
                    current.prev_final_rating = None

                curr_final = calc_result.final_rating

                # 변동 분석 실행
                change_status, notch_delta, change_label = analyze_rating_change(
                    prev_rating=current.prev_final_rating,
                    curr_rating=curr_final
                )
                current.rating_change_status = change_status
                current.rating_change_notch = notch_delta
                current.rating_change_label = change_label

                # 등급 변동 이력 감지 및 저장 (PRD 제22조, TC-10)
                if current.prev_final_rating and current.prev_final_rating != curr_final and curr_final:
                    history = CreditRatingHistory(
                        institution_id=inst_id,
                        agency_code="FINAL",
                        rating_type=res.rating_type,
                        rating=curr_final,
                        rating_date=execution_date_str,
                        recorded_at=datetime.now(timezone.utc)
                    )
                    db.add(history)

                current.final_rating = curr_final
                current.overall_status = calc_result.overall_status
                current.calculation_logic = calc_result.calculation_logic
                current.evaluated_at = datetime.now(timezone.utc)

                # (4) 통계 집계 및 자가 치유(Self-Healing) 대상 선정
                # - 실제 네트워크 통신 에러가 발생한 기관이거나
                # - 3사 전체가 NO_RATING인 경우만 정밀 타겟팅하여 불필요한 반복 지연 차단
                has_error_agency = False
                for agency_item in res.agency_results:
                    r_res = agency_item.rating_res
                    if r_res.status in [CollectionStatus.CRAWLING_ERROR.value, CollectionStatus.PARSING_ERROR.value]:
                        has_error_agency = True
                        break

                if calc_result.overall_status == CollectionStatus.SUCCESS.value:
                    success_count += 1
                    if has_error_agency:
                        failed_tasks_map[inst_id] = (orig_task, calc_result.overall_status)
                elif calc_result.overall_status == CollectionStatus.NO_RATING.value:
                    no_rating_count += 1
                    if has_error_agency:
                        failed_tasks_map[inst_id] = (orig_task, calc_result.overall_status)
                elif calc_result.overall_status in [CollectionStatus.CRAWLING_ERROR.value, CollectionStatus.PARSING_ERROR.value]:
                    error_count += 1
                    failed_tasks_map[inst_id] = (orig_task, calc_result.overall_status)
                else:
                    manual_check_count += 1

                # 실시간 DB 반영
                job.success_count = success_count
                job.no_rating_count = no_rating_count
                job.error_count = error_count
                job.manual_check_count = manual_check_count
                db.commit()

                # 실시간 진행 글로벌 상태 업데이트
                processed = success_count + no_rating_count + error_count + manual_check_count
                pct = round((processed / job.total_count) * 100, 1) if job.total_count > 0 else 0.0
                ACTIVE_JOB_PROGRESS.update({
                    "processed_count": processed,
                    "success_count": success_count,
                    "no_rating_count": no_rating_count,
                    "error_count": error_count,
                    "manual_check_count": manual_check_count,
                    "current_institution": res.institution_name,
                    "progress_percent": pct,
                })

        if STOP_COLLECTION_EVENT.is_set():
            if job.status != JobStatus.STOPPED.value:
                job.status = JobStatus.STOPPED.value
                job.finished_at = datetime.now(timezone.utc)
                job.error_message = "사용자에 의해 조사가 중지되었습니다."
                db.commit()
            ACTIVE_JOB_PROGRESS.update({
                "is_running": False,
                "is_stopping": False,
                "current_institution": "조사 중지됨",
            })
            return job_id

        # 5-2. [자가 치유 Self-Healing 최적화] 일시적 통신 오류/누락 기관을 병렬로 신속하게 1회 재수거
        if failed_tasks_map and len(failed_tasks_map) <= 15:
            retry_items = list(failed_tasks_map.items())
            retry_workers = min(4, len(retry_items))
            with ThreadPoolExecutor(max_workers=retry_workers) as retry_executor:
                future_to_retry = {
                    retry_executor.submit(
                        _collect_for_single_institution,
                        item[1][0][0], item[1][0][1], item[1][0][2], item[1][0][3], item[1][0][4], item[1][0][5], execution_date_str, item[1][0][6], item[1][0][7]
                    ): item
                    for item in retry_items
                }
                for fut in as_completed(future_to_retry):
                    if STOP_COLLECTION_EVENT.is_set():
                        logger.info(f"[CollectorJob] 재수집 중단 감지. Job {job_id} 즉시 중지.")
                        for f in future_to_retry:
                            f.cancel()
                        job.status = JobStatus.STOPPED.value
                        job.finished_at = datetime.now(timezone.utc)
                        job.error_message = "사용자에 의해 조사가 중지되었습니다."
                        db.commit()
                        break

                    inst_id, (retry_task, prev_stat) = future_to_retry[fut]
                    retry_res = fut.result()
                    if retry_res.calc_result.overall_status == CollectionStatus.SUCCESS.value:
                        cur_obj = db.query(CurrentRating).filter_by(institution_id=inst_id).first()
                        if cur_obj:
                            r_map = {item.agency_code: item.rating_res for item in retry_res.agency_results}
                            k_o, kis_o, n_o = r_map.get(AgencyCode.KR.value), r_map.get(AgencyCode.KIS.value), r_map.get(AgencyCode.NICE.value)
                            if k_o and (k_o.rating or not cur_obj.kr_rating):
                                cur_obj.kr_rating, cur_obj.kr_date, cur_obj.kr_status, cur_obj.kr_url = k_o.rating, k_o.rating_date, k_o.status, k_o.source_url
                            if kis_o and (kis_o.rating or not cur_obj.kis_rating):
                                cur_obj.kis_rating, cur_obj.kis_date, cur_obj.kis_status, cur_obj.kis_url = kis_o.rating, kis_o.rating_date, kis_o.status, kis_o.source_url
                            if n_o and (n_o.rating or not cur_obj.nice_rating):
                                cur_obj.nice_rating, cur_obj.nice_date, cur_obj.nice_status, cur_obj.nice_url = n_o.rating, n_o.rating_date, n_o.status, n_o.source_url

                            cur_obj.final_rating = retry_res.calc_result.final_rating
                            cur_obj.overall_status = retry_res.calc_result.overall_status
                            cur_obj.calculation_logic = retry_res.calc_result.calculation_logic
                            cur_obj.evaluated_at = datetime.now(timezone.utc)

                            # 변동 분석 재평가
                            c_stat, n_delta, c_label = analyze_rating_change(
                                prev_rating=cur_obj.prev_final_rating,
                                curr_rating=cur_obj.final_rating
                            )
                            cur_obj.rating_change_status = c_stat
                            cur_obj.rating_change_notch = n_delta
                            cur_obj.rating_change_label = c_label

                            # 통계 재조정
                            if prev_stat != CollectionStatus.SUCCESS.value:
                                success_count += 1
                                if prev_stat == CollectionStatus.NO_RATING.value:
                                    no_rating_count = max(0, no_rating_count - 1)
                                elif prev_stat in [CollectionStatus.CRAWLING_ERROR.value, CollectionStatus.PARSING_ERROR.value]:
                                    error_count = max(0, error_count - 1)

                            job.success_count = success_count
                            job.no_rating_count = no_rating_count
                            job.error_count = error_count
                            db.commit()
                        db.commit()

        if STOP_COLLECTION_EVENT.is_set():
            if job.status != JobStatus.STOPPED.value:
                job.status = JobStatus.STOPPED.value
                job.finished_at = datetime.now(timezone.utc)
                job.error_message = "사용자에 의해 조사가 중지되었습니다."
                db.commit()
            ACTIVE_JOB_PROGRESS.update({
                "is_running": False,
                "is_stopping": False,
                "current_institution": "조사 중지됨",
            })
            return job_id

        # 6. Job 완료 상태 업데이트
        job.finished_at = datetime.now(timezone.utc)
        job.success_count = success_count
        job.no_rating_count = no_rating_count
        job.error_count = error_count
        job.manual_check_count = manual_check_count
        job.status = JobStatus.SUCCESS.value if error_count == 0 else JobStatus.PARTIAL_SUCCESS.value
        db.commit()

        ACTIVE_JOB_PROGRESS.update({
            "is_running": False,
            "is_stopping": False,
            "processed_count": job.total_count,
            "current_institution": "조사 완료",
            "progress_percent": 100.0,
        })

        return job_id

    except Exception as exc:
        ACTIVE_JOB_PROGRESS.update({
            "is_running": False,
            "is_stopping": False,
            "current_institution": "조사 실패",
        })
        db.rollback()
        try:
            if job_id:
                failed_job = db.query(CollectionJob).filter_by(job_id=job_id).first()
                if failed_job:
                    failed_job.status = JobStatus.FAILED.value
                    failed_job.finished_at = datetime.now(timezone.utc)
                    failed_job.error_message = str(exc)
            # 잔여 COLLECTING 기관 상태 정리 (확정 잠김 및 고착 방지)
            if target_inst_ids:
                for t_id in target_inst_ids:
                    c_rem = db.query(CurrentRating).filter_by(institution_id=t_id).first()
                    if c_rem and c_rem.overall_status == CollectionStatus.COLLECTING.value:
                        c_rem.overall_status = CollectionStatus.CRAWLING_ERROR.value
                        c_rem.calculation_logic = f"배치 오류로 중단: {str(exc)}"
            db.commit()
        except Exception as inner_exc:
            logger.error("배치 예외 회수 중 오류 발생: %s", inner_exc)
        raise exc
    finally:
        ACTIVE_JOB_PROGRESS["is_running"] = False
        ACTIVE_JOB_PROGRESS["is_stopping"] = False
        db.close()
