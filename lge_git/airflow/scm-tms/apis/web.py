"""
Web Routes - HTML 페이지 렌더링
"""
import os
import logging
from flask import Blueprint, render_template, redirect, request, session
from utils.pg_db import pg

logger = logging.getLogger(__name__)

web_bp = Blueprint('web', __name__)

# 로그인 없이도 접근 가능한 경로 (권한 체크 제외)
_PUBLIC_PATHS = {'/login', '/glossary'}


def _norm_path(p: str) -> str:
    """경로 정규화 — 끝 슬래시 제거, 소문자화 없음"""
    if len(p) > 1 and p.endswith('/'):
        p = p.rstrip('/')
    return p


def _all_nav_menu_urls() -> dict:
    """
    d_menu_mst 의 최상위(page_id='_') 메뉴 URL → menu_id 매핑 반환.
    이 목록에 있는 페이지는 '메뉴로 관리되는 페이지'이므로 권한 점검 대상.
    """
    try:
        rows = pg.query(
            "SELECT menu_id, menu_url FROM d_menu_mst"
            " WHERE page_id='_' AND use_yn='Y' AND delete_flag='N'"
        )
        return { _norm_path(r['menu_url'] or f"/{r['menu_id']}"): r['menu_id'] for r in rows }
    except Exception as e:
        logger.warning(f"_all_nav_menu_urls error: {e}")
        return {}


@web_bp.before_request
def _guard_menu_access():
    """
    HTML 페이지 라우트에 대한 메뉴 접근 권한 점검.
    - URL 직접 입력으로 메뉴에 없는 페이지 접근을 차단
    - 세션 nav_menus(선택 법인 기준 허용 메뉴) 에 없는 '메뉴 관리 페이지'면 리다이렉트
    """
    path = _norm_path(request.path)

    # 정적 파일 / API 는 이 블루프린트 밖이지만 방어적으로 스킵
    if path.startswith('/static') or path.startswith('/api'):
        return None

    # 공개 경로 스킵
    if path in _PUBLIC_PATHS or path == '/':
        return None

    # 미로그인 → 로그인 페이지로
    if not session.get('user_id'):
        return redirect('/login?next=' + request.path)

    # 전체 메뉴 URL 매핑 (메뉴로 관리되는 페이지만 점검 대상)
    all_menu_urls = _all_nav_menu_urls()
    menu_id = all_menu_urls.get(path)

    # 메뉴로 관리되지 않는 페이지(서브 분석 페이지 등)는 통과
    if menu_id is None:
        return None

    # 세션의 허용 메뉴(선택 법인 기준) 확인
    allowed_menus = session.get('allowed_menus')

    # None = 전체 허용 (admin)
    if allowed_menus is None:
        return None

    allowed_ids = { m.get('id') for m in allowed_menus if isinstance(m, dict) }
    if menu_id in allowed_ids:
        return None

    # 권한 없음 → 허용된 첫 메뉴로 리다이렉트 (없으면 로그인)
    logger.warning(
        f"❌ Page access denied: user_id={session.get('user_id')}, "
        f"menu_id={menu_id}, path={request.path}, IP={request.remote_addr}"
    )
    nav_menus = session.get('nav_menus') or []
    if nav_menus:
        first_url = nav_menus[0].get('menu_url') or f"/{nav_menus[0].get('menu_id')}"
        return redirect(first_url)
    return redirect('/login')


@web_bp.route('/')
def index():
    # 미로그인 → 로그인 페이지 (next 강제 지정하지 않음: 로그인 후 첫 메뉴로 이동)
    if not session.get('user_id'):
        return redirect('/login')
    nav_menus = session.get('nav_menus') or []
    home_url = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'
    return redirect(home_url)


@web_bp.route('/login')
def login_page():
    """로그인 페이지 — 이미 로그인된 경우 홈으로 이동"""
    if session.get('user_id'):
        nav_menus = session.get('nav_menus') or []
        default_home = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'
        next_url = request.args.get('next') or default_home
        return redirect(next_url)
    return render_template('login.html')


@web_bp.route('/users')
def users_page():
    """사용자 관리 페이지 (관리자 전용)"""
    return render_template('users.html', active_page='users',
                           current_user_type=session.get('user_type'),
                           current_user_id=session.get('user_id'))

@web_bp.route('/master-data')
def master_data_page():
    """마스터 데이터 관리 (Bill-To / Ship-To / Product / Sales Target)"""
    # ── d_menu_mst 에서 master-data 서브페이지(탭) 목록 조회 ──────────
    # page_id='_' 는 최상위 메뉴, 나머지는 탭(서브페이지)
    # 탭 메타데이터는 api_master._TAB_META 에서 단일 관리한다.
    from apis.api_master import _TAB_META, tab_scripts_for, tab_script

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
        # DB 오류 시 기본값
        all_pages = list(_TAB_META.keys())

    # 세션의 allowed_pages + page_edits 로 필터링/편집권한 결정
    nav_menus     = session.get('nav_menus') or []
    allowed_pages = None   # None = 전체 허용
    page_edits    = {}     # {page_id: bool} — 빈 dict = admin (전체 편집 허용)
    for m in nav_menus:
        if m.get('menu_id') == 'master-data':
            allowed_pages = m.get('allowed_pages')  # None = 전체
            page_edits    = m.get('page_edits') or {}
            break

    visible_pages = [
        p for p in all_pages
        if allowed_pages is None or p in allowed_pages
    ]

    # edit_map: {page_id: bool} — page_edits 없으면(admin) 전체 True
    edit_map = {
        p: page_edits.get(p, True)   # page_edits 에 없으면 True (admin or 구버전)
        for p in visible_pages
    }

    master_tabs = [
        {**_TAB_META[p], 'page_id': p}
        for p in visible_pages
        if p in _TAB_META
    ]

    # DB 데이터 없거나 page_id 불일치 시 전체 탭 표시 (fallback)
    if not master_tabs:
        master_tabs = [{'page_id': k, **v} for k, v in _TAB_META.items()]
        edit_map    = {k: True for k in _TAB_META}

    # 선택 법인 기준으로 로드할 탭 스크립트 목록 (중복 제거·순서 유지)
    legal_entity   = session.get('subsdr_name') or ''
    master_scripts = tab_scripts_for(master_tabs, legal_entity)
    # 각 탭에 script 필드 부여 (프론트 동적 로드 시 참조)
    for _t in master_tabs:
        _t['script'] = tab_script(_t.get('key'), legal_entity)

    return render_template('master_data.html', active_page='master-data',
                           master_tabs=master_tabs, edit_map=edit_map,
                           master_scripts=master_scripts)

@web_bp.route('/shipment')
def shipment_page():
    """영역1: Shipment 기본 정보 분석"""
    return render_template('shipment.html')

@web_bp.route('/item')
def item_page():
    """영역2: 품목/컨테이너 타입·수량·부피(CBM) 분석"""
    return render_template('item.html')

@web_bp.route('/load')
def load_page():
    """영역3: 차량(Load) · 배차 분석"""
    return render_template('load.html')

@web_bp.route('/loading')
def loading_page():
    """영역4: Shipment ↔ Load 연결 분석(적재 구조)"""
    return render_template('loading.html')

@web_bp.route('/warehouse')
def warehouse_page():
    """영역5: 출고 실적 / 창고 릴리즈 분석"""
    return render_template('warehouse.html')

@web_bp.route('/cost')
def cost_page():
    """영역6: 운임 변경 / 비용 통제 분석"""
    return render_template('cost.html')

@web_bp.route('/network')
def network_page():
    """영역7: 지역(Zone) / 운송 네트워크 분석"""
    return render_template('network.html')

@web_bp.route('/leadtime')
def leadtime_page():
    """Load 소요일 분석 (LGETT 전일 기준)"""
    return render_template('leadtime.html')

@web_bp.route('/order')
def order_page():
    """영역9: Order (M_SO_LINE) 주문 KPI 분석"""
    return render_template('order.html', active_page='order')

@web_bp.route('/active-orders')
def active_orders_page():
    """Active Orders – System Flow & Performance (Open Lines)"""
    return render_template('active_orders.html', active_page='active_orders',
                           app_env=os.environ.get('APP_ENV', 'dev'))

@web_bp.route('/active-orders-ph')
def active_orders_lgeph_page():
    """Active Orders – System Flow & Performance (Open Lines)"""
    return render_template('active_orders_lgeph.html', active_page='active_orders',
                           app_env=os.environ.get('APP_ENV', 'dev'))

@web_bp.route('/active-po')
def active_po_page():
    """Active PO – PO Tracking Flow & Performance (In-Transit)"""
    return render_template('active_po.html', active_page='active_po')

@web_bp.route('/inventory')
def inventory_page():
    """Current Inventory – D_PROD_INV current stock quantity"""
    return render_template('inventory.html', active_page='inventory')

@web_bp.route('/obs-lmd')
def obs_lmd_page():
    """OBS LMD – Last Mile Delivery 성과 지표 (M_OBS_SO_LINE)"""
    return render_template('obs_lmd.html', active_page='obs-lmd')

@web_bp.route('/glossary')
def glossary_page():
    """Glossary – 용어 설명"""
    return render_template('glossary.html', active_page='glossary')

@web_bp.route('/web-stats')
def web_stats_page():
    """Usage Statistics – 월별 페이지 접속 통계 (관리자 전용)"""
    return render_template('web_stats.html', active_page='web-stats')

@web_bp.route('/system-config')
def system_config_page():
    """LIW 시스템 환경설정 (Menu / User Type / Subsidiary)"""
    return render_template('system_config.html', active_page='system-config')


@web_bp.route('/issues')
def issues_page():
    """Order Issue & Communication — 이슈 목록 · 상세"""
    return render_template('issues.html', active_page='issues')
