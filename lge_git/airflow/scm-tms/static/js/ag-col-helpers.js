/**
 * ag-col-helpers.js
 * AG Grid 공통 컬럼 헬퍼 함수
 * order.html / active_orders.html 에서 공유
 */

function c(field, headerName, opts = {}) {
    return {
        field,
        headerName,
        sortable: true,
        filter: true,
        resizable: true,
        headerClass: 'ag-header-center',
        cellStyle: { textAlign: 'right' },
        ...opts,
    };
}

function setCol(field, headerName, opts = {}) {
    return c(field, headerName, { filter: 'agSetColumnFilter', ...opts });
}

function txtCol(field, headerName, opts = {}) {
    return c(field, headerName, { filter: 'agTextColumnFilter', ...opts });
}

function dateCol(field, headerName, opts = {}) {
    return c(field, headerName, { filter: 'agDateColumnFilter', width: 120, ...opts });
}

/** 정수 수량 컬럼 (천 단위, 소수 없음) */
function qtyCol(field, headerName, opts = {}) {
    return c(field, headerName, {
        type: 'numericColumn',
        headerClass: 'ag-header-center',
        valueFormatter: p => (p.value != null && isFinite(p.value)) ? Math.trunc(p.value).toLocaleString() : '-',
        width: 100,
        cellClass: 'num',
        ...opts,
    });
}

/** 소수 2자리 금액 컬럼 */
function numCol(field, headerName, opts = {}) {
    return c(field, headerName, {
        type: 'numericColumn',
        valueFormatter: p => (p.value != null && isFinite(p.value) && p.value > 0)
            ? Number(p.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : '-',
        width: 120,
        cellClass: 'num',
        ...opts,
    });
}

/** 정수 로컬통화 금액 컬럼 (천 단위 구분, 소수 없음) */
function amtCol(field, headerName, opts = {}) {
    return c(field, headerName, {
        type: 'numericColumn',
        width: 130,
        cellClass: 'num',
        cellStyle: { textAlign: 'right' },
        valueFormatter: p => (p.value != null && isFinite(p.value)) ? Math.round(p.value).toLocaleString() : '-',
        ...opts,
    });
}

/** 정수 USD 금액 컬럼 ($ 접두, 천 단위 구분, 소수 없음) */
function usdCol(field, headerName, opts = {}) {
    return c(field, headerName, {
        type: 'numericColumn',
        width: 145,
        cellClass: 'num',
        cellStyle: { textAlign: 'right' },
        valueFormatter: p => (p.value != null && isFinite(p.value)) ? '$' + Math.round(p.value).toLocaleString() : '-',
        ...opts,
    });
}
