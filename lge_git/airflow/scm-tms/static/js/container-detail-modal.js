// ══════════════════════════════════════════════════════════════════════════════
// Container Detail Modal + Customer Orders Modal
// (container-detail-modal.js + customer-orders-modal.js 통합)
// ══════════════════════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════════════════════
// [1] Container Detail Modal
// ══════════════════════════════════════════════════════════════════════════════

// Timeline stage definitions for container tracking (Row1: 6 steps, Row2: 6 steps)
const CONTAINER_TIMELINE_STAGES = [
    // Row 1
    { key: 'STUFFING',          label: 'Stuffing',           icon: 'fa-box',              dateField: 'STUFFING_DATE' },
    { key: 'CC',                label: 'CC',                 icon: 'fa-warehouse',        dateField: 'CC_DATE' },
    { key: 'FACTORY_SHIP_OUT',  label: 'Factory Ship',       icon: 'fa-industry',         dateField: 'FACTORY_SHIP_OUT_DATE' },
    { key: 'POL_ETD',           label: 'POL Departure',      icon: 'fa-anchor',           dateField: 'POL_ATD_DATE' },
    { key: 'POD_ATA',           label: 'POD Arrival',        icon: 'fa-ship',             dateField: 'POD_ATA_DATE' },
    { key: 'CY_ARRIVAL',        label: 'CY Arrival',         icon: 'fa-warehouse',        dateField: 'CY1_ATA_DATE' },
    // Row 2
    { key: 'CUSTOMS_REQ',       label: 'Customs Req',        icon: 'fa-file-circle-plus', dateField: 'ZCCREQDAT' },
    { key: 'CUSTOMS_DEC',       label: 'Customs Dec',        icon: 'fa-file-signature',   dateField: 'ZIMDEC' },
    { key: 'CUSTOMS_CLEAR',     label: 'Customs Cleared',    icon: 'fa-shield-halved',    dateField: 'ZCCCOMPT' },
    { key: 'CY_DEPARTURE',      label: 'CY Departure',       icon: 'fa-truck-moving',     dateField: 'CY1_ATD_DATE' },
    { key: 'FDEST_ARRIVAL',     label: 'F Dest Arrival',     icon: 'fa-flag-checkered',   dateField: 'FDEST_ATA_DATE' },
    { key: 'FINAL_DEST',        label: 'Final Destination',  icon: 'fa-location-dot',     dateField: null },
];

// Container PO_DETAIL_STATUS to timeline step index mapping
const CONTAINER_STATUS_STEP = {
    'On factory Processing':    0,
    'Factory Ship Out':         2,
    'Intransit (POL~POD)':      3,
    'Intransit (POD~FDEST)':    4,
    'CY Arrival':               5,
    'Customs Requested':        6,
    'Customs Declared':         7,
    'Customs Cleared':          8,
    'CY Departure':             9,
    'F Dest Arrival':           10,
    'Final Destination':        11,
};

/**
 * Open container detail modal
 * @param {string} subsdrNm - Legal entity name
 * @param {string} containerNo - Container number
 */
function openContainerDetail(subsdrNm, containerNo, highlightModel = '') {
    if (!subsdrNm || !containerNo) {
        console.warn('Container info missing:', subsdrNm, containerNo);
        return;
    }

    // Show loading state
    const backdrop = document.getElementById('containerDetailBackdrop');
    backdrop.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Reset model grid to loading state
    document.getElementById('detailContainerModelGridBody').innerHTML =
        '<tr><td colspan="8" class="loading-row"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';
    document.getElementById('detailContainerLineCount').textContent = '';

    const params = new URLSearchParams({ subsdr_nm: subsdrNm, container_no: containerNo });

    // Fetch header + model lines in parallel
    Promise.all([
        fetch('/api/order/container-detail?' + params).then(r => r.json()),
        fetch('/api/order/container-detail-lines?' + params).then(r => r.json())
    ]).then(([headerRes, linesRes]) => {
        if (headerRes.success && headerRes.data) {
            renderContainerDetail(headerRes.data);
        } else {
            console.error('Failed to load container detail:', headerRes.message);
            closeContainerDetail();
            alert('Failed to load container detail: ' + (headerRes.message || 'Unknown error'));
            return;
        }
        renderContainerModelGrid(linesRes.success ? (linesRes.data || []) : [], highlightModel);
    }).catch(err => {
        console.error('Container detail error:', err);
        closeContainerDetail();
        alert('Error loading container detail');
    });
}/**
 * Close container detail modal
 */
function closeContainerDetail() {
    document.getElementById('containerDetailBackdrop').style.display = 'none';
    document.body.style.overflow = '';
}

/**
 * Render container detail data
 * @param {Object} c - Container data
 */
function renderContainerDetail(c) {
    if (!c) return;
    
    // Header
    document.getElementById('detailContainerNo').textContent = c.CNTR_NO || '—';
    document.getElementById('detailContainerSubsdr').textContent = c.SUBSDR_NM || '—';
    document.getElementById('detailContainerType').textContent = c.CNTR_TYPE ? `Type: ${c.CNTR_TYPE}` : '';
    
    // Header badges
    let badges = '';
    if (c.PO_STATUS) {
        const statusBadge = getContainerStatusBadge(c.PO_STATUS);
        badges += `<span class="pill ${statusBadge.class}">${statusBadge.icon} ${c.PO_STATUS}</span>`;
    }
    if (c.PO_DETAIL_STATUS) {
        badges += `<span class="pill pill-sky"><i class="fas fa-info-circle"></i>${c.PO_DETAIL_STATUS}</span>`;
    }
    document.getElementById('detailContainerBadges').innerHTML = badges;
    
    // Invoice Info
    document.getElementById('detailContainerInvoice').textContent = c.INVOICE_NO || '—';
    document.getElementById('detailContainerInvoiceDate').textContent = c.INVOICE_DATE || '—';
    document.getElementById('detailContainerBLDate').textContent = c.BL_DATE || '—';
    
    // Route Info
    document.getElementById('detailContainerFromSite').textContent = c.FROM_SITE_NAME || '—';
    document.getElementById('detailContainerToSite').textContent = c.TO_SITE_NAME || '—';
    document.getElementById('detailContainerShipTo').textContent = c.SHIP_TO_CUSTOMER || '—';
    document.getElementById('detailContainerRSD').textContent = c.RSD_DATE || '—';

    // Customs + CY Combined Info
    document.getElementById('detailContainerCyEta').textContent    = c.CY1_ETA_DATE || '—';
    document.getElementById('detailContainerCyAta').textContent    = c.CY1_ATA_DATE || '—';
    document.getElementById('detailContainerCyEtd').textContent    = c.CY1_ETD_DATE || '—';
    document.getElementById('detailContainerCyAtd').textContent    = c.CY1_ATD_DATE || '—';
    document.getElementById('detailContainerFdestEta').textContent = c.FDEST_ETA_DATE || '—';
    document.getElementById('detailContainerFdestAta').textContent = c.FDEST_ATA_DATE || '—';
    document.getElementById('detailContainerCustomsReq').textContent  = c.ZCCREQDAT || '—';
    document.getElementById('detailContainerCustomsDec').textContent  = c.ZIMDEC   || '—';
    document.getElementById('detailContainerCustomsComp').textContent = c.ZCCCOMPT || '—';
    const customsStatus = c.ZCCSTCD_TX ? `${c.ZCCSTCD_TX} (${c.ZCCSTCD || ''})` : (c.ZCCSTCD || '—');
    document.getElementById('detailContainerCustomsStatus').textContent = customsStatus;
    
    // Timeline
    renderContainerTimeline(c);
}

/**
 * Get container status badge configuration
 * @param {string} status - PO Status
 * @returns {Object} Badge configuration
 */
function getContainerStatusBadge(status) {
    const statusMap = {
        'On factory Processing': { class: 'pill-amber', icon: '<i class="fas fa-industry"></i>' },
        'Factory Ship Out': { class: 'pill-violet', icon: '<i class="fas fa-truck"></i>' },
        'Intransit (POL~POD)': { class: 'pill-sky', icon: '<i class="fas fa-ship"></i>' },
        'Intransit (POD~FDEST)': { class: 'pill-blue', icon: '<i class="fas fa-truck-fast"></i>' },
        'F Dest Arrival': { class: 'pill-emerald', icon: '<i class="fas fa-flag-checkered"></i>' }
    };
    return statusMap[status] || { class: 'pill-slate', icon: '<i class="fas fa-circle"></i>' };
}

/**
 * Render container timeline
 * @param {Object} c - Container data
 */
function renderContainerTimeline(c) {
    const currentStepIdx = CONTAINER_STATUS_STEP[c.PO_DETAIL_STATUS] ?? CONTAINER_STATUS_STEP[c.PO_STATUS] ?? -1;

    function renderStep(stage, idx) {
        const dateVal = stage.dateField ? c[stage.dateField] : null;
        let stepCls = 'container-timeline-step';
        if (dateVal) {
            stepCls += ' done';
        } else if (idx === currentStepIdx) {
            stepCls += ' current';
        } else if (idx < currentStepIdx) {
            stepCls += ' done';
        } else {
            stepCls += ' pending';
        }
        const dateStr = dateVal || '—';
        const dateCls = dateVal ? 'filled' : '';
        return `
            <div class="${stepCls}">
                <div class="container-step-icon">
                    <i class="fas ${stage.icon}"></i>
                </div>
                <div class="container-step-label">${stage.label}</div>
                <div class="container-step-date ${dateCls}">${dateStr}</div>
            </div>
        `;
    }

    const row1Html = CONTAINER_TIMELINE_STAGES.slice(0, 6).map((s, i) => renderStep(s, i)).join('');
    const row2Html = CONTAINER_TIMELINE_STAGES.slice(6, 12).map((s, i) => renderStep(s, i + 6)).join('');

    document.getElementById('detailContainerTimeline').innerHTML = `
        <div class="container-timeline-row">${row1Html}</div>
        <div class="container-timeline-row">${row2Html}</div>
    `;
}

/**
 * Render model list grid
 * @param {Array} rows - Array of PO line objects
 */
function renderContainerModelGrid(rows, highlightModel = '') {
    const countEl = document.getElementById('detailContainerLineCount');
    const tbody = document.getElementById('detailContainerModelGridBody');

    if (!rows.length) {
        countEl.textContent = '';
        tbody.innerHTML = '<tr><td colspan="7" class="loading-row">No data</td></tr>';
        return;
    }

    countEl.textContent = `${rows.length} line(s)`;

    const hl = highlightModel ? highlightModel.trim().toUpperCase() : '';

    tbody.innerHTML = rows.map(r => {
        const isActive = hl && (r.MODEL || '').trim().toUpperCase() === hl;
        const rowStyle = isActive
            ? 'background:oklch(0.94 0.06 240);border-left:3px solid oklch(0.55 0.20 240);'
            : '';
        const modelStyle = isActive
            ? 'font-weight:700;color:oklch(0.40 0.22 240);'
            : 'font-weight:600;color:#0f172a;';
        return `
        <tr style="${rowStyle}">
            <td class="mono">${r.BL_NO || '—'}</td>
            <td class="mono">${r.PO_NO || '—'}</td>
            <td>${r.PO_LINE_NO ?? '—'}</td>
            <td>${r.BIZ_TYPE || '—'}</td>
            <td>${r.DIVISION || '—'}</td>
            <td><span style="${modelStyle}">${r.MODEL || '—'}${isActive ? ' <span style="font-size:11px;color:oklch(0.55 0.20 240);">●</span>' : ''}</span></td>
            <td class="num">${r.QTY != null ? Number(r.QTY).toLocaleString() : '—'}</td>
        </tr>`;
    }).join('');
}

/**
 * Create container number link for grid cell renderer
 * @param {Object} params - AG Grid cell renderer params
 * @returns {string} HTML string
 */
function containerNoRenderer(params) {
    if (!params.value) return '—';
    
    const subsdrNm = params.data?.SUBSDR_NAME || params.data?.SUBSDR_NM;
    if (!subsdrNm) return params.value;
    
    return `<a href="#" class="container-no-link" data-subsdr="${subsdrNm}" data-container="${params.value}">${params.value}</a>`;
}

// ══════════════════════════════════════════════════════════════════════════════
// [2] Customer Orders Modal — Bill To Customer 클릭 시 R4 Sparkline 팝업
// 참조: 참조/mockup-multi-order-v5.html (R4 · Sparkline + Transition Dots)
// 재사용: order-detail-modal.js 의 openOrderDetail()/fmtCurrency() 등
// ══════════════════════════════════════════════════════════════════════════════

// 오더 진행 단계 정의 (실제 데이터 필드 매핑)
const CUST_STAGE_DEFS = [
    { key: 'ORDERED',           label: 'Ord',    date: 'ORDERED_DATE' },
    { key: 'BOOKED',            label: 'Bkd',    date: 'BOOKED_DATE' },
    { key: 'HOLD',              label: 'Hold',   date: 'HOLD_DATE' },
    { key: 'HOLD_RELEASE',      label: 'Rel',    date: 'HOLD_RELEASE_DATE' },
    { key: 'PICK_RELEASE',      label: 'Pick',   date: 'TMS_PICK_RELEASE_DATE' },
    { key: 'LOAD_CREATION',     label: 'Load',   date: 'TMS_LOAD_CREATION_DATE' },
    { key: 'WH_RELEASE',        label: 'WH',     date: 'TMS_WH_RELEASE_DATE' },
    { key: 'SHIPPING_CONFIRM',  label: 'ShipCf', date: 'WMS_SHIPPING_CONFIRM_DATE' },
    { key: 'SHIPPED',           label: 'Ship',   date: 'WMS_SHIPPED_DATE' },
    { key: 'IOD',               label: 'IOD',    date: 'TMS_IOD_DATE' },
    { key: 'POD',               label: 'POD',    date: 'TMS_POD_DATE' },
];

function _custEsc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// ── 팝업 열기: activeGrid 의 필터 적용된 행 중 동일 Bill To Customer 코드 추출 ──
function openCustomerOrders(custCode, custName) {
    if (typeof activeGridApi === 'undefined' || !activeGridApi) return;
    const rows = [];
    activeGridApi.forEachNodeAfterFilter(node => {
        if (String(node.data.BILL_TO_CUSTOMER_CODE) === String(custCode)) rows.push(node.data);
    });
    if (!rows.length) return;

    document.getElementById('custOrdersTitle').textContent = custName || custCode;
    document.getElementById('custOrdersSubtitle').textContent = (custCode || '') + ' · ' + rows.length + ' active order line(s)';

    renderCustOrdersSummary(rows);
    renderCustOrdersList(rows);

    const backdrop = document.getElementById('custOrdersBackdrop');
    backdrop.style.display = 'flex';
    backdrop.scrollTop = 0;
    document.body.style.overflow = 'hidden';
}

function closeCustomerOrders() {
    document.getElementById('custOrdersBackdrop').style.display = 'none';
    document.body.style.overflow = '';
}

function renderCustOrdersSummary(rows) {
    const num = v => (v != null && isFinite(v)) ? Number(v) : 0;
    const totalAmt = rows.reduce((s, r) => s + num(r.ACTIVE_AMOUNT ?? r.ORDER_AMOUNT), 0);
    const totalQty = rows.reduce((s, r) => s + num(r.ACTIVE_QTY ?? r.ORDER_QTY), 0);
    const riskCnt = rows.filter(r => r.risk_alert === 'Y').length;
    const curr = rows[0].CURRENCY_CODE;
    document.getElementById('custOrdersTotalAmt').textContent = fmtCurrency(totalAmt, curr);
    document.getElementById('custOrdersTotalQty').textContent = totalQty.toLocaleString() + ' units';
    document.getElementById('custOrdersRiskCnt').textContent = riskCnt;
}

// 실제 데이터 기준 완료/현재 스테이지 transition 리스트 + (있는 경우) 도착 예정 추정치 1건
function _buildCustTx(o) {
    const tx = [];
    CUST_STAGE_DEFS.forEach(sd => {
        const d = o[sd.date];
        if (d) tx.push({ date: d, label: sd.label, state: sd.key, estimated: false });
    });
    if (o.est_arrival_date && !o.TMS_POD_DATE) {
        tx.push({ date: o.est_arrival_date, label: 'Est.Arr', state: 'EST_ARRIVAL', estimated: true });
    }
    return tx;
}

// 전체 표시 윈도우(일 단위) 계산 — 모든 오더의 tx/RAD 최소~최대 + 여유
function _computeCustWindow(rows) {
    let minD = null, maxD = null;
    rows.forEach(o => {
        _buildCustTx(o).forEach(t => {
            const d = new Date(t.date);
            if (isNaN(d)) return;
            if (!minD || d < minD) minD = d;
            if (!maxD || d > maxD) maxD = d;
        });
        if (o.RAD_DATE) {
            const d = new Date(o.RAD_DATE);
            if (!isNaN(d)) {
                if (!minD || d < minD) minD = d;
                if (!maxD || d > maxD) maxD = d;
            }
        }
    });
    const today = new Date(); today.setHours(0, 0, 0, 0);
    if (!minD) minD = today;
    if (!maxD || today > maxD) maxD = today;
    minD = new Date(minD); minD.setHours(0, 0, 0, 0); minD.setDate(minD.getDate() - 3);
    maxD = new Date(maxD); maxD.setHours(0, 0, 0, 0); maxD.setDate(maxD.getDate() + 5);
    const days = Math.max(1, Math.round((maxD - minD) / 86400000));
    return { start: minD, days };
}

function _custDayIdx(dateStr, win) {
    if (!dateStr) return -1;
    const d = new Date(dateStr); d.setHours(0, 0, 0, 0);
    return Math.round((d - win.start) / 86400000);
}

function _renderCustDayAxis(win) {
    const months = [];
    let cur = new Date(win.start.getFullYear(), win.start.getMonth(), 1);
    const endD = new Date(win.start); endD.setDate(endD.getDate() + win.days);
    while (cur <= endD) {
        months.push(new Date(cur));
        cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
    }
    const monthEls = months.map(m => {
        const idx = Math.round((m - win.start) / 86400000);
        const pct = (idx / win.days) * 100;
        if (pct < 0 || pct > 100) return '';
        const label = m.toLocaleString('en-US', { month: 'short', year: 'numeric' });
        return `<div class="month-line" style="left:${pct}%;"></div><span class="month-label" style="left:${pct}%;">${label}</span>`;
    }).join('');
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const todayIdx = Math.round((today - win.start) / 86400000);
    const todayPct = (todayIdx / win.days) * 100;
    const todayEl = (todayPct >= 0 && todayPct <= 100)
        ? `<div class="today-marker" style="left:${todayPct}%;" data-ctip="Today"><span class="t-lbl">TDY</span></div>` : '';
    return `<div class="day-axis">${monthEls}${todayEl}</div>`;
}

function _renderCustR4Track(o, win) {
    const tx = _buildCustTx(o);
    if (!tx.length) return '<div class="R4-track"><div class="R4-baseline"></div></div>';

    const pastTx = tx.filter(t => !t.estimated);
    const estTx = tx.filter(t => t.estimated);
    const firstI = _custDayIdx(tx[0].date, win);
    const lastPastI = pastTx.length ? _custDayIdx(pastTx[pastTx.length - 1].date, win) : firstI;
    const lastEstI = estTx.length ? _custDayIdx(estTx[estTx.length - 1].date, win) : lastPastI;
    const pct = i => (i / win.days) * 100;
    const isHold = o.PROGRESS_STATUS === 'HOLD' || o.HOLD_FLAG === 'Y';

    const covered = `<div class="R4-baseline covered ${isHold ? 'hold' : ''}" style="left:${pct(firstI)}%;width:${Math.max(0, pct(lastPastI) - pct(firstI))}%;"></div>`;
    const projected = estTx.length
        ? `<div class="R4-baseline projected" style="left:${pct(lastPastI)}%;width:${Math.max(0, pct(lastEstI) - pct(lastPastI))}%;"></div>` : '';

    const dots = tx.map((t, i) => {
        const p = pct(_custDayIdx(t.date, win));
        const isCurrent = (i === pastTx.length - 1) && !t.estimated;
        const cls = ['R4-dot'];
        if (isCurrent) cls.push('current');
        if (t.state === 'HOLD') cls.push('hold');
        if (t.estimated) cls.push('est');
        const lblCls = ['R4-dot-lbl'];
        if (isCurrent) lblCls.push('emph');
        if (t.estimated) lblCls.push('est');
        const tipSuffix = t.estimated ? ' (estimated)' : '';
        return `<div class="${cls.join(' ')}" style="left:${p}%;" data-ctip="${_custEsc(t.label)} · ${_custEsc(t.date)}${tipSuffix}"></div>
                <div class="${lblCls.join(' ')}" style="left:${p}%;">${_custEsc(t.label)}</div>`;
    }).join('');

    let radLine = '';
    const rad = o.RAD_DATE;
    if (rad) {
        const rp = pct(_custDayIdx(rad, win));
        if (rp >= -1 && rp <= 101) {
            const changed = !!(o.INIT_PROMISED_ARRIVAL_DATE && o.INIT_PROMISED_ARRIVAL_DATE !== rad);
            radLine = `<div class="R4-line rad ${changed ? 'moved' : ''}" style="left:${rp}%;"><span class="l-lbl" data-ctip="RAD ${_custEsc(rad)}${changed ? ' (moved from ' + _custEsc(o.INIT_PROMISED_ARRIVAL_DATE) + ')' : ''}">RAD ${rad.slice(5)}${changed ? ' ↑' : ''}</span></div>`;
        }
    }

    return `<div class="R4-track"><div class="R4-baseline"></div>${covered}${projected}${dots}${radLine}</div>`;
}

function _renderCustLaneLeft(o) {
    const stageMap = {
        HOLD: 'pill-rose', BOOKED: 'pill-sky', ENTERED: 'pill-slate', PICK_READY: 'pill-slate', HOLD_RELEASED: 'pill-slate',
        PICK_RELEASE: 'pill-amber', LOAD_CREATION: 'pill-violet', WH_RELEASE: 'pill-violet',
        SHIPPING_CONFIRM: 'pill-amber', SHIPPED: 'pill-sky', IOD: 'pill-emerald'
    };
    const cls = stageMap[o.PROGRESS_STATUS] || 'pill-slate';
    const risk = o.risk_alert === 'Y' ? '<span class="risk-badge" data-ctip="Risk Alert = Y">Y</span>' : '';
    const bo = o.BACK_ORDER_HOLD === 'Y' ? '<span class="pill pill-amber" data-ctip="Back Order Hold">BO</span>' : '';
    const amt = (o.ACTIVE_AMOUNT != null ? o.ACTIVE_AMOUNT : o.ORDER_AMOUNT) || 0;
    const qty = (o.ACTIVE_QTY != null ? o.ACTIVE_QTY : o.ORDER_QTY) || 0;
    const rad = o.RAD_DATE;
    const radChanged = !!(o.INIT_PROMISED_ARRIVAL_DATE && rad && o.INIT_PROMISED_ARRIVAL_DATE !== rad);

    // PICK_READY → HOLD RELEASED 표기 변경
    const displayStatus = o.PROGRESS_STATUS === 'PICK_READY' ? 'HOLD RELEASED' : (o.PROGRESS_STATUS || '-');

    return `
      <div class="lane-l">
        <div class="l1">
          <span data-ctip="Flow Stage"><span class="pill ${cls}">${_custEsc(displayStatus)}</span></span>
          <span class="ono order-no-link" data-order-no="${_custEsc(o.SALES_ORDER_NO)}" data-line-no="${_custEsc(o.SALES_ORDER_LINE_NO)}" data-ctip="Open Order Detail">${_custEsc(o.SALES_ORDER_NO)}</span>
          ${risk}${bo}
          <span class="l1-right">
            <span class="metric" data-ctip="Quantity">${Number(qty).toLocaleString()}</span>
            <span class="metric amount" data-ctip="Order Amount">${fmtCurrency(amt, o.CURRENCY_CODE)}</span>
            ${rad ? `<span class="metric rad ${radChanged ? 'moved' : ''}" data-ctip="RAD">${rad.slice(5)}${radChanged ? ' ↑' : ''}</span>` : ''}
          </span>
        </div>
        <div class="l2">
          <span data-ctip="Ship To Customer">${_custEsc(o.SHIP_TO_CUSTOMER_NAME || '')}</span>
          <span class="sep">·</span>
          <span class="model" data-ctip="Model Code">${_custEsc(o.MODEL_CODE || '')}</span>
          <span class="sep">·</span>
          <span data-ctip="Order Type">${_custEsc(o.ORDER_TYPE_NAME || '')}</span>
        </div>
      </div>`;
}

function _renderCustGroupHead(name, gRows, groupId) {
    const num = v => (v != null && isFinite(v)) ? Number(v) : 0;
    const total = gRows.reduce((s, r) => s + num(r.ACTIVE_AMOUNT ?? r.ORDER_AMOUNT), 0);
    const units = gRows.reduce((s, r) => s + num(r.ACTIVE_QTY ?? r.ORDER_QTY), 0);
    const riskCnt = gRows.filter(r => r.risk_alert === 'Y').length;
    const alert = riskCnt > 0
        ? `<span class="alert" data-ctip="Risk alert count">Risk: <b>${riskCnt}</b></span>`
        : `<span data-ctip="No risk alerts">Risk: <b style="color:var(--muted-foreground);">0</b></span>`;
    return `
      <div class="grp-head" onclick="toggleCustGroup('${groupId}')" style="cursor:pointer;">
        <i class="fas fa-chevron-down gh-caret" id="caret-${groupId}"></i>
        <span class="gh-name" data-ctip="Ship To Customer">${_custEsc(name)}</span>
        <span class="gh-cnt" data-ctip="Order lines">${gRows.length} orders</span>
        <div class="gh-meta">
          <span data-ctip="Sum of Active Amount"><b>${fmtCurrency(total, gRows[0].CURRENCY_CODE)}</b> total</span>
          <span data-ctip="Sum of Active Quantity"><b>${units.toLocaleString()}</b> units</span>
          ${alert}
        </div>
      </div>`;
}

function renderCustOrdersList(rows) {
    const win = _computeCustWindow(rows);

    const groups = {};
    rows.forEach(o => {
        const k = o.SHIP_TO_CUSTOMER_NAME || 'Unknown Ship To';
        (groups[k] = groups[k] || []).push(o);
    });
    const groupKeys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);

    let html = `<div class="list-axis"><div class="head-l">Order · Info</div><div class="head-r">${_renderCustDayAxis(win)}</div></div>`;
    groupKeys.forEach((k, idx) => {
        const gRows = groups[k];
        const groupId = `custGrp${idx}`;
        html += _renderCustGroupHead(k, gRows, groupId);
        html += `<div id="${groupId}" class="cust-group-body">`;
        gRows.forEach(o => {
            html += `<div class="list-lane">${_renderCustLaneLeft(o)}<div class="lane-r">${_renderCustR4Track(o, win)}</div></div>`;
        });
        html += `</div>`;
    });

    document.getElementById('custOrdersListWrap').innerHTML = html;
}

// ── Ship To 그룹 토글 ──
function toggleCustGroup(groupId) {
    const body = document.getElementById(groupId);
    const caret = document.getElementById('caret-' + groupId);
    if (!body || !caret) return;

    if (body.style.display === 'none') {
        body.style.display = '';
        caret.className = 'fas fa-chevron-down gh-caret';
    } else {
        body.style.display = 'none';
        caret.className = 'fas fa-chevron-right gh-caret';
    }
}


// ══════════════════════════════════════════════════════════════════════════════
// [3] 공통 이벤트 리스너
// ══════════════════════════════════════════════════════════════════════════════

// Container no link 클릭
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('container-no-link')) {
        e.preventDefault();
        const subsdrNm = e.target.dataset.legalEntity || e.target.dataset.subsdr;
        const containerNo = e.target.dataset.containerNo || e.target.dataset.container;
        const modelCode = e.target.dataset.modelCode || '';
        openContainerDetail(subsdrNm, containerNo, modelCode);
    }
});

// Bill To Customer Name 셀 클릭 → 팝업 오픈
document.addEventListener('click', function(e) {
    const link = e.target.closest('.custname-link');
    if (link) {
        e.preventDefault();
        openCustomerOrders(link.dataset.custCode, link.dataset.custName);
    }
});

// ESC 키로 모달 닫기
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const containerBackdrop = document.getElementById('containerDetailBackdrop');
        if (containerBackdrop && containerBackdrop.style.display === 'flex') {
            closeContainerDetail();
        }
        const custBackdrop = document.getElementById('custOrdersBackdrop');
        if (custBackdrop && custBackdrop.style.display === 'flex') {
            closeCustomerOrders();
        }
    }
});

// Backdrop 클릭으로 모달 닫기
document.addEventListener('DOMContentLoaded', function() {
    const containerBackdrop = document.getElementById('containerDetailBackdrop');
    if (containerBackdrop) {
        containerBackdrop.addEventListener('click', function(e) {
            if (e.target.id === 'containerDetailBackdrop') closeContainerDetail();
        });
    }

    const custBackdrop = document.getElementById('custOrdersBackdrop');
    if (custBackdrop) {
        custBackdrop.addEventListener('click', function(e) {
            if (e.target.id === 'custOrdersBackdrop') closeCustomerOrders();
        });
    }
});
