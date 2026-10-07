"""
apis/api_sso.py — SSO 로그인 & 계정 접근 요청 API
  (Tomcat 의 liw-sso-token-receiver.jsp 에서 호출)

  POST /api/user/sso-login                      — SSO 계정으로 로그인
  GET  /api/user/access-request/subsdr-list     — 법인(Subsidiary) 목록
  POST /api/user/access-request/submit          — 계정 접근 요청 등록
  GET  /api/user/access-request/status          — user_id 기준 기존 요청내역 조회
  POST /api/user/get-code                        — 공통 코드 조회 (subsdr 등)

흐름
  1) SSO 파라미터(emp_no / user_id / email_id)를 받아 d_user_mst 에서 계정 조회
     - 계정 존재 & 잠금 아님 → 세션 생성 후 로그인 성공(subsidiary_list / prdt_list 포함)
     - 계정 없음(404)        → JSP 에서 계정 접근 요청 팝업 노출
  2) 계정 접근 요청
     - 동일 user_id PENDING 요청이 있으면 409, 없으면 신규 등록
"""
import logging
import os
from flask import Blueprint, request, jsonify, session

from utils.pg_db import pg
from utils.subsdr_cache import reload_subsdr_list, get_accessible_subsdrs
from utils.mailer import send_email, smtp_configured
# 일반 로그인과 동일한 세션/메뉴 구성을 재사용
from apis.api_auth import _load_nav_menus

logger = logging.getLogger(__name__)
sso_bp = Blueprint('sso', __name__)


# SSO 포털 진입 URL (환경별)
_SSO_PORTAL_URL_PROD = 'http://sso.lge.com/agentless/seoul/liwAgentless.jsp'
_SSO_PORTAL_URL_DEV  = 'http://testsso.lge.com/agentless/seoul/liwAgentless.jsp'


# ============================================================================
# 0. SSO 로그인 시작 — next page 세션 저장 + SSO 포털 URL 반환
# ============================================================================
@sso_bp.route('/api/user/sso-start', methods=['POST'])
def sso_start():
    """
    SSO 로그인 시작.
    - 이동 전 next page 를 세션(sso_next)에 저장
    - 환경(APP_ENV)에 맞는 SSO 포털 URL 을 반환 (프론트에서 이동)
    body: { next }
    """
    data     = request.get_json(silent=True) or {}
    next_url = (data.get('next') or '').strip()

    if next_url:
        session['sso_next'] = next_url
    else:
        session.pop('sso_next', None)

    app_env = (os.getenv('APP_ENV') or '').lower()
    sso_url = _SSO_PORTAL_URL_PROD if app_env in ('prod', 'production', 'prd') else _SSO_PORTAL_URL_DEV

    return jsonify({'success': True, 'sso_url': sso_url})


# ============================================================================
# 1. SSO 로그인
# ============================================================================
@sso_bp.route('/api/user/sso-login', methods=['POST'])
def sso_login():
    """
    SSO 인증 정보를 받아 시스템 로그인 처리.
    body: { emp_no, user_id, email_id }
    """
    data     = request.get_json(silent=True) or {}
    emp_no   = (data.get('emp_no')   or '').strip()
    user_id  = (data.get('user_id')  or '').strip()
    email_id = (data.get('email_id') or '').strip()

    if not user_id and not email_id:
        return jsonify({'success': False, 'message': 'SSO user information is missing.'}), 400

    # ── 사용자 조회 (user_id 우선, 없으면 email 매칭) ────────────────────
    try:
        rows = pg.query(
            """
            SELECT subsdr_name, user_id, user_name, email, user_type,
                   lock_yn, container_mail_yn
              FROM d_user_mst
             WHERE delete_flag = 'N'
               AND (user_id = %s OR email = %s)
             ORDER BY CASE WHEN user_id = %s THEN 0 ELSE 1 END
             LIMIT 1
            """,
            (user_id, email_id, user_id)
        )
    except Exception:
        logger.exception("❌ sso-login DB error")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500

    # ── 계정 없음 → 404 (JSP 에서 계정 접근 요청 유도) ────────────────────
    if not rows:
        logger.info(f"SSO LOGIN NOT FOUND  user={user_id} email={email_id}")
        return jsonify({
            'success': False,
            'message': 'Account not found in the system.'
        }), 404

    user = rows[0]

    # ── 계정 잠금 ────────────────────────────────────────────────────────
    if user['lock_yn'] == 'Y':
        return jsonify({
            'success': False,
            'message': 'Account is locked. Please contact administrator.'
        }), 403

    # ── 권한 정보 + 메뉴 목록 ─────────────────────────────────────────────
    try:
        type_rows     = pg.query(
            "SELECT allowed_menus FROM v_user_type_mst WHERE subsdr_name=%s AND user_type=%s LIMIT 1",
            (user['subsdr_name'], user['user_type'])
        )
        allowed_menus = type_rows[0]['allowed_menus'] if type_rows else None
    except Exception:
        allowed_menus = None

    nav_menus = _load_nav_menus(allowed_menus)

    # 접근 가능 법인 목록 (최신 캐시 반영)
    reload_subsdr_list()
    accessible_subsdr = get_accessible_subsdrs(user['subsdr_name'])

    # ── 세션 설정 (일반 로그인과 동일) ───────────────────────────────────
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

    # ── 마지막 로그인 갱신 ────────────────────────────────────────────────
    try:
        pg.execute(
            "UPDATE d_user_mst"
            " SET last_login_dt=CURRENT_TIMESTAMP, login_fail_cnt=0, lock_yn='N',"
            "     update_dt=CURRENT_TIMESTAMP"
            " WHERE subsdr_name=%s AND user_id=%s",
            (user['subsdr_name'], user['user_id'])
        )
    except Exception as e:
        logger.warning(f"sso last_login update failed: {e}")

    # ── 프론트(localStorage) 초기 데이터 ─────────────────────────────────
    prdt_list = _get_prdt_list(accessible_subsdr)

    # ── SSO 진입 전 저장한 next page (1회 사용 후 삭제) ──────────────────
    next_url = session.pop('sso_next', None)
    if not next_url:
        next_url = (nav_menus[0].get('menu_url') if nav_menus else None) or '/active-orders'

    logger.info(f"SSO LOGIN OK  user={user['user_id']} subsdr={user['subsdr_name']} type={user['user_type']}")
    return jsonify({
        'success': True,
        'redirect_url':    next_url,
        'user': {
            'user_id':       user['user_id'],
            'user_name':     user['user_name'],
            'subsdr_name':   user['subsdr_name'],
            'user_type':     user['user_type'],
            'email':         user.get('email') or '',
            'allowed_menus': allowed_menus,
        },
        'subsidiary_list': accessible_subsdr,
        'prdt_list':       prdt_list,
    })


def _get_prdt_list(accessible_subsdr: list) -> list:
    """접근 가능 법인의 Product Group 목록 (실패 시 빈 배열)."""
    try:
        if accessible_subsdr:
            placeholders = ','.join(['%s'] * len(accessible_subsdr))
            rows = pg.query(
                f"SELECT DISTINCT product_group_code AS prdt_grp_cd"
                f"  FROM d_product_mst"
                f" WHERE subsdr_name IN ({placeholders})"
                f" ORDER BY prdt_grp_cd",
                tuple(accessible_subsdr)
            )
        else:
            rows = pg.query(
                "SELECT DISTINCT product_group_code AS prdt_grp_cd"
                "  FROM d_product_mst ORDER BY prdt_grp_cd"
            )
        return [r['prdt_grp_cd'] for r in rows if r.get('prdt_grp_cd')]
    except Exception as e:
        logger.warning(f"prdt_list load failed: {e}")
        return []


# ============================================================================
# 2. 계정 접근 요청 — 법인 목록
# ============================================================================
@sso_bp.route('/api/user/access-request/subsdr-list', methods=['GET'])
def access_request_subsdr_list():
    """계정 요청 팝업의 Subsidiary 셀렉트 목록."""
    try:
        rows = pg.query(
            "SELECT subsdr_name FROM d_subsdr_mst"
            " WHERE use_yn = 'Y'"
            " ORDER BY sort_order, region_name, subsdr_name"
        )
        return jsonify({
            'success': True,
            'data': [r['subsdr_name'] for r in rows if r.get('subsdr_name')]
        })
    except Exception as e:
        logger.exception("❌ subsdr-list error")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 3. 계정 접근 요청 — 기존 요청내역 조회
# ============================================================================
@sso_bp.route('/api/user/access-request/status', methods=['GET'])
def access_request_status():
    """user_id 기준 최근 요청내역 조회 (있으면 보여주기 용)."""
    user_id = (request.args.get('user_id') or '').strip()
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id is required.'}), 400
    try:
        rows = pg.query(
            """
            SELECT request_id, email_id, subsdr_nm, user_id, user_emp_no,
                   request_reason_desc, request_status, process_reason_desc,
                   process_dt, input_dt
              FROM d_user_access_request
             WHERE user_id = %s AND delete_flag = 'N'
             ORDER BY input_dt DESC
             LIMIT 1
            """,
            (user_id,)
        )
        return jsonify({'success': True, 'data': rows[0] if rows else None})
    except Exception as e:
        logger.exception("❌ access-request status error")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 4. 계정 접근 요청 — 신규 등록
# ============================================================================
def _new_request_admin_email_html(user_id, email_id, emp_no, subsdr_nm, reason, users_url):
    """관리자에게 발송할 신규 계정요청 알림 메일 HTML."""
    reason_html = (reason or '-').replace('\n', '<br>')
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#222;line-height:1.6;">
      <p>Hello Administrator,</p>
      <p>A new <strong>account access request</strong> has been submitted for the
         <strong>LIW</strong> system and is waiting for your review.</p>
      <table style="border-collapse:collapse;margin:12px 0;">
        <tr><td style="padding:4px 12px;color:#666;">User ID</td><td style="padding:4px 12px;"><strong>{user_id}</strong></td></tr>
        <tr><td style="padding:4px 12px;color:#666;">Email</td><td style="padding:4px 12px;">{email_id or '-'}</td></tr>
        <tr><td style="padding:4px 12px;color:#666;">Employee No.</td><td style="padding:4px 12px;">{emp_no or '-'}</td></tr>
        <tr><td style="padding:4px 12px;color:#666;">Subsidiary</td><td style="padding:4px 12px;">{subsdr_nm}</td></tr>
      </table>
      <div style="margin:12px 0;padding:12px 16px;background:#f4f6fb;border-left:3px solid #2c5fc0;">
        <div style="color:#666;font-size:12px;margin-bottom:4px;">Request Reason</div>
        <div>{reason_html}</div>
      </div>
      <div style="margin:16px 0;padding:12px 16px;background:#f7f7f7;border-radius:6px;">
        <div style="color:#666;font-size:12px;margin-bottom:4px;">Menu Path</div>
        <div style="font-weight:600;">System &rsaquo; User Management</div>
      </div>
      <p style="margin:20px 0;">
        <a href="{users_url}" target="_blank"
           style="display:inline-block;padding:11px 24px;background:#A50034;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:600;font-size:14px;">
          Review in User Management
        </a>
      </p>
      <p style="margin-top:20px;color:#888;font-size:12px;">
         This is an automated message from LIW. Please do not reply.</p>
    </div>
    """


def _notify_admins_new_request(subsdr_nm, user_id, email_id, emp_no, reason):
    """해당 법인의 admin 계정 전체에게 신규 계정요청 알림 메일 발송 (실패해도 요청 자체는 성공 처리)."""
    if not smtp_configured():
        logger.warning("new access-request admin notice skipped: SMTP not configured")
        return
    try:
        # ── 법인 admin 계정 목록 ──────────────────────────────────────────
        admins = pg.query(
            """
            SELECT email FROM d_user_mst
             WHERE user_type = 'admin'
               AND subsdr_name = %s
               AND lock_yn = 'N'
               AND delete_flag = 'N'
               AND email IS NOT NULL AND email <> '' AND email <> '_'
            """,
            (subsdr_nm,)
        )
        subsdr_admin_emails = [r['email'] for r in admins if r.get('email')]

        # ── 환경설정 LIW_ADMIN_TO 관리자 계정 목록 ────────────────────────
        extra_to = os.getenv('LIW_ADMIN_TO', '')
        liw_admin_emails = [
            e for e in (x.strip() for x in extra_to.replace(';', ',').split(',')) if e
        ]

        if not subsdr_admin_emails and not liw_admin_emails:
            logger.warning(f"no admin recipients for subsdr={subsdr_nm}; access-request notice skipped")
            return

        base_url  = (os.getenv('LIW_BASE_URL') or 'https://liw.lge.com').rstrip('/')
        users_url = f"{base_url}/users"
        html      = _new_request_admin_email_html(user_id, email_id, emp_no, subsdr_nm, reason, users_url)
        subject   = f"[LIW] New Account Access Request — {user_id} ({subsdr_nm})"

        # ── 1) 법인 admin 유저에게 발송 ───────────────────────────────────
        if subsdr_admin_emails:
            send_email(
                to_addrs=subsdr_admin_emails,
                subject=subject,
                html_body=html,
                from_name='LIW',
            )
            logger.info(f"access-request notice sent to {len(subsdr_admin_emails)} subsdr admin(s) of {subsdr_nm}")

        # ── 2) LIW_ADMIN_TO 관리자에게 별도 발송 ──────────────────────────
        if liw_admin_emails:
            send_email(
                to_addrs=liw_admin_emails,
                subject=subject,
                html_body=html,
                from_name='LIW',
            )
            logger.info(f"access-request notice sent to {len(liw_admin_emails)} LIW_ADMIN_TO recipient(s)")
    except Exception:
        logger.exception("❌ new access-request admin notice failed")


@sso_bp.route('/api/user/access-request/submit', methods=['POST'])
def access_request_submit():
    """
    계정 접근 요청 등록.
    body: { email_id, subsdr_nm, user_id, user_emp_no, request_reason_desc }
    - 동일 user_id PENDING 요청 존재 시 409
    """
    data       = request.get_json(silent=True) or {}
    email_id   = (data.get('email_id')            or '').strip()
    subsdr_nm  = (data.get('subsdr_nm')           or '').strip()
    user_id    = (data.get('user_id')             or '').strip()
    emp_no     = (data.get('user_emp_no')         or '').strip()
    reason     = (data.get('request_reason_desc') or '').strip()

    # ── 필수값 검증 ──────────────────────────────────────────────────────
    if not user_id or not subsdr_nm or not reason:
        return jsonify({
            'success': False,
            'message': 'User ID, subsidiary and reason are required.'
        }), 400

    try:
        # ── 중복 PENDING 요청 확인 ────────────────────────────────────────
        dup = pg.query(
            "SELECT request_id FROM d_user_access_request"
            " WHERE user_id = %s AND request_status = 'PENDING' AND delete_flag = 'N'"
            " LIMIT 1",
            (user_id,)
        )
        if dup:
            return jsonify({
                'success': False,
                'message': 'An access request for this user already exists.'
            }), 409

        # ── 이미 가입된 계정인지 확인 ─────────────────────────────────────
        exists = pg.query(
            "SELECT user_id FROM d_user_mst"
            " WHERE user_id = %s AND delete_flag = 'N' LIMIT 1",
            (user_id,)
        )
        if exists:
            return jsonify({
                'success': False,
                'message': 'This account already exists. Please try logging in.'
            }), 409

        # ── 등록 ─────────────────────────────────────────────────────────
        new_id = pg.insert('d_user_access_request', {
            'email_id':            email_id or None,
            'subsdr_nm':           subsdr_nm,
            'user_id':             user_id,
            'user_emp_no':         emp_no or None,
            'request_reason_desc': reason,
            'request_status':      'PENDING',
            'input_user_id':       user_id,
        }, returning='request_id')

        logger.info(f"ACCESS REQUEST SUBMIT  id={new_id} user={user_id} subsdr={subsdr_nm}")

        # ── 해당 법인 admin 전체에게 알림 메일 발송 (실패해도 요청은 성공) ──
        _notify_admins_new_request(subsdr_nm, user_id, email_id, emp_no, reason)

        return jsonify({
            'success': True,
            'message': 'Access request submitted successfully.',
            'request_id': new_id,
        })
    except Exception as e:
        logger.exception("❌ access-request submit error")
        return jsonify({'success': False, 'message': 'A server error occurred.'}), 500


# ============================================================================
# 5. 공통 코드 조회 (JSP saveCode 대응)
# ============================================================================
@sso_bp.route('/api/user/get-code', methods=['POST'])
def get_code():
    """
    공통 코드 조회. body: { code_nm }
      code_nm='subsdr' → 법인 목록 반환
    """
    data    = request.get_json(silent=True) or {}
    code_nm = (data.get('code_nm') or '').strip()

    try:
        if code_nm == 'subsdr':
            rows = pg.query(
                "SELECT subsdr_name, display_name, region_name FROM d_subsdr_mst"
                " WHERE use_yn = 'Y'"
                " ORDER BY sort_order, region_name, subsdr_name"
            )
            data_list = [
                {
                    'code':    r['subsdr_name'],
                    'name':    r.get('display_name') or r['subsdr_name'],
                    'region':  r.get('region_name') or '',
                }
                for r in rows
            ]
            return jsonify({'success': True, 'code_nm': code_nm, 'data': data_list})

        return jsonify({'success': False, 'message': f'Unknown code_nm: {code_nm}', 'data': []}), 400
    except Exception as e:
        logger.exception("❌ get-code error")
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500
