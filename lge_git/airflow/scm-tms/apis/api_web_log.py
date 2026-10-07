"""
apis/api_web_log.py — 웹 접속 로그 통계 API (관리자 전용)
  GET /api/web-log/months  — 조회 가능 년월 목록
  GET /api/web-log/stats   — 월별 사용자×페이지 집계
  GET /api/web-log/detail  — 개별 접속 로그 상세
"""
import logging
from flask import Blueprint, request, jsonify, session
from utils.pg_db import pg
from utils.subsdr_cache import get_accessible_subsdrs
from utils.auth_check import require_menu_access

logger = logging.getLogger(__name__)
web_log_bp = Blueprint('web_log', __name__, url_prefix='/api/web-log')


def _accessible_subsdrs() -> list:
    """로그인 사용자가 접근 가능한 법인 목록 (본인 + 하위 법인)"""
    return get_accessible_subsdrs(session.get('subsdr_name', ''))


# ── 프론트엔드 직접 호출 — hash 기반 page_id 포함 페이지뷰 로그 ───────────
@web_log_bp.route('/pageview', methods=['POST'])
def log_pageview():
    """
    클라이언트 JS에서 직접 호출하는 페이지뷰 로그.
    URL hash(#shipto 등)는 HTTP 요청에 포함되지 않으므로 프론트엔드가 직접 전송.
    """
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required.'}), 401

    data    = request.get_json(silent=True) or {}
    menu_id = (data.get('menu_id') or '').strip()
    page_id = (data.get('page_id') or '_').strip()
    req_path = (data.get('request_path') or f'/{menu_id}').strip()

    if not menu_id:
        return jsonify({'success': False, 'message': 'menu_id required.'}), 400

    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        pg.execute(
            """
            INSERT INTO m_web_log
                (log_ym, log_dt, log_type, subsdr_name, user_id, user_name,
                 menu_id, page_id, request_path, ip_address)
            SELECT
                to_char(NOW() AT TIME ZONE COALESCE(s.timezone, 'UTC'), 'YYYYMM'),
                NOW(),
                %s, %s, %s, %s, %s, %s, %s, %s
            FROM (SELECT COALESCE(MAX(timezone), 'UTC') AS timezone
                    FROM d_subsdr_mst WHERE subsdr_name = %s) s
            """,
            ('PAGEVIEW',
             session.get('subsdr_name'), session.get('user_id'), session.get('user_name'),
             menu_id, page_id, req_path, ip,
             session.get('subsdr_name'))
        )
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"❌ web_log pageview error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 프론트엔드 직접 호출 — 주요 액션 로그 (엑셀 다운로드 등) ─────────────
@web_log_bp.route('/action', methods=['POST'])
def log_action():
    """
    페이지뷰 외 주요 사용자 액션을 기록.
    예) 엑셀 다운로드(EXCEL_DOWNLOAD), 이슈 등록(ISSUE_CREATE) 등.
    Body: {log_type, menu_id, page_id?, request_path?, log_detail?}
    """
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required.'}), 401

    data     = request.get_json(silent=True) or {}
    log_type = (data.get('log_type') or '').strip()
    menu_id  = (data.get('menu_id') or '').strip()
    page_id  = (data.get('page_id') or '_').strip()
    req_path = (data.get('request_path') or f'/{menu_id}').strip()
    detail   = (data.get('log_detail') or '').strip() or None

    if not log_type:
        return jsonify({'success': False, 'message': 'log_type required.'}), 400
    if not menu_id:
        return jsonify({'success': False, 'message': 'menu_id required.'}), 400

    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        pg.execute(
            """
            INSERT INTO m_web_log
                (log_ym, log_dt, log_type, subsdr_name, user_id, user_name,
                 menu_id, page_id, request_path, log_detail, ip_address)
            SELECT
                to_char(NOW() AT TIME ZONE COALESCE(s.timezone, 'UTC'), 'YYYYMM'),
                NOW(),
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM (SELECT COALESCE(MAX(timezone), 'UTC') AS timezone
                    FROM d_subsdr_mst WHERE subsdr_name = %s) s
            """,
            (log_type,
             session.get('subsdr_name'), session.get('user_id'), session.get('user_name'),
             menu_id, page_id, req_path, detail, ip,
             session.get('subsdr_name'))
        )
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"❌ web_log action error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 조회 가능 년월 목록 ────────────────────────────────────────────────────
@web_log_bp.route('/months', methods=['GET'])
def get_months():
    err = require_menu_access('web-stats')
    if err:
        return err
    subsdrs = _accessible_subsdrs()
    try:
        rows = pg.query(
            """
            SELECT DISTINCT log_ym
              FROM m_web_log
             WHERE subsdr_name = ANY(%s)
             ORDER BY log_ym DESC
             LIMIT 24
            """,
            (subsdrs,)
        )
        return jsonify({'success': True, 'data': [r['log_ym'] for r in rows]})
    except Exception as e:
        logger.exception(f"❌ web_log months error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 월별 집계 (사용자 × 메뉴) ─────────────────────────────────────────────
@web_log_bp.route('/stats', methods=['GET'])
def get_stats():
    err = require_menu_access('web-stats')
    if err:
        return err

    from datetime import datetime
    log_ym  = request.args.get('log_ym', '').strip() or datetime.now().strftime('%Y%m')
    subsdrs = _accessible_subsdrs()

    try:
        rows = pg.query(
            """
            SELECT
                l.subsdr_name,
                l.user_id,
                l.user_name,
                l.menu_id,
                l.page_id,
                COALESCE(m.menu_name, l.menu_id)        AS menu_name,
                COUNT(*) FILTER (WHERE l.log_type = 'PAGEVIEW')      AS visit_count,
                COUNT(*) FILTER (WHERE l.log_type = 'ISSUE_CREATE')  AS issue_count,
                COUNT(*) FILTER (WHERE l.log_type IN ('EXCEL_DOWNLOAD','EMAIL_SEND')) AS download_count,
                COUNT(*) FILTER (WHERE l.log_type = 'MAIL_DOWNLOAD')  AS mail_download_count,
                to_char(MIN(l.log_dt) AT TIME ZONE COALESCE(s.timezone, 'UTC'), 'YYYY-MM-DD HH24:MI') AS first_visit_dt,
                to_char(MAX(l.log_dt) AT TIME ZONE COALESCE(s.timezone, 'UTC'), 'YYYY-MM-DD HH24:MI') AS last_visit_dt
            FROM m_web_log l
            LEFT JOIN d_subsdr_mst s
                   ON l.subsdr_name = s.subsdr_name
            LEFT JOIN d_menu_mst m
                   ON l.menu_id = m.menu_id AND l.page_id = m.page_id
            WHERE l.log_ym      = %s
              AND l.subsdr_name = ANY(%s)
            GROUP BY l.subsdr_name, l.user_id, l.user_name,
                     l.menu_id, l.page_id, m.menu_name, s.timezone
            ORDER BY l.user_id, visit_count DESC
            """,
            (log_ym, subsdrs)
        )
        return jsonify({'success': True, 'data': rows, 'log_ym': log_ym})
    except Exception as e:
        logger.exception(f"❌ web_log stats error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 개별 접속 로그 상세 ────────────────────────────────────────────────────
@web_log_bp.route('/detail', methods=['GET'])
def get_detail():
    err = require_menu_access('web-stats')
    if err:
        return err

    log_ym       = request.args.get('log_ym', '').strip()
    user_id      = request.args.get('user_id', '').strip()
    menu_id      = request.args.get('menu_id', '').strip()
    subsdr_name  = request.args.get('subsdr_name', '').strip()
    log_type     = request.args.get('log_type', '').strip()
    subsdrs      = _accessible_subsdrs()

    where  = ["l.subsdr_name = ANY(%s)"]
    params = [subsdrs]

    if log_ym:
        where.append("l.log_ym = %s");        params.append(log_ym)
    if subsdr_name:
        where.append("l.subsdr_name = %s");   params.append(subsdr_name)
    if user_id:
        where.append("l.user_id = %s");       params.append(user_id)
    if menu_id:
        where.append("l.menu_id = %s");       params.append(menu_id)
    if log_type:
        where.append("l.log_type = %s");      params.append(log_type)

    where_sql = "WHERE " + " AND ".join(where)

    try:
        rows = pg.query(
            f"""
            SELECT
                l.log_id,
                to_char(l.log_dt AT TIME ZONE COALESCE(s.timezone, 'UTC'), 'YYYY-MM-DD HH24:MI:SS') AS log_dt,
                l.log_type,
                l.subsdr_name,
                l.user_id,
                l.user_name,
                l.menu_id,
                l.page_id,
                COALESCE(m.menu_name, l.menu_id) AS menu_name,
                l.request_path,
                l.log_detail,
                l.ip_address
            FROM m_web_log l
            LEFT JOIN d_subsdr_mst s ON l.subsdr_name = s.subsdr_name
            LEFT JOIN d_menu_mst m ON l.menu_id = m.menu_id AND l.page_id = m.page_id
            {where_sql}
            ORDER BY l.log_dt DESC
            LIMIT 1000
            """,
            tuple(params)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception(f"❌ web_log detail error:")
        return jsonify({'success': False, 'message': str(e)}), 500
