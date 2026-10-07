// ─────────────────────────────────────────────────────────────────────
// master_sales_team.js  ―  Sales Team 탭 그리드
// 피벗 형태: billto_biz_name(행) × division_name(열) → team_name(텍스트)
// 의존: master-shared.js (먼저 로드)
// ─────────────────────────────────────────────────────────────────────

// Sales Target 과 동일한 Division 목록 사용 (code.json 기준)
const _STT_DIVS = [
    'W/M', 'REF', 'Cooking', 'Dishwasher', 'VCC BD',
    'LTV', 'MNT', 'Audio', 'PC', 'MNT Signage', 'Commercial TV',
    'RAC BD', 'SAC', 'Air Care', 'LED Signage',
];

let sttGridApi = null;
let _sttDivs   = [];
let _sttDirty  = false;

// ── 플랫 데이터 + 마스터 biz names → 피벗 행 생성 ───────────────────
function _pivotStt(flatRows, divs, bizNames = []) {
    // 데이터 맵: biz → { div: team_name }
    const dataMap = {};
    for (const r of flatRows) {
        const biz = r.billto_biz_name;
        if (!dataMap[biz]) dataMap[biz] = {};
        dataMap[biz][r.division_name] = r.team_name;
    }
    // 마스터 biz names + 기존 데이터 병합 (마스터 우선)
    const allBiz = [...new Set([...bizNames, ...Object.keys(dataMap)])];
    return allBiz.map(biz => {
        const row = { billto_biz_name: biz, _orig: true };
        divs.forEach(div => { row[div] = dataMap[biz]?.[div] ?? null; });
        return row;
    });
}

// ── 피벗 컬럼 정의 생성 ──────────────────────────────────────────────
function _buildSttColDefs(divs, canEdit = true) {
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
        // Biz Name (좌측 고정, 기존 행 readonly)
        {
            headerName: 'Biz Name', field: 'billto_biz_name',
            width: 180, minWidth: 140, pinned: 'left',
            editable: canEdit ? (p => !p.node?.rowPinned && !p.data?._orig) : false,
            cellClassRules: {
                'cell-readonly': p => !canEdit || (!p.node?.rowPinned && !!p.data?._orig),
            },
            onCellValueChanged: p => { if (p.data.billto_biz_name) _sttMarkDirty(); },
        },
        // Division 컬럼 (동적, 텍스트 입력)
        ...divs.map(div => ({
            headerName: div,
            field: div,
            width: 120, minWidth: 90,
            editable: canEdit ? (p => !p.node?.rowPinned) : false,
            cellEditor: 'agTextCellEditor',
            onCellValueChanged: () => _sttMarkDirty(),
        })),
    ];
}

// ── 그리드에 데이터 반영 ──────────────────────────────────────────────
function _renderSttGrid(flatRows, divs, bizNames = []) {
    _sttDivs = divs;
    const pivotRows = _pivotStt(flatRows, divs, bizNames);
    const canEdit   = typeof EDIT_MAP === 'undefined' || EDIT_MAP['salesTeam'] !== false;
    const colDefs   = _buildSttColDefs(divs, canEdit);

    if (!sttGridApi) {
        sttGridApi = agGrid.createGrid(document.getElementById('sttGrid'), {
            ..._sharedGridOptions,
            columnDefs:    colDefs,
            defaultColDef: _stDefaultColDef,
            rowData:       pivotRows,
            suppressScrollOnNewData: true,
            onCellValueChanged: p => {
                _pivotCellChanged(p, 'billto_biz_name');
                _sttMarkDirty();
            },
            statusBar: { statusPanels: [
                { statusPanel: 'agAggregationComponent', align: 'right' },
            ]},
        });
    } else {
        _pivotClearChanges();   // rowData 반영 전에 clear → cellClassRules 재평가 시 노란색 없음
        sttGridApi.setGridOption('columnDefs', colDefs);
        sttGridApi.setGridOption('rowData', pivotRows);
    }
    _sttUpdateCount();
    _sttDirty = false;
    _pivotClearChanges();   // 최초 생성(if 분기) 시에도 보장
    const btn = document.getElementById('saveBtn_salesTeam');
    if (btn) btn.classList.remove('btn-save-dirty');
}

function _sttMarkDirty() {
    _sttDirty = true;
    const btn = document.getElementById('saveBtn_salesTeam');
    if (btn) btn.classList.add('btn-save-dirty');
}

function _sttUpdateCount() {
    if (!sttGridApi) return;
    let cnt = 0;
    sttGridApi.forEachNode(n => { if (n.data?.billto_biz_name) cnt++; });
    const rowEl = document.getElementById('sttRowCount');
    if (rowEl) rowEl.textContent = cnt.toLocaleString() + ' rows';
    const tabEl = document.getElementById('salesTeamCount');
    if (tabEl) tabEl.textContent = cnt.toLocaleString();
}

// ── 데이터 로드 ───────────────────────────────────────────────────────
async function loadSalesTeam() {
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    try {
        const [resData, resBiz] = await Promise.all([
            fetch(`/api/master/sales-team?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
            fetch(`/api/master/sales-target/biz-names?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
        ]);
        _renderSttGrid(resData.data || [], _STT_DIVS, resBiz.data || []);
    } catch (e) {
        console.error('loadSalesTeam error', e);
    }
}

// ── 초기화 (탭 최초 진입 시 1회) ─────────────────────────────────────
async function initSalesTeam() {
    await loadSalesTeam();
}

// ── 저장 ──────────────────────────────────────────────────────────────
async function saveSalesTeam() {
    if (!sttGridApi) return;
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';

    const rows = [];
    sttGridApi.forEachNode(n => { if (n.data?.billto_biz_name) rows.push(n.data); });
    if (!rows.length) { alert('No data to save.'); return; }
    if (!await confirm('Save Sales Team settings?\n(This will overwrite existing data.)')) return;

    const btn = document.getElementById('saveBtn_salesTeam');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

    try {
        const res  = await fetch('/api/master/sales-team/bulk-save', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ rows, divs: _sttDivs, legal_entity: le }),
        });
        const json = await res.json();
        if (json.success) {
            _sttDirty = false;
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; btn.classList.remove('btn-save-dirty'); }
            alert(`✅ ${json.saved} row(s) saved.`);
            await loadSalesTeam();
        } else {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
            alert('❌ Save failed: ' + (json.message || ''));
        }
    } catch (e) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
        alert('❌ Server error: ' + e);
    }
}

function exportSalesTeam() {
    if (sttGridApi) _agGridExport(sttGridApi, 'sales_team.xlsx');
}

// ── Excel Import ──────────────────────────────────────────────────────
function importSalesTeam() {
    if (!sttGridApi) return;
    _xlsImportFromFile({
        gridApi:  sttGridApi,
        pkField:  'billto_biz_name',
        pkHeader: 'Biz Name',
        // Division 컬럼은 텍스트 — 그대로 문자열로 처리
        valueConverter: (_field, raw) => {
            if (raw == null || raw === '') return null;
            return String(raw).trim() || null;
        },
        onComplete: () => {
            _sttMarkDirty();
            _sttUpdateCount();
        },
    });
}
