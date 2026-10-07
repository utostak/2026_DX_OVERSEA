// ─────────────────────────────────────────────────────────────────────
// master_billto.js  ―  Bill-To 탭 그리드
// 의존: master-shared.js (먼저 로드)
// ─────────────────────────────────────────────────────────────────────
let billtoGridApi = null;

const billtoColDefs = [
    _rowNumColDef,
    _statusColDef,
    {
        headerName: '', width: 52, minWidth: 52, maxWidth: 52, pinned: 'left',
        cellStyle: { padding: '2px 3px' }, sortable: false, filter: false,
        suppressMovable: true, resizable: false,
        cellRenderer: p => {
            const pk = p.data.billto_code;
            if (!pk || _isEmptyRow(p.data)) return '';
            if (p.data._status === 'NEW')
                return `<button class="btn-icon-sm" style="color:#c62828;font-size:.7rem" onclick="clearNewRow('billto','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-xmark"></i></button>`;
            if (typeof EDIT_MAP !== 'undefined' && EDIT_MAP['billto'] === false) return '';
            return `<button class="btn-icon-del" style="font-size:.75rem" onclick="openDel('billto','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-trash-alt"></i></button>`;
        },
    },
    txtCol('billto_code',       'Bill-To Code', { width:130, pinned:'left', editable: p => (typeof EDIT_MAP === 'undefined' || EDIT_MAP['billto'] !== false) && !p.data?._orig }),
    txtCol('billto_name',       'Bill-To Name', { width:220, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['billto'] !== false }), 
    ...auditCols,
];

if (document.getElementById('billtoGrid')) {
    // 그리드는 탭 첫 진입 시 initBillto() 에서 lazy 생성 (Sales Target 동일 패턴)
}

async function initBillto() {
    if (!billtoGridApi) {
        billtoGridApi = agGrid.createGrid(document.getElementById('billtoGrid'), {
            ..._crudGridOptions('billto', () => billtoGridApi),
            columnDefs: billtoColDefs,
        });
    }
    await loadData('billto');
}
