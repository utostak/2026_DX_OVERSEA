"""
Dashboard - Flask Application
"""
from flask import Flask, jsonify, session, redirect, request
from flask_cors import CORS
from flask_session import Session
import os
import sys
import json
from datetime import timedelta
from threading import Thread

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── 환경설정 로드 (가장 먼저 — logging 초기화보다 앞에)
from config.env import load_env
load_env()  # APP_ENV 환경변수로 자동 감지 (.env.dev / .env.prd)

# ── 로깅 설정
from config.logging_config import setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

from utils.subsdr_cache import load_subsdr_list, get_subsdr_list
from utils.pg_db import pg
from apis.web import web_bp
from apis.api import api_bp
from apis.api_order import order_bp
from apis.api_po import po_bp
from apis.api_inventory import inv_bp
from apis.api_obs import obs_bp
from apis.api_auth import auth_bp
from apis.api_user import user_bp
from apis.api_master import master_bp
from apis.api_web_log import web_log_bp
from apis.api_system_config import sysconfig_bp
from apis.api_issue import issue_bp
from apis.api_mail_file import mail_file_bp
from apis.api_sso import sso_bp
from apis.api_access_request import access_req_bp
app = Flask(__name__)
CORS(app)

# ============================================================================
# Configuration
# ============================================================================
app.config['JSON_AS_ASCII']   = False
app.config['JSON_SORT_KEYS']  = False
app.config['SECRET_KEY']      = os.getenv('SECRET_KEY', 'scm-tms-default-secret')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # 세션 유효 시간

# 정적 파일 / 템플릿 캐시 비활성화 (개발 환경)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Flask-Session 설정 — 파일시스템 기반 세션 (개발 환경 안정성)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(__file__), 'flask_session')
app.config['SESSION_FILE_THRESHOLD'] = 500  # 최대 세션 파일 수

# 환경별 세션 쿠키 이름 분리 (운영/개발 세션 충돌 방지)
app.config['SESSION_COOKIE_NAME'] = os.getenv('SESSION_COOKIE_NAME', 'liw_session')

Session(app)

# ============================================================================
# Register Blueprints
# ============================================================================
app.register_blueprint(web_bp)
app.register_blueprint(api_bp)
app.register_blueprint(order_bp)
app.register_blueprint(po_bp)
app.register_blueprint(inv_bp)
app.register_blueprint(obs_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(master_bp)
app.register_blueprint(web_log_bp)
app.register_blueprint(sysconfig_bp)
app.register_blueprint(issue_bp)
app.register_blueprint(mail_file_bp)
app.register_blueprint(sso_bp)
app.register_blueprint(access_req_bp)
# ============================================================================
# Template Context Processor — 모든 템플릿에 법인 목록 / Division 목록 자동 주입
# ============================================================================
_divisions_list = []

def _load_divisions():
    global _divisions_list
    try:
        code_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'code.json')
        with open(code_json_path, encoding='utf-8') as f:
            data = json.load(f)
        _divisions_list = sorted(data.get('divisions', []), key=lambda x: x.get('sort_order', 99))
        logger.info(f"✅ Division 목록 로드 완료: {len(_divisions_list)}개")
    except Exception as e:
        logger.error(f"❌ code.json 로드 실패: {e}")
        _divisions_list = []

_load_divisions()

@app.context_processor
def inject_common_lists():
    # 로그인 시 세션에 저장된 접근 가능 법인 목록으로 셀렉터를 필터링
    # 세션에 없으면(비로그인) 전체 목록 노출
    accessible = session.get('accessible_subsdr')  # list | None
    full_list  = get_subsdr_list()                 # 가상 법인 제외 전체 목록

    if accessible is not None:
        accessible_set = set(accessible)
        subsdr_list = [
            {'region': g['region'],
             'subsidiaries': [s for s in g['subsidiaries'] if s['code'] in accessible_set]}
            for g in full_list
        ]
        subsdr_list = [g for g in subsdr_list if g['subsidiaries']]  # 빈 지역 제거
    else:
        subsdr_list = full_list

    return {
        "subsdr_list":    subsdr_list,
        "divisions_list": _divisions_list,
        "app_env":        os.getenv('APP_ENV', 'production'),
        "session_user": {
            "user_id":     session.get('user_id'),
            "user_name":   session.get('user_name'),
            "user_type":   session.get('user_type'),
            "subsdr_name": session.get('subsdr_name'),
        },
        "nav_menus": session.get('nav_menus', []),
    }

# ============================================================================
# 세션 가드 — 미인증 요청 차단
# ============================================================================
_EXEMPT_PATHS    = {
    '/login',
    # ── SSO 로그인 / 계정 접근 요청 (미인증 상태에서 호출됨) ──
    '/api/user/sso-start',
    '/api/user/sso-login',
    '/api/user/access-request/subsdr-list',
    '/api/user/access-request/status',
    '/api/user/access-request/submit',
    '/api/user/get-code',
}
_EXEMPT_PREFIXES = ('/static/', '/api/auth/')

# ============================================================================
# 웹 접속 로그 — HTML 페이지 GET 요청을 m_web_log 에 비동기 기록
# ============================================================================
# request.path → (menu_id, page_id) 매핑
_WEB_PAGE_MENU_MAP = {
    '/active-orders': ('active-orders', '_'),
    '/active-po':     ('active-po',     '_'),
    '/inventory':     ('inventory',     '_'),
    '/order':         ('order',         '_'),
    '/obs-lmd':       ('obs-lmd',       '_'),
    # '/master-data' 는 hash(#billto 등) 기반 page_id 가 있으므로
    # 서버 after_request 에서 처리 불가 — master_data.html 프론트에서 직접 로깅
    '/users':         ('users',         '_'),
    '/web-stats':     ('web-stats',     '_'),
    '/glossary':      ('glossary',      '_'),
    '/issues':        ('issues',        '_'),
}

def _insert_web_log(subsdr_name, user_id, user_name,
                    menu_id, page_id, request_path, ip_address,
                    log_type='PAGEVIEW', log_detail=None):
    """m_web_log INSERT — 응답과 무관하게 별도 스레드에서 실행"""
    try:
        from datetime import datetime
        pg.insert('m_web_log', {
            'log_ym':       datetime.now().strftime('%Y%m'),
            'log_type':     log_type,
            'subsdr_name':  subsdr_name,
            'user_id':      user_id,
            'user_name':    user_name,
            'menu_id':      menu_id,
            'page_id':      page_id,
            'request_path': request_path,
            'log_detail':   log_detail,
            'ip_address':   ip_address,
        })
    except Exception as e:
        logger.warning(f"web_log insert failed: {e}")

@app.after_request
def log_web_page(response):
    """HTML 페이지 GET 200 응답만 m_web_log 에 기록"""
    if request.method != 'GET' or response.status_code != 200:
        return response
    path = request.path
    if (path in _EXEMPT_PATHS
            or any(path.startswith(p) for p in _EXEMPT_PREFIXES)
            or path.startswith('/api/')):
        return response
    user_id = session.get('user_id')
    if not user_id:
        return response
    menu_id, page_id = _WEB_PAGE_MENU_MAP.get(path, (None, None))
    if menu_id:
        # X-Forwarded-For 우선 (리버스 프록시 환경 대응)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        Thread(
            target=_insert_web_log,
            args=(session.get('subsdr_name'), user_id, session.get('user_name'),
                  menu_id, page_id, path, ip),
            daemon=True
        ).start()
    return response

# ============================================================================
# Startup — 첫 번째 요청 직전에 1회만 실행 (gunicorn/waitress 환경 포함)
# ============================================================================
_startup_done = False

@app.before_request
def startup_and_auth():
    global _startup_done
    if not _startup_done:
        _startup_done = True
        logger.info("🚀 앱 첫 요청 감지 — 법인 마스터 캐시 로드 시작")
        load_subsdr_list()

    path = request.path
    # 인증 불필요 경로 제외
    if path in _EXEMPT_PATHS or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return None
    # 인증 확인
    if not session.get('user_id'):
        if path.startswith('/api/'):
            return jsonify({'success': False, 'message': '로그인이 필요합니다.', 'redirect': '/login'}), 401
        # 쿼리스트링(필터 파라미터 포함)까지 next에 전달
        full = request.full_path  # e.g. /active-orders?le=KOR&pg=TV?
        next_url = full[:-1] if full.endswith('?') else full
        from urllib.parse import quote
        return redirect('/login?next=' + quote(next_url, safe=''))

# ============================================================================
# Error Handlers
# ============================================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ============================================================================
# Main
# ============================================================================
if __name__ == '__main__':
    _host  = os.environ.get('APP_HOST', '0.0.0.0')
    _port  = int(os.environ.get('APP_PORT', 8114))
    _debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info("=" * 80)
    logger.info(" Dashboard Flask Application Starting...")
    logger.info("=" * 80)
    logger.info(f" ENV  : {os.environ.get('APP_ENV', 'development')}")
    logger.info(f" URL  : http://{_host}:{_port}")
    logger.info(f" DEBUG: {_debug}")
    logger.info("=" * 80)
    app.run(host=_host, port=_port, debug=_debug, use_reloader=False)
