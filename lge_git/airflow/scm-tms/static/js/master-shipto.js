// ─────────────────────────────────────────────────────────────────────
// master_shipto.js  ―  Ship-To 탭 그리드
// 의존: master-shared.js (먼저 로드)
// ─────────────────────────────────────────────────────────────────────
let shiptoGridApi = null;

const shiptoColDefs = [
    _rowNumColDef,
    _statusColDef,
    {
        headerName: '', width: 52, minWidth: 52, maxWidth: 52, pinned: 'left',
        cellStyle: { padding: '2px 3px' }, sortable: false, filter: false,
        suppressMovable: true, resizable: false,
        cellRenderer: p => {
            const pk = p.data.shipto_code;
            if (!pk || _isEmptyRow(p.data)) return '';
            if (p.data._status === 'NEW')
                return `<button class="btn-icon-sm" style="color:#c62828;font-size:.7rem" onclick="clearNewRow('shipto','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-xmark"></i></button>`;
            if (typeof EDIT_MAP !== 'undefined' && EDIT_MAP['shipto'] === false) return '';
            return `<button class="btn-icon-del" style="font-size:.75rem" onclick="openDel('shipto','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-trash-alt"></i></button>`;
        },
    },
    txtCol('shipto_code', 'Ship-To Code', { width:130, pinned:'left', editable: p => (typeof EDIT_MAP === 'undefined' || EDIT_MAP['shipto'] !== false) && !p.data?._orig }),
    txtCol('shipto_name', 'Ship-To Name', { width:220, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['shipto'] !== false }),
    txtCol('address',     'Address',      { width:280, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['shipto'] !== false }),
    txtCol('postal_code', 'Postal Code',  { width:110, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['shipto'] !== false }),
    txtCol('route',       'Route',        { width:120, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['shipto'] !== false }),
    ...auditCols,
];

if (document.getElementById('shiptoGrid')) { /* lazy — initShipto() 에서 생성 */ }

async function initShipto() {
    if (!shiptoGridApi) {
        shiptoGridApi = agGrid.createGrid(document.getElementById('shiptoGrid'), {
            ..._crudGridOptions('shipto', () => shiptoGridApi),
            columnDefs: shiptoColDefs,
        });
    }
    await loadData('shipto');
}
