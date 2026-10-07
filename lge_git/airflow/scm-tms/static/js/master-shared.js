// ─────────────────────────────────────────────────────────────────────
// master-shared.js  ―  Master Data 공통 유틸리티
// 모든 탭 JS 파일보다 먼저 로드되어야 합니다.
// 의존: ag-col-helpers.js, ag-xls-grid.js
// 전역 전제: _FIRST_TAB, TABS (master_data.html 인라인 스크립트에서 설정)
// ─────────────────────────────────────────────────────────────────────

// ── 페이지뷰 로그 (URL hash 기반 page_id 포함) ─────────────────────────────
// URL hash(#shipto 등)는 서버 HTTP 요청에 포함되지 않으므로
// 프론트엔드에서 직접 /api/web-log/pageview 를 호출해 page_id 를 전송한다.
function _logMasterPageView(tab) {
    try {
        fetch('/api/web-log/pageview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                menu_id:      'master-data',
                page_id:      tab || '_',
                request_path: location.pathname + (tab ? '#' + tab : ''),
            }),
        });
    } catch(e) { /* silent */ }
}

// ── 탭 통합 정의 ───────────────────────────────────────────────────────
// 소문자 키(서버 page_id) → { canonical: 로직/그리드 키, panel: 패널 DOM id }
// canonical 은 initXxx / _getApi / loadData 등 프론트 내부 로직에서 사용하는 키,
// panel 은 해당 탭의 DOM 패널 id 이다.
const _TAB_DEFS = {
    'billto':      { canonical: 'billto',      panel: 'panelBillto'      },
    'billto-ph':   { canonical: 'billtoPh',    panel: 'panelBilltoPh'    }, // PH 전용: 별도 패널/그리드
    'shipto':      { canonical: 'shipto',      panel: 'panelShipto'      },
    'product':     { canonical: 'product',     panel: 'panelProduct'     },
    'salesteam':   { canonical: 'salesTeam',   panel: 'panelSalesTeam'   },
    'salestarget': { canonical: 'salesTarget', panel: 'panelSalesTarget' },
    'billtobiz':   { canonical: 'billtoBiz',   panel: 'panelBilltoBiz'   },
};

// 어떤 케이스(서버 page_id/canonical/원본)로 들어와도 정의를 찾는다.
function _tabDef(tab) {
    return _TAB_DEFS[(tab || '').toLowerCase()] || null;
}

// 어떤 케이스로 들어와도 canonical key 로 통일
// 'billTo' → 'billto',  'billto-ph' → 'billtoPh'  등 (미정의 시 원본 유지)
function _normalizeTab(tab) {
    const def = _tabDef(tab);
    return def ? def.canonical : tab;
}

// 탭 → 패널 DOM id (정의 없으면 'panel' + PascalCase 폴백)
function _panelId(tab) {
    const def = _tabDef(tab);
    if (def) return def.panel;
    const t = _normalizeTab(tab);
    return 'panel' + t.charAt(0).toUpperCase() + t.slice(1);
}

// ══════════════════════════════════════════════════════════════════════
// 공통 감사 컬럼
// ══════════════════════════════════════════════════════════════════════
const auditCols = [
    dateCol('input_dt',        'Created',    { width:130 }),
    txtCol('input_user_id',    'Created By', { width:110 }),
    dateCol('update_dt',       'Updated',    { width:130 }),
    txtCol('update_user_id',   'Updated By', { width:110 }),
];

// ══════════════════════════════════════════════════════════════════════
// 유효성 검증
// ══════════════════════════════════════════════════════════════════════
const _VAL_RULES = {
    billto: [
        { field:'billto_code',       label:'Bill-To Code', notNull:true, unique:true, maxLen:64 },
        { field:'billto_name',       label:'Bill-To Name', notNull:true, maxLen:256 },
        { field:'billto_group_name', label:'Group Name',   maxLen:256 },
        { field:'billto_biz_name',   label:'Biz Name',     maxLen:256 },
    ],
    billtoPh: [
        { field:'billto_code',       label:'Bill-To Code', notNull:true, unique:true, maxLen:64 },
        { field:'billto_name',       label:'Bill-To Name', notNull:true, maxLen:256 },
        { field:'billto_group_name', label:'Group Name',   maxLen:256 },
        { field:'billto_biz_name',   label:'Biz Name',     maxLen:256 },
    ],
    shipto: [
        { field:'shipto_code', label:'Ship-To Code', notNull:true, unique:true, maxLen:64 },
        { field:'shipto_name', label:'Ship-To Name', maxLen:256 },
        { field:'address',     label:'Address',      maxLen:1024 },
        { field:'postal_code', label:'Postal Code',  maxLen:64 },
        { field:'route',       label:'Route',        maxLen:64 },
    ],
    product: [
        { field:'product_code',          label:'Product Code',  notNull:true, unique:true, maxLen:64 },
        { field:'product_group_code',    label:'Group Code',    maxLen:64 },
        { field:'product_category_code', label:'Category Code', maxLen:64 },
    ],
};

const _cellErrors = {};

// 변경된 셀 추적 — CRUD 그리드용: 'nodeId__field'
const _changedCells = new Set();

// 변경된 셀 추적 — Pivot 그리드용(Sales Target / Sales Team): 'pkVal__field'
const _pivotChangedCells = new Set();

/**
 * Pivot 그리드 onCellValueChanged 공통 핸들러.
 * _stDefaultColDef.cellClassRules 의 cell-mod 규칙과 함께 사용.
 */
function _pivotCellChanged(params, pkField) {
    if (params.node?.rowPinned || !params.data?._orig) return;
    const field  = params.colDef?.field;
    const pkVal  = params.data[pkField];
    if (pkVal && field && !field.startsWith('_')) {
        _pivotChangedCells.add(`${pkVal}__${field}`);
        params.api.refreshCells({ rowNodes: [params.node], columns: [field], force: true });
    }
}

/** Pivot 변경 셀 초기화 (로드/저장 후 호출) */
function _pivotClearChanges() {
    _pivotChangedCells.clear();
}

function _valKey(rowNode, field) {
    return `${rowNode.rowIndex}__${field}`;
}

function _validateAll(tab, api) {
    const rules  = _VAL_RULES[tab] || [];
    const errors = [];
    const nodesToRefresh = new Set();

    Object.keys(_cellErrors).forEach(k => delete _cellErrors[k]);

    const pkSeen = {};
    api.forEachNode(node => {
        const d = node.data;
        if (_isEmptyRow(d)) return;
        if (d._status !== 'NEW' && d._status !== 'MOD') return;

        rules.forEach(rule => {
            const val = (d[rule.field] ?? '').toString().trim();
            let errMsg = null;

            if (rule.notNull && !val) {
                errMsg = `${rule.label}: is required`;
            } else if (rule.maxLen && val.length > rule.maxLen) {
                errMsg = `${rule.label}: ${rule.maxLen} chars max (current: ${val.length} chars)`;
            }

            if (errMsg) {
                _cellErrors[_valKey(node, rule.field)] = errMsg;
                errors.push(`행 ${node.rowIndex + 1} - ${errMsg}`);
                nodesToRefresh.add(node);
            }

            if (rule.unique && val) {
                if (pkSeen[val] !== undefined) {
                    const dupMsg = `${rule.label}: duplicate value "${val}"`;
                    _cellErrors[_valKey(node, rule.field)] = dupMsg;
                    _cellErrors[`${pkSeen[val]}__${rule.field}`] = dupMsg;
                    errors.push(`Row ${node.rowIndex + 1} - ${dupMsg}`);
                    nodesToRefresh.add(node);
                } else {
                    pkSeen[val] = node.rowIndex;
                }
            }
        });
    });

    if (nodesToRefresh.size)
        api.refreshCells({ rowNodes: Array.from(nodesToRefresh), force: true });
    api.refreshCells({ force: true });

    const banner = document.getElementById('valBanner_' + tab);
    const msgEl  = document.getElementById('valMsg_' + tab);
    if (errors.length) {
        msgEl.innerHTML = `<strong>${errors.length} error(s)</strong>: ` +
            errors.slice(0, 3).join(' / ') +
            (errors.length > 3 ? ` + ${errors.length - 3} more` : '');
        banner.classList.add('show');
    } else {
        banner.classList.remove('show');
    }
    return errors.length === 0;
}

// cellClassRules: 에러 셀 / 읽기전용 셀 / 변경 셀 강조
const _cellClassRules = {
    'cell-error': p => {
        if (!p.node || p.colDef.field === '_status') return false;
        return !!_cellErrors[`${p.node.rowIndex}__${p.colDef.field}`];
    },
    'cell-mod': p => {
        if (!p.node || !p.colDef.field || p.colDef.field.startsWith('_')) return false;
        if (!p.node.data?._orig) return false;   // NEW 행은 행 자체가 이미 표시됨
        return _changedCells.has(`${p.node.id}__${p.colDef.field}`);
    },
    'cell-readonly': p => {
        const field = p.colDef.field;
        if (!field || field.startsWith('_')) return false;
        if (!p.node || _isEmptyRow(p.node.data)) return false;
        const editable = p.colDef.editable;
        if (typeof editable === 'function') return !editable(p);
        return !editable;
    },
};

const _tooltipValueGetter = p => {
    if (!p.node || !p.colDef.field) return null;
    return _cellErrors[`${p.node.rowIndex}__${p.colDef.field}`] || null;
};

// ══════════════════════════════════════════════════════════════════════
// Excel 모드 헬퍼
// ══════════════════════════════════════════════════════════════════════
const _EMPTY_ROWS = 30;
const _PK_FIELD   = { billto:'billto_code', billtoPh:'billto_code', shipto:'shipto_code', product:'product_code' };
const _EDIT_COLS  = {
    billto:   ['billto_code', 'billto_name', 'billto_group_name', 'billto_biz_name'],
    billtoPh: ['billto_code', 'billto_name', 'billto_group_name', 'billto_biz_name'],
    shipto:  ['shipto_code', 'shipto_name', 'address', 'postal_code', 'route'],
    product: ['product_code', 'product_group_code', 'product_category_code'],
};

// 프론트 canonical tab → 서버 API 경로 / 편집권한 page_id 매핑
const _API_TAB  = { billtoPh: 'billto-ph' };
const _EDIT_TAB = { billtoPh: 'billto-ph' };
function _apiTab(tab)  { return _API_TAB[tab]  || tab; }
function _editTab(tab) { return _EDIT_TAB[tab] || tab; }

function _makeEmptyRow(tab) {
    const row = { _status: '', _orig: false };
    (_EDIT_COLS[tab] || []).forEach(f => { row[f] = null; });
    return row;
}

function _isEmptyRow(data) {
    if (data._status) return false;
    return Object.entries(data)
        .filter(([k]) => !k.startsWith('_'))
        .every(([, v]) => v == null || v === '');
}

function _ensureTrailingEmpty(api, tab, minEmpty = 5) {
    const allData = [];
    api.forEachNode(n => allData.push(n.data));
    let trailing = 0;
    for (let i = allData.length - 1; i >= 0; i--) {
        if (_isEmptyRow(allData[i])) trailing++;
        else break;
    }
    if (trailing < minEmpty) {
        api.applyTransaction({
            add: Array.from({ length: minEmpty - trailing }, () => _makeEmptyRow(tab))
        });
    }
}

function _xlsCellChanged(params, tab) {
    const { data, colDef, node, api } = params;
    if (colDef.field === '_status') return;
    const pk = _PK_FIELD[tab];
    // 기존 DB 행의 PK 변경 불가 — paste 우회 방지
    if (colDef.field === pk && data._orig) {
        node.setDataValue(pk, params.oldValue);
        return;
    }
    if (data._orig) {
        // 기존 DB 행 수정 → MOD + 변경 셀 추적
        _changedCells.add(`${node.id}__${colDef.field}`);
        // 변경된 셀 자체를 refresh 해야 cellClassRules(cell-mod)가 재평가됨
        api.refreshCells({ rowNodes: [node], columns: [colDef.field], force: true });
        if (data._status !== 'MOD') {
            data._status = 'MOD';
            api.refreshCells({ rowNodes: [node], columns: ['_status'], force: true });
        }
    } else if (!data._status) {
        // 빈 신규 행 → PK 입력 시 NEW로 전환
        if (data[pk]) {
            data._status = 'NEW';
            api.refreshCells({ rowNodes: [node], columns: ['_status'], force: true });
        }
    }
    _ensureTrailingEmpty(api, tab);
    _markDirty(tab, api);
}

function _xlsPasteProcess(params, tab, api) {
    if (!params.data || !params.data.length) return params.data;

    // Excel 클립보드는 마지막에 \n 이 붙어 빈 행이 생기므로 trailing 빈 행 제거
    let data = params.data;
    while (data.length > 0 && data[data.length - 1].every(cell => cell === '' || cell == null)) {
        data = data.slice(0, -1);
    }
    if (!data.length) return data;

    const focusedCell = api.getFocusedCell();
    if (!focusedCell) return data;
    const startRow = focusedCell.rowIndex;
    const needed   = startRow + data.length + 5;
    const have     = api.getDisplayedRowCount();
    if (needed > have) {
        api.applyTransaction({
            add: Array.from({ length: needed - have }, () => _makeEmptyRow(tab))
        });
    }
    return data;
}

function _xlsPasteEnd(tab, api) {
    const pk = _PK_FIELD[tab];
    const toRefresh = [];
    api.forEachNode(node => {
        const d = node.data;
        if (d._orig) return;   // 기존 DB 행은 onCellValueChanged(_xlsCellChanged)에서 개별 처리됨
        if (!d[pk]) return;
        if (!d._status) {
            d._status = 'NEW';
            toRefresh.push(node);
        }
    });
    if (toRefresh.length)
        api.refreshCells({ rowNodes: toRefresh, columns: ['_status'], force: true });
    _ensureTrailingEmpty(api, tab);
    _markDirty(tab, api);
}

function _markDirty(tab, api) {
    const btn = document.getElementById('saveBtn_' + tab);
    if (!btn) return;
    let hasDirty = false;
    api.forEachNode(n => {
        if (n.data._status === 'NEW' || n.data._status === 'MOD') hasDirty = true;
    });
    btn.classList.toggle('btn-save-dirty', hasDirty);
}

function clearNewRow(tab, pkVal) {
    const api = _getApi(tab);
    const pk  = _PK_FIELD[tab];
    let target = null;
    api.forEachNode(node => {
        if (String(node.data[pk]) === String(pkVal) && node.data._status === 'NEW')
            target = node;
    });
    if (target) {
        api.applyTransaction({ remove: [target.data] });
        _ensureTrailingEmpty(api, tab);
    }
}

// ══════════════════════════════════════════════════════════════════════
// 공통 defaultColDef
// ══════════════════════════════════════════════════════════════════════
const _defaultColDef = {
    resizable: true, sortable: true, filter: true,
    wrapHeaderText: true, autoHeaderHeight: true, headerClass: 'ag-header-center',
    menuTabs: ['filterMenuTab', 'generalMenuTab', 'columnsMenuTab'],
    cellClassRules: _cellClassRules, tooltipValueGetter: _tooltipValueGetter,
    suppressKeyboardEvent: params => {
        if (params.event.ctrlKey && params.event.key === 'Enter') {
            if (params.editing) {
                // 편집 중 → 편집 종료 후 suppress (enter 이동 방지)
                setTimeout(() => params.api.stopEditing(false), 0);
            }
            // 편집 중/비편집 모두 suppress → enterNavigatesVertically 이동 방지
            // (fill-down 은 onCellKeyDown → _onCtrlEnter 에서 처리)
            return true;
        }
        return false;
    },
};

// Ctrl+Enter: 선택 범위 전체에 첫 행 값 채우기
function _onCtrlEnter(params, tab, api) {
    const e = params.event;
    if (!e.ctrlKey || e.key !== 'Enter') return;
    e.preventDefault();
    const ranges = api.getCellRanges();
    if (!ranges || !ranges.length) return;
    for (const range of ranges) {
        const r0 = Math.min(range.startRow.rowIndex, range.endRow.rowIndex);
        const r1 = Math.max(range.startRow.rowIndex, range.endRow.rowIndex);
        if (r0 === r1) continue;
        for (const col of range.columns) {
            if (!col.getColDef().editable) continue;
            const colId   = col.getColId();
            const srcNode = api.getDisplayedRowAtIndex(r0);
            if (!srcNode) continue;
            const srcVal  = srcNode.data[colId];
            for (let r = r0 + 1; r <= r1; r++) {
                const node = api.getDisplayedRowAtIndex(r);
                if (!node) continue;
                node.setDataValue(colId, srcVal);
            }
        }
    }
}

// 행번호 컬럼 공통 정의
const _rowNumColDef = {
    headerName: '#', width: 48, minWidth: 48, maxWidth: 48,
    pinned: 'left', editable: false, sortable: false, filter: false,
    suppressMovable: true, resizable: false, suppressSizeToFit: true,
    valueGetter: p => {
        if (!p.node || p.node.rowIndex == null) return '';
        const d = p.node.data;
        if (!d || Object.entries(d).filter(([k]) => !k.startsWith('_')).every(([, v]) => v == null || v === '')) return '';
        return p.node.rowIndex + 1;
    },
    cellStyle: { textAlign:'right', color:'#9e9e9e', fontSize:'0.72rem',
                 paddingRight:'6px', paddingLeft:'2px', userSelect:'none',
                 background:'#f5f5f5', borderRight:'1px solid #d0d7de' },
};

// 상태 컬럼 공통 정의
const _statusColDef = {
    headerName: '', field: '_status', width: 48, minWidth: 48, maxWidth: 48,
    pinned: 'left', editable: false, sortable: false, filter: false,
    suppressMovable: true, resizable: false, suppressSizeToFit: true,
    cellStyle: p => {
        if (p.value === 'NEW') return { textAlign:'center', color:'#1565C0', fontWeight:700, fontSize:'0.7rem', background:'#E3F2FD', padding:'0' };
        if (p.value === 'MOD') return { textAlign:'center', color:'#BF360C', fontWeight:700, fontSize:'0.7rem', background:'#FBE9E7', padding:'0' };
        return { padding:'0' };
    },
    cellRenderer: p => p.value || '',
};

// ══════════════════════════════════════════════════════════════════════
// 공통 그리드 옵션 모듈
// ══════════════════════════════════════════════════════════════════════

// 4개 그리드 공통 기반 옵션 (선택·범위선택·편집 방식)
const _sharedGridOptions = {
    singleClickEdit:               false,
    stopEditingWhenCellsLoseFocus: true,
    rowSelection:                  'multiple',
    suppressRowClickSelection:     true,
    enableRangeSelection:          true,
};

// CRUD 그리드(Bill-To / Ship-To / Product) 공통 옵션 팩토리
// getApi: () => gridApiVariable  ← 클로저로 최신 API 참조
function _crudGridOptions(tab, getApi) {
    const _canEdit = () => typeof EDIT_MAP === 'undefined' || EDIT_MAP[_editTab(tab)] !== false;
    return {
        ..._sharedGridOptions,
        defaultColDef:                     _defaultColDef,
        tooltipShowDelay:                  300,
        rowData:                           [],
        enterNavigatesVertically:          true,
        enterNavigatesVerticallyAfterEdit: true,
        processDataFromClipboard: params => {
            if (!_canEdit()) return null;   // 편집 권한 없으면 paste 차단
            return _xlsPasteProcess(params, tab, getApi());
        },
        onCellValueChanged:    params => _xlsCellChanged(params, tab),
        onPasteEnd:            ()     => _xlsPasteEnd(tab, getApi()),
        onCellKeyDown:         params => _onCtrlEnter(params, tab, getApi()),
        postSortRows: params => {
            const rowNodes = params.nodes;
            const emptyRows = [];
            const filledRows = [];
            for (const node of rowNodes) {
                if (_isEmptyRow(node.data)) emptyRows.push(node);
                else filledRows.push(node);
            }
            let i = 0;
            for (const node of filledRows) { rowNodes[i++] = node; }
            for (const node of emptyRows)  { rowNodes[i++] = node; }
        },
        onFilterChanged: () => updateCount(tab),
        statusBar: { statusPanels: [
            { statusPanel: 'agSelectedRowCountComponent', align: 'left' },
            { statusPanel: 'agAggregationComponent',      align: 'right' },
        ]},
    };
}

// Sales Target / Sales Team 피벗 그리드 defaultColDef (정렬·필터 없음)
// cellClassRules.cell-mod 은 _pivotChangedCells 를 통해 공통 처리됨
const _stDefaultColDef = {
    resizable: true, sortable: false, filter: false,
    wrapHeaderText: true, autoHeaderHeight: true,
    menuTabs: ['filterMenuTab', 'generalMenuTab', 'columnsMenuTab'],
    cellClassRules: {
        'cell-mod': p => {
            if (!p.node || p.node.rowPinned || !p.data?._orig) return false;
            const field = p.colDef?.field;
            if (!field || field.startsWith('_')) return false;
            const pkVal = p.data.billto_biz_name;  // 두 피벗 그리드 공통 PK
            return !!pkVal && _pivotChangedCells.has(`${pkVal}__${field}`);
        },
    },
    suppressKeyboardEvent: params => {
        if (params.event.ctrlKey && params.event.key === 'Enter') {
            if (params.editing) setTimeout(() => params.api.stopEditing(false), 0);
            return true;
        }
        return false;
    },
};

// ══════════════════════════════════════════════════════════════════════
// Excel Import 공통 헬퍼
// ══════════════════════════════════════════════════════════════════════
/**
 * Excel 파일을 열어서 그리드에 import 합니다.
 *
 * @param {object} options
 *   gridApi        - AG Grid API
 *   pkField        - PK 필드명         (e.g. 'billto_biz_name')
 *   pkHeader       - Excel PK 헤더명   (e.g. 'Biz Name')
 *   valueConverter - (field, raw) => value  숫자 변환 등 (optional)
 *   onComplete     - ({ updated, added }) => void  완료 콜백 (optional)
 */
function _xlsImportFromFile({ gridApi, pkField, pkHeader, pkHeaderAliases = [], valueConverter, onComplete, skipUnmatched = false }) {
    if (typeof XLSX === 'undefined') {
        alert('Excel library is not loaded.');
        return;
    }

    const input = document.createElement('input');
    input.type    = 'file';
    input.accept  = '.xlsx,.xls,.csv';
    input.style.display = 'none';
    document.body.appendChild(input);

    input.onchange = async () => {
        const file = input.files[0];
        document.body.removeChild(input);
        if (!file) return;

        try {
            const buffer = await file.arrayBuffer();
            const wb     = XLSX.read(buffer, { type: 'array' });
            const ws     = wb.Sheets[wb.SheetNames[0]];
            const rows   = XLSX.utils.sheet_to_json(ws, { defval: null });

            if (!rows.length) { alert('No data found.'); return; }

            // 그리드 컬럼 headerName → field 맵 (내부 필드 _ 제외)
            // 대소문자 구분 없이 비교하기 위해 헤더명을 대문자로 정규화
            const _normHeader = (h) => String(h).trim().toUpperCase();
            const headerToField = {};
            gridApi.getColumnDefs().forEach(col => {
                if (col.field && col.headerName && !col.field.startsWith('_'))
                    headerToField[_normHeader(col.headerName)] = col.field;
            });

            // PK → 기존 노드 맵
            const nodeMap = {};
            gridApi.forEachNode(n => {
                const pk = n.data?.[pkField];
                if (pk != null) nodeMap[String(pk).trim().toUpperCase()] = n;
            });

            let updated = 0, added = 0, skipped = 0;
            const toAdd = [];

            for (const excelRow of rows) {
                // pkHeader 또는 alias 컬럼에서 PK 값 탐색 (대소문자 무시)
                const allPkHeaders = [pkHeader, ...pkHeaderAliases];
                const allPkHeadersNorm = allPkHeaders.map(_normHeader);
                let pkRaw = null;
                for (const [header, rawVal] of Object.entries(excelRow)) {
                    if (allPkHeadersNorm.includes(_normHeader(header))
                        && rawVal != null && String(rawVal).trim() !== '') {
                        pkRaw = rawVal;
                        break;
                    }
                }
                if (pkRaw == null) continue;
                const pkVal = String(pkRaw).trim();

                // header → field 변환 (PK 열·불명 열 제외)
                const mapped = {};
                for (const [header, rawVal] of Object.entries(excelRow)) {
                    const normHeader = _normHeader(header);
                    if (allPkHeadersNorm.includes(normHeader)) continue;
                    const field = headerToField[normHeader];
                    if (!field) continue;
                    mapped[field] = valueConverter ? valueConverter(field, rawVal) : (rawVal ?? null);
                }

                const existing = nodeMap[pkVal.toUpperCase()];
                if (existing) {
                    // 기존 행 업데이트 + 변경 셀 추적
                    Object.assign(existing.data, mapped);
                    if (existing.data._orig) {
                        Object.keys(mapped).forEach(field => {
                            _pivotChangedCells.add(`${pkVal}__${field}`);
                        });
                    }
                    gridApi.refreshCells({ rowNodes: [existing], force: true });
                    updated++;
                } else if (!skipUnmatched) {
                    // 신규 행 추가 (skipUnmatched=true 이면 무시)
                    toAdd.push({ [pkField]: pkVal, _orig: false, ...mapped });
                    added++;
                } else {
                    skipped++;
                }
            }

            if (toAdd.length) gridApi.applyTransaction({ add: toAdd });

            if (updated + added > 0) {
                if (onComplete) onComplete({ updated, added, skipped });
                const skipMsg = skipped > 0 ? `  skipped (unmatched): ${skipped}` : '';
                alert(`✅ Import complete  |  updated: ${updated}  added: ${added}${skipMsg}`);
            } else {
                alert(`No matching data found.\nPlease check if the Excel PK header is "${pkHeader}".`);
            }
        } catch (err) {
            console.error('Excel import error', err);
            alert('❌ Excel read error: ' + err.message);
        }
    };

    input.click();
}

/**
 * CRUD 그리드 (Bill-To / Ship-To / Product) 용 Excel Import
 * - PK 일치 → 기존 행 필드 갱신 + _status = 'MOD'
 * - PK 없음  → 신규 행 추가   + _status = 'NEW'
 * - audit 컬럼(input_dt 등)은 무시
 */
const _CRUD_IMPORT_META = {
    billto:  { pkField: 'billto_code',   pkHeader: 'Bill-To Code' },
    billtoPh:{ pkField: 'billto_code',   pkHeader: 'Bill-To Code' },
    shipto:  { pkField: 'shipto_code',   pkHeader: 'Ship-To Code' },
    product: { pkField: 'product_code',  pkHeader: 'Product Code' },
};
const _AUDIT_FIELDS = new Set(['input_dt','input_user_id','update_dt','update_user_id','_status','_orig']);

function importGrid(tab) {
    if (typeof XLSX === 'undefined') { alert('Excel library is not loaded.'); return; }
    const meta = _CRUD_IMPORT_META[tab];
    if (!meta) return;
    const api = _getApi(tab);
    if (!api) return;

    const input = document.createElement('input');
    input.type   = 'file';
    input.accept = '.xlsx,.xls,.csv';
    input.style.display = 'none';
    document.body.appendChild(input);

    input.onchange = async () => {
        const file = input.files[0];
        document.body.removeChild(input);
        if (!file) return;

        try {
            const buffer  = await file.arrayBuffer();
            const wb      = XLSX.read(buffer, { type: 'array' });
            const ws      = wb.Sheets[wb.SheetNames[0]];
            const excelRows = XLSX.utils.sheet_to_json(ws, { defval: null });
            if (!excelRows.length) { alert('No data found.'); return; }

            // 그리드 컬럼 headerName → field 맵 (audit·내부 필드 제외)
            // 대소문자 구분 없이 비교하기 위해 헤더명을 대문자로 정규화
            const _normHeader = (h) => String(h).trim().toUpperCase();
            const headerToField = {};
            api.getColumnDefs().forEach(col => {
                if (col.field && col.headerName && !_AUDIT_FIELDS.has(col.field))
                    headerToField[_normHeader(col.headerName)] = col.field;
            });

            // PK → 기존 노드 맵
            const nodeMap = {};
            api.forEachNode(n => {
                const pk = n.data?.[meta.pkField];
                if (pk != null && !_isEmptyRow(n.data))
                    nodeMap[String(pk).trim()] = n;
            });

            let updated = 0, added = 0;
            const toAdd        = [];
            const toRefresh    = [];

            for (const excelRow of excelRows) {
                // PK 헤더 탐색 (대소문자 무시)
                const pkHeaderNorm = _normHeader(meta.pkHeader);
                let pkRaw = null;
                for (const [header, rawVal] of Object.entries(excelRow)) {
                    if (_normHeader(header) === pkHeaderNorm) { pkRaw = rawVal; break; }
                }
                if (pkRaw == null || String(pkRaw).trim() === '') continue;
                const pkVal = String(pkRaw).trim();

                // Excel 행 → field 값 매핑 (PK·audit 제외)
                const mapped = {};
                for (const [header, rawVal] of Object.entries(excelRow)) {
                    const normHeader = _normHeader(header);
                    if (normHeader === pkHeaderNorm) continue;
                    const field = headerToField[normHeader];
                    if (!field || _AUDIT_FIELDS.has(field)) continue;
                    mapped[field] = (rawVal == null || rawVal === '') ? null : String(rawVal).trim() || null;
                }

                const existing = nodeMap[pkVal];
                if (existing) {
                    // 기존 DB 행 → MOD + 변경 셀 추적
                    Object.assign(existing.data, mapped);
                    existing.data._status = existing.data._orig ? 'MOD' : existing.data._status || 'NEW';
                    if (existing.data._orig) {
                        Object.keys(mapped).forEach(field => {
                            _changedCells.add(`${existing.id}__${field}`);
                        });
                    }
                    toRefresh.push(existing);
                    updated++;
                } else {
                    // 신규 행 → NEW
                    toAdd.push({
                        ...(() => { const r = _makeEmptyRow(tab); return r; })(),
                        [meta.pkField]: pkVal,
                        ...mapped,
                        _status: 'NEW',
                        _orig:   false,
                    });
                    added++;
                }
            }

            if (toRefresh.length)
                api.refreshCells({ rowNodes: toRefresh, force: true });
            if (toAdd.length)
                api.applyTransaction({ add: toAdd });

            if (updated + added > 0) {
                _ensureTrailingEmpty(api, tab);
                _markDirty(tab, api);
                updateCount(tab);
                alert(`✅ Import done  |  updated: ${updated}  added: ${added} rows`);
            } else {
                alert(`No matching data found.\nPlease check if the Excel PK header is "${meta.pkHeader}".`);
            }
        } catch (err) {
            console.error('Excel import error', err);
            alert('❌ Excel read error: ' + err.message);
        }
    };

    input.click();
}


let _loadedTabs = new Set();   // 로드 성공한 탭만 추가 (loadData 내부에서 관리)

const _TAB_GRID_ID = { billto: 'billtoGrid', billtoPh: 'billtoPhGrid', shipto: 'shiptoGrid', product: 'productGrid' };

function _getApi(tab) {
    if (tab === 'billto')   return billtoGridApi;
    if (tab === 'billtoPh') return (typeof billtoPhGridApi !== 'undefined') ? billtoPhGridApi : null;
    if (tab === 'shipto')  return shiptoGridApi;
    if (tab === 'product') return productGridApi;
    return null;
}

/** 컨테이너 width > 0이 될 때까지 폴링 후 sizeColumnsToFit 호출 */
function _fitWhenVisible(api, tab, attempts) {
    const el = document.getElementById(_TAB_GRID_ID[tab]);
    if (!el || !api) return;
    if (el.clientWidth > 0) {
        try { api.sizeColumnsToFit(); } catch(e) {}
    } else if ((attempts || 0) < 40) {
        setTimeout(() => _fitWhenVisible(api, tab, (attempts || 0) + 1), 30);
    }
}

// ══════════════════════════════════════════════════════════════════════
// 탭 목록 재점검 (법인 변경/조회 시)
//   법인이 바뀌면 권한(allowed_menus)에 따라 노출 탭이 달라질 수 있으므로,
//   /api/master/tabs 를 조회해 탭 바를 재구성하고
//   현재 탭이 목록에 없으면 첫 번째 탭으로 이동한다.
// ══════════════════════════════════════════════════════════════════════

// ── 탭 스크립트 동적 로더 ─────────────────────────────────────────────
// 서버가 반환하는 탭별 script 경로('js/master-xxx.js')를 필요 시 주입한다.
// 표준 Bill-To(master-billto.js)와 PH 전용(master-lgeph-billto.js)은
// 서로 독립된 전역/패널/그리드를 사용하므로 동시에 로드해도 충돌하지 않는다.

// static 파일의 절대 경로 베이스 계산 (예: '/static/')
function _staticBase() {
    const s = document.querySelector('script[src*="js/master-shared.js"]');
    if (s) return s.getAttribute('src').replace(/js\/master-shared\.js.*$/, '');
    return '/static/';
}

// 현재 로드된(또는 로드 예약된) 스크립트 파일명 목록
function _loadedScriptNames() {
    return Array.from(document.querySelectorAll('script[src]'))
        .map(s => (s.getAttribute('src') || '').split('/').pop().split('?')[0])
        .filter(Boolean);
}

function _loadScriptOnce(relSrc) {
    return new Promise((resolve, reject) => {
        if (!relSrc) { resolve(); return; }
        const fileName = relSrc.split('/').pop();
        const loaded   = _loadedScriptNames();

        // 이미 동일 파일 로드됨 → 스킵
        if (loaded.indexOf(fileName) !== -1) { resolve(); return; }

        const el = document.createElement('script');
        el.src   = _staticBase() + relSrc;
        el.onload  = () => resolve();
        el.onerror = () => { console.error('[master] 스크립트 로드 실패:', el.src); reject(new Error(el.src)); };
        document.body.appendChild(el);
    });
}

// 탭 목록(dict[]) 의 script 들을 순서대로 로드
async function _ensureTabScripts(tabs) {
    for (const t of (tabs || [])) {
        if (t && t.script) {
            try { await _loadScriptOnce(t.script); } catch (e) { /* 개별 실패 무시 */ }
        }
    }
}

// 탭 DOM 활성화(패널 전환)만 수행 — 그리드 초기화는 하지 않음
function _setActiveTabDom(tab) {
    const t = _normalizeTab(tab);
    document.querySelectorAll('.master-tab').forEach(b =>
        b.classList.toggle('active', _normalizeTab(b.getAttribute('data-tab')) === t));
    const panelId = _panelId(t);
    document.querySelectorAll('.master-panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById(panelId);
    if (panel) panel.classList.add('active');
    history.replaceState(null, '', '#' + t);
}

/**
 * 선택 법인 기준 탭 목록을 조회하여 탭 바를 재구성한다.
 * 현재 탭이 목록에 없으면 첫 번째 탭으로 이동(패널 전환)한다.
 * @returns {Promise<{validKeys: string[]|null, activeTab: string|null}>}
 *   validKeys : 정규화된 유효 탭 키 목록 (조회 실패 시 null → 필터링 안 함)
 *   activeTab : 재점검 후 활성화된 탭 키(정규화)
 */
async function refreshMasterTabs() {
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    let res = null;
    try {
        const r = await fetch('/api/master/tabs?legal_entity=' + encodeURIComponent(le));
        res = await r.json();
    } catch (e) {
        console.warn('[refreshMasterTabs] 탭 목록 조회 실패:', e);
    }

    // 현재 활성 탭 파악
    const activeBtn = document.querySelector('.master-tab.active');
    const curTab = activeBtn ? activeBtn.getAttribute('data-tab')
                             : (window.__INITIAL_TAB__ || (typeof _FIRST_TAB !== 'undefined' ? _FIRST_TAB : null));

    if (!res || !res.success || !Array.isArray(res.tabs)) {
        // 조회 실패 → 기존 탭 유지 (필터링 없이 진행)
        return { validKeys: null, activeTab: _normalizeTab(curTab) };
    }
    const tabs = res.tabs;

    // 편집 권한 맵 갱신
    if (res.edit_map && typeof EDIT_MAP !== 'undefined') {
        Object.keys(EDIT_MAP).forEach(k => { delete EDIT_MAP[k]; });
        Object.keys(res.edit_map).forEach(k => { EDIT_MAP[k] = res.edit_map[k]; });
    }

    // 탭 바 재생성
    const bar = document.querySelector('.master-tabs');
    if (bar) {
        bar.innerHTML = tabs.map(t => {
            const active = (_normalizeTab(t.key) === _normalizeTab(curTab)) ? ' active' : '';
            return `<button class="master-tab${active}" data-tab="${t.key}" onclick="switchTab('${t.key}', this)">`
                 + `<i class="fas ${t.icon}"></i> ${t.label}`
                 + `<span id="${t.count_id}" class="pill pill-slate" style="margin-left:.3rem;">—</span>`
                 + `</button>`;
        }).join('');
    }

    // 편집 버튼(.edit-btn) 표시/숨김 재적용
    document.querySelectorAll('.edit-btn[data-edit-tab]').forEach(btn => {
        const tab = btn.getAttribute('data-edit-tab');
        btn.style.display = (typeof EDIT_MAP !== 'undefined' && EDIT_MAP[tab] === false) ? 'none' : '';
    });

    // 전역 TABS 갱신
    try { window.TABS = tabs.map(t => t.key); } catch (e) {}

    // 법인별 탭 목록에 필요한 스크립트 로드 (아직 로드되지 않은 것만)
    await _ensureTabScripts(tabs);

    const validKeys = tabs.map(t => _normalizeTab(t.key));
    let activeTab   = _normalizeTab(curTab);

    if (tabs.length && (!curTab || validKeys.indexOf(activeTab) === -1)) {
        // 현재 탭이 목록에 없음 → 첫 번째 탭으로 이동
        activeTab = _normalizeTab(tabs[0].key);
        _setActiveTabDom(activeTab);
        window.__INITIAL_TAB__ = activeTab;
    } else if (tabs.length) {
        // 탭 바 재생성 후 active 상태를 확실히 반영
        _setActiveTabDom(activeTab);
    }

    return { validKeys, activeTab };
}

function switchTab(rawTab, btn) {
    const tab = _normalizeTab(rawTab);   // 'billTo' → 'billto', 'SalesTeam' → 'salesTeam'
    document.querySelectorAll('.master-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.querySelectorAll('.master-panel').forEach(p => p.classList.remove('active'));
    const panelId = _panelId(tab);
    const panel   = document.getElementById(panelId);
    if (!panel) {
        console.error(`[switchTab] 패널을 찾을 수 없습니다: #${panelId} (tab="${rawTab}")`);
        return;
    }
    panel.classList.add('active');
    history.replaceState(null, '', '#' + tab);
    _logMasterPageView(tab);   // ← 탭 전환 시 로그

    if (tab === 'salesTarget') {
        if (typeof stGridApi !== 'undefined' && stGridApi)
            setTimeout(() => { try { stGridApi.sizeColumnsToFit(); } catch(e){} }, 50);
        if (!_loadedTabs.has('salesTarget')) { _loadedTabs.add('salesTarget'); initSalesTarget(); }
        return;
    }

    if (tab === 'salesTeam') {
        if (typeof sttGridApi !== 'undefined' && sttGridApi)
            setTimeout(() => { try { sttGridApi.sizeColumnsToFit(); } catch(e){} }, 50);
        if (!_loadedTabs.has('salesTeam')) { _loadedTabs.add('salesTeam'); initSalesTeam(); }
        return;
    }

    if (tab === 'billtoBiz') {
        if (typeof bbizGridApi !== 'undefined' && bbizGridApi)
            setTimeout(() => { try { bbizGridApi.sizeColumnsToFit(); } catch(e){} }, 50);
        if (!_loadedTabs.has('billtoBiz')) { _loadedTabs.add('billtoBiz'); initBilltoBiz(); }
        return;
    }

    // billto / shipto / product — Sales Target 과 동일한 lazy init 패턴
    if (!_loadedTabs.has(tab)) {
        _loadedTabs.add(tab);
        if (tab === 'billto')   { initBillto();   return; }
        if (tab === 'billtoPh') { initBilltoPh(); return; }
        if (tab === 'shipto')  { initShipto();  return; }
        if (tab === 'product') { initProduct(); return; }
    }
    // 이미 로드된 탭 — 컬럼 리사이즈만
    const api = _getApi(tab);
    if (api) setTimeout(() => { try { api.sizeColumnsToFit(); } catch(e){} }, 50);
}

function _initTabFromHash() {
    const hash = (location.hash || '').replace('#', '');
    if (!hash) return;
    const tab = _normalizeTab(hash);   // 어떤 케이스든 canonical key 로 변환
    const btn = document.querySelector(`.master-tab[data-tab="${tab}"]`);
    if (btn) switchTab(tab, btn);
}

// 초기 활성 탭 즉시 결정: URL hash(#shipto 등)를 전역 TABS 와 매칭해 해당 패널만 활성화.
// billto 를 먼저 그렸다가 전환하는 플래시를 방지한다. (그리드 초기화는 하지 않음)
// 매칭 실패(=페이지 정보 없음)면 첫 번째 탭, 그것도 없으면 billto.
// 반환: 활성화된 탭 키(원본 data-tab 값)
function _initInitialTab() {
    const tabKeys = (typeof TABS !== 'undefined' && Array.isArray(TABS)) ? TABS : [];
    const want    = (location.hash || '').replace('#', '').toLowerCase();
    const tab     = tabKeys.find(k => String(k).toLowerCase() === want)
                 || tabKeys[0] || 'billto';

    document.querySelectorAll('.master-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.master-panel').forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.master-tab[data-tab="${tab}"]`);
    if (btn) btn.classList.add('active');
    const panel = document.getElementById(_panelId(tab));
    if (panel) panel.classList.add('active');

    window.__INITIAL_TAB__ = tab;               // 하단 데이터 로드에서 재사용
    history.replaceState(null, '', '#' + tab);  // hash 정규화
    return tab;
}

// ══════════════════════════════════════════════════════════════════════
// 데이터 로드 / 카운트 갱신
// ══════════════════════════════════════════════════════════════════════
function updateCount(tab) {
    const api = _getApi(tab);
    if (!api) return;
    let shown = 0;
    api.forEachNodeAfterFilter(n => { if (!_isEmptyRow(n.data)) shown++; });
    const el = document.getElementById(tab + 'Count');
    if (el) el.textContent = shown.toLocaleString();
}

async function loadData(rawTab) {
    const tab = _normalizeTab(rawTab);
    const api = _getApi(tab);
    if (!api) { console.warn(`[loadData] api not ready: ${tab}`); return; }
    try {
        const le  = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
        const res = await fetch('/api/master/' + _apiTab(tab) + '?legal_entity=' + encodeURIComponent(le));
        const data = await res.json();
        if (data.success) {
            _changedCells.clear();
            const rows = (data.data || []).map(r => ({ ...r, _status:'', _orig:true }));
            rows.push(...Array.from({ length: _EMPTY_ROWS }, () => _makeEmptyRow(tab)));
            api.setGridOption('rowData', rows);
            updateCount(tab);
            setTimeout(() => { try { api.sizeColumnsToFit(); } catch(e){} }, 50);
        } else {
            _loadedTabs.delete(tab);
            alert('Load failed: ' + (data.message || ''));
        }
    } catch(e) {
        _loadedTabs.delete(tab);
        console.error('loadData error', tab, e);
    }
}

/**
 * AG Grid Excel 다운로드 공통 헬퍼.
 * exportDataAsExcel 은 내부적으로 blob:http:// URL을 생성해
 * Chrome 보안 정책(HTTP 페이지 다운로드 차단/경고)에 걸릴 수 있으므로,
 * getDataAsExcel() 로 Blob을 받아 FileReader → base64 data URI 방식으로 다운로드.
 */
function _agGridExport(api, fileName) {
    if (!api) return;
    const blob = api.getDataAsExcel({ fileName });
    if (!blob) { console.warn('[_agGridExport] getDataAsExcel returned null'); return; }
    const reader = new FileReader();
    reader.onload = e => {
        const a = document.createElement('a');
        a.href = e.target.result;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };
    reader.readAsDataURL(blob);
}

function exportGrid(tab) {
    const api = _getApi(tab);
    if (api) _agGridExport(api, tab + '_master.xlsx');
}

async function refreshTab(tab) {
    // 변경사항이 있으면 확인
    const api = (tab === 'billto' || tab === 'billtoPh' || tab === 'shipto' || tab === 'product') ? _getApi(tab) : null;
    if (api) {
        let dirty = false;
        api.forEachNode(n => { if (n.data._status === 'NEW' || n.data._status === 'MOD') dirty = true; });
        if (dirty && !await confirm('You have unsaved changes.\nRefreshing will discard all changes.\nDo you want to continue?', { title: 'Confirm Changes' })) return;
    }
    const btn = document.querySelector(`[data-refresh="${tab}"]`);
    if (btn) { btn.disabled = true; btn.querySelector('i')?.classList.add('fa-spin'); }
    try {
        if      (tab === 'billto' || tab === 'billtoPh' || tab === 'shipto' || tab === 'product') await loadData(tab);
        else if (tab === 'salesTeam')   await loadSalesTeam();
        else if (tab === 'salesTarget') await loadSalesTarget();
        else if (tab === 'billtoBiz')   await loadBilltoBiz();
    } finally {
        if (btn) { btn.disabled = false; btn.querySelector('i')?.classList.remove('fa-spin'); }
    }
}

// ══════════════════════════════════════════════════════════════════════
// 변경사항 일괄 저장 (신규 → POST / 수정 → PUT)
// ══════════════════════════════════════════════════════════════════════
async function saveChanges(tab) {
    const api = _getApi(tab);
    if (!api) return;

    const toSave = [];
    api.forEachNode(n => {
        if (n.data._status === 'NEW' || n.data._status === 'MOD') toSave.push(n.data);
    });
    if (toSave.length === 0) { alert('No changes to save.'); return; }

    const isValid = _validateAll(tab, api);
    if (!isValid) {
        alert('⚠️ Validation errors detected.\nPlease review and fix the highlighted cells.');
        return;
    }

    if (!await confirm(`Save ${toSave.length} row(s)?`)) return;

    const btn = document.getElementById('saveBtn_' + tab);
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

    const _SKIP = new Set(['_orig', 'input_dt', 'input_user_id', 'update_dt', 'update_user_id']);
    const _le   = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    const rows  = toSave.map(row =>
        Object.fromEntries(Object.entries(row).filter(([k]) => !_SKIP.has(k)))
    );

    try {
        const res  = await fetch('/api/master/' + _apiTab(tab) + '/bulk-save', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ rows, legal_entity: _le }),
        });
        const json = await res.json();

        if (json.success) {
            api.forEachNode(n => {
                if (n.data._status === 'NEW' || n.data._status === 'MOD') {
                    n.data._status = '';
                    n.data._orig   = true;
                }
            });
            api.refreshCells({ columns: ['_status'], force: true });
            document.getElementById('valBanner_' + tab)?.classList.remove('show');
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; btn.classList.remove('btn-save-dirty'); }
            alert(`✅ ${json.saved} rows saved.`);
            _loadedTabs.delete(tab); _loadedTabs.add(tab); loadData(tab);
        } else {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
            alert('❌ Save failed: ' + (json.message || ''));
        }
    } catch(e) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
        alert('❌ Server error: ' + e);
    }
}

// ══════════════════════════════════════════════════════════════════════
// 모달 — 폼 스키마 정의
// ══════════════════════════════════════════════════════════════════════
const FORM_SCHEMA = {
    billto: [
        { field:'billto_code',       label:'Bill-To Code *', type:'text', required:true, readonly_on_edit:true },
        { field:'billto_name',       label:'Bill-To Name *', type:'text', required:true },
        { field:'billto_group_name', label:'Group Name',     type:'text' },
        { field:'billto_biz_name',   label:'Biz Name',       type:'text' },
    ],
    shipto: [
        { field:'shipto_code',  label:'Ship-To Code *', type:'text', required:true, readonly_on_edit:true },
        { field:'shipto_name',  label:'Ship-To Name',   type:'text' },
        { field:'address',      label:'Address',        type:'text' },
        { field:'postal_code',  label:'Postal Code',    type:'text' },
        { field:'route',        label:'Route',          type:'text' },
    ],
    product: [
        { field:'product_code',          label:'Product Code *',  type:'text', required:true, readonly_on_edit:true },
        { field:'product_group_code',    label:'Group Code',      type:'text' },
        { field:'product_category_code', label:'Category Code',   type:'text' },
    ],
};
FORM_SCHEMA.billtoPh = FORM_SCHEMA.billto;

const TITLE_MAP = { billto:'Bill-To', billtoPh:'Bill-To', shipto:'Ship-To', product:'Product' };

let _mdState = { tab:null, mode:null, data:null };

function _buildForm(tab, mode, rowData) {
    const schema = FORM_SCHEMA[tab];
    return schema.map(f => {
        const val      = rowData ? (rowData[f.field] ?? '') : '';
        const readonly = f.readonly_on_edit && mode === 'edit';
        return `<div class="form-field">
            <label>${f.label}</label>
            <input type="${f.type || 'text'}" class="input" id="md_${f.field}"
                   value="${String(val).replace(/"/g, '&quot;')}"
                   ${readonly ? 'readonly' : ''}
                   placeholder="${f.label.replace(' *', '')}">
        </div>`;
    }).join('');
}

function openAdd(tab) {
    _mdState = { tab, mode:'add', data:null };
    document.getElementById('mdTitle').textContent = 'Add ' + TITLE_MAP[tab];
    document.getElementById('mdBody').innerHTML    = _buildForm(tab, 'add', null);
    document.getElementById('mdBackdrop').classList.add('open');
    document.querySelector('#mdBody .input').focus();
}

function openEdit(tab, rowData) {
    _mdState = { tab, mode:'edit', data:rowData };
    document.getElementById('mdTitle').textContent = 'Edit ' + TITLE_MAP[tab];
    document.getElementById('mdBody').innerHTML    = _buildForm(tab, 'edit', rowData);
    document.getElementById('mdBackdrop').classList.add('open');
}

function closeMd() {
    document.getElementById('mdBackdrop').classList.remove('open');
}

async function saveMd() {
    const { tab, mode, data } = _mdState;
    const schema  = FORM_SCHEMA[tab];
    const payload = {};
    for (const f of schema) {
        const el = document.getElementById('md_' + f.field);
        if (!el) continue;
        const val = el.value.trim();
        if (f.required && !val) { el.focus(); alert(f.label.replace(' *', '') + ' is required.'); return; }
        payload[f.field] = val || null;
    }
    const pkField = schema.find(f => f.readonly_on_edit)?.field;
    const pkVal   = mode === 'edit' && data ? data[pkField] : null;
    const url     = '/api/master/' + _apiTab(tab) + (mode === 'edit' ? '/' + encodeURIComponent(pkVal) : '');
    const method  = mode === 'add' ? 'POST' : 'PUT';

    const btn = document.getElementById('mdSaveBtn');
    btn.disabled = true;
    try {
        const res  = await fetch(url, { method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        const resp = await res.json();
        if (resp.success) { closeMd(); loadData(tab); }
        else alert('Save failed: ' + (resp.message || ''));
    } catch(e) {
        alert('Server error: ' + e);
    } finally {
        btn.disabled = false;
    }
}

// ══════════════════════════════════════════════════════════════════════
// 삭제 모달
// ══════════════════════════════════════════════════════════════════════
let _delState = { tab:null, pk:null };

function openDel(tab, pk, rowData) {
    _delState = { tab, pk };
    const label = TITLE_MAP[tab];
    document.getElementById('delMsg').innerHTML =
        `Delete <strong>${label}</strong> code <code style="background:var(--muted);padding:1px 6px;border-radius:4px;">${pk}</code>.<br>
         <span style="color:var(--muted-foreground);font-size:.82rem;">This action cannot be undone.</span>`;
    document.getElementById('delConfirmBtn').onclick = confirmDel;
    document.getElementById('delBackdrop').classList.add('open');
}

function closeDel() {
    document.getElementById('delBackdrop').classList.remove('open');
}

async function confirmDel() {
    const { tab, pk } = _delState;
    const btn = document.getElementById('delConfirmBtn');
    btn.disabled = true;
    try {
        const le   = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
        const res  = await fetch('/api/master/' + _apiTab(tab) + '/' + encodeURIComponent(pk)
                     + '?legal_entity=' + encodeURIComponent(le), { method:'DELETE' });
        const resp = await res.json();
        if (resp.success) { closeDel(); loadData(tab); }
        else alert('Delete failed: ' + (resp.message || ''));
    } catch(e) {
        alert('Server error: ' + e);
    } finally {
        btn.disabled = false;
    }
}

// ══════════════════════════════════════════════════════════════════════
// 초기 활성 탭 설정
//   master-shared.js 는 body 하단(DOM 파싱 후, 탭 스크립트/$(document).ready 전)
//   에서 로드되므로, 여기서 즉시 초기 탭 패널을 활성화한다.
//   (모든 패널은 기본 display:none 이라 billto 플래시 없이 안전)
// ══════════════════════════════════════════════════════════════════════
_initInitialTab();
