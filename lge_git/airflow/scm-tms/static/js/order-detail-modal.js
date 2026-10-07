// ══════════════════════════════════════════════════════════════════════════════
// Order Detail Modal Functions
// ══════════════════════════════════════════════════════════════════════════════

// Timeline stage definitions
const TIMELINE_STAGES = [
    { key: 'ORDERED',          label: 'Ordered',        icon: 'fa-clipboard-list',   dateField: 'ORDERED_DATE',               daysField: 'ENTERED_IN_DAYS' },
    { key: 'BOOKED',           label: 'Booked',         icon: 'fa-calendar-check',   dateField: 'BOOKED_DATE',                daysField: 'BOOKED_IN_DAYS' },
    { key: 'HOLD',             label: 'Hold',           icon: 'fa-hand',             dateField: 'HOLD_DATE',                  daysField: 'HOLD_IN_DAYS' },
    { key: 'PICK_READY',       label: 'Hold Release',   icon: 'fa-box',              dateField: 'HOLD_RELEASE_DATE',          daysField: 'HOLD_RELEASE_IN_DAYS' },
    { key: 'PICK_RELEASE',     label: 'Pick Release',   icon: 'fa-dolly',            dateField: 'TMS_PICK_RELEASE_DATE',      daysField: 'PICK_RELEASE_IN_DAYS' },
    { key: 'LOAD_CREATION',    label: 'Load Creation',  icon: 'fa-truck-ramp-box',   dateField: 'TMS_LOAD_CREATION_DATE',     daysField: 'LOAD_CREATION_IN_DAYS' },
    { key: 'WH_RELEASE',       label: 'WH Release',     icon: 'fa-warehouse',        dateField: 'TMS_WH_RELEASE_DATE',        daysField: 'WH_RELEASE_IN_DAYS' },
    { key: 'SHIPPING_CONFIRM', label: 'Ship Confirm',   icon: 'fa-clipboard-check',  dateField: 'WMS_SHIPPING_CONFIRM_DATE',  daysField: 'SHIPPING_CONFIRM_IN_DAYS' },
    { key: 'SHIPPED',          label: 'Shipped',        icon: 'fa-truck-fast',       dateField: 'WMS_SHIPPED_DATE',           daysField: 'SHIPPED_IN_DAYS' },
];

// Stage to step index mapping
const STAGE_TO_STEP = {
    'ORDERED': 0, 'BOOKED': 1, 'HOLD': 2, 'PICK_READY': 3,
    'PICK_RELEASE': 4, 'LOAD_CREATION': 5, 'WH_RELEASE': 6,
    'SHIPPING_CONFIRM': 7, 'SHIPPED': 8
};

function openOrderDetail(orderNo, lineNo) {
    if (!orderNo) return;
    
    // Find the order data from the grid
    const rowData = [];
    if (typeof activeGridApi !== 'undefined' && activeGridApi) {
        activeGridApi.forEachNode(node => rowData.push(node.data));
    }
    
    const order = rowData.find(r => 
        r.SALES_ORDER_NO === orderNo && 
        (!lineNo || r.SALES_ORDER_LINE_NO == lineNo)
    );
    
    if (!order) {
        console.warn('Order not found:', orderNo, lineNo);
        return;
    }
    
    renderOrderDetail(order);
    const backdrop = document.getElementById('orderDetailBackdrop');
    backdrop.style.display = 'flex';
    backdrop.scrollTop = 0;  // Scroll to top when opening
    document.body.style.overflow = 'hidden';
}

function closeOrderDetail() {
    document.getElementById('orderDetailBackdrop').style.display = 'none';
    document.body.style.overflow = '';
}

function toggleDetailAcc(id) {
    document.getElementById(id).classList.toggle('open');
}

function renderOrderDetail(o) {
    if (!o) return;
    
    // Header
    document.getElementById('detailOrderNo').textContent = o.SALES_ORDER_NO || '—';
    document.getElementById('detailLineNo').textContent = '/ Line ' + (o.SALES_ORDER_LINE_NO || '—');
    document.getElementById('detailCustPo').textContent = o.CUST_PO_NO || '—';
    document.getElementById('detailOrderType').textContent = o.ORDER_TYPE_NAME || '—';
    document.getElementById('detailDivision').textContent = o.DIV_NM || '—';
    
    // Header badges
    let badges = '';
    if (o.PROGRESS_STATUS) {
        const stageMap = {
            'HOLD': 'pill-rose', 'BOOKED': 'pill-sky', 'ENTERED': 'pill-slate',
            'PICK_READY': 'pill-slate', 'PICK_RELEASE': 'pill-amber',
            'LOAD_CREATION': 'pill-violet', 'WH_RELEASE': 'pill-violet',
            'SHIPPING_CONFIRM': 'pill-amber', 'SHIPPED': 'pill-sky', 'IOD': 'pill-emerald'
        };
        const cls = stageMap[o.PROGRESS_STATUS] || 'pill-slate';
        badges += `<span class="pill ${cls}"><i class="fas fa-flag-checkered"></i>${o.PROGRESS_STATUS}</span>`;
    }
    if (o.risk_alert === 'Y') {
        badges += '<span class="pill pill-rose"><i class="fas fa-triangle-exclamation"></i>RISK</span>';
    }
    if (o.HOLD_FLAG === 'Y') {
        const holdType = o.hold_type ? ' · ' + o.hold_type : '';
        badges += `<span class="pill pill-rose"><i class="fas fa-hand"></i>HOLD${holdType}</span>`;
    }
    if (o.BACK_ORDER_HOLD === 'Y') {
        badges += '<span class="pill pill-amber"><i class="fas fa-box-open"></i>BACK ORDER</span>';
    }
    document.getElementById('detailHeaderBadges').innerHTML = badges;
    
    // Customer Info
    document.getElementById('detailBillName').textContent = o.BILL_TO_CUSTOMER_NAME || '—';
    document.getElementById('detailBillCode').textContent = o.BILL_TO_CUSTOMER_CODE || '';
    document.getElementById('detailShipName').textContent = o.SHIP_TO_CUSTOMER_NAME || '—';
    document.getElementById('detailShipCode').textContent = o.SHIP_TO_CUSTOMER_CODE || '';
    document.getElementById('detailBiz').textContent = o.BILLTO_BIZ_NAME || '—';
    document.getElementById('detailTeam').textContent = o.TEAM_NAME ? ('· ' + o.TEAM_NAME) : '';
    
    // Product Info
    document.getElementById('detailModel').textContent = o.MODEL_CODE || '—';
    document.getElementById('detailModelCat').textContent = o.MODEL_CATEGORY || '';
    const prodPath = [o.PRODUCT_LEVEL1_NAME, o.PRODUCT_LEVEL2_NAME, o.PRODUCT_LEVEL3_NAME, o.PRODUCT_LEVEL4_NAME]
        .filter(Boolean).join(' › ');
    document.getElementById('detailProdPath').textContent = prodPath || '—';
    document.getElementById('detailShipMethod').textContent = o.SHIPPING_METHOD_CODE || '—';
    document.getElementById('detailWarehouse').textContent = o.WAREHOUSE_CODE ? ('· WH ' + o.WAREHOUSE_CODE) : '';
    
    // Volume & Amount
    const qtyStr = o.ORDER_QTY != null ? Number(o.ORDER_QTY).toLocaleString() + ' units' : '—';
    document.getElementById('detailQty').textContent = qtyStr;
    const cancelStr = (o.CANCEL_QTY > 0) ? ('· cancelled ' + Number(o.CANCEL_QTY).toLocaleString()) : '';
    document.getElementById('detailCancelQty').textContent = cancelStr;
    
    const amtStr = o.ORDER_AMOUNT != null ? fmtCurrency(o.ORDER_AMOUNT, o.CURRENCY_CODE) : '—';
    document.getElementById('detailAmt').textContent = amtStr;
    const usdStr = (o.CURRENCY_CODE !== 'USD' && o.USD_ORDER_AMOUNT != null) 
        ? ('(USD ' + fmtCurrency(o.USD_ORDER_AMOUNT) + ')') : '';
    document.getElementById('detailAmtUsd').textContent = usdStr;
    
    const unitPriceStr = o.UNIT_SELLING_PRICE != null ? fmtCurrency(o.UNIT_SELLING_PRICE, o.CURRENCY_CODE) : '—';
    document.getElementById('detailUnitPrice').textContent = unitPriceStr;
    
    // Delivery Dates
    document.getElementById('detailRadCell').innerHTML = renderRadCell(o);
    const estArrival = o.est_arrival_date 
        ? `<span class="mono">${o.est_arrival_date}</span>${renderDdayPill(o.est_arrival_date)}`
        : '<span style="color:var(--muted-foreground);font-style:italic;">not estimated yet</span>';
    document.getElementById('detailEstArrival').innerHTML = estArrival;
    document.getElementById('detailApptCell').innerHTML = renderApptCell(o);
    
    // Timeline
    renderTimeline(o);
    
    // Key Dates
    renderDateGrid(o);
    
    // Flags & Status
    renderFlagGrid(o);
}

function renderRadCell(o) {
    const init = o.INIT_PROMISED_ARRIVAL_DATE;
    const cur = o.promised_arrival_date || o.RAD_DATE;
    if (!init && !cur) return '<span style="color:var(--muted-foreground);font-style:italic;">not set</span>';
    
    const changed = init && cur && init !== cur;
    const initCls = changed ? 'rad-init' : 'rad-init same';
    const latestCls = changed ? 'rad-latest changed' : 'rad-latest';
    const tag = changed 
        ? '<span class="rad-tag changed">changed</span>'
        : '<span class="rad-tag same">unchanged</span>';
    
    return `
        <div class="rad-cmp">
            <span class="${initCls}">${init || '—'}</span>
            ${changed ? '<i class="fas fa-arrow-right rad-arrow"></i>' : ''}
            <span class="${latestCls}">${cur || '—'}</span>
            ${tag}
        </div>
        ${renderDdayPill(cur)}
    `;
}

function renderApptCell(o) {
    const from = o.appointment_from_date;
    const to = o.appointment_to_date;
    if (!from && !to) return '<span style="color:var(--muted-foreground);font-style:italic;">not scheduled</span>';
    if (from && to && from !== to) {
        return `<span class="mono">${from}</span> <i class="fas fa-arrow-right" style="font-size:10px;color:var(--muted-foreground);"></i> <span class="mono">${to}</span>`;
    }
    return `<span class="mono">${from || to}</span>`;
}

function renderDdayPill(targetDate) {
    if (!targetDate) return '';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const target = new Date(targetDate);
    target.setHours(0, 0, 0, 0);
    const diffDays = Math.round((target - today) / (1000 * 60 * 60 * 24));
    
    let cls, txt;
    if (diffDays < 0) {
        cls = 'danger';
        txt = 'D+' + Math.abs(diffDays) + ' past';
    } else if (diffDays === 0) {
        cls = 'warn';
        txt = 'D-Day';
    } else if (diffDays <= 2) {
        cls = 'warn';
        txt = 'D-' + diffDays;
    } else {
        cls = 'ok';
        txt = 'D-' + diffDays;
    }
    return `<span class="dday-pill ${cls}">${txt}</span>`;
}

function renderTimeline(o) {
    const currentStepIdx = STAGE_TO_STEP[o.PROGRESS_STATUS] ?? -1;
    
    const html = TIMELINE_STAGES.map((stage, idx) => {
        const dateVal = o[stage.dateField];
        const daysVal = stage.daysField ? o[stage.daysField] : null;
        
        let stepCls = 'timeline-step';
        if (idx < currentStepIdx || (idx === currentStepIdx && dateVal)) {
            stepCls += ' done';
        } else if (idx === currentStepIdx) {
            stepCls += ' current';
        } else {
            stepCls += ' pending';
        }
        
        const dateStr = dateVal || '—';
        const daysStr = (daysVal != null && daysVal > 0) ? `${daysVal}d` : '';
        
        return `
            <div class="${stepCls}">
                <div class="step-icon"><i class="fas ${stage.icon}"></i></div>
                <div class="step-label">${stage.label}</div>
                <div class="step-date">${dateStr}</div>
                ${daysStr ? `<div class="step-days">${daysStr}</div>` : ''}
            </div>
        `;
    }).join('');
    
    document.getElementById('detailTimeline').innerHTML = html;
}

function renderDateGrid(o) {
    const dates = [
        ['Ordered', o.ORDERED_DATE],
        ['Booked', o.BOOKED_DATE],
        ['Hold', o.HOLD_DATE],
        ['Hold Release', o.HOLD_RELEASE_DATE],
        ['Pick Release', o.TMS_PICK_RELEASE_DATE],
        ['Load Creation', o.TMS_LOAD_CREATION_DATE],
        ['WH Release', o.TMS_WH_RELEASE_DATE],
        ['Ship Confirm', o.WMS_SHIPPING_CONFIRM_DATE],
        ['Shipped', o.WMS_SHIPPED_DATE],
        ['IOD', o.TMS_IOD_DATE],
        ['POD', o.TMS_POD_DATE],
        ['Sales', o.SALES_DATE],
        ['RAD', o.RAD_DATE],
        ['Est. Arrival', o.est_arrival_date],
        ['Appt From', o.appointment_from_date],
        ['Appt To', o.appointment_to_date],
    ];
    
    const html = dates.map(([label, val]) => {
        const filled = val ? 'filled' : '';
        const valCls = val ? '' : 'empty';
        const valText = val || '—';
        return `
            <div class="date-tile ${filled}">
                <div class="d-label">${label}</div>
                <div class="d-value ${valCls}">${valText}</div>
            </div>
        `;
    }).join('');
    
    document.getElementById('detailDateGrid').innerHTML = html;
}

function renderFlagGrid(o) {
    const fmtNum = v => (v != null && isFinite(v)) ? Number(v).toLocaleString() : '—';
    
    const items = [
        { key: 'Risk Alert', val: o.risk_alert || 'N', on: o.risk_alert === 'Y' ? 'danger' : 'off' },
        { key: 'Hold', val: o.HOLD_FLAG === 'Y' ? (o.HOLD_REASON_CODE || 'Y') : 'N', on: o.HOLD_FLAG === 'Y' ? 'danger' : 'off' },
        { key: 'Back Order', val: o.BACK_ORDER_HOLD === 'Y' ? 'Y' : 'N', on: o.BACK_ORDER_HOLD === 'Y' ? 'warn' : 'off' },
        { key: 'RAD Mgmt', val: o.rad_mgmt_type || '—', on: o.rad_mgmt_type === 'Unmanaged' ? 'info' : (o.rad_mgmt_type === 'Managed' ? 'ok' : 'off') },
        { key: 'Status', val: o.LINE_STATUS_CODE || '—', on: (o.LINE_STATUS_CODE === 'CLOSED' || o.LINE_STATUS_CODE === 'Completed') ? 'off' : 'ok' },
        { key: 'Cancel Qty', val: fmtNum(o.CANCEL_QTY || 0), on: (o.CANCEL_QTY > 0) ? 'warn' : 'off' },
    ];
    
    if (o.hold_type) {
        items.splice(2, 0, { key: 'Hold Type', val: o.hold_type, on: 'warn' });
    }
    if (o.days_since_ordered != null) {
        items.push({ key: 'Order Age', val: o.days_since_ordered + 'd', on: 'off' });
    }
    
    const html = items.map(it => `
        <div class="flag-item ${it.on}">
            <span class="flag-key">${it.key}</span>
            <span class="flag-val">${it.val}</span>
        </div>
    `).join('');
    
    document.getElementById('detailFlagGrid').innerHTML = html;
}

// Event listener for order no links in the grid
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('order-no-link')) {
        e.preventDefault();
        const orderNo = e.target.dataset.orderNo;
        const lineNo = e.target.dataset.lineNo;
        openOrderDetail(orderNo, lineNo);
    }
});

// Keyboard shortcut (ESC to close)
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const backdrop = document.getElementById('orderDetailBackdrop');
        if (backdrop && backdrop.style.display === 'flex') {
            closeOrderDetail();
        }
    }
});

// Click backdrop to close
document.addEventListener('DOMContentLoaded', function() {
    const backdrop = document.getElementById('orderDetailBackdrop');
    if (backdrop) {
        backdrop.addEventListener('click', function(e) {
            if (e.target.id === 'orderDetailBackdrop') {
                closeOrderDetail();
            }
        });
    }
});
