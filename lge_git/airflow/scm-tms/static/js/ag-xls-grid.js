/**
 * ag-xls-grid.js  —  Excel-like AG Grid 공통 모듈
 * ─────────────────────────────────────────────────────────────────────────────
 * AG Grid Enterprise v31+ 에서 인라인 편집, 엑셀 붙여넣기, 유효성 검증,
 * 상태 컬럼, 행 번호, 일괄 저장 기능을 제공하는 재사용 가능한 클래스.
 *
 * 사용법:
 *   const xls = new XlsGrid({
 *     tab:      'billto',                    // 식별자 (saveBtn_{tab}, valBanner_{tab} id 에 사용)
 *     pkField:  'billto_code',               // PK 컬럼 field 명
 *     editCols: ['billto_code', 'billto_name', ...],  // 편집 컬럼 목록 (빈 행 구조에 사용)
 *     valRules: [                            // 유효성 규칙
 *       { field:'billto_code', label:'Bill-To Code', notNull:true, unique:true, maxLen:64 },
 *       { field:'billto_name', label:'Bill-To Name', notNull:true, maxLen:256 },
 *     ],
 *     apiPath:  '/api/master/billto',        // REST API 기본 경로
 *     getApi:   () => billtoGridApi,         // AG Grid API 반환 함수
 *     getLegalEntity: () => 'LGEHQ',         // 현재 법인 코드 반환 함수 (선택)
 *   });
 *
 *   // AG Grid 옵션에 연결:
 *   {
 *     defaultColDef: {
 *       cellClassRules:      xls.cellClassRules,
 *       tooltipValueGetter:  p => xls.getTooltip(p),
 *     },
 *     tooltipShowDelay:              300,
 *     processDataFromClipboard:      p  => xls.onPasteProcess(p),
 *     onCellValueChanged:            p  => xls.onCellChanged(p),
 *     onPasteEnd:                    ()  => xls.onPasteEnd(),
 *     onFilterChanged:               ()  => xls.updateCount(),
 *     onGridReady:   p => { myGridApi = p.api; xls.loadData(); },
 *   }
 *
 *   // 툴바 버튼:
 *   <button id="saveBtn_billto" onclick="xls.saveChanges()">저장</button>
 *
 *   // 유효성 배너 (그리드 위 배치):
 *   <div id="valBanner_billto" class="val-banner">
 *     <i class="fas fa-triangle-exclamation"></i>
 *     <span id="valMsg_billto"></span>
 *   </div>
 *
 *   // 그리드 컨테이너에 xls-grid 클래스 추가:
 *   <div id="billtoGrid" class="ag-theme-alpine xls-grid"></div>
 */
class XlsGrid {
    /**
     * @param {object}   cfg
     * @param {string}   cfg.tab              탭/그리드 식별자
     * @param {string}   cfg.pkField          PK 컬럼 field 명
     * @param {string[]} cfg.editCols         편집 컬럼 목록
     * @param {Array}    [cfg.valRules=[]]    유효성 규칙
     * @param {string}   cfg.apiPath          REST API 기본 경로
     * @param {function} cfg.getApi           () => AG Grid API
     * @param {function} [cfg.getLegalEntity] () => 현재 법인 코드
     * @param {number}   [cfg.emptyRows=30]   초기 빈 행 수
     * @param {number}   [cfg.minTrailing=5]  하단 최소 빈 행 수
     * @param {string[]} [cfg.skipFields]     저장 시 제외 필드 (감사 컬럼 등)
     */
    constructor({
        tab,
        pkField,
        editCols      = [],
        valRules      = [],
        apiPath,
        getApi,
        getLegalEntity = () => 'ALL',
        emptyRows      = 30,
        minTrailing    = 5,
        skipFields     = ['input_dt', 'input_user_id', 'update_dt', 'update_user_id'],
    }) {
        this.tab           = tab;
        this.pkField       = pkField;
        this.editCols      = editCols;
        this.valRules      = valRules;
        this.apiPath       = apiPath;
        this.getApi        = getApi;
        this.getLegalEntity = getLegalEntity;
        this.emptyRows     = emptyRows;
        this.minTrailing   = minTrailing;
        this._skipSet      = new Set(['_status', '_orig', ...skipFields]);
        this._errors       = {};   // { "rowIndex__field": "에러 메시지" }

        // 메서드 바인딩 (이벤트 핸들러로 직접 넘길 때 필요)
        this.onCellChanged  = this.onCellChanged.bind(this);
        this.onPasteProcess = this.onPasteProcess.bind(this);
        this.onPasteEnd     = this.onPasteEnd.bind(this);
        this.saveChanges    = this.saveChanges.bind(this);
    }

    // ══════════════════════════════════════════════════════════════════════
    // 빈 행 관리
    // ══════════════════════════════════════════════════════════════════════

    /** 빈 행 객체 생성 */
    makeEmptyRow() {
        const row = { _status: '', _orig: false };
        this.editCols.forEach(f => { row[f] = null; });
        return row;
    }

    /** 행이 빈 행인지 확인 */
    isEmptyRow(data) {
        if (!data) return true;
        if (data._status) return false;
        return Object.entries(data)
            .filter(([k]) => !k.startsWith('_'))
            .every(([, v]) => v == null || v === '');
    }

    /** 하단 빈 행이 minTrailing 미만이면 자동 추가 */
    ensureTrailingEmpty() {
        const api = this.getApi();
        if (!api) return;
        const allData = [];
        api.forEachNode(n => allData.push(n.data));
        let trailing = 0;
        for (let i = allData.length - 1; i >= 0; i--) {
            if (this.isEmptyRow(allData[i])) trailing++;
            else break;
        }
        if (trailing < this.minTrailing) {
            api.applyTransaction({
                add: Array.from({ length: this.minTrailing - trailing }, () => this.makeEmptyRow()),
            });
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // AG Grid 이벤트 핸들러
    // ══════════════════════════════════════════════════════════════════════

    /** onCellValueChanged 핸들러 */
    onCellChanged(params) {
        const { data, colDef, node, api } = params;
        if (!colDef.field || colDef.field === '_status') return;
        if (!data._status) {
            if (data[this.pkField]) {
                data._status = '신규';
                api.refreshCells({ rowNodes: [node], columns: ['_status'], force: true });
            }
        } else if (data._status !== '신규') {
            data._status = '수정';
            api.refreshCells({ rowNodes: [node], columns: ['_status'], force: true });
        }
        this.ensureTrailingEmpty();
        this._markDirty();
    }

    /** processDataFromClipboard 핸들러 — 붙여넣기 전 빈 행 확보 */
    onPasteProcess(params) {
        if (!params.data || !params.data.length) return params.data;
        const api = this.getApi();
        const focusedCell = api ? api.getFocusedCell() : null;
        if (!focusedCell) return params.data;
        const needed = focusedCell.rowIndex + params.data.length + 5;
        const have   = api.getDisplayedRowCount();
        if (needed > have) {
            api.applyTransaction({
                add: Array.from({ length: needed - have }, () => this.makeEmptyRow()),
            });
        }
        return params.data;
    }

    /** onPasteEnd 핸들러 — 붙여넣기 후 상태 자동 판별 */
    onPasteEnd() {
        const api = this.getApi();
        if (!api) return;
        const toRefresh = [];
        api.forEachNode(node => {
            const d = node.data;
            if (!d[this.pkField]) return;
            if (!d._status) {
                d._status = d._orig ? '수정' : '신규';
                toRefresh.push(node);
            }
        });
        if (toRefresh.length)
            api.refreshCells({ rowNodes: toRefresh, columns: ['_status'], force: true });
        this.ensureTrailingEmpty();
        this._markDirty();
    }

    // ══════════════════════════════════════════════════════════════════════
    // 신규 행 취소
    // ══════════════════════════════════════════════════════════════════════

    clearNewRow(pkVal) {
        const api = this.getApi();
        if (!api) return;
        let target = null;
        api.forEachNode(node => {
            if (String(node.data[this.pkField]) === String(pkVal) && node.data._status === '신규')
                target = node;
        });
        if (target) {
            api.applyTransaction({ remove: [target.data] });
            this.ensureTrailingEmpty();
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // Dirty 표시 (저장 버튼 강조)
    // ══════════════════════════════════════════════════════════════════════

    _markDirty() {
        const api = this.getApi();
        const btn = document.getElementById('saveBtn_' + this.tab);
        if (!btn || !api) return;
        let hasDirty = false;
        api.forEachNode(n => {
            if (n.data._status === '신규' || n.data._status === '수정') hasDirty = true;
        });
        btn.classList.toggle('btn-save-dirty', hasDirty);
    }

    // ══════════════════════════════════════════════════════════════════════
    // 유효성 검증
    // ══════════════════════════════════════════════════════════════════════

    _errKey(rowIndex, field) {
        return `${rowIndex}__${field}`;
    }

    /**
     * 변경 행 전체 유효성 검증. 에러 셀에 CSS + 툴팁 적용.
     * @returns {boolean} 에러 없으면 true
     */
    validate() {
        const api = this.getApi();
        if (!api) return true;

        this._errors = {};
        const errors = [];
        const pkSeen = {};

        api.forEachNode(node => {
            const d = node.data;
            if (this.isEmptyRow(d)) return;
            if (d._status !== '신규' && d._status !== '수정') return;

            this.valRules.forEach(rule => {
                const val    = (d[rule.field] ?? '').toString().trim();
                let   errMsg = null;

                if (rule.notNull && !val) {
                    errMsg = `${rule.label}: 필수값입니다`;
                } else if (rule.maxLen && val.length > rule.maxLen) {
                    errMsg = `${rule.label}: ${rule.maxLen}자 이하 (현재 ${val.length}자)`;
                }
                if (errMsg) {
                    this._errors[this._errKey(node.rowIndex, rule.field)] = errMsg;
                    errors.push(`행 ${node.rowIndex + 1} - ${errMsg}`);
                }

                if (rule.unique && val) {
                    if (pkSeen[val] !== undefined) {
                        const msg = `${rule.label}: 중복값 "${val}"`;
                        this._errors[this._errKey(node.rowIndex, rule.field)] = msg;
                        this._errors[this._errKey(pkSeen[val],   rule.field)] = msg;
                        errors.push(`행 ${node.rowIndex + 1} - ${msg}`);
                    } else {
                        pkSeen[val] = node.rowIndex;
                    }
                }
            });
        });

        api.refreshCells({ force: true });

        const banner = document.getElementById('valBanner_' + this.tab);
        const msgEl  = document.getElementById('valMsg_'    + this.tab);
        if (banner && msgEl) {
            if (errors.length) {
                msgEl.innerHTML =
                    `<strong>${errors.length} error(s)</strong>: ` +
                    errors.slice(0, 3).join(' / ') +
                    (errors.length > 3 ? ` and ${errors.length - 3} more` : '');
                banner.classList.add('show');
            } else {
                banner.classList.remove('show');
            }
        }
        return errors.length === 0;
    }

    /** AG Grid defaultColDef.cellClassRules 에 전달할 객체 */
    get cellClassRules() {
        return {
            'cell-error': p => {
                if (!p.node || !p.colDef.field || p.colDef.field === '_status') return false;
                return !!this._errors[this._errKey(p.node.rowIndex, p.colDef.field)];
            },
        };
    }

    /** AG Grid defaultColDef.tooltipValueGetter 에 전달할 함수 */
    getTooltip(p) {
        if (!p.node || !p.colDef.field) return null;
        return this._errors[this._errKey(p.node.rowIndex, p.colDef.field)] || null;
    }

    // ══════════════════════════════════════════════════════════════════════
    // 컬럼 정의 헬퍼 (getter)
    // ══════════════════════════════════════════════════════════════════════

    /** 행 번호 컬럼 정의 */
    get rowNumColDef() {
        return {
            headerName: '#', width: 48, minWidth: 48, maxWidth: 48,
            pinned: 'left', editable: false, sortable: false, filter: false,
            suppressMovable: true, resizable: false, suppressSizeToFit: true,
            valueGetter: p => {
                if (!p.node || p.node.rowIndex == null) return '';
                const d = p.node.data;
                if (!d) return '';
                const isEmpty = Object.entries(d)
                    .filter(([k]) => !k.startsWith('_'))
                    .every(([, v]) => v == null || v === '');
                return isEmpty ? '' : p.node.rowIndex + 1;
            },
            cellStyle: {
                textAlign: 'right', color: '#9e9e9e', fontSize: '0.72rem',
                paddingRight: '6px', paddingLeft: '2px', userSelect: 'none',
                background: '#f5f5f5', borderRight: '1px solid #d0d7de',
            },
        };
    }

    /** 상태 컬럼 정의 (신규/수정 표시) */
    get statusColDef() {
        return {
            headerName: '', field: '_status', width: 48, minWidth: 48, maxWidth: 48,
            pinned: 'left', editable: false, sortable: false, filter: false,
            suppressMovable: true, resizable: false, suppressSizeToFit: true,
            cellStyle: p => {
                if (p.value === '신규') return { textAlign: 'center', color: '#1565C0', fontWeight: 700, fontSize: '0.7rem', background: '#E3F2FD', padding: '0' };
                if (p.value === '수정') return { textAlign: 'center', color: '#BF360C', fontWeight: 700, fontSize: '0.7rem', background: '#FBE9E7', padding: '0' };
                return { padding: '0' };
            },
            cellRenderer: p => p.value || '',
        };
    }

    // ══════════════════════════════════════════════════════════════════════
    // 데이터 로드 / 카운트
    // ══════════════════════════════════════════════════════════════════════

    /**
     * API에서 데이터 조회 후 그리드에 설정.
     * @param {object} [extraParams] 추가 쿼리 파라미터 (ex: { division: 'HA' })
     */
    async loadData(extraParams = {}) {
        const api = this.getApi();
        if (!api) return;
        try {
            const le  = this.getLegalEntity();
            const qs  = new URLSearchParams({ legal_entity: le, ...extraParams }).toString();
            const res = await fetch(`${this.apiPath}?${qs}`);
            const json = await res.json();
            if (json.success) {
                const rows = (json.data || []).map(r => ({ ...r, _status: '', _orig: true }));
                rows.push(...Array.from({ length: this.emptyRows }, () => this.makeEmptyRow()));
                api.setGridOption('rowData', rows);
                this.updateCount();
            } else {
                alert('Failed to load data: ' + (json.message || ''));
            }
        } catch (e) {
            console.error(`XlsGrid[${this.tab}] loadData error`, e);
        }
    }

    /** {tab}Count 엘리먼트에 실제 데이터 행 수 표시 (빈 행 제외) */
    updateCount() {
        const api = this.getApi();
        if (!api) return;
        let shown = 0;
        api.forEachNodeAfterFilter(n => { if (!this.isEmptyRow(n.data)) shown++; });
        const el = document.getElementById(this.tab + 'Count');
        if (el) el.textContent = shown.toLocaleString();
    }

    // ══════════════════════════════════════════════════════════════════════
    // 일괄 저장 (신규 → POST / 수정 → PUT)
    // ══════════════════════════════════════════════════════════════════════

    async saveChanges() {
        const api = this.getApi();
        if (!api) return;

        const toSave = [];
        api.forEachNode(n => {
            if (n.data._status === '신규' || n.data._status === '수정') toSave.push(n.data);
        });
        if (!toSave.length) { alert('No changes to save.'); return; }

        if (!this.validate()) {
            alert('⚠️ Validation errors found.\nPlease check and fix the error cells.');
            return;
        }
        if (!await confirm(`${toSave.length}개 레코드를 저장하시겠습니까?`)) return;

        const btn = document.getElementById('saveBtn_' + this.tab);
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중…'; }

        let ok = 0, fail = 0;
        const failMsgs = [];

        for (const row of toSave) {
            const isNew = row._status === '신규';
            const pkVal = row[this.pkField];
            if (!pkVal) { fail++; failMsgs.push('Row without PK skipped'); continue; }

            const payload = Object.fromEntries(
                Object.entries(row).filter(([k]) => !this._skipSet.has(k))
            );
            try {
                const url    = this.apiPath + (isNew ? '' : '/' + encodeURIComponent(pkVal));
                const method = isNew ? 'POST' : 'PUT';
                const res    = await fetch(url, {
                    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
                });
                const json = await res.json();
                if (json.success) { row._status = '__ok__'; row._orig = true; ok++; }
                else { fail++; failMsgs.push(`[${pkVal}] ${json.message}`); }
            } catch (e) {
                fail++; failMsgs.push(String(e));
            }
        }

        api.forEachNode(n => { if (n.data._status === '__ok__') n.data._status = ''; });
        api.refreshCells({ columns: ['_status'], force: true });

        document.getElementById('valBanner_' + this.tab)?.classList.remove('show');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-save"></i> 저장';
            btn.classList.remove('btn-save-dirty');
        }

        alert(ok
            ? `✅ ${ok} record(s) saved successfully` + (fail ? `\n❌ ${fail} record(s) failed:\n` + failMsgs.join('\n') : '')
            : `❌ ${fail} record(s) failed:\n` + failMsgs.join('\n')
        );
        if (ok) await this.loadData();
    }
}
