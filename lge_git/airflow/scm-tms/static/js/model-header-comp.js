/**
 * ModelHeaderComp — AG Grid 커스텀 헤더 컴포넌트
 * MODEL_CODE 헤더 옆 버튼으로 PRODUCT_LEVEL1~4 컬럼 토글
 */
class ModelHeaderComp {
    init(params) {
        this._expanded = false;
        this._api = params.api;
        this.eGui = document.createElement('div');
        this.eGui.style.cssText = 'display:flex;align-items:center;justify-content:center;gap:5px;width:100%;overflow:hidden;';
        this.eGui.innerHTML = `
            <span class="ag-header-cell-text" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${params.displayName}</span>
            <button class="model-expand-btn" title="Show / Hide Product Level columns">
                <i class="fas fa-table-columns"></i>
            </button>`;
        this.eGui.querySelector('.model-expand-btn').addEventListener('click', e => {
            e.stopPropagation();
            this._expanded = !this._expanded;
            const cols = ['PRODUCT_LEVEL1_NAME','PRODUCT_LEVEL2_NAME','PRODUCT_LEVEL3_NAME','PRODUCT_LEVEL4_NAME'];
            this._api.setColumnsVisible(cols, this._expanded);
            const btn = this.eGui.querySelector('.model-expand-btn');
            btn.classList.toggle('active', this._expanded);
            btn.title = this._expanded ? 'Hide Product Level columns' : 'Show Product Level columns';
        });
    }
    getGui() { return this.eGui; }
    destroy() {}
}
