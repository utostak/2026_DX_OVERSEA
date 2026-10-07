// ─────────────────────────────────────────────────────────────────────
// master_billto_biz.js  ―  Bill-To Biz 탭 그리드
// 피벗 형태: billto_code(행) × product_group_code(열)
//   행 레이블 : billto_code + billto_name (d_billto_mst 기준, readonly)
//   열 레이블 : product_group_code (d_product_mst DISTINCT)
//   셀 값     : billto_biz_name / team_name  (2개, 텍스트 입력)
// 저장 시 법인별 전체 삭제 후 재삽입 (replace)
// 의존: master-shared.js (먼저 로드)
// 참조: master_sales_team.js
// ─────────────────────────────────────────────────────────────────────

let bbizGridApi   = null;
let _bbizPgs      = [];      // product_group_code 목록 (열)
let _bbizDirty    = false;

// ── 플랫 데이터 + billto 마스터 → 피벗 행 생성 ─────────────────────────
// flatRows : [{billto_code, product_group_code, billto_biz_name, team_name}]
// billtos  : [{billto_code, billto_name}]
function _pivotBbiz(flatRows, pgs, billtos = []) {
    // 데이터 맵: code → { pg: {biz, team} }
    const dataMap = {};
    for (const r of flatRows) {
        const code = r.billto_code;
        if (!dataMap[code]) dataMap[code] = {};
        dataMap[code][r.product_group_code] = {
            biz:  r.billto_biz_name,
            team: r.team_name,
        };
    }
    // billto 이름 맵
    const nameMap = {};
    billtos.forEach(b => { nameMap[b.billto_code] = b.billto_name; });

    // 마스터 billto_code + 기존 데이터 병합 (마스터 우선)
    const allCode = [...new Set([...billtos.map(b => b.billto_code), ...Object.keys(dataMap)])];

    return allCode.map(code => {
        const row = {
            billto_code: code,
            billto_name: nameMap[code] ?? null,
            _orig:       true,
        };
        pgs.forEach(pg => {
            const cell = dataMap[code]?.[pg];
            row[`${pg}__biz`]  = cell?.biz  ?? null;
            row[`${pg}__team`] = cell?.team ?? null;
        });
        return row;
    });
}

// ── 피벗 컬럼 정의 생성 ──────────────────────────────────────────────
function _buildBbizColDefs(pgs, canEdit = true) {
    const cols = [
        // 행번호
        {
            headerName: '#', width: 46, minWidth: 46, maxWidth: 46,
            pinned: 'left', editable: false, sortable: false, filter: false,
            suppressMovable: true, resizable: false,
            valueGetter: p => (p.node && !p.node.rowPinned && p.node.data?.billto_code)
                ? p.node.rowIndex + 1 : '',
            cellStyle: { textAlign: 'right', color: '#9e9e9e', fontSize: '0.72rem',
                         background: '#f5f5f5', borderRight: '1px solid #d0d7de' },
        },
        // Billto Code (좌측 고정, 기존 행 readonly)
        {
            headerName: 'Billto Code', field: 'billto_code',
            width: 140, minWidth: 110, pinned: 'left',
            filter: 'agSetColumnFilter',
            editable: canEdit ? (p => !p.node?.rowPinned && !p.data?._orig) : false,
            cellClassRules: {
                'cell-readonly': p => !canEdit || (!p.node?.rowPinned && !!p.data?._orig),
            },
        },
        // Billto Name (좌측 고정, readonly)
        {
            headerName: 'Billto Name', field: 'billto_name',
            width: 200, minWidth: 140, pinned: 'left', editable: false,
            filter: 'agSetColumnFilter',
            cellClassRules: { 'cell-readonly': () => true },
        },
    ];

    // Product Group 컬럼 그룹 (그룹당 Biz / Team 2개 자식 컬럼)
    pgs.forEach((pg, idx) => {
        const shade = idx % 2 === 0 ? '#fafafa' : '#f0f6ff';
        cols.push({
            headerName: pg,           // ← 상위 헤더
            marryChildren: true,
            children: [
                {
                    headerName: 'Biz Name', field: `${pg}__biz`,
                    width: 150, minWidth: 110,
                    editable: canEdit ? (p => !p.node?.rowPinned) : false,
                    cellEditor: 'agTextCellEditor',
                    filter: 'agSetColumnFilter',
                    cellStyle: { background: shade },
                    onCellValueChanged: () => _bbizMarkDirty(),
                },
                {
                    headerName: 'Team', field: `${pg}__team`,
                    width: 130, minWidth: 100,
                    editable: canEdit ? (p => !p.node?.rowPinned) : false,
                    cellEditor: 'agTextCellEditor',
                    filter: 'agSetColumnFilter',
                    cellStyle: { background: shade },
                    onCellValueChanged: () => _bbizMarkDirty(),
                },
            ],
        });
    });

    return cols;
}

// ── Bill-To Biz 전용 defaultColDef ────────────────────────────────────
const _bbizDefaultColDef = {
    resizable: true, sortable: true, filter: 'agSetColumnFilter',
    wrapHeaderText: true, autoHeaderHeight: true,
    menuTabs: ['filterMenuTab', 'generalMenuTab', 'columnsMenuTab'],
    suppressKeyboardEvent: params => {
        if (params.event.ctrlKey && params.event.key === 'Enter') {
            if (params.editing) setTimeout(() => params.api.stopEditing(false), 0);
            return true;
        }
        return false;
    },
};

// ── 그리드에 데이터 반영 ──────────────────────────────────────────────
function _renderBbizGrid(flatRows, pgs, billtos = []) {
    _bbizPgs = pgs;
    const pivotRows = _pivotBbiz(flatRows, pgs, billtos);
    const canEdit   = typeof EDIT_MAP === 'undefined' || EDIT_MAP['billtoBiz'] !== false;
    const colDefs   = _buildBbizColDefs(pgs, canEdit);

    if (!bbizGridApi) {
        bbizGridApi = agGrid.createGrid(document.getElementById('bbizGrid'), {
            ..._sharedGridOptions,
            columnDefs:    colDefs,
            defaultColDef: _bbizDefaultColDef,
            rowData:       pivotRows,
            suppressScrollOnNewData: true,
            onCellValueChanged: () => _bbizMarkDirty(),
            statusBar: { statusPanels: [
                { statusPanel: 'agAggregationComponent', align: 'right' },
            ]},
        });
    } else {
        bbizGridApi.setGridOption('columnDefs', colDefs);
        bbizGridApi.setGridOption('rowData', pivotRows);
    }
    _bbizUpdateCount();
    _bbizDirty = false;
    const btn = document.getElementById('saveBtn_billtoBiz');
    if (btn) btn.classList.remove('btn-save-dirty');
}

function _bbizMarkDirty() {
    _bbizDirty = true;
    const btn = document.getElementById('saveBtn_billtoBiz');
    if (btn) btn.classList.add('btn-save-dirty');
}

function _bbizUpdateCount() {
    if (!bbizGridApi) return;
    let cnt = 0;
    bbizGridApi.forEachNode(n => { if (n.data?.billto_code) cnt++; });
    const rowEl = document.getElementById('bbizRowCount');
    if (rowEl) rowEl.textContent = cnt.toLocaleString() + ' rows';
    const tabEl = document.getElementById('billtoBizCount');
    if (tabEl) tabEl.textContent = cnt.toLocaleString();
}

// ── 데이터 로드 ───────────────────────────────────────────────────────
async function loadBilltoBiz() {
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';
    try {
        const [resData, resPg, resBillto] = await Promise.all([
            fetch(`/api/master/billto-biz?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
            fetch(`/api/master/billto-biz/product-groups?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
            fetch(`/api/master/billto-biz/billto-list?legal_entity=${encodeURIComponent(le)}`).then(r => r.json()),
        ]);
        _renderBbizGrid(resData.data || [], resPg.data || [], resBillto.data || []);
    } catch (e) {
        console.error('loadBilltoBiz error', e);
    }
}

// ── 초기화 (탭 최초 진입 시 1회) ─────────────────────────────────────
async function initBilltoBiz() {
    await loadBilltoBiz();
}

// ── 저장 ──────────────────────────────────────────────────────────────
async function saveBilltoBiz() {
    if (!bbizGridApi) return;
    const le = (typeof getGlobalLegalEntity === 'function') ? getGlobalLegalEntity() : 'ALL';

    const rows = [];
    bbizGridApi.forEachNode(n => { if (n.data?.billto_code) rows.push(n.data); });
    if (!rows.length) { alert('No data to save.'); return; }
    if (!await confirm('Are you sure you want to save the Bill-To Biz settings?\n(All existing data for this legal entity will be deleted and replaced.)')) return;

    const btn = document.getElementById('saveBtn_billtoBiz');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…'; }

    try {
        const res  = await fetch('/api/master/billto-biz/bulk-save', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ rows, pgs: _bbizPgs, legal_entity: le }),
        });
        const json = await res.json();
        if (json.success) {
            _bbizDirty = false;
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; btn.classList.remove('btn-save-dirty'); }
            alert(`✅ ${json.saved} record(s) saved.`);
            await loadBilltoBiz();
        } else {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
            alert('❌ Save failed: ' + (json.message || ''));
        }
    } catch (e) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-save"></i> Save'; }
        alert('❌ Server error: ' + e);
    }
}

function exportBilltoBiz() {
    if (bbizGridApi) _agGridExport(bbizGridApi, 'billto_biz.xlsx');
}

// ── Excel Import ──────────────────────────────────────────────────────
// exportDataAsExcel 이 컬럼 그룹을 2행 헤더로 출력하므로
// 공통 헬퍼(_xlsImportFromFile) 대신 직접 파싱합니다.
//
// 내보낸 Excel 헤더 구조 예시:
//   Row 0 (그룹행): [ '#', 'Billto Code', 'Billto Name', 'W/M',      '',     'REF',      '',     ... ]
//   Row 1 (자식행): [ '',  '',            '',            'Biz Name', 'Team', 'Biz Name', 'Team', ... ]
//
// 매핑: 자식행 'Biz Name' → `${group}__biz`,  'Team' → `${group}__team`
function importBilltoBiz() {
    if (!bbizGridApi) return;
    if (typeof XLSX === 'undefined') { alert('Excel library is not loaded.'); return; }

    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.xls,.csv';
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
            // header:1 → 2차원 배열로 읽어 2행 헤더를 직접 처리
            const raw = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null });

            if (raw.length < 3) { alert('No data found.'); return; }

            const row0 = raw[0];  // 그룹 헤더행 (product_group_code)
            const row1 = raw[1];  // 자식 헤더행 (Billto Code / Biz Name / Team)

            // 열 인덱스 → field 명 매핑
            const colFields = [];
            let lastGroup = '';
            for (let i = 0; i < row1.length; i++) {
                const g = row0[i] != null ? String(row0[i]).trim() : '';
                if (g) lastGroup = g;

                const h = row1[i] != null ? String(row1[i]).trim() : '';
                if      (h === 'Billto Code') colFields[i] = 'billto_code';
                else if (h === 'Biz Name')    colFields[i] = `${lastGroup}__biz`;
                else if (h === 'Team')        colFields[i] = `${lastGroup}__team`;
                else                          colFields[i] = null;  // #, Billto Name 등 무시
            }

            const pkIdx = colFields.indexOf('billto_code');
            if (pkIdx < 0) { alert('Billto Code column not found.\nPlease check if this is the Excel file exported from this tab.'); return; }

            // PK → 기존 노드 맵
            const nodeMap = {};
            bbizGridApi.forEachNode(n => {
                const pk = n.data?.billto_code;
                if (pk != null) nodeMap[String(pk).trim()] = n;
            });

            let updated = 0, added = 0;
            const toAdd = [];

            for (let r = 2; r < raw.length; r++) {
                const dr   = raw[r];
                const pkRaw = dr[pkIdx];
                if (pkRaw == null || String(pkRaw).trim() === '') continue;
                const pkVal = String(pkRaw).trim();

                const mapped = {};
                for (let i = 0; i < colFields.length; i++) {
                    const field = colFields[i];
                    if (!field || field === 'billto_code') continue;
                    const v = dr[i];
                    mapped[field] = (v == null || v === '') ? null : String(v).trim() || null;
                }

                const existing = nodeMap[pkVal];
                if (existing) {
                    Object.assign(existing.data, mapped);
                    bbizGridApi.refreshCells({ rowNodes: [existing], force: true });
                    updated++;
                } else {
                    toAdd.push({ billto_code: pkVal, billto_name: null, _orig: false, ...mapped });
                    added++;
                }
            }

            if (toAdd.length) bbizGridApi.applyTransaction({ add: toAdd });

            if (updated + added > 0) {
                _bbizMarkDirty();
                _bbizUpdateCount();
                alert(`✅ Import complete: ${updated} record(s) updated, ${added} record(s) added.`);
            } else {
                alert('No changes detected.');
            }
        } catch (e) {
            alert('❌ Import error: ' + e);
            console.error('importBilltoBiz error', e);
        }
    };

    input.click();
}
