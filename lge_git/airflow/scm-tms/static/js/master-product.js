// ─────────────────────────────────────────────────────────────────────
// master_product.js  ―  Product 탭 그리드
// 의존: master-shared.js (먼저 로드)
// ─────────────────────────────────────────────────────────────────────
let productGridApi = null;

const productColDefs = [
    _rowNumColDef,
    _statusColDef,
    {
        headerName: '', width: 52, minWidth: 52, maxWidth: 52, pinned: 'left',
        cellStyle: { padding: '2px 3px' }, sortable: false, filter: false,
        suppressMovable: true, resizable: false,
        cellRenderer: p => {
            const pk = p.data.product_code;
            if (!pk || _isEmptyRow(p.data)) return '';
            if (p.data._status === 'NEW')
                return `<button class="btn-icon-sm" style="color:#c62828;font-size:.7rem" onclick="clearNewRow('product','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-xmark"></i></button>`;
            if (typeof EDIT_MAP !== 'undefined' && EDIT_MAP['product'] === false) return '';
            return `<button class="btn-icon-del" style="font-size:.75rem" onclick="openDel('product','${String(pk).replace(/'/g, "\\'")}')"><i class="fas fa-trash-alt"></i></button>`;
        },
    },
    txtCol('product_code',          'Product Code',  { width:150, pinned:'left', editable: p => (typeof EDIT_MAP === 'undefined' || EDIT_MAP['product'] !== false) && !p.data?._orig }),
    txtCol('product_group_code',    'Group Code',    { width:150, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['product'] !== false }),
    txtCol('product_category_code', 'Category Code', { width:150, editable: () => typeof EDIT_MAP === 'undefined' || EDIT_MAP['product'] !== false }),
    ...auditCols,
];

if (document.getElementById('productGrid')) { /* lazy — initProduct() 에서 생성 */ }

async function initProduct() {
    if (!productGridApi) {
        productGridApi = agGrid.createGrid(document.getElementById('productGrid'), {
            ..._crudGridOptions('product', () => productGridApi),
            columnDefs: productColDefs,
        });
    }
    await loadData('product');
}
