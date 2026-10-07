// ─────────────────────────────────────────────────────────────────────
// master-lgeph-billto.js  ―  Bill-To 탭 그리드 (PH 전용 / canonical tab: 'billtoPh')
// 의존: master-shared.js (먼저 로드)
// 표준 Bill-To(master-billto.js)와 독립된 패널/그리드/API 를 사용한다.
//   · 그리드 컨테이너  : #billtoPhGrid
//   · API 경로         : /api/master/billto-ph  (_apiTab 매핑)
//   · 편집권한 page_id : 'billto-ph'
// ─────────────────────────────────────────────────────────────────────
let billtoPhGridApi = null;

const billtoPhColDefs = [
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
                return `<button class="btn-icon-sm" style="color:#c62828;font-size:.7rem" onclick="clearNewRow('billtoPh','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-xmark"></i></button>`;
            if (typeof EDIT_MAP !== 'undefined' && EDIT_MAP['billto-ph'] === false) return '';
            return `<button class="btn-icon-del" style="font-size:.75rem" onclick="openDel('billtoPh','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-trash-alt"></i></button>`;
        },
    },
    txtCol('billto_code',       'Bill-To Code', { width:130, pinned:'left', editable: p => (typeof EDIT_MAP === 'undefined' || EDIT_MAP['billto-ph'] !== false) && !p.data?._orig }),
    txtCol('billto_name',       'Bill-To Name', { width:220, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['billto-ph'] !== false }),
    txtCol('billto_group_name', 'Group Name',   { width:180, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['billto-ph'] !== false }),
    ...auditCols,
];

async function initBilltoPh() {
    if (!billtoPhGridApi) {
        billtoPhGridApi = agGrid.createGrid(document.getElementById('billtoPhGrid'), {
            ..._crudGridOptions('billtoPh', () => billtoPhGridApi),
            columnDefs: billtoPhColDefs,
        });
    }
    await loadData('billtoPh');
}

