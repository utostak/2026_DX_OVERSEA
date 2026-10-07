"""
apis/api_master.py — 마스터 데이터 CRUD API
  GET/POST/PUT/DELETE        /api/master/billto
  GET/POST/PUT/DELETE        /api/master/shipto
  GET/POST/PUT/DELETE        /api/master/product
  POST /api/master/billto/bulk-save
  POST /api/master/shipto/bulk-save
  POST /api/master/product/bulk-save
  GET  /api/master/sales-target
  GET  /api/master/sales-target/currencies
  GET  /api/master/sales-target/divisions
  POST /api/master/sales-target/bulk-save
  GET  /api/master/sales-team
  POST /api/master/sales-team/bulk-save
  GET  /api/master/billto-biz
  GET  /api/master/billto-biz/product-groups
  GET  /api/master/billto-biz/billto-list
  POST /api/master/billto-biz/bulk-save
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from utils.pg_db import pg
from utils.auth_check import require_login

logger    = logging.getLogger(__name__)
master_bp = Blueprint('master', __name__, url_prefix='/api/master')


def _subsdr() -> str:
    """
    법인 코드 우선순위:
      1. request.args    (GET/DELETE 쿼리파라미터 ?legal_entity=)
      2. request.json    (POST/PUT body 의 legal_entity 키)
      3. session subsdr_name (로그인 세션 기본값)
    'ALL' 은 세션값으로 대체.
    """
    le = (request.args.get('legal_entity') or '').strip()
    if not le or le == 'ALL':
        body = request.get_json(silent=True, force=True) or {}
        le = (body.get('legal_entity') or '').strip()
    if le and le != 'ALL':
        return le
    return session.get('subsdr_name', '')


def _audit() -> dict:
    """감사 컬럼 공통값 반환"""
    return {
        'update_dt':      datetime.now(),
        'update_user_id': session.get('user_id', 'system'),
    }


def _datetime_str(row: dict) -> dict:
    """datetime → 'YYYY-MM-DD HH:MM' 변환"""
    for k in ('input_dt', 'update_dt'):
        if row.get(k) and isinstance(row[k], datetime):
            row[k] = row[k].strftime('%Y-%m-%d %H:%M')
    return row


# d_menu_mst 의 page_id 와 매핑 (탭별 서브페이지 권한 체크용)
_TAB_PAGE = {
    'billto':      'billto',
    'billto-ph':   'billto-ph',
    'shipto':      'shipto',
    'product':     'product',
    'salesTarget': 'salesTarget',
    'salesTeam':   'salesTeam',
    'billtoBiz':   'billtoBiz',
}

def _effective_master_perm():
    """
    현재 요청의 법인(legal_entity) 기준으로 master-data 메뉴 권한을 반환.

    로그인 세션의 allowed_menus 는 '로그인 법인' 기준이므로, 사용자가 다른
    법인으로 전환하면 탭 노출(list_master_tabs)과 실제 데이터 권한 체크가
    서로 다른 기준을 쓰게 되어 403 이 발생한다. 이를 막기 위해 탭 노출과
    동일하게 선택 법인 기준으로 allowed_menus 를 조회한다.

    반환: (allowed_menus_is_admin: bool, info: dict | None)
      - is_admin True  → 전체 허용 (권한 체크 불필요)
      - info None       → master-data 메뉴 자체 권한 없음
      - info dict        → {'edit': bool, 'pages': None|list, 'page_edits': {}}
    """
    from apis.api_auth import _parse_allowed_menus

    legal_entity = _subsdr()
    user_type    = session.get('user_type')

    allowed_menus = session.get('allowed_menus')
    if legal_entity and user_type:
        try:
            rows = pg.query(
                "SELECT allowed_menus FROM v_user_type_mst"
                " WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
                (legal_entity, user_type)
            )
            if rows:
                allowed_menus = rows[0]['allowed_menus']
        except Exception as e:
            logger.warning(f"_effective_master_perm allowed_menus lookup error: {e}")

    allowed_dict = _parse_allowed_menus(allowed_menus)   # None = 전체(admin)
    if allowed_dict is None:
        return True, None
    return False, allowed_dict.get('master-data')


def _require_tab_access(tab: str):
    """탭 접근 권한 확인 (읽기) — 선택 법인 기준"""
    err = require_login()
    if err:
        return err
    page_id = _TAB_PAGE.get(tab, tab)
    is_admin, info = _effective_master_perm()
    if is_admin:
        return None
    if info is None:
        logger.warning(f"❌ Menu access denied: user_id={session.get('user_id')}, menu_id=master-data, IP: {request.remote_addr}")
        return jsonify({'success': False, 'message': 'master-data 접근 권한이 없습니다.'}), 403
    pages = info.get('pages')
    if pages is None or page_id in pages:
        return None
    logger.warning(f"❌ Page access denied: user_id={session.get('user_id')}, menu_id=master-data, page_id={page_id}, IP: {request.remote_addr}")
    return jsonify({'success': False, 'message': f'master-data/{page_id} 접근 권한이 없습니다.'}), 403


def _require_edit_access(tab: str):
    """탭 편집 권한 확인 (쓰기) — 선택 법인 기준"""
    err = require_login()
    if err:
        return err
    page_id = _TAB_PAGE.get(tab, tab)
    is_admin, info = _effective_master_perm()
    if is_admin:
        return None
    if info is None:
        logger.warning(f"❌ Edit access denied: user_id={session.get('user_id')}, menu_id=master-data, IP: {request.remote_addr}")
        return jsonify({'success': False, 'message': 'master-data 편집 권한이 없습니다.'}), 403
    pages      = info.get('pages')
    page_edits = info.get('page_edits') or {}
    # pages 목록이 있으면 페이지별 edit 권한, 없으면 메뉴 레벨 edit 권한
    if pages is None:
        if info.get('edit', False):
            return None
    elif page_id in pages:
        if page_edits.get(page_id, False):
            return None
    logger.warning(f"❌ Edit access denied: user_id={session.get('user_id')}, menu_id=master-data, page_id={page_id}, IP: {request.remote_addr}")
    return jsonify({'success': False, 'message': f'master-data/{page_id} 편집 권한이 없습니다.'}), 403


# 탭 메타데이터 (아이콘/레이블/카운트 id/로드할 JS 파일 — 단일 관리)
_TAB_META = {
    'billto':      {'key': 'billto',      'icon': 'fa-building',     'label': 'Bill-To',      'count_id': 'billtoCount',      'script': 'js/master-billto.js'},
    'billto-ph':   {'key': 'billto-ph',   'icon': 'fa-building',     'label': 'Bill-To',      'count_id': 'billtoPhCount',    'script': 'js/master-lgeph-billto.js'},
    'shipto':      {'key': 'shipto',      'icon': 'fa-location-dot', 'label': 'Ship-To',      'count_id': 'shiptoCount',      'script': 'js/master-shipto.js'},
    'product':     {'key': 'product',     'icon': 'fa-box',          'label': 'Product',      'count_id': 'productCount',     'script': 'js/master-product.js'},
    'salesTeam':   {'key': 'salesTeam',   'icon': 'fa-users',        'label': 'Sales Team',   'count_id': 'salesTeamCount',   'script': 'js/master-sales-team.js'},
    'salesTarget': {'key': 'salesTarget', 'icon': 'fa-bullseye',     'label': 'Sales Target', 'count_id': 'salesTargetCount', 'script': 'js/master-sales-target.js'},
    'billtoBiz':   {'key': 'billtoBiz',   'icon': 'fa-sitemap',      'label': 'Bill-To Biz',  'count_id': 'billtoBizCount',   'script': 'js/master-billto-biz.js'},
}


def tab_script(tab: str, legal_entity: str | None = None) -> str | None:
    """탭 기준으로 로드할 JS 파일명 반환 (없으면 None)."""
    meta = _TAB_META.get(tab)
    return meta.get('script') if meta else None


def tab_scripts_for(tabs, legal_entity: str | None = None) -> list:
    """탭 목록(키 문자열 또는 dict) → 중복 제거된 스크립트 파일명 목록(순서 유지)."""
    seen, out = set(), []
    for t in tabs:
        key = t if isinstance(t, str) else (t.get('key') or t.get('page_id'))
        src = tab_script(key)
        if src and src not in seen:
            seen.add(src)
            out.append(src)
    return out


@master_bp.route('/tabs', methods=['GET'])
def list_master_tabs():
    """
    선택된 법인(legal_entity) 기준으로 노출 가능한 Master Data 탭 목록을 반환.

    법인이 바뀌면 권한(allowed_menus)에 따라 탭 목록이 달라질 수 있으므로,
    프론트엔드에서 조회 시 이 API 를 호출해 탭 목록을 재점검한다.

    반환: { success, legal_entity, tabs: [{key, icon, label, count_id, page_id}], edit_map }
    """
    err = require_login()
    if err:
        return err

    from apis.api_auth import _parse_allowed_menus

    legal_entity = (request.args.get('legal_entity') or '').strip()
    if not legal_entity or legal_entity == 'ALL':
        legal_entity = session.get('subsdr_name') or ''

    user_type = session.get('user_type')

    # 1) 선택 법인 기준 allowed_menus 조회 (없으면 세션 기본값)
    allowed_menus = session.get('allowed_menus')
    try:
        rows = pg.query(
            "SELECT allowed_menus FROM v_user_type_mst"
            " WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
            (legal_entity, user_type)
        )
        if rows:
            allowed_menus = rows[0]['allowed_menus']
    except Exception as e:
        logger.warning(f"list_master_tabs allowed_menus lookup error: {e}")

    # 2) master-data 의 allowed_pages / page_edits 추출
    allowed_dict  = _parse_allowed_menus(allowed_menus)   # None = 전체(admin)
    allowed_pages = None   # None = 전체 허용
    page_edits    = {}
    if allowed_dict is not None:
        info = allowed_dict.get('master-data')
        if info is None:
            # master-data 메뉴 권한 자체가 없음 → 탭 없음
            return jsonify({'success': True, 'legal_entity': legal_entity,
                            'tabs': [], 'edit_map': {}})
        allowed_pages = info.get('pages')
        page_edits    = info.get('page_edits') or {}

    # 3) d_menu_mst 에서 master-data 서브페이지(탭) 순서 조회
    try:
        db_tabs = pg.query(
            "SELECT page_id, menu_name, sort_order"
            "  FROM d_menu_mst"
            " WHERE menu_id = 'master-data'"
            "   AND page_id <> '_'"
            "   AND use_yn = 'Y' AND delete_flag = 'N'"
            " ORDER BY sort_order",
        )
        all_pages = [r['page_id'] for r in db_tabs]
    except Exception:
        all_pages = list(_TAB_META.keys())

    visible_pages = [
        p for p in all_pages
        if allowed_pages is None or p in allowed_pages
    ]

    edit_map = {p: page_edits.get(p, True) for p in visible_pages}

    tabs = [
        {**_TAB_META[p], 'page_id': p, 'script': tab_script(p, legal_entity)}
        for p in visible_pages
        if p in _TAB_META
    ]

    # 폴백: DB 데이터 없거나 page_id 불일치 시 전체 탭 (admin 만 해당)
    if not tabs and allowed_dict is None:
        tabs     = [{'page_id': k, **v, 'script': tab_script(k, legal_entity)}
                    for k, v in _TAB_META.items()]
        edit_map = {k: True for k in _TAB_META}

    return jsonify({'success': True, 'legal_entity': legal_entity,
                    'tabs': tabs, 'edit_map': edit_map})


# ══════════════════════════════════════════════════════════════
# 공통 bulk-save 헬퍼
# ══════════════════════════════════════════════════════════════

def _bulk_save(table: str, pk_cols: list, data_cols: list, rows: list,
               subsdr: str) -> dict:
    """
    rows 를 한 트랜잭션 안에서 pg.merge() 로 UPSERT.
    각 row dict 에는 _status('NEW'|'MOD') 가 포함되어 있어야 함.
    모든 컬럼(audit 포함)을 서버에서 채워 넣은 뒤 merge.
    """
    now      = datetime.now()
    user_id  = session.get('user_id', 'system')
    prepared = []

    for row in rows:
        status = row.get('_status', '')
        if status not in ('NEW', 'MOD'):
            continue

        rec = {'subsdr_name': subsdr}
        for col in pk_cols[1:]:          # subsdr_name 은 위에서 이미 세팅
            rec[col] = (row.get(col) or '').strip() or None
        for col in data_cols:
            rec[col] = (row.get(col) or '').strip() or None

        # audit
        if status == 'NEW':
            rec['input_user_id'] = user_id
        rec['update_dt']       = now
        rec['update_user_id']  = user_id

        prepared.append(rec)

    if not prepared:
        return {'success': True, 'saved': 0}

    conflict_cols = pk_cols                          # PK 전체 (subsdr_name + code)
    # conflict(기존 행 UPDATE) 시 input_user_id 는 건드리지 않음
    update_cols   = data_cols + ['update_dt', 'update_user_id']

    pg.merge(table, rows=prepared,
             conflict_cols=conflict_cols,
             update_cols=update_cols)

    return {'success': True, 'saved': len(prepared)}


# ══════════════════════════════════════════════════════════════
# 1. Bill-To 마스터  (subsdr_name + billto_code)
#    표준(billto)과 PH 전용(billto-ph)이 동일 테이블(d_billto_mst)을 공유하며
#    subsdr_name(=legal_entity) 로 데이터가 구분된다. 두 탭은 서로 다른
#    page_id 권한(access_tab)만 다르고 로직은 동일하므로 내부 impl 을 공유한다.
# ══════════════════════════════════════════════════════════════
def _billto_list_impl(access_tab):
    err = require_login() or _require_tab_access(access_tab)
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT subsdr_name, billto_code, billto_name,"
            "       billto_group_name,"
            "       input_dt, input_user_id, update_dt, update_user_id"
            "  FROM d_billto_mst"
            " WHERE subsdr_name = %s AND delete_flag = 'N'"
            " ORDER BY billto_code",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': [_datetime_str(r) for r in rows]})
    except Exception as e:
        logger.exception(f" list_billto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


def _billto_create_impl(access_tab):
    err = require_login() or _require_tab_access(access_tab)
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    code   = (d.get('billto_code') or '').strip()
    if not code:
        return jsonify({'success': False, 'message': 'billto_code 는 필수입니다.'}), 400
    try:
        pg.insert('d_billto_mst', {
            'subsdr_name':       subsdr,
            'billto_code':       code,
            'billto_name':       (d.get('billto_name')       or '').strip(),
            'billto_group_name': (d.get('billto_group_name') or '').strip() or None,
            'input_user_id':     session.get('user_id'),
            **_audit(),
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" create_billto error:")
        msg = '이미 존재하는 코드입니다.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


def _billto_update_impl(access_tab, code):
    err = require_login() or _require_tab_access(access_tab)
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    upd    = {k: (d[k] or '').strip() or None
               for k in ('billto_name', 'billto_group_name')
               if k in d}
    if not upd:
        return jsonify({'success': False, 'message': '변경 항목이 없습니다.'}), 400
    upd.update(_audit())
    try:
        pg.update('d_billto_mst', set=upd,
                  where={'subsdr_name': subsdr, 'billto_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" update_billto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


def _billto_delete_impl(access_tab, code):
    err = require_login() or _require_tab_access(access_tab)
    if err: return err
    subsdr = _subsdr()
    try:
        pg.update('d_billto_mst',
                  set={'delete_flag': 'Y', **_audit()},
                  where={'subsdr_name': subsdr, 'billto_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" delete_billto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


def _billto_bulk_save_impl(access_tab):
    err = require_login() or _require_tab_access(access_tab) or _require_edit_access(access_tab)
    if err: return err
    body   = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    rows   = body.get('rows', [])
    if not rows:
        return jsonify({'success': False, 'message': '저장할 행이 없습니다.'}), 400
    try:
        result = _bulk_save(
            table      = 'd_billto_mst',
            pk_cols    = ['subsdr_name', 'billto_code'],
            data_cols  = ['billto_name', 'billto_group_name'],
            rows       = rows,
            subsdr     = subsdr,
        )
        return jsonify(result)
    except Exception as e:
        logger.exception(f" bulk_save_billto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 표준 Bill-To 라우트 ──────────────────────────────────────────
@master_bp.route('/billto', methods=['GET'])
def list_billto():
    return _billto_list_impl('billto')


@master_bp.route('/billto', methods=['POST'])
def create_billto():
    return _billto_create_impl('billto')


@master_bp.route('/billto/<code>', methods=['PUT'])
def update_billto(code):
    return _billto_update_impl('billto', code)


@master_bp.route('/billto/<code>', methods=['DELETE'])
def delete_billto(code):
    return _billto_delete_impl('billto', code)


@master_bp.route('/billto/bulk-save', methods=['POST'])
def bulk_save_billto():
    return _billto_bulk_save_impl('billto')


# ── PH 전용 Bill-To 라우트 (page_id: billto-ph) ─────────────────
@master_bp.route('/billto-ph', methods=['GET'])
def list_billto_ph():
    return _billto_list_impl('billto-ph')


@master_bp.route('/billto-ph', methods=['POST'])
def create_billto_ph():
    return _billto_create_impl('billto-ph')


@master_bp.route('/billto-ph/<code>', methods=['PUT'])
def update_billto_ph(code):
    return _billto_update_impl('billto-ph', code)


@master_bp.route('/billto-ph/<code>', methods=['DELETE'])
def delete_billto_ph(code):
    return _billto_delete_impl('billto-ph', code)


@master_bp.route('/billto-ph/bulk-save', methods=['POST'])
def bulk_save_billto_ph():
    return _billto_bulk_save_impl('billto-ph')


# ══════════════════════════════════════════════════════════════
# 2. Ship-To 마스터  (subsdr_name + shipto_code)
# ══════════════════════════════════════════════════════════════
@master_bp.route('/shipto', methods=['GET'])
def list_shipto():
    err = require_login() or _require_tab_access('shipto')
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT subsdr_name, shipto_code, shipto_name,"
            "       address, postal_code, route,"
            "       input_dt, input_user_id, update_dt, update_user_id"
            "  FROM d_shipto_mst"
            " WHERE subsdr_name = %s AND delete_flag = 'N'"
            " ORDER BY shipto_code",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': [_datetime_str(r) for r in rows]})
    except Exception as e:
        logger.exception(f" list_shipto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/shipto', methods=['POST'])
def create_shipto():
    err = require_login() or _require_tab_access('shipto')
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    code   = (d.get('shipto_code') or '').strip()
    if not code:
        return jsonify({'success': False, 'message': 'shipto_code 는 필수입니다.'}), 400
    try:
        pg.insert('d_shipto_mst', {
            'subsdr_name':   subsdr,
            'shipto_code':   code,
            'shipto_name':   (d.get('shipto_name')   or '').strip() or None,
            'address':       (d.get('address')        or '').strip() or None,
            'postal_code':   (d.get('postal_code')    or '').strip() or None,
            'route':         (d.get('route')          or '').strip() or None,
            'input_user_id': session.get('user_id'),
            **_audit(),
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" create_shipto error:")
        msg = '이미 존재하는 코드입니다.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


@master_bp.route('/shipto/<code>', methods=['PUT'])
def update_shipto(code):
    err = require_login() or _require_tab_access('shipto')
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    upd    = {k: (d[k] or '').strip() or None
               for k in ('shipto_name', 'address', 'postal_code', 'route')
               if k in d}
    if not upd:
        return jsonify({'success': False, 'message': '변경 항목이 없습니다.'}), 400
    upd.update(_audit())
    try:
        pg.update('d_shipto_mst', set=upd,
                  where={'subsdr_name': subsdr, 'shipto_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" update_shipto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/shipto/<code>', methods=['DELETE'])
def delete_shipto(code):
    err = require_login() or _require_tab_access('shipto')
    if err: return err
    subsdr = _subsdr()
    try:
        pg.update('d_shipto_mst',
                  set={'delete_flag': 'Y', **_audit()},
                  where={'subsdr_name': subsdr, 'shipto_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" delete_shipto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/shipto/bulk-save', methods=['POST'])
def bulk_save_shipto():
    err = require_login() or _require_tab_access('shipto') or _require_edit_access('shipto')
    if err: return err
    body   = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    rows   = body.get('rows', [])
    if not rows:
        return jsonify({'success': False, 'message': '저장할 행이 없습니다.'}), 400
    try:
        result = _bulk_save(
            table      = 'd_shipto_mst',
            pk_cols    = ['subsdr_name', 'shipto_code'],
            data_cols  = ['shipto_name', 'address', 'postal_code', 'route'],
            rows       = rows,
            subsdr     = subsdr,
        )
        return jsonify(result)
    except Exception as e:
        logger.exception(f" bulk_save_shipto error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# 3. Product 마스터  (subsdr_name + product_code)
# ══════════════════════════════════════════════════════════════
@master_bp.route('/product', methods=['GET'])
def list_product():
    err = require_login() or _require_tab_access('product')
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT subsdr_name, product_code, product_group_code, product_category_code,"
            "       input_dt, input_user_id, update_dt, update_user_id"
            "  FROM d_product_mst"
            " WHERE subsdr_name = %s AND delete_flag = 'N'"
            " ORDER BY product_code",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': [_datetime_str(r) for r in rows]})
    except Exception as e:
        logger.exception(f" list_product error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/product', methods=['POST'])
def create_product():
    err = require_login() or _require_tab_access('product')
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    code   = (d.get('product_code') or '').strip()
    if not code:
        return jsonify({'success': False, 'message': 'product_code 는 필수입니다.'}), 400
    try:
        pg.insert('d_product_mst', {
            'subsdr_name':             subsdr,
            'product_code':            code,
            'product_group_code':      (d.get('product_group_code')    or '').strip() or None,
            'product_category_code':   (d.get('product_category_code') or '').strip() or None,
            'input_user_id':           session.get('user_id'),
            **_audit(),
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" create_product error:")
        msg = '이미 존재하는 코드입니다.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


@master_bp.route('/product/<code>', methods=['PUT'])
def update_product(code):
    err = require_login() or _require_tab_access('product')
    if err: return err
    d      = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    upd    = {k: (d[k] or '').strip() or None
               for k in ('product_group_code', 'product_category_code')
               if k in d}
    if not upd:
        return jsonify({'success': False, 'message': '변경 항목이 없습니다.'}), 400
    upd.update(_audit())
    try:
        pg.update('d_product_mst', set=upd,
                  where={'subsdr_name': subsdr, 'product_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" update_product error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/product/<code>', methods=['DELETE'])
def delete_product(code):
    err = require_login() or _require_tab_access('product')
    if err: return err
    subsdr = _subsdr()
    try:
        pg.update('d_product_mst',
                  set={'delete_flag': 'Y', **_audit()},
                  where={'subsdr_name': subsdr, 'product_code': code})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" delete_product error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/product/bulk-save', methods=['POST'])
def bulk_save_product():
    err = require_login() or _require_tab_access('product') or _require_edit_access('product')
    if err: return err
    body   = request.get_json(silent=True) or {}
    subsdr = _subsdr()
    rows   = body.get('rows', [])
    if not rows:
        return jsonify({'success': False, 'message': '저장할 행이 없습니다.'}), 400
    try:
        result = _bulk_save(
            table      = 'd_product_mst',
            pk_cols    = ['subsdr_name', 'product_code'],
            data_cols  = ['product_group_code', 'product_category_code'],
            rows       = rows,
            subsdr     = subsdr,
        )
        return jsonify(result)
    except Exception as e:
        logger.exception(f" bulk_save_product error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# 4. Sales Target  (subsdr_name + base_ym + product_group_code + billto_biz_name)
# ══════════════════════════════════════════════════════════════

@master_bp.route('/sales-target/currencies', methods=['GET'])
def get_sales_target_currencies():
    """법인별 통화 목록 (d_subsdr_mst.currency_list 첫 번째 값 우선)"""
    err = require_login()
    if err: return err
    subsdr = _subsdr()
    from utils.subsdr_cache import get_currency_list
    currencies = get_currency_list(subsdr) or ['USD']
    return jsonify({'success': True, 'data': currencies})


@master_bp.route('/sales-target/biz-names', methods=['GET'])
def get_sales_target_biz_names():
    """Biz Name 목록 (d_billto_biz_mst 기준 — 피벗 행 사전 채우기용)"""
    err = require_login()
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT DISTINCT billto_biz_name"
            "  FROM d_billto_biz_mst"
            " WHERE subsdr_name = %s"
            "   AND billto_biz_name IS NOT NULL AND billto_biz_name <> ''"
            " ORDER BY billto_biz_name",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': [r['billto_biz_name'] for r in rows]})
    except Exception as e:
        logger.exception(f" get_sales_target_biz_names error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/sales-target/divisions', methods=['GET'])
def get_sales_target_divisions():
    """product_group_code 목록 (d_product_mst 기준)"""
    err = require_login()
    if err: return err
    try:
        rows = pg.query(
            "SELECT DISTINCT product_group_code"
            "  FROM d_product_mst"
            " WHERE product_group_code IS NOT NULL AND product_group_code <> ''"
            " ORDER BY product_group_code"
        )
        return jsonify({'success': True, 'data': [r['product_group_code'] for r in rows]})
    except Exception as e:
        logger.exception(f" get_sales_target_divisions error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/sales-target', methods=['GET'])
def list_sales_target():
    """선택 법인 + 기준년월의 판매목표 플랫 데이터 반환"""
    err = require_login()
    if err: return err
    subsdr  = _subsdr()
    base_ym = request.args.get('base_ym', '')
    if not base_ym:
        from datetime import date
        base_ym = date.today().strftime('%Y%m')
    try:
        rows = pg.query(
            "SELECT product_group_code, billto_biz_name, currency_code,"
            "       CAST(target_amount AS FLOAT) AS target_amount"
            "  FROM d_sales_target_mst"
            " WHERE subsdr_name = %s AND base_ym = %s"
            " ORDER BY billto_biz_name, product_group_code",
            (subsdr, base_ym)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception(f" list_sales_target error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/sales-target/bulk-save', methods=['POST'])
def bulk_save_sales_target():
    """
    피벗 행 [{billto_biz_name, div1, div2, ...}] → 플랫 UPSERT.
    해당 법인+기준년월의 기존 데이터를 삭제 후 재삽입 (replace).
    """
    err = require_login() or _require_edit_access('salesTarget')
    if err: return err
    body          = request.get_json(silent=True) or {}
    subsdr        = _subsdr()
    base_ym       = (body.get('base_ym') or '').strip()
    currency_code = (body.get('currency_code') or 'USD').strip()
    pivot_rows    = body.get('rows', [])
    divs          = body.get('divs', [])

    if not base_ym:
        return jsonify({'success': False, 'message': 'base_ym 은 필수입니다.'}), 400

    # 피벗 → 플랫 변환 (빈 셀 제외)
    prepared = []
    for row in pivot_rows:
        biz = (row.get('billto_biz_name') or '').strip()
        if not biz:
            continue
        for div in divs:
            raw = row.get(div)
            if raw is None or raw == '':
                continue
            try:
                amt = float(raw)
            except (ValueError, TypeError):
                continue
            prepared.append({
                'subsdr_name':        subsdr,
                'base_ym':            base_ym,
                'product_group_code': div,
                'billto_biz_name':    biz,
                'currency_code':      currency_code,
                'target_amount':      amt,
            })

    try:
        # 해당 법인+기준년월 전체 삭제 후 재삽입
        with pg.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM d_sales_target_mst"
                    " WHERE subsdr_name = %s AND base_ym = %s",
                    (subsdr, base_ym)
                )
                if prepared:
                    import psycopg2.extras
                    cols    = list(prepared[0].keys())
                    col_str = ', '.join(f'"{c}"' for c in cols)
                    q       = f'INSERT INTO d_sales_target_mst ({col_str}) VALUES %s'
                    values  = [[r[c] for c in cols] for r in prepared]
                    psycopg2.extras.execute_values(cur, q, values)
        return jsonify({'success': True, 'saved': len(prepared)})
    except Exception as e:
        logger.exception(f" bulk_save_sales_target error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# 5. Sales Team  (subsdr_name + division_name + billto_biz_name)
# ══════════════════════════════════════════════════════════════

@master_bp.route('/sales-team', methods=['GET'])
def list_sales_team():
    """법인별 Sales Team 플랫 데이터 반환 (biz × division → team_name)"""
    err = require_login()
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT division_name, billto_biz_name, team_name"
            "  FROM d_sales_team_mst"
            " WHERE subsdr_name = %s"
            " ORDER BY billto_biz_name, division_name",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception(f" list_sales_team error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/sales-team/bulk-save', methods=['POST'])
def bulk_save_sales_team():
    """
    피벗 행 [{billto_biz_name, div1, div2, ...}] → 플랫 UPSERT.
    해당 법인의 기존 데이터를 삭제 후 재삽입 (replace).
    """
    err = require_login() or _require_edit_access('salesTeam')
    if err: return err
    body       = request.get_json(silent=True) or {}
    subsdr     = _subsdr()
    pivot_rows = body.get('rows', [])
    divs       = body.get('divs', [])

    # 피벗 → 플랫 변환 (team_name 이 null 인 셀도 포함 — 빈값 허용)
    prepared = []
    for row in pivot_rows:
        biz = (row.get('billto_biz_name') or '').strip()
        if not biz:
            continue
        for div in divs:
            team = (row.get(div) or '').strip() or None
            prepared.append({
                'subsdr_name':     subsdr,
                'division_name':   div,
                'billto_biz_name': biz,
                'team_name':       team,
            })

    try:
        # 해당 법인 전체 삭제 후 재삽입
        with pg.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM d_sales_team_mst WHERE subsdr_name = %s",
                    (subsdr,)
                )
                if prepared:
                    import psycopg2.extras
                    cols    = list(prepared[0].keys())
                    col_str = ', '.join(f'"{c}"' for c in cols)
                    q       = f'INSERT INTO d_sales_team_mst ({col_str}) VALUES %s'
                    values  = [[r[c] for c in cols] for r in prepared]
                    psycopg2.extras.execute_values(cur, q, values)
        return jsonify({'success': True, 'saved': len(prepared)})
    except Exception as e:
        logger.exception(f" bulk_save_sales_team error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ══════════════════════════════════════════════════════════════
# 6. Bill-To Biz  (subsdr_name + billto_code + product_group_code)
#    피벗: billto_code(행) × product_group_code(열)
#          → 셀당 billto_biz_name / team_name 2개 값
# ══════════════════════════════════════════════════════════════

@master_bp.route('/billto-biz/product-groups', methods=['GET'])
def get_billto_biz_product_groups():
    """열 레이블용 product_group_code 목록 (d_product_mst 기준)"""
    err = require_login()
    if err: return err
    try:
        rows = pg.query(
            "SELECT DISTINCT product_group_code"
            "  FROM d_product_mst"
            " WHERE product_group_code IS NOT NULL AND product_group_code <> ''"
            " ORDER BY product_group_code"
        )
        return jsonify({'success': True, 'data': [r['product_group_code'] for r in rows]})
    except Exception as e:
        logger.exception(f" get_billto_biz_product_groups error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/billto-biz/billto-list', methods=['GET'])
def get_billto_biz_billto_list():
    """행 레이블용 billto_code + billto_name 목록 (d_billto_mst 기준)"""
    err = require_login()
    if err: return err
    subsdr = _subsdr()
    if not subsdr or subsdr == 'ALL':
        return jsonify({'success': True, 'data': []})
    try:
        rows = pg.query(
            "SELECT billto_code, billto_name"
            "  FROM d_billto_mst"
            " WHERE subsdr_name = %s"
            "   AND delete_flag = 'N'"
            " ORDER BY billto_code",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception(f" get_billto_biz_billto_list error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/billto-biz', methods=['GET'])
def list_billto_biz():
    """법인별 Bill-To Biz 플랫 데이터 반환 (billto_code × product_group → biz/team)"""
    err = require_login()
    if err: return err
    subsdr = _subsdr()
    try:
        rows = pg.query(
            "SELECT billto_code, product_group_code, billto_biz_name, team_name"
            "  FROM d_billto_biz_mst"
            " WHERE subsdr_name = %s"
            " ORDER BY billto_code, product_group_code",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception(f" list_billto_biz error:")
        return jsonify({'success': False, 'message': str(e)}), 500


@master_bp.route('/billto-biz/bulk-save', methods=['POST'])
def bulk_save_billto_biz():
    """
    피벗 행 [{billto_code, <pg>__biz, <pg>__team, ...}] → 플랫 변환 후
    해당 법인의 기존 데이터를 전체 삭제 후 재삽입 (replace).
    billto_biz_name / team_name 둘 다 입력된 셀만 저장 (둘 다 NOT NULL).
    """
    err = require_login() or _require_edit_access('billtoBiz')
    if err: return err
    body       = request.get_json(silent=True) or {}
    subsdr     = _subsdr()
    pivot_rows = body.get('rows', [])
    pgs        = body.get('pgs', [])
    now        = datetime.now()
    user_id    = session.get('user_id', 'system')

    # 피벗 → 플랫 변환 (biz/team 둘 다 값이 있는 셀만)
    prepared = []
    for row in pivot_rows:
        code = (row.get('billto_code') or '').strip()
        if not code:
            continue
        for pg_code in pgs:
            biz  = (row.get(f'{pg_code}__biz')  or '').strip()
            team = (row.get(f'{pg_code}__team') or '').strip()
            if not biz or not team:
                continue
            prepared.append({
                'subsdr_name':        subsdr,
                'billto_code':        code,
                'product_group_code': pg_code,
                'billto_biz_name':    biz,
                'team_name':          team,
                'input_dt':           now,
                'input_user_id':      user_id,
                'update_dt':          now,
                'update_user_id':     user_id,
            })

    try:
        # 해당 법인 전체 삭제 후 재삽입
        with pg.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM d_billto_biz_mst WHERE subsdr_name = %s",
                    (subsdr,)
                )
                if prepared:
                    import psycopg2.extras
                    cols    = list(prepared[0].keys())
                    col_str = ', '.join(f'"{c}"' for c in cols)
                    q       = f'INSERT INTO d_billto_biz_mst ({col_str}) VALUES %s'
                    values  = [[r[c] for c in cols] for r in prepared]
                    psycopg2.extras.execute_values(cur, q, values)
        return jsonify({'success': True, 'saved': len(prepared)})
    except Exception as e:
        logger.exception(f" bulk_save_billto_biz error:")
        return jsonify({'success': False, 'message': str(e)}), 500
