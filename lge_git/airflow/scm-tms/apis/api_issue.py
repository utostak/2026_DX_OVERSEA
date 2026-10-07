"""
apis/api_issue.py — Order Issue & Communication API

GitHub Issue 유사 기능: Active Orders 에서 오더에 이슈 티켓을 붙여
담당자 지정 · 처리 · 이력을 관리한다.

  POST   /api/issues                         — 이슈 생성
  GET    /api/issues                         — 이슈 리스트 (tab=inbox/outbox/all/closed)
  GET    /api/issues/<id>                     — 이슈 상세
  PATCH  /api/issues/<id>                     — 상태 변경 (CAS)
  POST   /api/issues/<id>/comments            — 코멘트 추가
  GET    /api/issues/inbox-count              — 본인 Inbox open count (nav 뱃지)
  GET    /api/issues/departments              — 수신 부서 목록
  GET    /api/orders/issue-badges        — 배치 뱃지 조회 (법인 전체, 화면에서 매핑)
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from utils.pg_db import pg
from utils.db_query import run_query
from utils.auth_check import require_login
from utils.mailer import send_email, smtp_configured

logger = logging.getLogger(__name__)
issue_bp = Blueprint('issue', __name__, url_prefix='/api')

# ── 상태 전이 규칙 (상태 머신) ──────────────────────────────────
_VALID_TRANSITIONS = {
    'OPEN':        {'IN_PROGRESS', 'CANCELLED'},
    'IN_PROGRESS': {'RESOLVED', 'CANCELLED'},
    'RESOLVED':    {'CLOSED', 'IN_PROGRESS'},   # sender 반려 → IN_PROGRESS
    'CLOSED':      {'IN_PROGRESS'},              # admin reopen
    'CANCELLED':   set(),
}

# ── 수신 부서 목록 (마스터 테이블 없이 최소 구현) ───────────────
_DEPARTMENTS = [
    {'code': 'SCM',    'name': 'SCM'},
    {'code': 'FIN',    'name': 'Finance'},
    {'code': 'SALES',  'name': 'Sales'},
    {'code': 'LOGI',   'name': 'Logistics'},
    {'code': 'ETC',    'name': 'Etc'},
]


def _me():
    return {
        'user_id':   session.get('user_id'),
        'user_name': session.get('user_name'),
        'subsdr':    session.get('subsdr_name'),
    }


# ============================================================================
# 이슈 메일 알림 헬퍼
# ============================================================================
def _issue_url(issue_id: int) -> str:
    """이슈 상세 페이지 URL (절대경로)"""
    try:
        from flask import request as _req
        base = _req.host_url.rstrip('/')
    except Exception:
        base = ''
    return f"{base}/issues/{issue_id}"


def _send_issue_notification(issue_id: int, actor_user_id: str, comment_body: str, subject_prefix: str = ''):
    """
    이슈에 관여된 모든 사람(등록자 · 대상자 · 코멘트 작성자)에게 메일을 보낸다.
    액션을 수행한 actor_user_id 본인은 수신 대상에서 제외한다.

    :param issue_id:       이슈 ID
    :param actor_user_id:  액션 수행자 (제외 대상)
    :param comment_body:   메일 본문에 포함할 코멘트 내용
    :param subject_prefix: 제목 앞에 붙일 접두어 (예: '[New]', '[Updated]')
    """
    if not smtp_configured():
        return  # SMTP 미설정 시 무시

    try:
        # ── 이슈 헤더 조회 ──────────────────────────────────────
        head_rows = pg.query(
            """
            SELECT title, category, status,
                   sender_user_id, receiver_user_id
              FROM d_issue_mst
             WHERE issue_id = %s AND delete_flag = 'N'
            """,
            (issue_id,)
        )
        if not head_rows:
            return
        head = head_rows[0]

        # ── 코멘트 작성자 user_id 수집 ──────────────────────────
        comment_authors = pg.query(
            """
            SELECT DISTINCT author_user_id
              FROM d_issue_comment
             WHERE issue_id = %s AND author_user_id IS NOT NULL AND author_role <> 'SYSTEM'
            """,
            (issue_id,)
        )
        author_ids = {r['author_user_id'] for r in comment_authors}

        # ── 관여자 전원 user_id 집합 ────────────────────────────
        participant_ids = set(filter(None, [
            head.get('sender_user_id'),
            head.get('receiver_user_id'),
        ])) | author_ids

        # 액션 수행자 본인 제외
        participant_ids.discard(actor_user_id)

        if not participant_ids:
            return

        # ── 이메일 주소 조회 ────────────────────────────────────
        placeholders = ','.join(['%s'] * len(participant_ids))
        user_rows = pg.query(
            f"""
            SELECT user_id, user_name, email
              FROM d_user_mst
             WHERE user_id IN ({placeholders})
               AND delete_flag = 'N'
               AND email IS NOT NULL AND email <> ''
            """,
            tuple(participant_ids)
        )
        to_addrs = [r['email'] for r in user_rows if r.get('email')]
        if not to_addrs:
            return

        # ── 메일 제목 / 본문 ────────────────────────────────────
        prefix   = subject_prefix.strip()
        subject  = f"{('[' + prefix + '] ') if prefix else ''}[Issue #{issue_id}] {head['title']}"
        issue_link = _issue_url(issue_id)

        html_body = f"""
    <html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
    <p>A new update has been registered for this issue.</p>
    <table style="border-collapse:collapse;width:100%;max-width:640px;">
      <tr><td style="padding:4px 8px;font-weight:bold;width:120px;">Issue #</td>
          <td style="padding:4px 8px;">{issue_id}</td></tr>
      <tr style="background:#f5f5f5;">
          <td style="padding:4px 8px;font-weight:bold;">Title</td>
          <td style="padding:4px 8px;">{head['title']}</td></tr>
      <tr><td style="padding:4px 8px;font-weight:bold;">Category</td>
          <td style="padding:4px 8px;">{head['category']}</td></tr>
      <tr style="background:#f5f5f5;">
          <td style="padding:4px 8px;font-weight:bold;">Status</td>
          <td style="padding:4px 8px;">{head['status']}</td></tr>
    </table>
    <hr style="margin:16px 0;border:none;border-top:1px solid #ddd;">
    <p style="font-weight:bold;">Comment / Activity</p>
    <div style="background:#f9f9f9;border-left:4px solid #0078d4;padding:10px 14px;
            white-space:pre-wrap;font-size:13px;">{comment_body}</div>
    <hr style="margin:16px 0;border:none;border-top:1px solid #ddd;">
    <p><a href="{issue_link}" style="color:#0078d4;">▶ Go to Issue</a></p>
    </body></html>
    """
        send_email(
            to_addrs   = to_addrs,
            subject    = subject,
            html_body  = html_body,
            from_name  = 'LIW Issues',
        )
    except Exception:
        logger.exception(f"_send_issue_notification failed (issue_id={issue_id})")


# ============================================================================
# 배치 뱃지 조회 (N+1 방지 · Active Orders 그리드용)
# ============================================================================
@issue_bp.route('/orders/issue-badges', methods=['GET'])
def issue_badges():
    """
    d_issue_order 전체를 법인 단위로 조회해 반환.
    order_nos 파라미터 없이 화면(JS)에서 sales_order_no 매핑 처리.
    d_issue_order 는 데이터 규모가 작으므로 full-scan 이 더 단순·안전.
    """
    err = require_login()
    if err:
        return err

    me     = _me()
    subsdr = me['subsdr']   # 로그인 사용자 법인으로 스코프 제한

    try:
        rows = pg.query(
            """
            SELECT o.sales_order_no,
                   o.line_no,
                   COUNT(DISTINCT m.issue_id)                       AS open_cnt,
                   BOOL_OR(m.due_date < CURRENT_DATE)              AS overdue,
                   BOOL_OR(m.receiver_user_id = %s)                AS mine,
                   ARRAY_AGG(DISTINCT m.issue_id)                  AS issue_ids
              FROM d_issue_order o
              JOIN d_issue_mst   m ON m.issue_id = o.issue_id
             WHERE m.delete_flag = 'N'
               AND m.category <> 'EMAIL_SEND'
               AND m.status NOT IN ('CLOSED','CANCELLED')
               AND m.sender_subsdr = %s
             GROUP BY o.sales_order_no, o.line_no
            """,
            (me['user_id'], subsdr)
        )
        data = {
            f"{r['sales_order_no']}|{r['line_no']}": {
                'open':      int(r['open_cnt']),
                'overdue':   bool(r['overdue']),
                'mine':      bool(r['mine']),
                'issue_ids': r['issue_ids'] if r['issue_ids'] else [],
            } for r in rows
        }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception("issue_badges failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 부서 목록
# ============================================================================
@issue_bp.route('/issues/departments', methods=['GET'])
def get_departments():
    err = require_login()
    if err:
        return err
    return jsonify({'success': True, 'data': _DEPARTMENTS})


# ============================================================================
# 수신 담당자(개인) 목록 — 특정 법인의 사용자 아이디
# ============================================================================
@issue_bp.route('/issues/users', methods=['GET'])
def get_issue_users():
    err = require_login()
    if err:
        return err
    # ?legal_entity= 우선, 없으면 로그인 사용자 법인
    subsdr = (request.args.get('legal_entity') or '').strip() or session.get('subsdr_name')
    try:
        rows = pg.query(
            """
            SELECT user_id, user_name, email
              FROM d_user_mst
             WHERE subsdr_name = %s AND delete_flag = 'N'
             ORDER BY user_name, user_id
            """,
            (subsdr,)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception("get_issue_users failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 메일 발송 이력 (EMAIL_SEND 카테고리)
# ============================================================================
@issue_bp.route('/issues/mail-history', methods=['GET'])
def mail_history():
    """내가 보낸 메일 이력 목록 (category = EMAIL_SEND)"""
    err = require_login()
    if err:
        return err
    me     = _me()
    subsdr = (request.args.get('legal_entity') or '').strip() or me['subsdr']
    limit  = min(int(request.args.get('limit') or 200), 500)
    try:
        rows = pg.query(
            """
            SELECT issue_id, title, mail_to, mail_subject,
                   description, order_count, input_dt, sender_user_name
              FROM d_issue_mst
             WHERE delete_flag = 'N'
               AND category = 'EMAIL_SEND'
               AND sender_subsdr = %s
             ORDER BY input_dt DESC
             LIMIT %s
            """,
            (subsdr, limit)
        )
        for r in rows:
            r['input_dt'] = r['input_dt'].strftime('%Y-%m-%d %H:%M') if r.get('input_dt') else None
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception("mail_history failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# Inbox 카운트 (nav 뱃지)
# ============================================================================
@issue_bp.route('/issues/inbox-count', methods=['GET'])
def inbox_count():
    err = require_login()
    if err:
        return err
    me = _me()
    try:
        rows = pg.query(
            """
            SELECT COUNT(*) AS cnt
              FROM d_issue_mst
             WHERE delete_flag = 'N'
               AND status IN ('OPEN','IN_PROGRESS','RESOLVED')
               AND receiver_user_id = %s
            """,
            (me['user_id'],)
        )
        return jsonify({'success': True, 'count': int(rows[0]['cnt']) if rows else 0})
    except Exception as e:
        logger.exception("inbox_count failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 이슈 생성
# ============================================================================
@issue_bp.route('/issues', methods=['POST'])
def create_issue():
    err = require_login()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    me   = _me()

    title    = (data.get('title') or '').strip()
    category = (data.get('category') or '').strip()
    orders   = data.get('orders') or []   # [{sales_order_no, line_no, customer_code, customer_name, model_code, order_qty, usd_amount, stage}]

    if not title:
        return jsonify({'success': False, 'message': 'Please enter a title.'}), 400
    if not category:
        return jsonify({'success': False, 'message': 'Please select a category.'}), 400
    if not orders:
        return jsonify({'success': False, 'message': 'No target orders selected.'}), 400

    total_amount = sum(float(o.get('usd_amount') or 0) for o in orders)

    try:
        with pg.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO d_issue_mst
                        (title, category, description, status, action_text,
                         sender_subsdr, sender_user_id, sender_user_name,
                         receiver_dept, receiver_user_id, receiver_user_name,
                         due_date, total_amount, order_count,
                         input_user_id)
                    VALUES (%s,%s,%s,'OPEN',%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s)
                    RETURNING issue_id
                    """,
                    (
                        title, category, data.get('description'), data.get('action_text'),
                        me['subsdr'], me['user_id'], me['user_name'],
                        data.get('receiver_dept'), data.get('receiver_user_id') or None,
                        data.get('receiver_user_name'),
                        data.get('due_date') or None, total_amount, len(orders),
                        me['user_id'],
                    )
                )
                issue_id = cur.fetchone()[0]

                for o in orders:
                    cur.execute(
                        """
                        INSERT INTO d_issue_order
                            (issue_id, sales_order_no, line_no, customer_code,
                             customer_name, model_code, order_qty, usd_amount, stage_snapshot,
                             order_amount, currency_code)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            issue_id,
                            str(o.get('sales_order_no') or '').strip(),
                            str(o.get('line_no') or '*').strip() or '*',
                            o.get('customer_code'), o.get('customer_name'),
                            o.get('model_code'), o.get('order_qty') or None,
                            o.get('usd_amount') or None, o.get('stage'),
                            o.get('order_amount') or None, o.get('currency_code') or None,
                        )
                    )

                # 생성 이력 코멘트 (SYSTEM)
                cur.execute(
                    """
                    INSERT INTO d_issue_comment
                        (issue_id, author_user_id, author_name, author_role, body)
                    VALUES (%s,%s,%s,'SYSTEM',%s)
                    """,
                    (issue_id, me['user_id'], me['user_name'],
                     f"Issue created · {len(orders)} order(s) linked")
                )

        logger.info(f"ISSUE CREATED #{issue_id} by {me['user_id']} ({len(orders)} orders)")
        # 웹 로그 기록 (ISSUE_CREATE) — 실패해도 응답에 영향 없음
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
                ('ISSUE_CREATE',
                 me['subsdr'], me['user_id'], me['user_name'],
                 'active-orders', '_', '/active-orders',
                 f"Issue #{issue_id} · {title} ({len(orders)} orders)", ip,
                 me['subsdr'])
            )
        except Exception as _log_e:
            logger.warning(f"web_log ISSUE_CREATE insert failed: {_log_e}")
        # 메일 알림 (비동기 X — 실패해도 응답에 영향 없음)
        _send_issue_notification(
            issue_id       = issue_id,
            actor_user_id  = me['user_id'],
            comment_body   = f"Issue created by {me['user_name']} · {len(orders)} order(s) linked",
            subject_prefix = 'New Issue',
        )
        return jsonify({'success': True, 'issue_id': issue_id})
    except Exception as e:
        logger.exception("create_issue failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 이슈 리스트
# ============================================================================
@issue_bp.route('/issues', methods=['GET'])
def list_issues():
    err = require_login()
    if err:
        return err
    me           = _me()
    tab          = (request.args.get('tab') or 'all').lower()
    q            = (request.args.get('q') or '').strip()
    # 법인 파라미터 — 미지정 시 로그인 사용자 법인
    legal_entity = (request.args.get('legal_entity') or '').strip() or me['subsdr']

    where  = ["m.delete_flag = 'N'", "m.category <> 'EMAIL_SEND'"]
    params = []

    # ── 법인 스코프 (전체 기준) ──────────────────────────────────────
    # sender_subsdr 가 해당 법인이거나, 수신 담당자가 해당 법인 소속인 경우 모두 표시
    where.append(
        "(m.sender_subsdr = %s"
        " OR m.receiver_user_id IN ("
        "     SELECT user_id FROM d_user_mst"
        "     WHERE subsdr_name = %s AND delete_flag = 'N'"
        " ))"
    )
    params += [legal_entity, legal_entity]

    # ── 탭별 추가 필터 ────────────────────────────────────────────────
    if tab == 'inbox':
        # 나에게 온 열린 이슈
        where.append("m.status IN ('OPEN','IN_PROGRESS','RESOLVED')")
        where.append("m.receiver_user_id = %s")
        params.append(me['user_id'])
    elif tab == 'outbox':
        # 내가 보낸 열린 이슈
        where.append("m.status IN ('OPEN','IN_PROGRESS','RESOLVED')")
        where.append("m.sender_user_id = %s")
        params.append(me['user_id'])
    elif tab == 'closed':
        where.append("m.status IN ('CLOSED','CANCELLED')")
    # tab == 'all' → 법인 전체, 상태 필터 없음 (open + closed 모두)

    if q:
        where.append(
            "(m.title ILIKE %s OR m.sender_user_name ILIKE %s"
            " OR m.receiver_user_name ILIKE %s"
            " OR EXISTS (SELECT 1 FROM d_issue_order o"
            "            WHERE o.issue_id = m.issue_id AND o.sales_order_no ILIKE %s))"
        )
        like = f"%{q}%"
        params += [like, like, like, like]

    sql = f"""
        SELECT m.issue_id, m.title, m.category, m.status,
               m.sender_user_id, m.sender_user_name,
               m.receiver_dept, m.receiver_user_id, m.receiver_user_name,
               m.due_date, m.total_amount, m.order_count,
               m.input_dt,
               (m.due_date IS NOT NULL AND m.due_date < CURRENT_DATE
                AND m.status IN ('OPEN','IN_PROGRESS','RESOLVED')) AS overdue
          FROM d_issue_mst m
         WHERE {' AND '.join(where)}
         ORDER BY
               CASE m.status
                   WHEN 'OPEN'        THEN 1
                   WHEN 'IN_PROGRESS' THEN 2
                   WHEN 'RESOLVED'    THEN 3
                   WHEN 'CLOSED'      THEN 4
                   ELSE 5
               END,
               m.due_date NULLS LAST,
               m.issue_id DESC
         LIMIT 500
    """
    try:
        rows = pg.query(sql, tuple(params))
        for r in rows:
            r['input_dt']     = r['input_dt'].strftime('%Y-%m-%d %H:%M') if r.get('input_dt') else None
            r['due_date']     = r['due_date'].strftime('%Y-%m-%d')       if r.get('due_date')  else None
            r['total_amount'] = float(r['total_amount'])                 if r.get('total_amount') is not None else 0
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception("list_issues failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 이슈 상세
# ============================================================================
@issue_bp.route('/issues/<int:issue_id>', methods=['GET'])
def get_issue(issue_id):
    err = require_login()
    if err:
        return err
    try:
        head = pg.query(
            "SELECT * FROM d_issue_mst WHERE issue_id = %s AND delete_flag = 'N'",
            (issue_id,)
        )
        if not head:
            return jsonify({'success': False, 'message': 'Issue not found.'}), 404
        m = head[0]

        orders = pg.query(
            "SELECT sales_order_no, line_no, customer_code, customer_name, "
            "model_code, order_qty, usd_amount, stage_snapshot, "
            "order_amount, currency_code "
            "FROM d_issue_order WHERE issue_id = %s ORDER BY sales_order_no, line_no",
            (issue_id,)
        )

        # BigQuery에서 현재 PROGRESS_STATUS 조회
        if orders:
            order_nos = list({o['sales_order_no'] for o in orders})
            nos_str = ', '.join(f"'{n}'" for n in order_nos)
            bq_sql = f"""
                SELECT SALES_ORDER_NO, MAX(PROGRESS_STATUS) AS current_stage
                FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE
                WHERE SALES_ORDER_NO IN ({nos_str})
                GROUP BY SALES_ORDER_NO
            """
            try:
                df_stage = run_query(bq_sql, query_name="Issue current stage")
                if df_stage is not None and not df_stage.empty:
                    stage_map = dict(zip(df_stage['SALES_ORDER_NO'], df_stage['current_stage']))
                else:
                    stage_map = {}
            except Exception:
                stage_map = {}
            for o in orders:
                o['current_stage'] = stage_map.get(o['sales_order_no'])
        comments = pg.query(
            "SELECT author_user_id, author_name, author_role, body, input_dt "
            "FROM d_issue_comment WHERE issue_id = %s ORDER BY input_dt",
            (issue_id,)
        )

        for c in comments:
            c['input_dt'] = c['input_dt'].strftime('%Y-%m-%d %H:%M') if c.get('input_dt') else None
        for o in orders:
            o['order_qty']    = float(o['order_qty'])    if o.get('order_qty')    is not None else None
            o['usd_amount']   = float(o['usd_amount'])   if o.get('usd_amount')   is not None else None
            o['order_amount'] = float(o['order_amount']) if o.get('order_amount') is not None else None

        m['due_date']     = m['due_date'].strftime('%Y-%m-%d') if m.get('due_date') else None
        m['input_dt']     = m['input_dt'].strftime('%Y-%m-%d %H:%M') if m.get('input_dt') else None
        m['update_dt']    = m['update_dt'].strftime('%Y-%m-%d %H:%M') if m.get('update_dt') else None
        m['total_amount'] = float(m['total_amount']) if m.get('total_amount') is not None else 0

        return jsonify({'success': True, 'data': {
            'issue': m, 'orders': orders, 'comments': comments
        }})
    except Exception as e:
        logger.exception("get_issue failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 상태 변경 (CAS)
# ============================================================================
@issue_bp.route('/issues/<int:issue_id>', methods=['PATCH'])
def patch_issue(issue_id):
    err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    me   = _me()

    new_status       = (data.get('status') or '').strip().upper()
    expected_status  = (data.get('expected_status') or '').strip().upper()
    expected_version = data.get('expected_version')
    resolution_note  = (data.get('resolution_note') or '').strip()

    if new_status not in _VALID_TRANSITIONS:
        return jsonify({'success': False, 'message': 'Invalid status.'}), 400
    if expected_status not in _VALID_TRANSITIONS:
        return jsonify({'success': False, 'message': 'expected_status is missing.'}), 400
    if new_status not in _VALID_TRANSITIONS.get(expected_status, set()):
        return jsonify({'success': False,
                        'message': f'Transition {expected_status} → {new_status} is not allowed.'}), 400
    if new_status == 'RESOLVED' and not resolution_note:
        return jsonify({'success': False, 'message': 'Please enter the resolution note.'}), 400
    if expected_version is None:
        return jsonify({'success': False, 'message': 'expected_version is missing.'}), 400

    try:
        cnt = pg.execute(
            """
            UPDATE d_issue_mst
               SET status = %s,
                   state_version = state_version + 1,
                   resolution_note = COALESCE(NULLIF(%s, ''), resolution_note),
                   update_dt = CURRENT_TIMESTAMP,
                   update_user_id = %s
             WHERE issue_id = %s
               AND status = %s
               AND state_version = %s
               AND delete_flag = 'N'
            """,
            (new_status, resolution_note, me['user_id'],
             issue_id, expected_status, expected_version)
        )
        if cnt == 0:
            return jsonify({'success': False, 'conflict': True,
                            'message': 'Another user has already changed the status. Please refresh and try again.'}), 409

        # Status change history comment
        comment_text = (
            f"Status changed: {expected_status} → {new_status}"
            + (f" · {resolution_note}" if resolution_note else "")
        )
        pg.execute(
            "INSERT INTO d_issue_comment (issue_id, author_user_id, author_name, author_role, body) "
            "VALUES (%s,%s,%s,'SYSTEM',%s)",
            (issue_id, me['user_id'], me['user_name'], comment_text)
        )
        _send_issue_notification(
            issue_id       = issue_id,
            actor_user_id  = me['user_id'],
            comment_body   = f"[{me['user_name']}] {comment_text}",
            subject_prefix = f'Status → {new_status}',
        )
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("patch_issue failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 코멘트 추가
# ============================================================================
@issue_bp.route('/issues/<int:issue_id>/comments', methods=['POST'])
def add_comment(issue_id):
    err = require_login()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    me   = _me()
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'success': False, 'message': 'Please enter a comment.'}), 400

    try:
        head = pg.query(
            "SELECT sender_user_id, receiver_user_id FROM d_issue_mst "
            "WHERE issue_id = %s AND delete_flag = 'N'", (issue_id,))
        if not head:
            return jsonify({'success': False, 'message': 'Issue not found.'}), 404

        role = 'SENDER' if head[0]['sender_user_id'] == me['user_id'] else \
               ('RECEIVER' if head[0]['receiver_user_id'] == me['user_id'] else 'SENDER')

        pg.execute(
            "INSERT INTO d_issue_comment (issue_id, author_user_id, author_name, author_role, body) "
            "VALUES (%s,%s,%s,%s,%s)",
            (issue_id, me['user_id'], me['user_name'], role, body)
        )
        _send_issue_notification(
            issue_id       = issue_id,
            actor_user_id  = me['user_id'],
            comment_body   = f"[{me['user_name']}] {body}",
            subject_prefix = 'Comment',
        )
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("add_comment failed")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# 필드 개별 수정 (receiver / due_date)
# ============================================================================
@issue_bp.route('/issues/<int:issue_id>/update-field', methods=['PATCH'])
def update_issue_field(issue_id):
    err = require_login()
    if err:
        return err

    data  = request.get_json(silent=True) or {}
    me    = _me()
    field = (data.get('field') or '').strip()
    value = data.get('value')

    if field not in ('receiver', 'due_date'):
        return jsonify({'success': False, 'message': f'Unsupported field: {field}'}), 400

    try:
        row = pg.query(
            "SELECT receiver_user_id, receiver_user_name, due_date "
            "FROM d_issue_mst WHERE issue_id = %s AND delete_flag = 'N'",
            (issue_id,)
        )
        if not row:
            return jsonify({'success': False, 'message': 'Issue not found.'}), 404

        old = row[0]

        if field == 'receiver':
            new_user_id   = (value.get('user_id')   or '').strip() if isinstance(value, dict) else ''
            new_user_name = (value.get('user_name')  or '').strip() if isinstance(value, dict) else ''
            if not new_user_id:
                return jsonify({'success': False, 'message': 'user_id is required.'}), 400

            pg.execute(
                """
                UPDATE d_issue_mst
                   SET receiver_user_id   = %s,
                       receiver_user_name = %s,
                       update_dt          = CURRENT_TIMESTAMP,
                       update_user_id     = %s
                 WHERE issue_id = %s AND delete_flag = 'N'
                """,
                (new_user_id, new_user_name, me['user_id'], issue_id)
            )

            old_name = old['receiver_user_name'] or old['receiver_user_id'] or '-'
            log_body = f"Receiver changed: {old_name} → {new_user_name} ({new_user_id})"

        else:  # due_date
            new_date = value if value else None
            pg.execute(
                """
                UPDATE d_issue_mst
                   SET due_date       = %s,
                       update_dt      = CURRENT_TIMESTAMP,
                       update_user_id = %s
                 WHERE issue_id = %s AND delete_flag = 'N'
                """,
                (new_date, me['user_id'], issue_id)
            )

            old_date = str(old['due_date']) if old['due_date'] else '-'
            log_body = f"Due date changed: {old_date} → {new_date or '-'}"

        # Thread 에 변경 이력 등록
        pg.execute(
            "INSERT INTO d_issue_comment (issue_id, author_user_id, author_name, author_role, body) "
            "VALUES (%s,%s,%s,'SYSTEM',%s)",
            (issue_id, me['user_id'], me['user_name'], log_body)
        )
        _send_issue_notification(
            issue_id       = issue_id,
            actor_user_id  = me['user_id'],
            comment_body   = f"[{me['user_name']}] {log_body}",
            subject_prefix = 'Updated',
        )

        logger.info(f"ISSUE #{issue_id} field '{field}' updated by {me['user_id']}: {log_body}")
        return jsonify({'success': True})

    except Exception as e:
        logger.exception("update_issue_field failed")
        return jsonify({'success': False, 'message': str(e)}), 500
