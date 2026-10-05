// Frontend Application Logic
let allRatingsData = [];
let currentHistoryData = [];
let selectedInstitutionIds = new Set();
let pollingInterval = null;
let activeTab = "tabCurrent";
let liveUpdatedIds = new Set();
let prevRatingsSnapshot = new Map();
let isLiveUpdating = false;

// 3단계 최초 정렬 규칙 (요구사항 8-2: 업권별 가중치 > 신용등급 우량순 > 기관명 가나다순)
const INDUSTRY_ORDER = {
  SECURITIES: 1,        // 증권
  BANK: 2,              // 은행
  LIFE_INSURANCE: 3,    // 생명보험
  NON_LIFE_INSURANCE: 4,// 손해보험
  SAVINGS_BANK: 5       // 저축은행
};

const RATING_ORDER = {
  "AAA": 1, "AA+": 2, "AA": 3, "AA-": 4,
  "A+": 5, "A": 6, "A-": 7,
  "BBB+": 8, "BBB": 9, "BBB-": 10,
  "BB+": 11, "BB": 12, "BB-": 13,
  "B+": 14, "B": 15, "B-": 16,
  "CCC+": 17, "CCC": 18, "CCC-": 19,
  "CC": 20, "C": 21, "D": 22
};

function sortRatings(list) {
  return [...list].sort((a, b) => {
    // 1순위: 업권별 (증권 > 은행 > 생명보험 > 손해보험 > 저축은행)
    const indA = INDUSTRY_ORDER[a.industry_type] || 99;
    const indB = INDUSTRY_ORDER[b.industry_type] || 99;
    if (indA !== indB) return indA - indB;

    // 2순위: 최종 신용등급 우량순
    const rankA = RATING_ORDER[a.final_rating] || 999;
    const rankB = RATING_ORDER[b.final_rating] || 999;
    if (rankA !== rankB) return rankA - rankB;

    // 3순위: 기관명 가나다순
    return (a.institution_name || "").localeCompare(b.institution_name || "", "ko");
  });
}

function setHeaderBaseMonth() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const el = document.getElementById("baseDateText");
  if (el) el.textContent = `${year}년 ${month}월`;
}

function restoreLastBatchTime() {
  const saved = localStorage.getItem("crc_last_batch_time");
  if (saved) {
    const el = document.getElementById("lastBatchTime");
    if (el) el.textContent = saved;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setHeaderBaseMonth();
  restoreLastBatchTime();
  checkServerHealth();
  initTabs();
  loadDashboardData();
  loadHistoryMonths();
  loadInstitutionsData();
  bindEvents();
});

// 1. 서버 상태 점검
async function checkServerHealth() {
  const badge = document.getElementById("serverStatusBadge");
  const dot = badge.querySelector(".status-dot");
  const text = badge.querySelector(".status-text");

  try {
    const res = await fetch("/health");
    if (res.ok) {
      dot.classList.add("active");
      text.textContent = "서버 정상 연결됨";
    } else {
      dot.classList.remove("active");
      text.textContent = "서버 응답 오류";
    }
  } catch (err) {
    dot.classList.remove("active");
    text.textContent = "서버 오프라인";
  }
}

// 2. 탭 전환 초기화
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.dataset.tab;
      if (activeTab === targetTab) return;

      tabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-panel").forEach(p => {
        p.classList.remove("active");
        p.style.display = "none";
      });

      const activePanel = document.getElementById(targetTab);
      if (activePanel) {
        activePanel.classList.add("active");
        activePanel.style.display = "flex";
      }

      activeTab = targetTab;

      if (targetTab === "tabHistory") {
        loadHistoryMonths();
      } else if (targetTab === "tabManage") {
        loadInstitutionsData();
      }
    });
  });
}

// 3. 당월 대시보드 데이터 로드
async function loadDashboardData() {
  try {
    const res = await fetch("/api/v1/ratings");
    if (!res.ok) {
      renderTable([]);
      return;
    }
    const data = await res.json();
    allRatingsData = sortRatings(data);
    updateKPIs(allRatingsData);
    applyFilters();
    checkJobStatus();
  } catch (err) {
    console.error("데이터 로드 실패:", err);
    renderTable([]);
  }
}

let wasJobRunning = false;
let isJobCurrentlyRunning = false;

// 4. 실시간 조사 결과 라이브 갱신 (조사 완료된 기업 즉시 표기)
async function refreshLiveRatings() {
  if (isLiveUpdating) return;
  isLiveUpdating = true;
  try {
    const res = await fetch("/api/v1/ratings");
    if (!res.ok) return;
    const data = await res.json();
    
    // 새로 조사 완료된 기관 감지 (이전 스냅샷과 비교)
    liveUpdatedIds.clear();
    data.forEach(item => {
      const prev = prevRatingsSnapshot.get(item.institution_id);
      if (prev) {
        const hasNewRating = (item.final_rating && !prev.final_rating);
        const hasChangedRating = (item.kr_rating !== prev.kr_rating || item.kis_rating !== prev.kis_rating || item.nice_rating !== prev.nice_rating);
        const hasChangedStatus = (item.overall_status !== prev.overall_status && item.overall_status !== 'NO_RATING');
        
        if (hasNewRating || hasChangedRating || hasChangedStatus) {
          liveUpdatedIds.add(item.institution_id);
        }
      }
      prevRatingsSnapshot.set(item.institution_id, {
        final_rating: item.final_rating,
        kr_rating: item.kr_rating,
        kis_rating: item.kis_rating,
        nice_rating: item.nice_rating,
        overall_status: item.overall_status
      });
    });

    allRatingsData = sortRatings(data);
    updateKPIs(allRatingsData);
    applyFilters();
  } catch (err) {
    console.error("실시간 라이브 데이터 갱신 실패:", err);
  } finally {
    isLiveUpdating = false;
  }
}

// 4-1. 수집 작업 상태 확인 및 실시간 라이브 렌더링
async function checkJobStatus() {
  try {
    const res = await fetch("/api/v1/collector/status");
    if (!res.ok) return;
    const data = await res.json();
    const lastBatchSpan = document.getElementById("lastBatchTime");
    const runAllBtn = document.getElementById("btnRunAll");
    const runSelectedBtn = document.getElementById("btnRunSelected");

    const progressCard = document.getElementById("progressCard");
    const progressBarFill = document.getElementById("progressBarFill");
    const progressPercent = document.getElementById("progressPercent");
    const progressProcessed = document.getElementById("progressProcessed");
    const progressTotal = document.getElementById("progressTotal");
    const progressCurrentInst = document.getElementById("progressCurrentInst");
    const progressSuccess = document.getElementById("progressSuccess");
    const progressNoRating = document.getElementById("progressNoRating");
    const progressManual = document.getElementById("progressManual");
    const progressError = document.getElementById("progressError");

    if (data.is_running) {
      wasJobRunning = true;
      isJobCurrentlyRunning = true;

      // 전체조사 버튼을 [조사중지] 상태로 전환
      if (runAllBtn) {
        runAllBtn.disabled = false;
        runAllBtn.classList.add("btn-stop");
        runAllBtn.title = "진행 중인 신용등급 조사를 즉시 중지합니다";
        runAllBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>
          조사중지
        `;
      }
      if (runSelectedBtn) runSelectedBtn.disabled = true;

      if (progressCard) {
        progressCard.style.display = "block";
      }

      if (data.progress) {
        const p = data.progress;
        const pct = p.progress_percent !== undefined ? p.progress_percent : 0;
        if (progressBarFill) progressBarFill.style.width = `${pct}%`;
        if (progressPercent) progressPercent.textContent = `${pct}%`;
        if (progressProcessed) progressProcessed.textContent = p.processed_count || 0;
        if (progressTotal) progressTotal.textContent = p.total_count || 0;
        if (progressCurrentInst) progressCurrentInst.textContent = p.current_institution || "수집 진행 중...";
        if (progressSuccess) progressSuccess.textContent = p.success_count || 0;
        if (progressNoRating) progressNoRating.textContent = p.no_rating_count || 0;
        if (progressManual) progressManual.textContent = p.manual_check_count || 0;
        if (progressError) progressError.textContent = p.error_count || 0;
      }

      // [핵심] 조사 완료된 기관을 실시간으로 화면 테이블에 즉시 표기!
      refreshLiveRatings();

      if (!pollingInterval) {
        pollingInterval = setInterval(checkJobStatus, 1000);
      }
    } else {
      isJobCurrentlyRunning = false;
      if (wasJobRunning) {
        wasJobRunning = false;
        if (progressBarFill) progressBarFill.style.width = "100%";
        if (progressPercent) progressPercent.textContent = "100%";
        if (progressCurrentInst) progressCurrentInst.textContent = "조사 완료!";
        
        liveUpdatedIds.clear();
        await loadDashboardData();
        showToast("신용등급 조사가 완료되었습니다! 검토 후 [당월 등급 최종 확정]을 진행해 주세요.", true);

        setTimeout(() => {
          if (progressCard) progressCard.style.display = "none";
        }, 2500);
      } else {
        if (progressCard) progressCard.style.display = "none";
      }

      if (runAllBtn) {
        runAllBtn.disabled = false;
        runAllBtn.classList.remove("btn-stop");
        runAllBtn.title = "";
        runAllBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          전체조사
        `;
      }
      updateSelectedCount();

      if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
      }
    }

    if (data.last_job && data.last_job.started_at) {
      const dt = new Date(data.last_job.started_at);
      lastBatchSpan.textContent = dt.toLocaleString("ko-KR");
    }
  } catch (err) {
    console.error("작업 상태 확인 실패:", err);
  }
}

// 5. 조사 시작 시 화면 초기화 및 라이브 스냅샷 보존
function cleanseScreen() {
  selectedInstitutionIds.clear();
  updateSelectedCount();

  // 기존 기관 데이터 스냅샷 보존 (어떤 기관이 새로 갱신되는지 추적)
  prevRatingsSnapshot.clear();
  liveUpdatedIds.clear();
  allRatingsData.forEach(item => {
    prevRatingsSnapshot.set(item.institution_id, {
      final_rating: item.final_rating,
      kr_rating: item.kr_rating,
      kis_rating: item.kis_rating,
      nice_rating: item.nice_rating,
      overall_status: item.overall_status
    });
  });

  showToast("⚡ 3대 평가사 실시간 조사가 시작되었습니다. 완료된 기관부터 화면에 즉시 노출됩니다.", true);
}

function updateKPIs(data) {
  const total = data.length;
  let maintain = 0;
  let upgrade = 0;
  let downgrade = 0;
  let newCount = 0;
  let error = 0;

  data.forEach(item => {
    const status = item.rating_change_status;
    if (status === "MAINTAIN") maintain++;
    else if (status === "UPGRADE") upgrade++;
    else if (status === "DOWNGRADE") downgrade++;
    else if (status === "NEW") newCount++;
    
    if (item.overall_status === "CRAWLING_ERROR" || 
        item.overall_status === "PARSING_ERROR" || 
        item.overall_status === "MANUAL_CHECK" ||
        item.kr_status === "CRAWLING_ERROR" ||
        item.kis_status === "CRAWLING_ERROR" ||
        item.nice_status === "CRAWLING_ERROR") {
      error++;
    }
  });

  const elTotal = document.getElementById("kpiTotal");
  const elMaintain = document.getElementById("kpiMaintain");
  const elUpgrade = document.getElementById("kpiUpgrade");
  const elDowngrade = document.getElementById("kpiDowngrade");
  const elNew = document.getElementById("kpiNew");
  const elError = document.getElementById("kpiError");
  const elErrorRetry = document.getElementById("errorRetryCount");

  if (elTotal) elTotal.textContent = total;
  if (elMaintain) elMaintain.textContent = maintain;
  if (elUpgrade) elUpgrade.textContent = upgrade;
  if (elDowngrade) elDowngrade.textContent = downgrade;
  if (elNew) elNew.textContent = newCount;
  if (elError) elError.textContent = error;
  if (elErrorRetry) elErrorRetry.textContent = error;
  
  const elRowCount = document.getElementById("tableRowCount");
  if (elRowCount) elRowCount.textContent = total;
}

function applyFilters() {
  const search = document.getElementById("searchInput").value.trim().toLowerCase();
  const industry = document.getElementById("industryFilter").value;
  const changeFilter = document.getElementById("changeFilter") ? document.getElementById("changeFilter").value : "ALL";
  const status = document.getElementById("statusFilter").value;

  const filtered = allRatingsData.filter(item => {
    const matchesSearch = !search || 
      item.institution_name.toLowerCase().includes(search) || 
      (item.original_name && item.original_name.toLowerCase().includes(search));
    
    const matchesIndustry = industry === "ALL" || item.industry_type === industry;
    const matchesChange = changeFilter === "ALL" || item.rating_change_status === changeFilter;
    
    let matchesStatus = true;
    if (status === "ALL") {
      matchesStatus = true;
    } else if (status === "ERROR_OR_MANUAL") {
      matchesStatus = (
        item.overall_status === "CRAWLING_ERROR" || 
        item.overall_status === "PARSING_ERROR" || 
        item.overall_status === "MANUAL_CHECK" ||
        item.kr_status === "CRAWLING_ERROR" ||
        item.kis_status === "CRAWLING_ERROR" ||
        item.nice_status === "CRAWLING_ERROR"
      );
    } else {
      matchesStatus = item.overall_status === status;
    }

    return matchesSearch && matchesIndustry && matchesChange && matchesStatus;
  });

  renderTable(filtered);
  syncKpiActiveBadge();
}

function syncKpiActiveBadge() {
  const changeVal = document.getElementById("changeFilter") ? document.getElementById("changeFilter").value : "ALL";
  const statusVal = document.getElementById("statusFilter") ? document.getElementById("statusFilter").value : "ALL";

  document.querySelectorAll("#tab1KpiMiniBar .mini-kpi").forEach(el => el.classList.remove("active"));

  if (statusVal === "ERROR_OR_MANUAL" || statusVal === "CRAWLING_ERROR" || statusVal === "MANUAL_CHECK") {
    const errEl = document.getElementById("kpiCardError");
    if (errEl) errEl.classList.add("active");
  } else if (changeVal === "MAINTAIN") {
    const el = document.querySelector('#tab1KpiMiniBar [data-filter-val="MAINTAIN"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "UPGRADE") {
    const el = document.querySelector('#tab1KpiMiniBar [data-filter-val="UPGRADE"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "DOWNGRADE") {
    const el = document.querySelector('#tab1KpiMiniBar [data-filter-val="DOWNGRADE"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "NEW") {
    const el = document.querySelector('#tab1KpiMiniBar [data-filter-val="NEW"]');
    if (el) el.classList.add("active");
  } else {
    const el = document.querySelector('#tab1KpiMiniBar [data-filter-val="ALL"]');
    if (el) el.classList.add("active");
  }
}

/**
 * 평가사별 신용등급 심플 포맷터 (사용자 요건: 조잡한 태그/뱃지 제거, 전망은 색상으로만 직관적 표기)
 */
function formatAgencyRatingCell(rating, ratingType, outlook, status) {
  // 통신 연결 실패/수집 오류 상태 분리 표기
  if (status === "CRAWLING_ERROR" || status === "PARSING_ERROR" || status === "TIMEOUT" || status === "CONNECTION_ERROR") {
    return `<span class="badge-fail-pill" title="평가사 페이지 연결 오류 또는 수집 실패">조사실패</span>`;
  }
  
  if (!rating || rating === "-" || status === "NO_RATING") {
    return `<span style="color:var(--text-dim)">-</span>`;
  }

  // 툴팁 구성 (마우스 호버 시 등급종류 및 상세 전망 확인 가능)
  const tipParts = [];
  if (ratingType) tipParts.push(ratingType);
  if (outlook && outlook !== "-" && outlook !== "null" && outlook !== "None") tipParts.push(`전망: ${outlook}`);
  const titleAttr = tipParts.length > 0 ? `title="${tipParts.join(' | ')}"` : '';

  // 전망(Outlook)에 따른 글자/배지 색상 분류
  let outlookClass = "out-color-stable";
  if (outlook && outlook !== "-" && outlook !== "null" && outlook !== "None") {
    if (outlook.includes("부정") || outlook.toLowerCase().includes("negative")) {
      outlookClass = "out-color-neg"; // 부정적: 붉은색
    } else if (outlook.includes("긍정") || outlook.toLowerCase().includes("positive")) {
      outlookClass = "out-color-pos"; // 긍정적: 청록색
    } else if (outlook.includes("유동") || outlook.toLowerCase().includes("developing")) {
      outlookClass = "out-color-dev"; // 유동적: 주황색
    }
  }

  return `<span class="rating-badge-color mono ${outlookClass}" ${titleAttr}>${rating}</span>`;
}

function renderTable(data) {
  const tbody = document.getElementById("ratingsTableBody");
  const elRowCount = document.getElementById("tableRowCount");
  if (elRowCount) elRowCount.textContent = data.length;

  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="14" class="empty-row">조회된 기관 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.map(item => {
    const isChecked = selectedInstitutionIds.has(item.institution_id);
    
    // 1. 전월 최종등급
    const prevBadge = item.prev_final_rating 
      ? `<span class="rating-badge prev mono" style="background:rgba(148,163,184,0.12); color:#94a3b8; font-weight:600;">${item.prev_final_rating}</span>`
      : `<span style="color:var(--text-dim)">-</span>`;

    // 2. 당월 최종등급
    const finalBadge = item.final_rating 
      ? `<span class="rating-badge final mono">${item.final_rating}</span>` 
      : `<span style="color:var(--text-dim)">-</span>`;

    // 3. 전월대비 변동 뱃지
    let changeBadge = `<span style="color:var(--text-dim)">-</span>`;
    const cStatus = item.rating_change_status || "NEW";
    const cLabel = item.rating_change_label || "신규";
    if (cStatus === "UPGRADE") {
      changeBadge = `<span class="change-badge upgrade">${cLabel}</span>`;
    } else if (cStatus === "DOWNGRADE") {
      changeBadge = `<span class="change-badge downgrade">${cLabel}</span>`;
    } else if (cStatus === "MAINTAIN") {
      changeBadge = `<span class="change-badge maintain">유지</span>`;
    } else if (cStatus === "NEW") {
      changeBadge = `<span class="change-badge new">신규</span>`;
    }

    // 4. 각 평가사별 등급/전망 콤팩트 카드 및 확정일
    const krGrd = formatAgencyRatingCell(item.kr_rating, item.kr_rating_type, item.kr_outlook, item.kr_status);
    const krDt = item.kr_date ? `<span class="mono cell-date">${item.kr_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;

    const kisGrd = formatAgencyRatingCell(item.kis_rating, item.kis_rating_type, item.kis_outlook, item.kis_status);
    const kisDt = item.kis_date ? `<span class="mono cell-date">${item.kis_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;

    const niceGrd = formatAgencyRatingCell(item.nice_rating, item.nice_rating_type, item.nice_outlook, item.nice_status);
    const niceDt = item.nice_date ? `<span class="mono cell-date">${item.nice_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;
    const isLiveUpdated = liveUpdatedIds.has(item.institution_id);
    const rowClass = isLiveUpdated ? 'row-live-updated' : '';

    return `
      <tr class="${rowClass}">
        <td class="col-center">
          <input type="checkbox" class="row-checkbox" data-id="${item.institution_id}" ${isChecked ? 'checked' : ''}>
        </td>
        <td class="col-center">
          <span class="tag-industry">${getIndustryName(item.industry_type)}</span>
        </td>
        <td>
          <div class="cell-inst-name">
            <strong>${item.institution_name}</strong>
          </div>
        </td>
        <!-- 최종 결정 등급 (전월, 당월, 변동) -->
        <td class="col-center">${prevBadge}</td>
        <td class="col-center">${finalBadge}</td>
        <td class="col-center">${changeBadge}</td>
        <!-- 한국기업평가 -->
        <td class="col-center">${krGrd}</td>
        <td class="col-center">${krDt}</td>
        <!-- 한국신용평가 -->
        <td class="col-center">${kisGrd}</td>
        <td class="col-center">${kisDt}</td>
        <!-- NICE신용평가 -->
        <td class="col-center">${niceGrd}</td>
        <td class="col-center">${niceDt}</td>
        <!-- 수집상태 및 재조회 -->
        <td class="col-center">
          <div class="status-cell-wrapper">
            <span class="status-badge ${item.overall_status}">${getStatusName(item.overall_status)}</span>
            <button class="btn-action-sync" onclick="syncSingleInstitution('${item.institution_id}', this)" title="${item.institution_name} 신용등급 실시간 재조회/동기화">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
            </button>
          </div>
        </td>
        <td class="col-center">
          <button class="btn-action-icon" onclick="openDetailModal('${item.institution_id}')" title="상세 검증 보기">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  bindCheckboxEvents();
}

/**
 * 단일 상품제공기관 즉시 재조회/동기화 (전체 대기 없이 2~3초 내 1건 갱신)
 */
async function syncSingleInstitution(institutionId, btn) {
  if (!btn) return;
  btn.classList.add("spinning");
  btn.disabled = true;

  try {
    showToast("해당 기관의 3대 신용평가사 등급을 실시간 재조회 중입니다...", true);
    const res = await fetch(`/api/v1/ratings/${institutionId}/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `재조회 실패 (${res.status})`);
    }

    const updated = await res.json();
    
    // 데이터 캐시 및 테이블 상태 업데이트
    const idx = allRatingsData.findIndex(item => item.institution_id === institutionId);
    if (idx !== -1) {
      allRatingsData[idx] = updated;
    }
    
    // 화면 재반영
    applyFilters();
    updateKPIs(allRatingsData);

    const gradeText = updated.final_rating ? `${updated.final_rating}등급` : "미공시";
    showToast(`✅ [${updated.institution_name}] 재조회 완료! 최종 등급: ${gradeText}`, true);
  } catch (err) {
    console.error("단일 재조회 오류:", err);
    showToast(`❌ 재조회 중 오류 발생: ${err.message}`, false);
  } finally {
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
}

// 6. 월별 확정 이력 관리 (사용자 요건 4)
async function loadHistoryMonths() {
  try {
    const res = await fetch("/api/v1/ratings/history/months");
    if (!res.ok) return;
    const data = await res.json();
    const months = data.months || [];
    
    const badge = document.getElementById("historyBadge");
    if (badge) badge.textContent = `${months.length}개월`;

    const select = document.getElementById("historyMonthSelect");
    if (!select) return;

    if (months.length === 0) {
      select.innerHTML = `<option value="">확정된 이력이 없습니다</option>`;
      renderHistoryTable([]);
      return;
    }

    const currentSelected = select.value;
    select.innerHTML = months.map(m => `
      <option value="${m}" ${m === currentSelected ? 'selected' : ''}>${m} 확정 내역</option>
    `).join("");

    // 첫 번째 항목 자동 로드
    const activeYm = select.value || months[0];
    select.value = activeYm;
    loadMonthlyHistory(activeYm);
  } catch (err) {
    console.error("확정 년월 로드 실패:", err);
  }
}

async function loadMonthlyHistory(yearMonth) {
  if (!yearMonth) return;
  const tbody = document.getElementById("historyTableBody");
  tbody.innerHTML = `<tr><td colspan="13" class="empty-row"><span class="pulse-indicator"></span> ${yearMonth} 확정 이력을 불러오는 중입니다...</td></tr>`;

  try {
    const res = await fetch(`/api/v1/ratings/history?base_year_month=${yearMonth}`);
    if (!res.ok) {
      renderHistoryTable([]);
      return;
    }
    const data = await res.json();
    currentHistoryData = sortRatings(data.items || []);

    // 메타바 갱신
    if (data.confirmed_at) {
      const dt = new Date(data.confirmed_at);
      document.getElementById("histConfirmedAt").textContent = dt.toLocaleString("ko-KR");
    } else {
      document.getElementById("histConfirmedAt").textContent = "-";
    }
    document.getElementById("histConfirmedBy").textContent = data.confirmed_by || "-";
    document.getElementById("histTotalCount").textContent = data.total_count || 0;

    // 이력 KPI 갱신
    const s = data.summary || {};
    document.getElementById("histKpiTotal").textContent = s.total || 0;
    document.getElementById("histKpiMaintain").textContent = s.maintain || 0;
    document.getElementById("histKpiUpgrade").textContent = s.upgrade || 0;
    document.getElementById("histKpiDowngrade").textContent = s.downgrade || 0;
    const elHistNew = document.getElementById("histKpiNew");
    if (elHistNew) elHistNew.textContent = s.new || 0;
    document.getElementById("histKpiError").textContent = s.error || 0;

    applyHistoryFilters();
  } catch (err) {
    console.error("이력 데이터 로드 실패:", err);
    renderHistoryTable([]);
  }
}

function applyHistoryFilters() {
  const search = document.getElementById("historySearchInput").value.trim().toLowerCase();
  const industry = document.getElementById("historyIndustryFilter").value;
  const changeFilter = document.getElementById("historyChangeFilter").value;
  const statusFilter = document.getElementById("historyStatusFilter") ? document.getElementById("historyStatusFilter").value : "ALL";

  const filtered = currentHistoryData.filter(item => {
    const matchesSearch = !search || 
      item.institution_name.toLowerCase().includes(search) || 
      (item.original_name && item.original_name.toLowerCase().includes(search));
    
    const matchesIndustry = industry === "ALL" || item.industry_type === industry;
    const matchesChange = changeFilter === "ALL" || item.rating_change_status === changeFilter;
    
    let matchesStatus = true;
    if (statusFilter === "ALL") {
      matchesStatus = true;
    } else if (statusFilter === "ERROR_OR_MANUAL") {
      matchesStatus = (
        item.overall_status === "CRAWLING_ERROR" || 
        item.overall_status === "PARSING_ERROR" || 
        item.overall_status === "MANUAL_CHECK" ||
        item.kr_status === "CRAWLING_ERROR" ||
        item.kis_status === "CRAWLING_ERROR" ||
        item.nice_status === "CRAWLING_ERROR"
      );
    } else {
      matchesStatus = item.overall_status === statusFilter;
    }

    return matchesSearch && matchesIndustry && matchesChange && matchesStatus;
  });

  renderHistoryTable(filtered);
  syncHistoryKpiActiveBadge();
}

function syncHistoryKpiActiveBadge() {
  const changeVal = document.getElementById("historyChangeFilter") ? document.getElementById("historyChangeFilter").value : "ALL";
  const statusVal = document.getElementById("historyStatusFilter") ? document.getElementById("historyStatusFilter").value : "ALL";

  document.querySelectorAll("#tab2KpiMiniBar .mini-kpi").forEach(el => el.classList.remove("active"));

  if (statusVal === "ERROR_OR_MANUAL" || statusVal === "CRAWLING_ERROR" || statusVal === "MANUAL_CHECK") {
    const errEl = document.getElementById("histKpiErrorBox");
    if (errEl) errEl.classList.add("active");
  } else if (changeVal === "MAINTAIN") {
    const el = document.querySelector('#tab2KpiMiniBar [data-hist-filter-val="MAINTAIN"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "UPGRADE") {
    const el = document.querySelector('#tab2KpiMiniBar [data-hist-filter-val="UPGRADE"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "DOWNGRADE") {
    const el = document.querySelector('#tab2KpiMiniBar [data-hist-filter-val="DOWNGRADE"]');
    if (el) el.classList.add("active");
  } else if (changeVal === "NEW") {
    const el = document.querySelector('#tab2KpiMiniBar [data-hist-filter-val="NEW"]');
    if (el) el.classList.add("active");
  } else {
    const el = document.querySelector('#tab2KpiMiniBar [data-hist-filter-val="ALL"]');
    if (el) el.classList.add("active");
  }
}

function renderHistoryTable(data) {
  const tbody = document.getElementById("historyTableBody");
  document.getElementById("historyRowCount").textContent = data.length;

  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="13" class="empty-row">해당 조건의 확정 이력 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.map((item, idx) => {
    const prevBadge = item.prev_final_rating 
      ? `<span class="rating-badge prev mono" style="background:rgba(148,163,184,0.12); color:#94a3b8; font-weight:600;">${item.prev_final_rating}</span>`
      : `<span style="color:var(--text-dim)">-</span>`;

    const finalBadge = item.final_rating 
      ? `<span class="rating-badge final mono">${item.final_rating}</span>` 
      : `<span style="color:var(--text-dim)">-</span>`;

    let changeBadge = `<span style="color:var(--text-dim)">-</span>`;
    const cStatus = item.rating_change_status || "NEW";
    const cLabel = item.rating_change_label || "신규";
    if (cStatus === "UPGRADE") changeBadge = `<span class="change-badge upgrade">${cLabel}</span>`;
    else if (cStatus === "DOWNGRADE") changeBadge = `<span class="change-badge downgrade">${cLabel}</span>`;
    else if (cStatus === "MAINTAIN") changeBadge = `<span class="change-badge maintain">유지</span>`;
    else if (cStatus === "NEW") changeBadge = `<span class="change-badge new">신규</span>`;

    const krGrd = formatAgencyRatingCell(item.kr_rating, item.kr_rating_type, item.kr_outlook, item.kr_status);
    const krDt = item.kr_date ? `<span class="mono cell-date">${item.kr_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;

    const kisGrd = formatAgencyRatingCell(item.kis_rating, item.kis_rating_type, item.kis_outlook, item.kis_status);
    const kisDt = item.kis_date ? `<span class="mono cell-date">${item.kis_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;

    const niceGrd = formatAgencyRatingCell(item.nice_rating, item.nice_rating_type, item.nice_outlook, item.nice_status);
    const niceDt = item.nice_date ? `<span class="mono cell-date">${item.nice_date}</span>` : `<span style="color:var(--text-dim)">-</span>`;

    return `
      <tr>
        <td class="col-center mono" style="color:var(--text-dim); font-size:0.8rem;">${idx + 1}</td>
        <td class="col-center">
          <span class="tag-industry">${getIndustryName(item.industry_type)}</span>
        </td>
        <td>
          <div class="cell-inst-name">
            <strong>${item.institution_name}</strong>
          </div>
        </td>
        <td class="col-center">${prevBadge}</td>
        <td class="col-center">${finalBadge}</td>
        <td class="col-center">${changeBadge}</td>
        <td class="col-center">${krGrd}</td>
        <td class="col-center">${krDt}</td>
        <td class="col-center">${kisGrd}</td>
        <td class="col-center">${kisDt}</td>
        <td class="col-center">${niceGrd}</td>
        <td class="col-center">${niceDt}</td>
        <td class="col-center">
          <span class="status-badge ${item.overall_status}">${getStatusName(item.overall_status)}</span>
        </td>
      </tr>
    `;
  }).join("");
}

// 7. 토스트 메시지 함수
function showToast(msg, isSuccess = true) {
  const toast = document.getElementById("toastMessage");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `toast show ${isSuccess ? 'success' : ''}`;
  setTimeout(() => {
    toast.className = "toast";
  }, 4000);
}

function getIndustryName(code) {
  const map = {
    BANK: "은행",
    SAVINGS_BANK: "저축은행",
    SECURITIES: "증권",
    LIFE_INSURANCE: "생명보험",
    NON_LIFE_INSURANCE: "손해보험"
  };
  return map[code] || code;
}

function getRatingTypeBadge(code, name) {
  const label = name || getRatingTypeName(code);
  let color = "#38bdf8";
  if (code === "INSURANCE_FINANCIAL_STRENGTH") color = "#c084fc";
  else if (code === "SENIOR_BOND") color = "#34d399";
  return `<span style="font-size:0.7rem; color:${color}; background:rgba(255,255,255,0.05); padding:1px 6px; border-radius:4px;">${label}</span>`;
}

function getRatingTypeName(code) {
  const map = {
    CORPORATE_CREDIT: "기업신용",
    SENIOR_BOND: "선순위회사채",
    INSURANCE_FINANCIAL_STRENGTH: "보험지급능력"
  };
  return map[code] || code;
}

function getStatusName(code) {
  const map = {
    SUCCESS: "정상",
    NO_RATING: "무등급",
    MANUAL_CHECK: "수동확인",
    CRAWLING_ERROR: "수집오류",
    PARSING_ERROR: "파싱오류",
    MAPPING_REQUIRED: "매칭필요"
  };
  return map[code] || code;
}

// 8. 이벤트 바인딩
function bindEvents() {
  document.getElementById("searchInput").addEventListener("input", applyFilters);
  document.getElementById("industryFilter").addEventListener("change", applyFilters);
  const changeEl = document.getElementById("changeFilter");
  if (changeEl) changeEl.addEventListener("change", applyFilters);
  document.getElementById("statusFilter").addEventListener("change", applyFilters);

  // 1번 탭 미니 KPI 바 원클릭 필터링 및 번개(⚡) 재조회 분리
  const tab1KpiBar = document.getElementById("tab1KpiMiniBar");
  if (tab1KpiBar) {
    tab1KpiBar.addEventListener("click", (e) => {
      // 번개 버튼 클릭은 별도 리스너에서 처리하므로 중단
      if (e.target.closest("#btnQuickRetryZap")) return;

      const kpiEl = e.target.closest(".mini-kpi");
      if (!kpiEl) return;

      const changeSelect = document.getElementById("changeFilter");
      const statusSelect = document.getElementById("statusFilter");

      if (kpiEl.id === "kpiCardError" || e.target.closest(".error-filter-trigger")) {
        // 오류/확인 클릭 ➔ 오류 및 확인필요 대상 기관만 필터링
        if (statusSelect) statusSelect.value = "ERROR_OR_MANUAL";
        if (changeSelect) changeSelect.value = "ALL";
      } else {
        const filterVal = kpiEl.getAttribute("data-filter-val");
        if (filterVal) {
          if (changeSelect) changeSelect.value = filterVal;
          if (statusSelect) statusSelect.value = "ALL";
        }
      }
      applyFilters();
    });
  }

  // 번개 버튼 전용: 수집오류/확인필요 대상 즉시 재조회 갱신 팝업 실행
  const btnQuickRetryZap = document.getElementById("btnQuickRetryZap");
  if (btnQuickRetryZap) {
    btnQuickRetryZap.addEventListener("click", (e) => {
      e.stopPropagation();
      openRetryErrorsModal();
    });
  }

  // 2번 탭 이력 미니 KPI 바 원클릭 필터링
  const tab2KpiBar = document.getElementById("tab2KpiMiniBar");
  if (tab2KpiBar) {
    tab2KpiBar.addEventListener("click", (e) => {
      const kpiEl = e.target.closest(".mini-kpi");
      if (!kpiEl) return;

      const histChangeSelect = document.getElementById("historyChangeFilter");
      const histStatusSelect = document.getElementById("historyStatusFilter");

      if (kpiEl.id === "histKpiErrorBox") {
        if (histStatusSelect) histStatusSelect.value = "ERROR_OR_MANUAL";
        if (histChangeSelect) histChangeSelect.value = "ALL";
      } else {
        const filterVal = kpiEl.getAttribute("data-hist-filter-val");
        if (filterVal) {
          if (histChangeSelect) histChangeSelect.value = filterVal;
          if (histStatusSelect) histStatusSelect.value = "ALL";
        }
      }
      applyHistoryFilters();
    });
  }

  document.getElementById("checkAll").addEventListener("change", (e) => {
    const isChecked = e.target.checked;
    document.querySelectorAll(".row-checkbox").forEach(cb => {
      cb.checked = isChecked;
      const id = cb.dataset.id;
      if (isChecked) selectedInstitutionIds.add(id);
      else selectedInstitutionIds.delete(id);
    });
    updateSelectedCount();
  });

/**
 * 윈도우 파일 탐색기("다른 이름으로 저장") 창을 열어 사용자가 직접 원하는 폴더와 파일명을 지정하여 저장
 */
async function saveExcelWithPicker(blob, defaultFileName) {
  // 1. 최신 브라우저 File System Access API (showSaveFilePicker)
  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: defaultFileName,
        types: [{
          description: "Excel 통합 문서 (*.xlsx)",
          accept: {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"]
          }
        }]
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      showToast(`지정하신 위치에 저장되었습니다: ${defaultFileName}`, true);
      return true;
    } catch (err) {
      if (err.name === "AbortError") {
        showToast("파일 저장이 취소되었습니다.", false);
        return false;
      }
      console.warn("showSaveFilePicker 오류, 일반 다운로드로 대체:", err);
    }
  }

  // 2. Fallback: 기존 브라우저 기본 다운로드 (안전한 60초 URL 유지)
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = defaultFileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => window.URL.revokeObjectURL(url), 60000);
  showToast(`다운로드 폴더에 저장되었습니다: ${defaultFileName}`, true);
  return true;
}

  document.getElementById("btnExportExcel").addEventListener("click", async () => {
    const btn = document.getElementById("btnExportExcel");
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spin-icon" style="display:inline-block;">⏳</span> 저장 위치 선택 중...`;
    try {
      const res = await fetch("/api/v1/excel/download");
      if (!res.ok) throw new Error("서버에서 엑셀 파일 생성 실패");
      const blob = await res.blob();
      const nowStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      const defaultName = `신용등급_조사보고서_${nowStr}.xlsx`;
      await saveExcelWithPicker(blob, defaultName);
    } catch (err) {
      console.error("엑셀 다운로드 오류:", err);
      alert("엑셀 다운로드 중 오류가 발생했습니다: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  });

  // 이력 탭 이벤트
  document.getElementById("historyMonthSelect").addEventListener("change", (e) => {
    loadMonthlyHistory(e.target.value);
  });
  const btnRefreshHist = document.getElementById("btnRefreshHistory");
  if (btnRefreshHist) {
    btnRefreshHist.addEventListener("click", () => {
      showToast("월별 확정 목록을 새로고침합니다.", true);
      loadHistoryMonths();
    });
  }
  document.getElementById("historySearchInput").addEventListener("input", applyHistoryFilters);
  document.getElementById("historyIndustryFilter").addEventListener("change", applyHistoryFilters);
  document.getElementById("historyChangeFilter").addEventListener("change", applyHistoryFilters);
  const histStatusEl = document.getElementById("historyStatusFilter");
  if (histStatusEl) histStatusEl.addEventListener("change", applyHistoryFilters);
  document.getElementById("btnExportHistoryExcel").addEventListener("click", async () => {
    const ym = document.getElementById("historyMonthSelect").value;
    if (!ym) {
      alert("다운로드할 기준년월을 선택해주세요.");
      return;
    }
    const btn = document.getElementById("btnExportHistoryExcel");
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spin-icon" style="display:inline-block;">⏳</span> 저장 위치 선택 중...`;
    try {
      const res = await fetch(`/api/v1/excel/history?base_year_month=${ym}`);
      if (!res.ok) throw new Error("서버에서 월별 확정 엑셀 생성 실패");
      const blob = await res.blob();
      const defaultName = `신용등급_공식확정_${ym.replace(/-/g, "")}.xlsx`;
      await saveExcelWithPicker(blob, defaultName);
    } catch (err) {
      console.error("월별 확정 엑셀 다운로드 오류:", err);
      alert("월별 확정 엑셀 다운로드 중 오류가 발생했습니다: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  });

  // 전체 조사 실행 및 중지 토글
  document.getElementById("btnRunAll").addEventListener("click", async () => {
    const runBtn = document.getElementById("btnRunAll");

    // 이미 조사가 실행 중인 경우 -> 즉시 [조사중지] 수행
    if (isJobCurrentlyRunning) {
      runBtn.disabled = true;
      runBtn.innerHTML = `
        <svg class="spin-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
        중지 요청 중...
      `;
      try {
        await fetch("/api/v1/collector/stop", { method: "POST" });
        showToast("신용등급 조사를 중지했습니다.", false);
        setTimeout(checkJobStatus, 300);
      } catch (err) {
        console.error("조사 중지 요청 실패:", err);
        alert("조사 중지 중 오류가 발생했습니다.");
        setTimeout(checkJobStatus, 300);
      }
      return;
    }

    // 1. 화면 즉시 클렌징 (사용자 요건 2)
    cleanseScreen();

    // 2. 최근 조사 일시 낙관적 갱신 & localStorage 보존 (요구사항 3)
    const nowStr = new Date().toLocaleString("ko-KR");
    localStorage.setItem("crc_last_batch_time", nowStr);
    const lastBatchSpan = document.getElementById("lastBatchTime");
    if (lastBatchSpan) lastBatchSpan.textContent = nowStr;

    runBtn.disabled = true;
    runBtn.innerHTML = `
      <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
      조사 시작 중...
    `;

    const progressCard = document.getElementById("progressCard");
    if (progressCard) {
      progressCard.style.display = "block";
      document.getElementById("progressBarFill").style.width = "3%";
      document.getElementById("progressPercent").textContent = "시작 중...";
      document.getElementById("progressCurrentInst").textContent = "전체 기관(85개) 조사 준비 중...";
    }

    wasJobRunning = true;
    isJobCurrentlyRunning = true;
    try {
      const res = await fetch("/api/v1/collector/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_type: "MANUAL_ALL" })
      });
      setTimeout(checkJobStatus, 300);
    } catch (err) {
      console.error("서버 통신 실패:", err);
      setTimeout(checkJobStatus, 300);
    }
  });

  // 선택 조사 실행
  document.getElementById("btnRunSelected").addEventListener("click", async () => {
    const ids = Array.from(selectedInstitutionIds);
    if (ids.length === 0) return;

    const runSelectedBtn = document.getElementById("btnRunSelected");
    runSelectedBtn.disabled = true;
    runSelectedBtn.innerHTML = `
      <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
      선택조사 중... (<span id="selectedCount">${ids.length}</span>)
    `;

    const progressCard = document.getElementById("progressCard");
    if (progressCard) {
      progressCard.style.display = "block";
      document.getElementById("progressBarFill").style.width = "5%";
      document.getElementById("progressPercent").textContent = "시작 중...";
      document.getElementById("progressCurrentInst").textContent = `선택 기관(${ids.length}개) 수집 준비 중...`;
    }

    wasJobRunning = true;
    try {
      const res = await fetch("/api/v1/collector/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execution_type: "MANUAL_SELECT", institution_ids: ids })
      });
      setTimeout(checkJobStatus, 300);
    } catch (err) {
      console.error("서버 통신 실패:", err);
      setTimeout(checkJobStatus, 300);
    }
  });

  // [최종 확정] 모달 열기 버튼 (사용자 요건 3)
  document.getElementById("btnConfirmRating").addEventListener("click", () => {
    if (!allRatingsData || allRatingsData.length === 0) {
      alert("확정할 신용등급 조사 내역이 없습니다. 먼저 조사를 실행해주세요.");
      return;
    }
    const now = new Date();
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    document.getElementById("modalConfirmYm").textContent = ym;
    document.getElementById("modalConfirmCount").textContent = allRatingsData.length;
    document.getElementById("confirmModal").classList.add("active");
  });

  // [최종 확정] 실행 버튼 클릭 (Last-Win API 호출)
  document.getElementById("btnModalConfirmSubmit").addEventListener("click", async () => {
    const submitBtn = document.getElementById("btnModalConfirmSubmit");
    submitBtn.disabled = true;
    submitBtn.textContent = "확정 처리 중...";

    const now = new Date();
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    try {
      const res = await fetch("/api/v1/ratings/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_year_month: ym,
          confirmed_by: "USER"
        })
      });

      if (res.ok) {
        const result = await res.json();
        closeModal("confirmModal");
        showToast(`🎉 ${ym}월 신용등급(${result.confirmed_count}건)이 최종 확정되었습니다! (Last-Win 덮어쓰기 완료)`, true);
        loadHistoryMonths();
      } else {
        const err = await res.json();
        alert(`확정 실패: ${err.detail || "알 수 없는 오류"}`);
      }
    } catch (err) {
      console.error("확정 요청 오류:", err);
      alert("서버 통신 오류가 발생했습니다.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "최종 확정 실행";
    }
  });

  // 수집 오류 / 확인필요 기관 선별 재조회 이벤트 (상단 툴바 버튼)
  const btnRetryErrors = document.getElementById("btnRetryErrors");
  if (btnRetryErrors) btnRetryErrors.addEventListener("click", openRetryErrorsModal);

  const btnSubmitRetryErrors = document.getElementById("btnSubmitRetryErrors");
  if (btnSubmitRetryErrors) btnSubmitRetryErrors.addEventListener("click", executeRetryErrors);

  // 3번 탭 (상품제공기관 관리) 이벤트
  const manageSearch = document.getElementById("manageSearchInput");
  if (manageSearch) manageSearch.addEventListener("input", applyManageFilters);
  const manageInd = document.getElementById("manageIndustryFilter");
  if (manageInd) manageInd.addEventListener("change", applyManageFilters);
  const manageUse = document.getElementById("manageUseFilter");
  if (manageUse) manageUse.addEventListener("change", applyManageFilters);
  const btnExportInst = document.getElementById("btnExportInstExcel");
  if (btnExportInst) {
    btnExportInst.addEventListener("click", async () => {
      const originalHtml = btnExportInst.innerHTML;
      btnExportInst.disabled = true;
      btnExportInst.innerHTML = `<span class="spin-icon" style="display:inline-block;">⏳</span> 저장 위치 선택 중...`;
      try {
        const res = await fetch("/api/v1/institutions/export/excel");
        if (!res.ok) throw new Error("서버에서 기관 마스터 엑셀 생성 실패");
        const blob = await res.blob();
        const nowStr = new Date().toISOString().slice(0, 10).replace(/-/g, "");
        const defaultName = `상품제공기관_마스터_${nowStr}.xlsx`;
        await saveExcelWithPicker(blob, defaultName);
      } catch (err) {
        console.error("기관 마스터 엑셀 다운로드 오류:", err);
        alert("기관 마스터 엑셀 다운로드 중 오류가 발생했습니다: " + err.message);
      } finally {
        btnExportInst.disabled = false;
        btnExportInst.innerHTML = originalHtml;
      }
    });
  }
}

/**
 * 수집 오류 / 확인필요 대상 기관 선별 재조회 모달 열기 (사용자 맹점 5번 요건)
 */
function openRetryErrorsModal() {
  const errorItems = allRatingsData.filter(item =>
    item.overall_status === "CRAWLING_ERROR" ||
    item.overall_status === "PARSING_ERROR" ||
    item.overall_status === "MANUAL_CHECK" ||
    item.kr_status === "CRAWLING_ERROR" ||
    item.kis_status === "CRAWLING_ERROR" ||
    item.nice_status === "CRAWLING_ERROR"
  );

  if (errorItems.length === 0) {
    showToast("현재 수집 오류 또는 확인필요 기관이 없습니다. (전건 정상 완료)", true);
    return;
  }

  const countEl = document.getElementById("retryModalCount");
  if (countEl) countEl.textContent = errorItems.length;

  const listEl = document.getElementById("retryModalInstList");
  if (listEl) {
    listEl.innerHTML = errorItems.map(item => `
      <span style="background:rgba(239,68,68,0.15); color:#fca5a5; border:1px solid rgba(239,68,68,0.3); border-radius:4px; padding:3px 8px; font-weight:600; display:inline-flex; align-items:center; gap:4px;">
        ${item.institution_name}
        <span style="font-size:0.7rem; color:var(--text-dim);">(${getIndustryName(item.industry_type)})</span>
      </span>
    `).join("");
  }

  document.getElementById("retryConfirmModal").classList.add("active");
}

/**
 * 수집 오류 / 확인필요 대상 기관들만 선별 재조회 실행
 */
async function executeRetryErrors() {
  const errorItems = allRatingsData.filter(item =>
    item.overall_status === "CRAWLING_ERROR" ||
    item.overall_status === "PARSING_ERROR" ||
    item.overall_status === "MANUAL_CHECK" ||
    item.kr_status === "CRAWLING_ERROR" ||
    item.kis_status === "CRAWLING_ERROR" ||
    item.nice_status === "CRAWLING_ERROR"
  );

  if (errorItems.length === 0) {
    closeModal("retryConfirmModal");
    return;
  }

  const ids = errorItems.map(item => item.institution_id);
  closeModal("retryConfirmModal");

  // 진행 상태바 활성화
  const progressCard = document.getElementById("progressCard");
  if (progressCard) {
    progressCard.style.display = "block";
    document.getElementById("progressBarFill").style.width = "5%";
    document.getElementById("progressPercent").textContent = "시작 중...";
    document.getElementById("progressCurrentInst").textContent = `오류/확인 대상(${ids.length}개) 재수집 준비 중...`;
  }

  wasJobRunning = true;
  try {
    showToast(`수집오류/확인필요 대상 ${ids.length}개 기관 선별 재조회를 시작합니다...`, true);
    await fetch("/api/v1/collector/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ execution_type: "MANUAL_SELECT", institution_ids: ids })
    });
    setTimeout(checkJobStatus, 300);
  } catch (err) {
    console.error("선별 재조회 요청 실패:", err);
    setTimeout(checkJobStatus, 300);
  }
}

function bindCheckboxEvents() {
  document.querySelectorAll(".row-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) selectedInstitutionIds.add(id);
      else selectedInstitutionIds.delete(id);
      updateSelectedCount();
    });
  });
}

function updateSelectedCount() {
  const count = selectedInstitutionIds.size;
  const btn = document.getElementById("btnRunSelected");
  if (btn) {
    btn.disabled = count === 0;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
      선택조사 (<span id="selectedCount">${count}</span>)
    `;
  }
}

// 9. 상세 정보 모달
async function openDetailModal(id) {
  const item = allRatingsData.find(d => d.institution_id === id);
  if (!item) return;

  const modal = document.getElementById("detailModal");
  document.getElementById("modalTitle").textContent = `${item.institution_name} 신용등급 검증 상세`;

  const body = document.getElementById("modalBody");
  body.innerHTML = `<div style="text-align:center; padding:32px; color:var(--text-dim);">검증 데이터를 불러오는 중입니다...</div>`;
  modal.classList.add("active");

  try {
    const res = await fetch(`/api/v1/ratings/${id}/detail`);
    const detail = res.ok ? await res.json() : item;

    const agencies = detail.agencies || [
      { agency_code: "KR", agency_name: "한국기업평가", rating: item.kr_rating, rating_date: item.kr_date, status: item.kr_status, source_url: item.kr_url },
      { agency_code: "KIS", agency_name: "한국신용평가", rating: item.kis_rating, rating_date: item.kis_date, status: item.kis_status, source_url: item.kis_url },
      { agency_code: "NICE", agency_name: "NICE신용평가", rating: item.nice_rating, rating_date: item.nice_date, status: item.nice_status, source_url: item.nice_url }
    ];

    body.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid var(--border-color);">
        <div>
          <span class="tag-industry">${getIndustryName(item.industry_type)}</span>
          <span style="margin-left:8px;">${getRatingTypeBadge(item.rating_type, item.rating_type_name)}</span>
        </div>
        <div style="font-size:0.8rem; color:var(--text-dim);">
          기관코드: <span class="mono">${item.institution_id}</span>
        </div>
      </div>

      <!-- 검색어 인라인 편집 및 원스톱 재조회 박스 (요구사항 5) -->
      <div style="background:rgba(15,23,42,0.7); border:1px solid var(--border-color); border-radius:10px; padding:14px 16px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <span style="font-size:0.84rem; font-weight:700; color:var(--text-main);">🔍 평가사 검색어 관리 & 즉시 재조회</span>
          <button id="btnSaveSearchSync" class="btn btn-primary" style="padding:4px 12px; font-size:0.78rem;" onclick="saveSearchNamesAndSync('${item.institution_id}')">
            저장 및 즉시 재조회 ⚡
          </button>
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; margin-bottom:10px;">
          <div>
            <label style="font-size:0.72rem; color:var(--text-muted); display:block; margin-bottom:3px;">1순위 검색어 (우선)</label>
            <input type="text" id="editSearchName1" value="${item.search_name_1 || item.institution_name}" class="custom-select" style="width:100%; padding:6px 10px; font-size:0.82rem; font-weight:600; color:var(--primary);">
          </div>
          <div>
            <label style="font-size:0.72rem; color:var(--text-muted); display:block; margin-bottom:3px;">2순위 검색어 (차선)</label>
            <input type="text" id="editSearchName2" value="${item.search_name_2 || ''}" placeholder="차선 검색어 없음" class="custom-select" style="width:100%; padding:6px 10px; font-size:0.82rem; color:#c084fc;">
          </div>
          <div>
            <label style="font-size:0.72rem; color:var(--text-muted); display:block; margin-bottom:3px;">3순위 검색어 (추가확장)</label>
            <input type="text" id="editSearchName3" value="${item.search_name_3 || ''}" placeholder="추가 검색어 없음" class="custom-select" style="width:100%; padding:6px 10px; font-size:0.82rem; color:#34d399;">
          </div>
        </div>
        <div style="display:flex; gap:12px; color:var(--text-dim); font-size:0.74rem;">
          <span>평가사별 조사항목:</span>
          <span>한기평: <strong style="color:var(--text-main);">${item.kr_target_rating || "-"}</strong></span>
          <span>· 한신평: <strong style="color:var(--text-main);">${item.kis_target_rating || "-"}</strong></span>
          <span>· NICE: <strong style="color:var(--text-main);">${item.nice_target_rating || "-"}</strong></span>
        </div>
      </div>

      <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-color); border-radius:10px; padding:18px; margin-bottom:20px; text-align:center;">
        <div style="font-size:0.82rem; color:var(--text-muted); font-weight:600;">최종 결정 신용등급 (최저등급 산출)</div>
        <div style="font-size:2.4rem; font-weight:800; color:var(--primary); margin:6px 0;" class="mono">${item.final_rating || "-"}</div>
        <div style="font-size:0.8rem; color:var(--text-dim); background:rgba(255,255,255,0.03); display:inline-block; padding:4px 12px; border-radius:20px;">
          산출 근거: <strong>${item.calculation_logic || "등급 산출 내역 없음"}</strong>
        </div>
      </div>

      <div style="margin-bottom:10px; font-size:0.85rem; font-weight:700; color:var(--text-main);">
        🔍 3대 신용평가사 원본 공시 검증
      </div>

      <div class="agency-verify-grid">
        ${agencies.map(ag => {
          const hasRating = ag.rating && ag.status !== 'NO_RATING';
          const rawRatingStr = ag.raw_rating && ag.raw_rating !== ag.rating ? `(원문: ${ag.raw_rating})` : '';
          const linkBtn = ag.source_url 
            ? `<a href="${ag.source_url}" target="_blank" rel="noopener noreferrer" class="agency-link-btn">
                 공시 원본 확인 ↗
               </a>`
            : `<span class="agency-link-btn disabled">공시 링크 없음</span>`;

          return `
            <div class="agency-verify-card">
              <div>
                <div class="agency-verify-header">
                  <span class="agency-verify-title">${ag.agency_name}</span>
                  <span class="status-badge ${ag.status}" style="font-size:0.68rem; padding:1px 5px;">${getStatusName(ag.status)}</span>
                </div>
                <div class="agency-verify-rating mono" style="color: ${hasRating ? 'var(--text-main)' : 'var(--text-dim)'};">
                  ${ag.rating || "-"}
                </div>
                <div class="agency-verify-meta">
                  ${rawRatingStr ? `<div style="color:var(--primary); font-size:0.7rem;">${rawRatingStr}</div>` : ''}
                  <div>확정일: <span class="mono">${ag.rating_date || "-"}</span></div>
                  ${ag.valid_to ? `<div>만료일: <span class="mono">${ag.valid_to}</span></div>` : ''}
                </div>
              </div>
              ${linkBtn}
            </div>
          `;
        }).join("")}
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:16px; padding-top:12px; border-top:1px solid var(--border-color);">
        <span style="font-size:0.75rem; color:var(--text-dim);">💡 외부 공시 링크는 평가사 공식 페이지로 직접 연결됩니다.</span>
        <button class="btn btn-secondary" onclick="closeModal('detailModal')">닫기</button>
      </div>
    `;
  } catch (err) {
    body.innerHTML = `<div style="text-align:center; padding:24px; color:var(--danger);">상세 정보를 불러오는 중 오류가 발생했습니다.</div>`;
  }
}

function closeModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.remove("active");
}

// 10. 상세 모달 내 검색어 저장 및 원스톱 즉시 재조회 (요구사항 5)
async function saveSearchNamesAndSync(id) {
  const s1 = document.getElementById("editSearchName1").value.trim();
  const s2 = document.getElementById("editSearchName2").value.trim();
  const s3 = document.getElementById("editSearchName3").value.trim();
  const btn = document.getElementById("btnSaveSearchSync");

  btn.disabled = true;
  btn.innerHTML = `<span class="spin-icon" style="display:inline-block;">↻</span> 저장 및 재조회 중...`;

  try {
    // 1. 검색어 DB 저장 (user_modified=True)
    const resSave = await fetch(`/api/v1/institutions/${id}/search-names`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        search_name_1: s1,
        search_name_2: s2,
        search_name_3: s3
      })
    });
    if (!resSave.ok) {
      const err = await resSave.json();
      throw new Error(err.detail || "검색어 저장 실패");
    }

    // 2. 단일 기관 3대 평가사 실시간 재크롤링 및 산출
    const resSync = await fetch(`/api/v1/ratings/${id}/sync`, { method: "POST" });
    if (!resSync.ok) {
      const err = await resSync.json();
      throw new Error(err.detail || "실시간 재조회 실패");
    }

    showToast("검색어가 저장되고 3사 실시간 재조회가 완료되었습니다!", true);

    // 3. 메인 대시보드 데이터 갱신 및 팝업 다시 로드
    await loadDashboardData();
    await openDetailModal(id);
  } catch (err) {
    console.error("검색어 저장 및 재조회 오류:", err);
    alert(`오류: ${err.message || err}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `저장 및 즉시 재조회 ⚡`;
    }
  }
}

// ==========================================
// 11. 상품제공기관 관리 (Tab 3) 로직 (요구사항 6)
// ==========================================
let allInstitutionsData = [];

async function loadInstitutionsData() {
  try {
    const res = await fetch("/api/v1/institutions");
    if (!res.ok) return;
    const data = await res.json();
    allInstitutionsData = data;

    // 배지 갱신
    const badge = document.getElementById("instCountBadge");
    if (badge) badge.textContent = `${data.length}개`;

    applyManageFilters();
  } catch (err) {
    console.error("기관 마스터 로드 실패:", err);
  }
}

function applyManageFilters() {
  const search = (document.getElementById("manageSearchInput")?.value || "").trim().toLowerCase();
  const industry = document.getElementById("manageIndustryFilter")?.value || "ALL";
  const useYn = document.getElementById("manageUseFilter")?.value || "ALL";

  const filtered = allInstitutionsData.filter(item => {
    const matchesSearch = !search ||
      (item.institution_name && item.institution_name.toLowerCase().includes(search)) ||
      (item.institution_id && item.institution_id.toLowerCase().includes(search)) ||
      (item.search_name_1 && item.search_name_1.toLowerCase().includes(search)) ||
      (item.search_name_2 && item.search_name_2.toLowerCase().includes(search));

    const matchesInd = industry === "ALL" || item.industry_type === industry;
    const matchesUse = useYn === "ALL" || item.use_yn === useYn;

    return matchesSearch && matchesInd && matchesUse;
  });

  renderInstitutionsTable(filtered);
}

function renderInstitutionsTable(data) {
  const tbody = document.getElementById("manageTableBody");
  const countEl = document.getElementById("manageRowCount");
  if (countEl) countEl.textContent = data.length;

  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-row">조건에 해당하는 기관이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.map(item => {
    const isUsed = item.use_yn === "Y";
    const useBadge = isUsed
      ? `<span class="status-badge SUCCESS" style="font-size:0.72rem; padding:2px 6px;">사용중</span>`
      : `<span class="status-badge NO_RATING" style="font-size:0.72rem; padding:2px 6px;">미사용</span>`;

    const memoStr = item.memo ? `<span style="font-size:0.78rem; color:var(--text-muted);">${item.memo}</span>` : `<span style="color:var(--text-dim);">-</span>`;

    return `
      <tr>
        <td class="col-center mono" style="font-size:0.8rem; color:var(--text-dim);">${item.institution_id}</td>
        <td class="col-center">
          <span class="tag-industry">${getIndustryName(item.industry_type)}</span>
        </td>
        <td>
          <strong style="color:var(--text-main); font-size:0.9rem;">${item.institution_name}</strong>
          ${item.user_modified ? `<span style="font-size:0.68rem; color:#38bdf8; background:rgba(56,189,248,0.1); border-radius:3px; padding:1px 4px; margin-left:4px;">화면수정</span>` : ''}
        </td>
        <td class="col-center mono" style="color:var(--primary); font-size:0.82rem; font-weight:600;">${item.search_name_1 || "-"}</td>
        <td class="col-center mono" style="color:#c084fc; font-size:0.82rem;">${item.search_name_2 || "-"}</td>
        <td class="col-center mono" style="color:#34d399; font-size:0.82rem;">${item.search_name_3 || "-"}</td>
        <td style="font-size:0.75rem;">
          <div style="display:flex; flex-direction:column; gap:2px; line-height:1.2;">
            <div><span style="color:#60a5fa; font-weight:700; font-size:0.7rem;">KR:</span> <span style="color:var(--text-main);">${item.kr_target_rating || "-"}</span></div>
            <div><span style="color:#f59e0b; font-weight:700; font-size:0.7rem;">KIS:</span> <span style="color:var(--text-main);">${item.kis_target_rating || "-"}</span></div>
            <div><span style="color:#10b981; font-weight:700; font-size:0.7rem;">NICE:</span> <span style="color:var(--text-main);">${item.nice_target_rating || "-"}</span></div>
          </div>
        </td>
        <td>${memoStr}</td>
        <td class="col-center">${useBadge}</td>
        <td class="col-center">
          <div style="display:inline-flex; gap:6px;">
            <button class="btn btn-secondary" style="padding:3px 8px; font-size:0.72rem;" onclick="openEditInstitutionModal('${item.institution_id}')">수정</button>
            <button class="btn btn-outline" style="padding:3px 8px; font-size:0.72rem; color:var(--danger); border-color:rgba(239,68,68,0.4);" onclick="deleteInstitution('${item.institution_id}', '${item.institution_name}')">삭제</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function updateDefaultRatingTypesByIndustry(industry) {
  const krInput = document.getElementById("instFormKrTarget");
  const kisInput = document.getElementById("instFormKisTarget");
  const niceInput = document.getElementById("instFormNiceTarget");
  if (!krInput || !kisInput || !niceInput) return;

  if (industry === "BANK" || industry === "SAVINGS_BANK") {
    krInput.value = "기업신용평가";
    kisInput.value = "Issuer Rating";
    niceInput.value = "ICR";
  } else if (industry === "SECURITIES") {
    krInput.value = "회사채(선순위)";
    kisInput.value = "회사채(선순위)";
    niceInput.value = "회사채(선순위)";
  } else if (industry === "LIFE_INSURANCE" || industry === "NON_LIFE_INSURANCE") {
    krInput.value = "보험금지급능력평가";
    kisInput.value = "보험금지급능력평가";
    niceInput.value = "보험금지급능력평가";
  }
}

function openCreateInstitutionModal() {
  document.getElementById("instModalTitle").textContent = "신규 상품제공기관 등록";
  document.getElementById("instFormMode").value = "CREATE";
  document.getElementById("instFormId").value = "";
  document.getElementById("instFormIndustry").value = "BANK";
  document.getElementById("instFormName").value = "";
  document.getElementById("instFormSearch1").value = "";
  document.getElementById("instFormSearch2").value = "";
  document.getElementById("instFormSearch3").value = "";
  document.getElementById("instFormMemo").value = "";
  updateDefaultRatingTypesByIndustry("BANK");
  const rY = document.querySelector('input[name="instFormUseYn"][value="Y"]');
  if (rY) rY.checked = true;

  document.getElementById("institutionModal").classList.add("active");
}

function openEditInstitutionModal(id) {
  const item = allInstitutionsData.find(d => d.institution_id === id);
  if (!item) return;

  document.getElementById("instModalTitle").textContent = `${item.institution_name} 정보 수정`;
  document.getElementById("instFormMode").value = "EDIT";
  document.getElementById("instFormId").value = id;
  document.getElementById("instFormIndustry").value = item.industry_type;
  document.getElementById("instFormName").value = item.institution_name;
  document.getElementById("instFormSearch1").value = item.search_name_1 || item.institution_name;
  document.getElementById("instFormSearch2").value = item.search_name_2 || "";
  document.getElementById("instFormSearch3").value = item.search_name_3 || "";
  document.getElementById("instFormKrTarget").value = item.kr_target_rating || "";
  document.getElementById("instFormKisTarget").value = item.kis_target_rating || "";
  document.getElementById("instFormNiceTarget").value = item.nice_target_rating || "";
  document.getElementById("instFormMemo").value = item.memo || "";

  const r = document.querySelector(`input[name="instFormUseYn"][value="${item.use_yn}"]`);
  if (r) r.checked = true;

  document.getElementById("institutionModal").classList.add("active");
}

async function submitInstitutionForm() {
  const mode = document.getElementById("instFormMode").value;
  const id = document.getElementById("instFormId").value;
  const name = document.getElementById("instFormName").value.trim();
  const industry = document.getElementById("instFormIndustry").value;
  const s1 = document.getElementById("instFormSearch1").value.trim();
  const s2 = document.getElementById("instFormSearch2").value.trim();
  const s3 = document.getElementById("instFormSearch3").value.trim();
  const krTarget = document.getElementById("instFormKrTarget")?.value.trim() || null;
  const kisTarget = document.getElementById("instFormKisTarget")?.value.trim() || null;
  const niceTarget = document.getElementById("instFormNiceTarget")?.value.trim() || null;
  const memo = document.getElementById("instFormMemo").value.trim();
  const useYn = document.querySelector('input[name="instFormUseYn"]:checked')?.value || "Y";

  if (!name) {
    alert("상품제공기관명을 입력해주세요.");
    return;
  }

  // 업권 기반 rating_type 자동 결정
  const ratingType = (industry === "LIFE_INSURANCE" || industry === "NON_LIFE_INSURANCE")
    ? "INSURANCE_FINANCIAL_STRENGTH"
    : (industry === "SECURITIES" ? "SENIOR_BOND" : "CORPORATE_CREDIT");

  const btn = document.getElementById("btnSubmitInstForm");
  btn.disabled = true;
  btn.textContent = "저장 중...";

  try {
    const payload = {
      institution_name: name,
      industry_type: industry,
      rating_type: ratingType,
      search_name_1: s1 || name,
      search_name_2: s2,
      search_name_3: s3,
      kr_target_rating: krTarget,
      kis_target_rating: kisTarget,
      nice_target_rating: niceTarget,
      memo: memo,
      use_yn: useYn
    };

    if (mode === "CREATE") {
      const res = await fetch("/api/v1/institutions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "등록 실패");
      }
      showToast(`🎉 '${name}' 기관이 성공적으로 등록되었습니다!`, true);
    } else {
      const res = await fetch(`/api/v1/institutions/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "수정 실패");
      }
      showToast(`'${name}' 기관 정보가 수정되었습니다!`, true);
    }

    closeModal("institutionModal");
    await loadInstitutionsData();
    await loadDashboardData();
  } catch (err) {
    console.error("기관 저장 실패:", err);
    alert(`오류: ${err.message || err}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "저장 완료";
  }
}

async function deleteInstitution(id, name) {
  if (!confirm(`정말로 '${name}' 기관을 비활성화(미사용 처리)하시겠습니까?\n이후 등급 조사 대상에서 제외됩니다.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/v1/institutions/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "삭제 실패");
    }
    showToast(`'${name}' 기관이 비활성화되었습니다.`, true);
    await loadInstitutionsData();
    await loadDashboardData();
  } catch (err) {
    alert(`삭제 오류: ${err.message || err}`);
  }
}

// 업권 변경 시 신규 등록 모드에서 기본 등급종류 자동 추천
document.getElementById("instFormIndustry")?.addEventListener("change", (e) => {
  const mode = document.getElementById("instFormMode")?.value;
  if (mode === "CREATE") {
    updateDefaultRatingTypesByIndustry(e.target.value);
  }
});

