"""
apis/api_auth.py — 인증 API
  POST /api/auth/login                  — 로그인
  POST /api/auth/logout                 — 로그아웃
  GET  /api/auth/me                     — 현재 세션 사용자 정보
  PUT  /api/auth/preferences            — 본인 알림 설정 변경 (container_mail_yn 등)
  POST /api/auth/register/send-code     — 회원가입 이메일 인증코드 발송
  POST /api/auth/register               — 회원가입
"""
import logging
import random
import time
from datetime import datetime, timezone as dt_timezone
from flask import Blueprint, request, jsonify, session
from utils.pg_db import pg
from utils.subsdr_cache import reload_subsdr_list, get_accessible_subsdrs
from utils.mailer import send_email, smtp_configured

# ── 이메일 인증 코드 임시 저장소 ─────────────────────────────────────
# { email: { 'code': '123456', 'expires': unix_timestamp, 'user_id': ..., ... } }
_reg_pending: dict = {}
_CODE_TTL = 600  # 10분

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

MAX_FAIL = 5   # 연속 실패 허용 횟수


def _normalize_biz_group_list(val):
    """biz_group_list 를 jsonb 저장용 값으로 정규화.
      - None / [] / '' → None (관리 안 함)
      - ['ALL'] (대소문자 무관) → ['ALL'] (전체)
      - 그 외 → 문자열 리스트 (공백 제거, 중복 제거, 순서 유지)
    반환: psycopg2 Json 어댑터 또는 None
    """
    import json as _json
    from psycopg2.extras import Json as PgJson
    if val is None:
        return None
    if isinstance(val, str):
        try:
            val = _json.loads(val)
        except Exception:
            val = [val]
    if not isinstance(val, (list, tuple)):
        return None
    items = [str(x).strip() for x in val if str(x).strip()]
    if not items:
        return None
    if any(x.upper() == 'ALL' for x in items):
        return PgJson(['ALL'])
    items = list(dict.fromkeys(items))
    return PgJson(items)


# Font Awesome 아이콘 폴백 매핑 (DB에 icon_class 없는 경우 대비)
_ICON_FALLBACK = {
    'active-orders': 'fa-list-check',
    'active-po':     'fa-ship',
    'inventory':     'fa-boxes-stacked',
    'order':         'fa-file-alt',
    'master-data':   'fa-database',
}


def _parse_allowed_menus(allowed_menus) -> dict | None:
    """
    DB에서 읽은 allowed_menus(다양한 형식)를 내부 lookup dict로 정규화.

    반환: None → 전체 허용 (admin)
          dict → {
            "menu_id": {
              "edit": bool,
              "pages": None | [page_id, ...],
              "page_edits": {page_id: bool}   # 페이지별 편집 권한
            }
          }

    지원 형식:
      None                  → 전체 허용
      list of dict (신규)   → [{"id": "menu_id", "edit": bool,
                                "pages": [{"id": "page_id", "edit": bool}]}]
      list of str (구버전)  → ["menu_id", ...] (edit=True, pages=None)
      dict (구버전)         → {"menu_id": null | ["page_id", ...]} (edit=True)
    """
    if allowed_menus is None:
        return None

    result = {}
    if isinstance(allowed_menus, list):
        for item in allowed_menus:
            if isinstance(item, dict):
                mid = item.get('id')
                if not mid:
                    continue
                pages_raw  = item.get('pages')
                # pages: 접근 허용된 page_id 목록 (None=전체)
                # page_edits: {page_id: edit bool}
                pages      = None
                page_edits = {}
                if isinstance(pages_raw, list):
                    pages = []
                    for p in pages_raw:
                        if isinstance(p, dict) and p.get('id'):
                            pages.append(p['id'])
                            page_edits[p['id']] = bool(p.get('edit', False))
                    if not pages:
                        pages = None
                # 메뉴 자체의 edit: pages가 없으면 item.edit, 있으면 페이지별로 판단
                menu_edit = bool(item.get('edit', False))
                result[mid] = {'edit': menu_edit, 'pages': pages, 'page_edits': page_edits}
            elif isinstance(item, str):
                # 구버전 호환: ["menu_id", ...]
                result[item] = {'edit': True, 'pages': None, 'page_edits': {}}
    elif isinstance(allowed_menus, dict):
        # 구버전 호환: {"menu_id": null | ["page_id", ...]}
        for mid, pages in allowed_menus.items():
            result[mid] = {
                'edit': True,
                'pages': pages if isinstance(pages, list) else None,
                'page_edits': {},
            }

    return result


def _load_nav_menus(allowed_menus) -> list:
    """
    d_menu_mst 에서 사용자 권한에 맞는 메뉴 목록 반환.

    allowed_menus 형식 (신규):
      None                  → 전체 허용 (admin)
      list of dict          → [{"id": "menu_id", "edit": bool,
                                "pages": [{"id": "page_id", "edit": bool}]}]
                              pages 없음 = 해당 메뉴 전체 서브페이지 허용

    반환: [{menu_id, menu_name, menu_url, icon_class, allowed_pages, edit}]
      allowed_pages : None = 전체, list[str] = 허용된 page_id 목록
      edit          : bool = 편집 권한 여부 (admin은 항상 True)
    """
    allowed_dict = _parse_allowed_menus(allowed_menus)  # None or {mid: {edit, pages}}

    try:
        rows = pg.query(
            "SELECT menu_id, menu_name, menu_url, icon_class, sort_order"
            " FROM d_menu_mst"
            " WHERE page_id='_' AND use_yn='Y' AND delete_flag='N'"
            " ORDER BY sort_order"
        )
        menus = []
        for r in rows:
            mid = r['menu_id']
            # allowed_dict = None → 전체(admin), dict → 허용 목록에 있는 것만
            if allowed_dict is not None and mid not in allowed_dict:
                continue
            info          = allowed_dict[mid] if allowed_dict is not None else None
            allowed_pages = info['pages']      if info else None   # None = 전체 허용
            edit          = info['edit']       if info else True   # admin = 항상 편집 허용
            page_edits    = info['page_edits'] if info else {}     # {page_id: bool}
            menus.append({
                'menu_id':       mid,
                'menu_name':     r['menu_name'] or mid,
                'menu_url':      r['menu_url']  or f'/{mid}',
                'icon_class':    r.get('icon_class') or _ICON_FALLBACK.get(mid, 'fa-circle'),
                'allowed_pages': allowed_pages,
                'edit':          edit,
                'page_edits':    page_edits,   # 페이지별 편집 권한 {page_id: bool}
            })
        return menus
    except Exception as e:
        logger.warning(f"_load_nav_menus error: {e}")
        # DB 오류 시 폴백: 전체 메뉴 하드코딩
        default = [
            {'menu_id': 'active-orders', 'menu_name': 'Active Orders',  'menu_url': '/active-orders', 'icon_class': 'fa-list-check',    'allowed_pages': None, 'edit': True, 'page_edits': {}},
            {'menu_id': 'active-po',     'menu_name': 'Active PO',       'menu_url': '/active-po',     'icon_class': 'fa-ship',          'allowed_pages': None, 'edit': True, 'page_edits': {}},
            {'menu_id': 'inventory',     'menu_name': 'Inventory',        'menu_url': '/inventory',     'icon_class': 'fa-boxes-stacked', 'allowed_pages': None, 'edit': True, 'page_edits': {}},
            {'menu_id': 'order',         'menu_name': 'Order Analysis',   'menu_url': '/order',         'icon_class': 'fa-file-alt',      'allowed_pages': None, 'edit': True, 'page_edits': {}},
            {'menu_id': 'master-data',   'menu_name': 'Master Data',      'menu_url': '/master-data',   'icon_class': 'fa-database',      'allowed_pages': None, 'edit': True, 'page_edits': {}},
        ]
        if allowed_dict is None:
            return default
        return [
            {**m, 'edit': allowed_dict[m['menu_id']]['edit'], 'page_edits': allowed_dict[m['menu_id']]['page_edits']}
            for m in default if m['menu_id'] in allowed_dict
        ]


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        import bcrypt
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.warning(f"bcrypt verify error: {e}")
        return False


@auth_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    user_id  = (data.get('user_id')  or '').strip()
    password = (data.get('password') or '').strip()
    # 브라우저 localStorage 에 저장된 마지막 선택 법인 (선택적)
    pref_entity = (data.get('legal_entity') or '').strip()

    if not user_id:
        return jsonify({'success': False, 'message': 'Please enter user_id.'}), 400

    # ── 사용자 조회 ───────────────────────────────────────────────────
    try:
        rows = pg.query(
            """
            SELECT subsdr_name, user_id, user_name, user_password,
                   email, user_type, login_fail_cnt, lock_yn,
                   container_mail_yn, container_yard_mail_yn, hold_order_mail_yn
              FROM d_user_mst
             WHERE user_id = %s AND delete_flag = 'N'
             LIMIT 1
            """,
            (user_id,)
        )
    except Exception as e:
        logger.exception(f"❌ login DB error:")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    if not rows:
        return jsonify({'success': False, 'message': 'Invalid user ID or password.'}), 401

    user = rows[0]

    # ── 계정 잠금 확인 ────────────────────────────────────────────────
    if user['lock_yn'] == 'Y':
        return jsonify({'success': False, 'message': 'Account is locked. Please contact administrator.'}), 403

    # ── 비밀번호 확인 ────────────────────────────────────────────────
    pwd_hash  = (user.get('user_password') or '').strip()
    skip_pwd  = not pwd_hash or pwd_hash == '_'

    # 패스워드가 미설정된 사용자 → 패스워드 설정 요청
    if skip_pwd:
        return jsonify({
            'success':          False,
            'need_set_password': True,
            'message':          'No password set. Please set your password to continue.',
        }), 200

    if not password:
        return jsonify({'success': False, 'message': 'Please enter password.'}), 400

    if not _verify_password(password, pwd_hash):
        new_fail = (user['login_fail_cnt'] or 0) + 1
        lock_yn  = 'Y' if new_fail >= MAX_FAIL else 'N'
        try:
            pg.execute(
                "UPDATE d_user_mst SET login_fail_cnt=%s, lock_yn=%s, update_dt=CURRENT_TIMESTAMP"
                " WHERE subsdr_name=%s AND user_id=%s",
                (new_fail, lock_yn, user['subsdr_name'], user['user_id'])
            )
        except Exception:
            pass
        msg = (
            f'Incorrect password. ({new_fail}/{MAX_FAIL} failed attempts)'
            if lock_yn == 'N'
            else f'Account locked after {MAX_FAIL} failed login attempts. Please contact administrator.'
        )
        return jsonify({'success': False, 'message': msg}), 401

    # ── 권한 정보 + 메뉴 목록 조회 ──────────────────────────────────────
    try:
        type_rows     = pg.query(
            "SELECT allowed_menus FROM v_user_type_mst WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
            (user['subsdr_name'], user['user_type'])
        )
        allowed_menus = type_rows[0]['allowed_menus'] if type_rows else None
    except Exception:
        allowed_menus = None

    # d_menu_mst 에서 허용된 메뉴 목록 조회 (sort_order 순)
    nav_menus = _load_nav_menus(allowed_menus)

    # 로그인 시 법인 캐시를 갱신한 뒤 접근 가능 법인 목록 계산 → 세션 저장
    # (앱 기동 후 DB 변경이 있어도 로그인 시점에 항상 최신 데이터를 반영)
    reload_subsdr_list()
    accessible_subsdr = get_accessible_subsdrs(user['subsdr_name'])

    # ── 브라우저에 저장된 선택 법인(localStorage) 반영 ──────────────────
    # 사용자가 마지막에 보던 법인이 접근 가능하고 사용자 홈 법인과 다르면,
    # 그 법인 기준 메뉴로 재구성 → 로그인 직후 첫 페이지를 해당 법인 첫 메뉴로 지정.
    # (예: LGEPH 는 /active-orders-ph 가 첫 메뉴 → /active-orders 경유 리다이렉트 방지)
    if pref_entity and pref_entity in accessible_subsdr and pref_entity != user['subsdr_name']:
        try:
            pref_rows = pg.query(
                "SELECT allowed_menus FROM v_user_type_mst"
                " WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
                (pref_entity, user['user_type'])
            )
            if pref_rows:
                allowed_menus = pref_rows[0]['allowed_menus']
                pref_nav = _load_nav_menus(allowed_menus)
                if pref_nav:
                    nav_menus = pref_nav
                    logger.info(f"LOGIN pref legal_entity applied: {pref_entity} (home={nav_menus[0].get('menu_url')})")
        except Exception as e:
            logger.warning(f"login pref legal_entity lookup error: {e}")

    # ── 세션 설정 ─────────────────────────────────────────────────────
    session.permanent = True
    session['user_id']           = user['user_id']
    session['user_name']         = user['user_name']
    session['subsdr_name']       = user['subsdr_name']
    session['user_type']         = user['user_type']
    session['email']             = user.get('email') or ''
    session['allowed_menus']     = allowed_menus        # None = 전체 허용
    session['nav_menus']         = nav_menus            # [{menu_id, menu_name, ...}]
    session['accessible_subsdr'] = accessible_subsdr   # 접근 가능 법인 코드 목록
    session['container_mail_yn'] = user.get('container_mail_yn') or 'N'
    session['container_yard_mail_yn'] = user.get('container_yard_mail_yn') or 'N'
    session['hold_order_mail_yn']     = user.get('hold_order_mail_yn') or 'N'

    # ── 마지막 로그인 갱신 ────────────────────────────────────────────
    try:
        pg.execute(
            "UPDATE d_user_mst"
            " SET last_login_dt=CURRENT_TIMESTAMP, login_fail_cnt=0, lock_yn='N',"
            "     update_dt=CURRENT_TIMESTAMP"
            " WHERE subsdr_name=%s AND user_id=%s",
            (user['subsdr_name'], user['user_id'])
        )
    except Exception as e:
        logger.warning(f"last_login_dt update failed: {e}")

    logger.info(f"LOGIN OK  user={user['user_id']} subsdr={user['subsdr_name']} type={user['user_type']}")
    home_url = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'
    return jsonify({
        'success': True,
        'redirect_url': home_url,
        'user': {
            'user_id':       user['user_id'],
            'user_name':     user['user_name'],
            'subsdr_name':   user['subsdr_name'],
            'user_type':     user['user_type'],
            'allowed_menus': allowed_menus,
        }
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    uid = session.get('user_id', '-')
    session.clear()
    logger.info(f"LOGOUT: {uid}")
    return jsonify({'success': True})


@auth_bp.route('/me', methods=['GET'])
def me():
    if not session.get('user_id'):
        return jsonify({'success': False, 'authenticated': False}), 401
    # biz_group_list 는 세션에 없으므로 DB 에서 조회 (None=관리 안 함)
    biz_group_list = None
    try:
        rows = pg.query(
            "SELECT biz_group_list FROM d_user_mst"
            " WHERE subsdr_name = %s AND user_id = %s",
            (session.get('subsdr_name'), session.get('user_id'))
        )
        if rows:
            biz_group_list = rows[0].get('biz_group_list')
    except Exception:
        logger.exception('me() biz_group_list lookup error:')
    return jsonify({
        'success':       True,
        'authenticated': True,
        'user': {
            'user_id':            session.get('user_id'),
            'user_name':          session.get('user_name'),
            'subsdr_name':        session.get('subsdr_name'),
            'user_type':          session.get('user_type'),
            'email':              session.get('email', ''),
            'allowed_menus':      session.get('allowed_menus'),
            'container_mail_yn':  session.get('container_mail_yn', 'N'),
            'container_yard_mail_yn': session.get('container_yard_mail_yn', 'N'),
            'hold_order_mail_yn':     session.get('hold_order_mail_yn', 'N'),
            'biz_group_list':     biz_group_list,
        }
    })


@auth_bp.route('/impersonate', methods=['POST'])
def impersonate():
    """
    현재 로그인 계정 유형이 'owner' 인 경우에만,
    대상 사용자 계정으로 세션을 전환(로그인)한다.
    """
    # ── 권한 확인 ─────────────────────────────────────────────────────
    if not session.get('user_id'):
        return jsonify({'success': False, 'authenticated': False}), 401
    if session.get('user_type') != 'owner':
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403

    data       = request.get_json(silent=True) or {}
    target_id  = (data.get('user_id') or '').strip()
    if not target_id:
        return jsonify({'success': False, 'message': 'user_id is required.'}), 400

    origin_id = session.get('user_id')
    if target_id == origin_id:
        return jsonify({'success': False, 'message': 'You are already logged in as this account.'}), 400

    # ── 대상 사용자 조회 ──────────────────────────────────────────────
    try:
        rows = pg.query(
            """
            SELECT subsdr_name, user_id, user_name, email, user_type,
                   lock_yn, container_mail_yn, container_yard_mail_yn, hold_order_mail_yn
              FROM d_user_mst
             WHERE user_id = %s AND delete_flag = 'N'
             LIMIT 1
            """,
            (target_id,)
        )
    except Exception:
        logger.exception("❌ impersonate DB error:")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    if not rows:
        return jsonify({'success': False, 'message': 'Target user not found.'}), 404

    user = rows[0]

    # ── 권한 정보 + 메뉴 목록 조회 ──────────────────────────────────────
    try:
        type_rows     = pg.query(
            "SELECT allowed_menus FROM v_user_type_mst WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
            (user['subsdr_name'], user['user_type'])
        )
        allowed_menus = type_rows[0]['allowed_menus'] if type_rows else None
    except Exception:
        allowed_menus = None

    nav_menus = _load_nav_menus(allowed_menus)
    reload_subsdr_list()
    accessible_subsdr = get_accessible_subsdrs(user['subsdr_name'])

    # ── 세션 전환 ─────────────────────────────────────────────────────
    session.permanent = True
    session['user_id']           = user['user_id']
    session['user_name']         = user['user_name']
    session['subsdr_name']       = user['subsdr_name']
    session['user_type']         = user['user_type']
    session['email']             = user.get('email') or ''
    session['allowed_menus']     = allowed_menus
    session['nav_menus']         = nav_menus
    session['accessible_subsdr'] = accessible_subsdr
    session['container_mail_yn'] = user.get('container_mail_yn') or 'N'
    session['container_yard_mail_yn'] = user.get('container_yard_mail_yn') or 'N'
    session['hold_order_mail_yn']     = user.get('hold_order_mail_yn') or 'N'

    logger.info(f"IMPERSONATE: {origin_id} (owner) -> {user['user_id']} ({user['user_type']})")
    home_url = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'
    return jsonify({
        'success': True,
        'redirect_url': home_url,
        'user': {
            'user_id':     user['user_id'],
            'user_name':   user['user_name'],
            'subsdr_name': user['subsdr_name'],
            'user_type':   user['user_type'],
        }
    })


@auth_bp.route('/nav-menus', methods=['POST'])
def nav_menus_for_entity():
    """
    상단 법인 셀렉터에서 선택한 법인(legal_entity) 기준으로
    v_user_type_mst 에서 해당 법인의 allowed_menus 를 조회해
    nav_menus 를 재구성하고 세션에 반영한 뒤 반환한다.

    - 법인별 개별 정의가 있으면 그 정의, 없으면 '[ALL]' 공통 정의가
      v_user_type_mst 에서 자동 확장되어 조회된다.
    """
    if not session.get('user_id'):
        return jsonify({'success': False, 'authenticated': False}), 401

    data          = request.get_json(silent=True) or {}
    legal_entity  = (data.get('legal_entity') or '').strip()
    user_type     = session.get('user_type')

    if not legal_entity:
        # 법인 미지정 시 세션 법인 기준
        legal_entity = session.get('subsdr_name')

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
        logger.warning(f"nav-menus lookup error: {e}")

    nav_menus = _load_nav_menus(allowed_menus)

    # 세션 반영 → 이후 페이지 이동/서버 렌더링에도 선택 법인 기준 메뉴 유지
    session['allowed_menus'] = allowed_menus
    session['nav_menus']     = nav_menus

    return jsonify({'success': True, 'legal_entity': legal_entity, 'nav_menus': nav_menus})


@auth_bp.route('/set-initial-password', methods=['POST'])
def set_initial_password():
    """패스워드 미설정 사용자의 최초 패스워드 설정 후 자동 로그인"""
    data     = request.get_json(silent=True) or {}
    user_id  = (data.get('user_id')      or '').strip()
    new_pwd  = (data.get('new_password') or '').strip()

    if not user_id or not new_pwd:
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400
    if len(new_pwd) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400

    try:
        rows = pg.query(
            """
            SELECT subsdr_name, user_id, user_name, user_password,
                   email, user_type, lock_yn,
                   container_mail_yn, container_yard_mail_yn, hold_order_mail_yn
              FROM d_user_mst
             WHERE user_id = %s AND delete_flag = 'N'
             LIMIT 1
            """,
            (user_id,)
        )
    except Exception as e:
        logger.exception("set_initial_password DB error:")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    if not rows:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    user     = rows[0]
    pwd_hash = (user.get('user_password') or '').strip()
    if pwd_hash and pwd_hash != '_':
        return jsonify({'success': False, 'message': 'Password is already set. Please login normally.'}), 400

    if user['lock_yn'] == 'Y':
        return jsonify({'success': False, 'message': 'Account is locked. Please contact administrator.'}), 403

    import bcrypt
    new_hash = bcrypt.hashpw(new_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        pg.execute(
            "UPDATE d_user_mst SET user_password=%s, login_fail_cnt=0, lock_yn='N',"
            " update_dt=CURRENT_TIMESTAMP WHERE subsdr_name=%s AND user_id=%s",
            (new_hash, user['subsdr_name'], user['user_id'])
        )
    except Exception as e:
        logger.exception("set_initial_password update error:")
        return jsonify({'success': False, 'message': 'Failed to set password.'}), 500

    # 패스워드 설정 후 자동 로그인
    try:
        type_rows     = pg.query(
            "SELECT allowed_menus FROM v_user_type_mst WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
            (user['subsdr_name'], user['user_type'])
        )
        allowed_menus = type_rows[0]['allowed_menus'] if type_rows else None
    except Exception:
        allowed_menus = None

    nav_menus = _load_nav_menus(allowed_menus)
    reload_subsdr_list()
    accessible_subsdr = get_accessible_subsdrs(user['subsdr_name'])

    session.permanent = True
    session['user_id']           = user['user_id']
    session['user_name']         = user['user_name']
    session['subsdr_name']       = user['subsdr_name']
    session['user_type']         = user['user_type']
    session['email']             = user.get('email') or ''
    session['allowed_menus']     = allowed_menus
    session['nav_menus']         = nav_menus
    session['accessible_subsdr'] = accessible_subsdr
    session['container_mail_yn'] = user.get('container_mail_yn') or 'N'
    session['container_yard_mail_yn'] = user.get('container_yard_mail_yn') or 'N'
    session['hold_order_mail_yn']     = user.get('hold_order_mail_yn') or 'N'

    try:
        pg.execute(
            "UPDATE d_user_mst SET last_login_dt=CURRENT_TIMESTAMP, login_fail_cnt=0,"
            " lock_yn='N', update_dt=CURRENT_TIMESTAMP WHERE subsdr_name=%s AND user_id=%s",
            (user['subsdr_name'], user['user_id'])
        )
    except Exception:
        pass

    logger.info(f"INITIAL PASSWORD SET & LOGIN: {user['user_id']}")
    home_url = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'
    return jsonify({'success': True, 'redirect_url': home_url})


@auth_bp.route('/preferences', methods=['PUT'])
def update_preferences():
    """로그인 사용자 본인의 알림 설정 변경 (container_mail_yn / container_yard_mail_yn / hold_order_mail_yn 등)"""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required.'}), 401

    data = request.get_json(silent=True) or {}

    # 변경 요청된 알림 설정 컬럼만 수집 (Y/N 검증)
    pref_keys = ('container_mail_yn', 'container_yard_mail_yn', 'hold_order_mail_yn')
    set_data: dict = {}
    for key in pref_keys:
        if key in data:
            val = (data.get(key) or '').strip().upper()
            if val not in ('Y', 'N'):
                return jsonify({'success': False, 'message': f'{key} 은 Y 또는 N 이어야 합니다.'}), 400
            set_data[key] = val

    # Biz Group 목록 (JSONB) — None=관리 안 함, ["ALL"]=전체, [...]=개별
    if 'biz_group_list' in data:
        set_data['biz_group_list'] = _normalize_biz_group_list(data.get('biz_group_list'))

    if not set_data:
        return jsonify({'success': False, 'message': '변경할 항목이 없습니다.'}), 400

    user_id    = session.get('user_id')
    try:
        set_data['update_dt']      = datetime.now(tz=dt_timezone.utc)
        set_data['update_user_id'] = user_id
        pg.update('d_user_mst', set=set_data, where={'user_id': user_id})
        # 세션 갱신
        for key in pref_keys:
            if key in set_data:
                session[key] = set_data[key]
        logger.info(f"PREF UPDATE {({k: set_data[k] for k in pref_keys if k in set_data})} user={user_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception('update_preferences error:')
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/biz-groups', methods=['GET'])
def my_biz_groups():
    """로그인 사용자 본인 법인의 Biz Group 목록 (My Info 다중 선택용)."""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required.'}), 401
    subsdr = session.get('subsdr_name')
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
        logger.exception('my_biz_groups error:')
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """Change password for the logged-in user (regardless of permissions)"""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required.'}), 401

    data     = request.get_json(silent=True) or {}
    new_pwd  = (data.get('new_password') or '').strip()
    if not new_pwd:
        return jsonify({'success': False, 'message': 'Please enter new password.'}), 400
    if len(new_pwd) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400

    import bcrypt
    pwd_hash = bcrypt.hashpw(new_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        pg.execute(
            "UPDATE d_user_mst SET user_password=%s, login_fail_cnt=0, lock_yn='N',"
            " update_dt=CURRENT_TIMESTAMP, update_user_id=%s"
            " WHERE subsdr_name=%s AND user_id=%s",
            (pwd_hash, session['user_id'], session['subsdr_name'], session['user_id'])
        )
        logger.info(f"PASSWORD CHANGED: {session['user_id']}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"❌ change_password error:")
        return jsonify({'success': False, 'message': 'Failed to change password.'}), 500


# ══════════════════════════════════════════════════════════════════════
# 비밀번호 재설정 (잠금 해제 포함) — 이메일 인증코드 발송
# ══════════════════════════════════════════════════════════════════════

# 비밀번호 재설정 임시 저장소 { email: { code, expires, user_id, subsdr_name } }
_reset_pending: dict = {}

@auth_bp.route('/reset-password/send-code', methods=['POST'])
def reset_password_send_code():
    """
    비밀번호 재설정용 이메일 인증코드 발송.
    요청: { user_id }  — User ID로 이메일 자동 조회 후 발송
    """
    data    = request.get_json(silent=True) or {}
    user_id = (data.get('user_id') or '').strip()

    if not user_id:
        return jsonify({'success': False, 'message': 'Please enter your User ID.'}), 400

    # 사용자 조회 (잠금/삭제 무관하게 존재하는 계정)
    try:
        rows = pg.query(
            "SELECT subsdr_name, user_id, email FROM d_user_mst"
            " WHERE user_id=%s AND delete_flag='N' LIMIT 1",
            (user_id,)
        )
    except Exception as e:
        logger.exception("reset_password_send_code DB error:")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    if not rows:
        return jsonify({'success': False, 'message': 'User ID not found.'}), 404

    user  = rows[0]
    email = (user.get('email') or '').strip()
    if not email:
        return jsonify({'success': False, 'message': 'No email address is registered for this account. Please contact administrator.'}), 400

    if not smtp_configured():
        return jsonify({'success': False, 'message': 'SMTP is not configured. Cannot send email.'}), 500

    code = f"{random.randint(0, 999999):06d}"
    _reset_pending[user_id] = {
        'code':        code,
        'expires':     time.time() + _CODE_TTL,
        'user_id':     user['user_id'],
        'subsdr_name': user['subsdr_name'],
        'email':       email,
    }

    shown = email

    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2 style="color:#c5002e;">LIW Password Reset</h2>
      <p>A password reset was requested for account <strong>{user_id}</strong>.</p>
      <p>Enter the verification code below to reset your password.</p>
      <div style="font-size:2rem;font-weight:700;letter-spacing:0.3em;
                  padding:1rem 2rem;background:#f4f4f4;border-radius:8px;
                  text-align:center;color:#111;margin:1rem 0;">
        {code}
      </div>
      <p style="color:#666;font-size:0.85rem;">This code expires in <strong>10 minutes</strong>.<br>
      If you did not request this, please ignore this email.</p>
    </div>
    """
    try:
        send_email(
            to_addrs=email,
            subject='[LIW] Password Reset Verification Code',
            html_body=html_body,
        )
        logger.info(f"RESET-PWD send-code to {email} (user_id={user_id})")
    except Exception as e:
        logger.exception("reset_password_send_code mail error:")
        return jsonify({'success': False, 'message': f'Failed to send email: {e}'}), 500

    return jsonify({'success': True, 'message': f'A verification code has been sent to {shown}.', 'email_hint': shown})


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    인증코드 검증 후 비밀번호 재설정 + 잠금 해제.
    요청: { user_id, code, new_password }
    """
    data        = request.get_json(silent=True) or {}
    user_id     = (data.get('user_id')      or '').strip()
    code        = (data.get('code')         or '').strip()
    new_pwd     = (data.get('new_password') or '').strip()

    if not all([user_id, code, new_pwd]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    if len(new_pwd) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400

    pending = _reset_pending.get(user_id)
    if not pending:
        return jsonify({'success': False, 'message': 'No verification code found. Please request a new one.'}), 400
    if time.time() > pending['expires']:
        _reset_pending.pop(user_id, None)
        return jsonify({'success': False, 'message': 'Verification code has expired. Please request a new one.'}), 400
    if pending['code'] != code:
        return jsonify({'success': False, 'message': 'Incorrect verification code.'}), 400

    import bcrypt
    pwd_hash = bcrypt.hashpw(new_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        pg.execute(
            "UPDATE d_user_mst SET user_password=%s, login_fail_cnt=0, lock_yn='N',"
            " update_dt=CURRENT_TIMESTAMP"
            " WHERE subsdr_name=%s AND user_id=%s",
            (pwd_hash, pending['subsdr_name'], user_id)
        )
    except Exception as e:
        logger.exception("reset_password update error:")
        return jsonify({'success': False, 'message': 'Failed to reset password.'}), 500

    _reset_pending.pop(user_id, None)
    logger.info(f"RESET-PWD OK  user_id={user_id} subsdr={pending['subsdr_name']}")
    return jsonify({'success': True, 'message': 'Password has been reset. Please sign in with your new password.'})


# ══════════════════════════════════════════════════════════════════════
# 회원가입 — 이메일 인증코드 발송
# ══════════════════════════════════════════════════════════════════════
@auth_bp.route('/register/send-code', methods=['POST'])
def register_send_code():
    """
    회원가입용 이메일 인증코드 발송.
    요청: { user_id, user_name, email, password, subsdr_name }
    """
    data        = request.get_json(silent=True) or {}
    user_id     = (data.get('user_id')     or '').strip()
    user_name   = (data.get('user_name')   or '').strip()
    email       = (data.get('email')       or '').strip().lower()
    password    = (data.get('password')    or '').strip()
    subsdr_name = (data.get('subsdr_name') or '').strip()

    # ── 입력 검증 ─────────────────────────────────────────────────────
    if not all([user_id, user_name, email, password, subsdr_name]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    if subsdr_name != 'LGEPH':
        return jsonify({'success': False, 'message': 'Registration is only available for LGEPH.'}), 400
    if len(password) < 4:
        return jsonify({'success': False, 'message': 'Password must be at least 4 characters.'}), 400
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'}), 400

    # ── 중복 User ID / Email 확인 ─────────────────────────────────────
    try:
        dup_id = pg.query(
            "SELECT 1 FROM d_user_mst WHERE user_id=%s AND delete_flag='N' LIMIT 1",
            (user_id,)
        )
        if dup_id:
            return jsonify({'success': False, 'message': 'User ID is already taken.'}), 409

        dup_email = pg.query(
            "SELECT 1 FROM d_user_mst WHERE email=%s AND delete_flag='N' LIMIT 1",
            (email,)
        )
        if dup_email:
            return jsonify({'success': False, 'message': 'This email is already registered.'}), 409
    except Exception as e:
        logger.exception("register_send_code DB check error:")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    if not smtp_configured():
        return jsonify({'success': False, 'message': 'SMTP is not configured. Cannot send email.'}), 500

    # ── 인증 코드 생성 및 저장 ────────────────────────────────────────
    code = f"{random.randint(0, 999999):06d}"
    _reg_pending[email] = {
        'code':        code,
        'expires':     time.time() + _CODE_TTL,
        'user_id':     user_id,
        'user_name':   user_name,
        'password':    password,
        'subsdr_name': subsdr_name,
    }

    # ── 인증 이메일 발송 ──────────────────────────────────────────────
    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
      <h2 style="color:#c5002e;">LIW Email Verification</h2>
      <p>Hello, <strong>{user_name}</strong>.</p>
      <p>Please enter the verification code below to complete your registration.</p>
      <div style="font-size:2rem;font-weight:700;letter-spacing:0.3em;
                  padding:1rem 2rem;background:#f4f4f4;border-radius:8px;
                  text-align:center;color:#111;margin:1rem 0;">
        {code}
      </div>
      <p style="color:#666;font-size:0.85rem;">This code expires in <strong>10 minutes</strong>.<br>
      If you did not request this, please ignore this email.</p>
    </div>
    """
    try:
        send_email(
            to_addrs=email,
            subject='[LIW] Email Verification Code for Registration',
            html_body=html_body,
        )
        logger.info(f"REGISTER send-code to {email} (user_id={user_id})")
    except Exception as e:
        logger.exception("register_send_code mail error:")
        return jsonify({'success': False, 'message': f'Failed to send email: {e}'}), 500

    return jsonify({'success': True, 'message': f'A verification code has been sent to {email}.'})


# ══════════════════════════════════════════════════════════════════════
# 회원가입 — 코드 확인 후 계정 생성
# ══════════════════════════════════════════════════════════════════════
@auth_bp.route('/register', methods=['POST'])
def register():
    """
    이메일 인증코드 검증 후 계정 생성.
    요청: { email, code }
    """
    data  = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    code  = (data.get('code')  or '').strip()

    if not email or not code:
        return jsonify({'success': False, 'message': 'email과 인증 코드를 입력해주세요.'}), 400

    pending = _reg_pending.get(email)
    if not pending:
        return jsonify({'success': False, 'message': 'No verification code found. Please request a new one.'}), 400
    if time.time() > pending['expires']:
        _reg_pending.pop(email, None)
        return jsonify({'success': False, 'message': 'Verification code has expired. Please request a new one.'}), 400
    if pending['code'] != code:
        return jsonify({'success': False, 'message': 'Incorrect verification code.'}), 400

    # ── 계정 생성 ──────────────────────────────────────────────────────
    import bcrypt
    pwd_hash = bcrypt.hashpw(pending['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        # ── 기존 계정 존재 여부 확인 (delete_flag 무관하게 전체 조회) ──
        existing = pg.query(
            "SELECT subsdr_name, user_id, delete_flag FROM d_user_mst"
            " WHERE user_id=%s LIMIT 1",
            (pending['user_id'],)
        )
        if existing:
            row = existing[0]
            if row['delete_flag'] == 'N':
                # 활성 계정이 이미 존재 → 가입 불가
                _reg_pending.pop(email, None)
                return jsonify({'success': False, 'message': 'User ID is already taken.'}), 409
            else:
                # 삭제된 계정이 존재 → 먼저 물리 삭제 후 신규 인서트
                pg.execute(
                    "DELETE FROM d_user_mst WHERE subsdr_name=%s AND user_id=%s",
                    (row['subsdr_name'], row['user_id'])
                )
                logger.info(f"REGISTER: deleted old record subsdr={row['subsdr_name']} user_id={row['user_id']}")

        pg.execute(
            """
            INSERT INTO d_user_mst
              (subsdr_name, user_id, user_name, user_password, email,
               user_type, lock_yn, delete_flag, login_fail_cnt, input_dt)
            VALUES (%s, %s, %s, %s, %s, 'user', 'N', 'N', 0, CURRENT_TIMESTAMP)
            """,
            (pending['subsdr_name'], pending['user_id'], pending['user_name'],
             pwd_hash, email)
        )
    except Exception as e:
        logger.exception("register DB insert error:")
        return jsonify({'success': False, 'message': 'An error occurred while creating your account.'}), 500

    _reg_pending.pop(email, None)
    logger.info(f"REGISTER OK  user_id={pending['user_id']} email={email} subsdr={pending['subsdr_name']}")
    return jsonify({'success': True, 'message': 'Registration complete. Please sign in.'})
