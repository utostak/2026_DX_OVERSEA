// ─────────────────────────────────────────────────────────────────────
// master_sales_target.js  ―  Sales Target 탭 그리드
// 의존: master-shared.js (먼저 로드)
// ─────────────────────────────────────────────────────────────────────

let stGridApi = null;
let _stDivs   = [];
let _stDirty  = false;

// ── Base YM 셀렉터 초기화 (최근 12개월 ~ 다음달, 기본=어제 기준 월) ─
function _initStBaseYm() {
    const sel = document.getElementById('stBaseYm');
    sel.innerHTML = '';
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const defaultYm = `${yesterday.getFullYear()}${String(yesterday.getMonth() + 1).padStart(2, '0')}`;
    const now = new Date();
    for (let i = 1; i >= -12; i--) {
        const d   = new Date(now.getFullYear(), now.getMonth() + i, 1);
        const ym  = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
        const lbl = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        const opt = new Option(lbl, ym);
        if (ym === defaultYm) opt.selected = true;
        sel.appendChild(opt);
    }
}


// ── 통화 표시 초기화 (첫 번째 통화만 텍스트로 표시) ────────────────
async function _initStCurrencies() {
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    try {
        const res   = await fetch('/api/master/sales-target/currencies?legal_entity=' + encodeURIComponent(le));
        const data  = await res.json();
        const first = (data.data && data.data.length) ? data.data[0] : 'USD';
        const el = document.getElementById('stCurrency');
        el.textContent   = first;
        el.dataset.value = first;
    } catch (e) {
        const el = document.getElementById('stCurrency');
        el.textContent   = 'USD';
        el.dataset.value = 'USD';
    }
}

// ── 플랫 데이터 + 마스터 biz names → 피벗 행 생성 ──────────────────
function _pivotSt(flatRows, divs, bizNames = []) {
    const dataMap = {};
    for (const r of flatRows) {
        const biz = r.billto_biz_name;
        if (!dataMap[biz]) dataMap[biz] = {};
        dataMap[biz][r.product_group_code] = r.target_amount;
    }
    // 마스터 biz names만 사용
    // (d_billto_mst WHERE subsdr_name=? AND delete_flag='N' 기준 — 데이터에만 있는 orphan 행 제외)
    const allBiz = bizNames.length ? bizNames : [...new Set(Object.keys(dataMap))];
    return allBiz.map(biz => {
        const row = { billto_biz_name: biz, _orig: true };
        divs.forEach(div => { row[div] = dataMap[biz]?.[div] ?? null; });
        return row;
    });
}

// ── 피벗 컬럼 정의 생성 ──────────────────────────────────────────────
function _buildStColDefs(divs, canEdit = true) {
    const numCellStyle = { textAlign: 'right' };
    const fmtNum = p => {
        if (p.value == null || p.value === '') return '';
        const n = Number(p.value);
        return isNaN(n) ? p.value : n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    };
    const parseNum = p => {
        const v = String(p.newValue || '').replace(/,/g, '').trim();
        if (!v) return null;
        const n = parseFloat(v);
        return isNaN(n) ? null : n;
    };

    return [
        // 행번호
        {
            headerName: '#', width: 46, minWidth: 46, maxWidth: 46,
            pinned: 'left', editable: false, sortable: false, filter: false,
            suppressMovable: true, resizable: false,
            valueGetter: p => (p.node && !p.node.rowPinned && p.node.data?.billto_biz_name)
                ? p.node.rowIndex + 1 : '',
            cellStyle: { textAlign: 'right', color: '#9e9e9e', fontSize: '0.72rem',
                         background: '#f5f5f5', borderRight: '1px solid #d0d7de' },
        },
        // Biz Name (PK 역할 — 기존 행은 readonly)
        {
            headerName: 'Biz Name', field: 'billto_biz_name',
            width: 180, minWidth: 140, pinned: 'left',
            filter: 'agSetColumnFilter',
            editable: canEdit ? (p => !p.node?.rowPinned && !p.data?._orig) : false,
            cellClassRules: {
                'cell-readonly': p => !canEdit || (!p.node?.rowPinned && !!p.data?._orig),
            },
            onCellValueChanged: p => { if (p.data.billto_biz_name) _stMarkDirty(); },
        },
        // Division 컬럼 (동적)
        ...divs.map(div => ({
            headerName: div,
            field: div,
            width: 110, minWidth: 90,
            editable: canEdit ? (p => !p.node?.rowPinned) : false,
            cellStyle: numCellStyle,
            valueFormatter: fmtNum,
            valueParser: parseNum,
            onCellValueChanged: () => _stMarkDirty(),
            aggFunc: 'sum',
        })),
        // TTL (행 합계 — 우측 고정)
        {
            headerName: 'TTL', field: '_ttl',
            width: 120, minWidth: 100, pinned: 'right',
            editable: false, sortable: false,
            cellStyle: { ...numCellStyle, fontWeight: 600, background: '#f0f4fa' },
            valueGetter: p => {
                if (!p.data) return null;
                const s = divs.reduce((acc, d) => acc + (parseFloat(p.data[d]) || 0), 0);
                return s || null;
            },
            valueFormatter: fmtNum,
        },
    ];
}

// ── 피닝된 하단 합계 행 생성 ─────────────────────────────────────────
function _buildStPinnedBottom(rows, divs) {
    const ttlRow = { billto_biz_name: 'GROSS' };
    divs.forEach(d => {
        ttlRow[d] = rows.reduce((s, r) => s + (parseFloat(r[d]) || 0), 0) || null;
    });
    return [ttlRow];
}

// ── 그리드에 데이터 반영 ──────────────────────────────────────────────
function _renderStGrid(flatRows, divs, bizNames = []) {
    _stDivs = divs;
    const pivotRows = _pivotSt(flatRows, divs, bizNames);
    const canEdit   = typeof EDIT_MAP === 'undefined' || EDIT_MAP['salesTarget'] !== false;
    const colDefs   = _buildStColDefs(divs, canEdit);

    if (!stGridApi) {
        stGridApi = agGrid.createGrid(document.getElementById('stGrid'), {
            ..._sharedGridOptions,
            columnDefs:          colDefs,
            defaultColDef:       _stDefaultColDef,
            rowData:             pivotRows,
            pinnedBottomRowData: _buildStPinnedBottom(pivotRows.filter(r => r.billto_biz_name), divs),
            suppressScrollOnNewData: true,
            onCellValueChanged: p => {
                _pivotCellChanged(p, 'billto_biz_name');
                _stRefreshPinnedBottom();
                _stMarkDirty();
            },
            onCellKeyDown: params => _onCtrlEnter(params, 'salesTarget', stGridApi),
            statusBar: { statusPanels: [
                { statusPanel: 'agAggregationComponent', align: 'right' },
            ]},
        });
    } else {
        _pivotClearChanges();   // rowData 반영 전에 clear → cellClassRules 재평가 시 노란색 없음
        stGridApi.setGridOption('columnDefs', colDefs);
        stGridApi.setGridOption('rowData', pivotRows);
        stGridApi.setGridOption('pinnedBottomRowData',
            _buildStPinnedBottom(pivotRows.filter(r => r.billto_biz_name), divs));
    }
    _stUpdateCount();
    _stDirty = false;
    _pivotClearChanges();   // 최초 생성(if 분기) 시에도 보장
    const btn = document.getElementById('saveBtn_salesTarget');
    if (btn) btn.classList.remove('btn-save-dirty');
}

function _stRefreshPinnedBottom() {
    if (!stGridApi) return;
    const rows = [];
    stGridApi.forEachNode(n => { if (n.data?.billto_biz_name) rows.push(n.data); });
    stGridApi.setGridOption('pinnedBottomRowData', _buildStPinnedBottom(rows, _stDivs));
}

function _stMarkDirty() {
    _stDirty = true;
    const btn = document.getElementById('saveBtn_salesTarget');
    if (btn) btn.classList.add('btn-save-dirty');
}

function _stUpdateCount() {
    if (!stGridApi) return;
    let cnt = 0;
    stGridApi.forEachNode(n => { if (n.data?.billto_biz_name) cnt++; });
    const rowCountEl = document.getElementById('stRowCount');
    if (rowCountEl) rowCountEl.textContent = cnt.toLocaleString() + ' rows';
    const tabCountEl = document.getElementById('salesTargetCount');
    if (tabCountEl) tabCountEl.textContent = cnt.toLocaleString();
}

function _addStRow() {
    if (!stGridApi) return;
    stGridApi.applyTransaction({ add: [{ billto_biz_name: null, _orig: false }] });
}

// ── 데이터 로드 ───────────────────────────────────────────────────────
async function loadSalesTarget() {
    const le      = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    const base_ym = document.getElementById('stBaseYm').value;
    try {
        const [resData, resBiz, resDivs] = await Promise.all([
            fetch(`/api/master/sales-target?legal_entity=${encodeURIComponent(le)}&base_ym=${base_ym}`).then(r => r.json()),
            fetch(`/api/master/sales-target/biz-names?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
            fetch(`/api/master/sales-target/divisions?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
        ]);
        const divs = resDivs.data || [];
        _renderStGrid(resData.data || [], divs, resBiz.data || []);
    } catch (e) {
        console.error('loadSalesTarget error', e);
    }
}

// ── 초기화 (탭 최초 진입 시 1회) ─────────────────────────────────────
async function initSalesTarget() {
    _initStBaseYm();
    await _initStCurrencies();
    await loadSalesTarget();
}

// ── 저장 ──────────────────────────────────────────────────────────────
async function saveSalesTarget() {
    if (!stGridApi) return;
    const le            = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    const base_ym       = document.getElementById('stBaseYm').value;
    const currency_code = document.getElementById('stCurrency').dataset.value || 'USD';

    const rows = [];
    stGridApi.forEachNode(n => { if (n.data?.billto_biz_name) rows.push(n.data); });
    if (!rows.length) { alert('No data to save.'); return; }
    if (!await confirm(`Save Sales Target for ${base_ym}?\n(Existing data will be overwritten.)`)) return;

    const btn = document.getElementById('saveBtn_salesTarget');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

    try {
        const res  = await fetch('/api/master/sales-target/bulk-save', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ rows, divs: _stDivs, base_ym, currency_code, legal_entity: le }),
        });
        const json = await res.json();
        if (json.success) {
            _stDirty = false;
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; btn.classList.remove('btn-save-dirty'); }
            alert(`✅ ${json.saved} rows saved.`);
            await loadSalesTarget();
        } else {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
            alert('❌ Save failed: ' + (json.message || ''));
        }
    } catch (e) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
        alert('❌ Server error: ' + e);
    }
}

function exportSalesTarget() {
    if (stGridApi) _agGridExport(stGridApi, 'sales_target.xlsx');
}

// ── Excel Import ──────────────────────────────────────────────────────
function importSalesTarget() {
    if (!stGridApi) return;
    _xlsImportFromFile({
        gridApi:  stGridApi,
        pkField:  'billto_biz_name',
        pkHeader: 'Biz Name',
        pkHeaderAliases: ['GROSS'],   // 'GROSS' 컬럼도 Biz Name으로 인식
        skipUnmatched: true,   // 매핑 안 되는 biz name은 추가하지 않고 무시
        // Division 컬럼은 숫자 — 쉼표 제거 후 float 변환
        valueConverter: (_field, raw) => {
            if (raw == null || raw === '') return null;
            const n = parseFloat(String(raw).replace(/,/g, ''));
            return isNaN(n) ? null : n;
        },
        onComplete: () => {
            _stRefreshPinnedBottom();
            _stMarkDirty();
            _stUpdateCount();
        },
    });
}
