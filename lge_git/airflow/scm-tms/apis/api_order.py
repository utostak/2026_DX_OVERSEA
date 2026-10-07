"""
API Routes - Order (M_SO_LINE)
"""
from flask import Blueprint, jsonify, request, session, Response, stream_with_context
from datetime import datetime, timedelta
import calendar
import traceback

from utils.db_query import run_query, dataframe_to_dict, dataframe_iter_rows, logger
from utils.subsdr_cache import get_currency_list
from utils.pg_db import pg
from utils.mailer import send_email, smtp_configured
from utils.auth_check import require_login, require_menu_access
from queries.order_queries import (
    QUERY_ORDER_KPI, QUERY_ORDER_RAW,
)
from queries.active_orders_queries import (
    QUERY_ORDER_ACTIVE_FLOW, QUERY_ORDER_ACTIVE_RAW,
    QUERY_ORDER_HOLD_DETAIL, QUERY_ORDER_TYPE_LIST,
    QUERY_ORDER_INBOUND_FLOW, QUERY_ORDER_BILLTO_BIZ_LIST,
    QUERY_ORDER_INBOUND_RAW, QUERY_ORDER_IOD_RAW,
    QUERY_ORDER_DELIVERY_FLOW, QUERY_IOD_REPORT, QUERY_IOD_REPORT_TARGET, QUERY_FLOW_REPORT,
    QUERY_ORDER_TARGET_USD, QUERY_CONTAINER_DETAIL, QUERY_CONTAINER_DETAIL_LINES,
    QUERY_DATA_TIMESTAMP,
)

order_bp = Blueprint('order', __name__, url_prefix='/api/order')


# ============================================================================
# Helper
# ============================================================================
def get_order_filters():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    end_date_exclusive = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'start_date': start_date,
        'end_date': end_date_exclusive,
        'legal_entity': request.args.get('legal_entity', 'ALL'),
        'division': request.args.get('division', '[ALL]'),
        'order_status': request.args.get('order_status', 'ALL'),
        'line_status': request.args.get('line_status', 'ALL'),
        'line_category': request.args.get('line_category', 'ALL'),
        'order_category': request.args.get('order_category', 'ALL'),
        'currency': request.args.get('currency', 'USD'),
    }


def get_active_filters():
    from datetime import date
    # 기준년월: 프론트에서 YYYY-MM 형식으로 전달, 없으면 전날 기준 당월
    base_ym = request.args.get('base_ym', '')
    if not base_ym:
        yesterday = date.today() - timedelta(days=1)
        base_ym = yesterday.strftime('%Y-%m')
    return {
        'rad_all':      True,
        'rad_last_day': '2099-12-31',
        'base_ym':      base_ym,
        'legal_entity': request.args.get('legal_entity', 'ALL'),
        'prdt_grp_cd':  request.args.get('prdt_grp_cd', '[ALL]'),
        'division':     request.args.get('division', '[ALL]'),
        'order_type':   request.args.get('order_type', '[ALL]'),
        'biz_name':     request.args.get('biz_name', '[ALL]'),
        'currency':     request.args.get('currency', 'USD'),
    }


def ok(df):
    return jsonify({'success': True, 'data': dataframe_to_dict(df)})


def ok_stream(df):
    """대용량 DataFrame을 JSON 스트리밍으로 반환 (MemoryError 방지)"""
    import json

    def generate(df):
        yield '{"success":true,"data":['
        first = True
        for row in dataframe_iter_rows(df):
            if not first:
                yield ','
            yield json.dumps(row, ensure_ascii=False, default=str)
            first = False
        yield ']}'

    return Response(
        stream_with_context(generate(df)),
        mimetype='application/json',
        headers={'X-Accel-Buffering': 'no'},  # nginx proxy buffering 비활성화
    )


def err(e):
    logger.error(f"❌ API Error: {e}\n{traceback.format_exc()}")
    return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Endpoints
# ============================================================================
@order_bp.route('/kpi', methods=['GET'])
def get_order_kpi():
    try:
        filters = get_order_filters()
        logger.info(f"📊 /api/order/kpi - {filters}")
        return ok(run_query(QUERY_ORDER_KPI, filters, query_name="Order KPI"))
    except Exception as e:
        return err(e)


@order_bp.route('/raw', methods=['GET'])
def get_order_raw():
    try:
        filters = get_order_filters()
        logger.info(f"📊 /api/order/raw - {filters}")
        return ok(run_query(QUERY_ORDER_RAW, filters, query_name="Order Raw"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-flow', methods=['GET'])
def get_order_active_flow():
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-flow - {filters}")
        return ok(run_query(QUERY_ORDER_ACTIVE_FLOW, filters, query_name="Order Active Flow"))
    except Exception as e:
        return err(e)


@order_bp.route('/prdt-grp-list', methods=['GET'])
def get_prdt_grp_list():
    """Product Group 목록 (d_product_mst 기준, 법인 필터 지원)"""
    try:
        legal_entity = request.args.get('legal_entity', '').strip()
        if legal_entity and legal_entity.upper() != 'ALL':
            rows = pg.query(
                "SELECT DISTINCT product_group_code AS prdt_grp_cd"
                "  FROM d_product_mst"
                " WHERE subsdr_name = %s"
                " ORDER BY prdt_grp_cd",
                (legal_entity,)
            )
        else:
            rows = pg.query(
                "SELECT DISTINCT product_group_code AS prdt_grp_cd"
                "  FROM d_product_mst"
                " ORDER BY prdt_grp_cd"
            )
        return jsonify({'success': True, 'data': [r['prdt_grp_cd'] for r in rows if r.get('prdt_grp_cd')]})
    except Exception as e:
        return err(e)


@order_bp.route('/active-delivery', methods=['GET'])
def get_order_active_delivery():
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-delivery - {filters}")
        rows = run_query(QUERY_ORDER_DELIVERY_FLOW, filters, query_name="Order Delivery Flow")
        rows = dataframe_to_dict(rows)
        # target_amt 는 모든 행에 동일하게 포함되므로 첫 행에서 추출 후 별도 키로 분리
        target_usd = 0.0
        if rows:
            tv = rows[0].get('target_amt') or rows[0].get('TARGET_AMT')
            target_usd = float(tv) if tv is not None else 0.0
            for r in rows:
                r.pop('target_amt', None); r.pop('TARGET_AMT', None)
        base_ym = filters.get('base_ym', '')
        logger.info(f"📊 /api/order/active-delivery target_usd={target_usd:,.0f} base_ym={base_ym}")
        return jsonify({'success': True, 'data': rows,
                        'target_amount': round(target_usd), 'base_ym': base_ym})
    except Exception as e:
        return err(e)


@order_bp.route('/active-flow-report', methods=['GET'])
def get_order_active_flow_report():
    """Order/Shipping 카드 상세 보고서 — PROGRESS_STATUS 지정, TEAM × BIZ 별 오더금액."""
    try:
        filters = get_active_filters()
        progress_status = request.args.get('progress_status', '')
        if not progress_status:
            return jsonify({'success': False, 'error': 'progress_status required'}), 400
        filters['progress_status'] = progress_status
        logger.info(f"📊 /api/order/active-flow-report - status={progress_status} {filters}")
        return ok(run_query(QUERY_FLOW_REPORT, filters, query_name="Flow Report"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-inbound', methods=['GET'])
def get_order_active_inbound():
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-inbound - {filters}")
        return ok(run_query(QUERY_ORDER_INBOUND_FLOW, filters, query_name="Order Inbound Flow"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-inbound-raw', methods=['GET'])
def get_order_active_inbound_raw():
    """Inbound 단계 상세 라인 (M_SO_LINE_BACK).
    back_status='ALL'(기본)이면 현재 필터 기준 전체 라인을 반환한다.
    프론트엔드는 이 전체 결과를 한 번만 받아 카드 클릭 시 클라이언트 사이드 필터만 적용한다."""
    try:
        filters = get_active_filters()
        filters['back_status'] = request.args.get('back_status', 'ALL')
        logger.info(f"📊 /api/order/active-inbound-raw - {filters}")
        return ok(run_query(QUERY_ORDER_INBOUND_RAW, filters, query_name="Order Inbound Raw"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-iod-raw', methods=['GET'])
def get_order_active_iod_raw():
    """당월 마감(IOD / MTD_Closed) 주문 Raw 데이터 (M_SO_LINE SALES_DATE 기준 당월)."""
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-iod-raw - {filters}")
        return ok(run_query(QUERY_ORDER_IOD_RAW, filters, query_name="Order IOD Raw"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-iod-report', methods=['GET'])
def get_order_active_iod_report():
    """IOD 보고서 — BQ 매출(team × biz) + BQ target(biz, 선택 통화 환산) 병합."""
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-iod-report - {filters}")

        # BigQuery: team_name × billto_biz_name 별 매출
        df = run_query(QUERY_IOD_REPORT, filters, query_name="IOD Report")
        sales_rows = dataframe_to_dict(df)

        # BigQuery: billto_biz_name 별 target — 현지통화 target 을 선택 통화로 환산 (메인 IOD 카드와 동일 로직)
        df_tgt = run_query(QUERY_IOD_REPORT_TARGET, filters, query_name="IOD Report Target")
        target_rows = dataframe_to_dict(df_tgt)

        return jsonify({'success': True, 'data': {
            'sales': sales_rows, 'targets': target_rows,
            'base_ym': filters['base_ym'], 'currency': filters['currency'],
        }})
    except Exception as e:
        logger.error(f"❌ active-iod-report error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@order_bp.route('/container-detail', methods=['GET'])
def get_container_detail():
    """Container 상세 정보 조회 (M_PO_TRACKING 기준)."""
    try:
        subsdr_nm = request.args.get('subsdr_nm', '')
        container_no = request.args.get('container_no', '')
        
        if not subsdr_nm or not container_no:
            return jsonify({'success': False, 'message': 'subsdr_nm and container_no are required'}), 400
        
        params = {
            'subsdr_nm': subsdr_nm,
            'container_no': container_no
        }
        
        logger.info(f"📦 /api/order/container-detail - subsdr_nm={subsdr_nm}, container_no={container_no}")
        df = run_query(QUERY_CONTAINER_DETAIL, params, query_name="Container Detail")
        
        if df.empty:
            return jsonify({'success': False, 'message': 'Container not found'}), 404
        
        result = dataframe_to_dict(df)
        return jsonify({'success': True, 'data': result[0] if result else None})
    except Exception as e:
        logger.error(f"❌ container-detail error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@order_bp.route('/container-detail-lines', methods=['GET'])
def get_container_detail_lines():
    """Container 내 모델별 PO Line 목록 조회."""
    try:
        subsdr_nm = request.args.get('subsdr_nm', '')
        container_no = request.args.get('container_no', '')

        if not subsdr_nm or not container_no:
            return jsonify({'success': False, 'message': 'subsdr_nm and container_no are required'}), 400

        params = {'subsdr_nm': subsdr_nm, 'container_no': container_no}
        logger.info(f"📦 /api/order/container-detail-lines - subsdr_nm={subsdr_nm}, container_no={container_no}")
        df = run_query(QUERY_CONTAINER_DETAIL_LINES, params, query_name="Container Detail Lines")

        return jsonify({'success': True, 'data': dataframe_to_dict(df)})
    except Exception as e:
        logger.error(f"❌ container-detail-lines error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@order_bp.route('/send-grid-email', methods=['POST'])
def send_grid_email():
    """그리드 내용을 Excel 첨부 + HTML 본문으로 로그인 사용자에게 메일 발송.

    요청 JSON:
      { "title": "Active Orders",
        "filename": "active_orders.xlsx",
        "xlsx_base64": "<base64>",              # (선택) AG Grid 에서 생성한 xlsx
        "columns": ["A","B", ...],               # HTML 본문용 헤더
        "rows": [["v1","v2", ...], ...],         # HTML 본문용 데이터 (표시분)
        "total_rows": 1234 }                     # 전체 행수(표시분과 다를 수 있음)
    """
    # ── 로그인 확인
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401

    if not smtp_configured():
        return jsonify({'success': False,
                        'message': '메일 서버(SMTP)가 설정되지 않았습니다. 관리자에게 문의하세요.'}), 503

    # ── 수신자 = 로그인 사용자 이메일 (세션 우선, 없으면 DB 조회)
    to_email = (session.get('email') or '').strip()
    if not to_email:
        try:
            rows = pg.query(
                "SELECT email FROM d_user_mst WHERE subsdr_name=%s AND user_id=%s AND delete_flag='N'",
                (session.get('subsdr_name'), session.get('user_id'))
            )
            if rows and rows[0].get('email'):
                to_email = rows[0]['email'].strip()
                session['email'] = to_email
        except Exception as e:
            logger.warning(f"send-grid-email 이메일 조회 실패: {e}")

    if not to_email:
        return jsonify({'success': False,
                        'message': '로그인 사용자의 이메일 주소가 없습니다. 사용자 정보를 확인하세요.'}), 400

    try:
        data       = request.get_json(force=True) or {}
        legal_entity = (data.get('legal_entity') or '').strip()
        title      = (data.get('title') or 'LIW Grid').strip()
        filename   = (data.get('filename') or 'grid_export.xlsx').strip()
        xlsx_b64   = data.get('xlsx_base64')
        columns    = data.get('columns') or []
        rows       = data.get('rows') or []
        total_rows = data.get('total_rows', len(rows))
        user_name  = session.get('user_name') or session.get('user_id')

        # 사용자 입력 값 (프론트에서 전달)
        to_override      = (data.get('to_email') or '').strip()
        cc_override      = (data.get('cc_email') or '').strip()
        bcc_override     = (data.get('bcc_email') or '').strip()  # 로그인 계정 히든 참조
        subject_override = (data.get('subject') or '').strip()
        note             = (data.get('note') or '').strip()   # 사용자 메모 (본문 상단 추가)

        # 수신자: 사용자 입력 → 세션 이메일 → DB 조회 순
        recipient    = to_override or to_email
        cc_recipient = cc_override or None
        bcc_recipient = bcc_override or to_email or None  # BCC: 프론트 전달값 또는 세션 이메일

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        subject = subject_override or f"[LIW] {title} — {now_str} ({total_rows:,} rows)"

        # ── HTML 본문 ──────────────────────────────────────────────
        MAX_BODY_ROWS = 300
        shown = rows[:MAX_BODY_ROWS]

        def esc(v):
            s = '' if v is None else str(v)
            return (s.replace('&', '&amp;').replace('<', '&lt;')
                     .replace('>', '&gt;').replace('"', '&quot;'))

        note_block = (f'<div style="background:#fff8e1;border-left:4px solid #f59e0b;'
                      f'padding:10px 14px;margin-bottom:14px;font-size:13px;border-radius:4px;">'
                      f'<b>Note:</b> {esc(note)}</div>') if note else ''

        thead = ''.join(f'<th style="border:1px solid #ddd;padding:5px 8px;'
                        f'background:#A50034;color:#fff;font-size:12px;text-align:left;'
                        f'white-space:nowrap;">{esc(c)}</th>' for c in columns)
        trows = []
        for i, r in enumerate(shown):
            bg = '#ffffff' if i % 2 == 0 else '#f7f5f3'
            tds = ''.join(f'<td style="border:1px solid #e5e5e5;padding:4px 8px;'
                          f'font-size:12px;white-space:nowrap;">{esc(v)}</td>' for v in r)
            trows.append(f'<tr style="background:{bg};">{tds}</tr>')
        table_html = (f'<table style="border-collapse:collapse;border:1px solid #ddd;">'
                      f'<thead><tr>{thead}</tr></thead><tbody>{"".join(trows)}</tbody></table>')

        more_note = ''
        if total_rows > len(shown):
            more_note = (f'<p style="color:#888;font-size:12px;">※ This email shows {len(shown):,} rows. '
                         f'Please refer to the attached Excel file for all {total_rows:,} rows.</p>')

        html_body = f"""
        <div style="font-family:Segoe UI,Arial,sans-serif;color:#1c1c1c;">
          <h2 style="color:#A50034;margin:0 0 4px;">LIW · {esc(title)}</h2>
          <p style="margin:0 0 2px;font-size:13px;">Requested by: <b>{esc(user_name)}</b></p>
          <p style="margin:0 0 12px;font-size:13px;">Generated: {now_str} · Total {total_rows:,} rows</p>
          {note_block}
          {'<p style="font-size:13px;">📎 An Excel file is attached.</p>' if xlsx_b64 else ''}
          {more_note}
          {table_html}
          <p style="color:#aaa;font-size:11px;margin-top:16px;">This email was automatically sent by the LIW system.</p>
        </div>"""

        note_text = f"[Note] {note}\n\n" if note else ''
        text_lines = ['\t'.join(str(c) for c in columns)]
        for r in shown:
            text_lines.append('\t'.join('' if v is None else str(v) for v in r))
        text_body = f"{title} ({total_rows} rows)\n{note_text}\n" + '\n'.join(text_lines)

        # ── 첨부 (xlsx) ───────────────────────────────────────────
        attachments = []
        if xlsx_b64:
            attachments.append({
                'filename': filename,
                'content': xlsx_b64,
                'is_base64': True,
                'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })

        send_email(
            to_addrs=recipient,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachments=attachments,
            from_name=user_name,
            from_addr=to_email or None,   # 로그인 사용자 이메일을 From 주소로 사용
            cc_addrs=cc_recipient or None,
            bcc_addrs=bcc_recipient or None,
        )


        # ── LGEPH Teams 알림 발송 ──────────────────────────────────
        # 이메일 발송 성공 후, 현재 선택 법인이 LGEPH일 때만 발송
        # Teams 알림이 실패해도 이메일 발송 결과는 성공으로 유지
        if legal_entity == 'LGEPH':
            try:
                from utils.teams_liw_lgeph import send_liw_lgeph_message

                teams_message = (
                    f"<b>LIW Send To Notification</b><br><br>"
                    f"<b>Sent by:</b> {user_name} ({to_email})<br>"
                    f"<b>Sent at:</b> {now_str}<br>"
                    f"<b>Subject:</b> {subject}<br>"
                    f"<b>Recipients:</b> {recipient}"
                )

                teams_sent = send_liw_lgeph_message(
                    message=teams_message
                )

                if teams_sent:
                    logger.info(
                        f"LGEPH Teams 알림 발송 완료: "
                        f"title={title}, rows={total_rows}"
                    )
                else:
                    logger.warning(
                        f"LGEPH Teams 알림 발송 실패: "
                        f"title={title}, rows={total_rows}"
                    )

            except Exception as teams_error:
                logger.warning(
                    f"LGEPH Teams 알림 처리 오류 "
                    f"(이메일 발송 성공 유지): {teams_error}"
                )
        # ───────────────────────────────────────────────────────────

        # ── d_issue_mst + d_issue_order 에 EMAIL_SEND 이력 저장 ──
        try:
            orders = data.get('orders') or []  # [{sales_order_no, line_no, ...}]
            with pg.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO d_issue_mst
                            (title, category, description, status,
                             sender_subsdr, sender_user_id, sender_user_name,
                             order_count, mail_to, mail_cc, mail_subject, input_user_id)
                        VALUES (%s,'EMAIL_SEND',%s,'CLOSED', %s,%s,%s, %s,%s,%s,%s, %s)
                        RETURNING issue_id
                        """,
                        (
                            subject, note or None,
                            session.get('subsdr_name'),
                            session.get('user_id'),
                            session.get('user_name') or session.get('user_id'),
                            total_rows, recipient, cc_recipient or None, subject,
                            session.get('user_id'),
                        )
                    )
                    issue_id = cur.fetchone()[0]

                    for o in orders:
                        so = str(o.get('sales_order_no') or '').strip()
                        ln = str(o.get('line_no') or '*').strip() or '*'
                        if not so:
                            continue
                        cur.execute(
                            """
                            INSERT INTO d_issue_order
                                (issue_id, sales_order_no, line_no,
                                 customer_code, customer_name, model_code,
                                 order_qty, usd_amount, stage_snapshot,
                                 order_amount, currency_code)
                            VALUES (%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                issue_id, so, ln,
                                o.get('customer_code'), o.get('customer_name'),
                                o.get('model_code'),
                                o.get('order_qty') or None,
                                o.get('usd_amount') or None,
                                o.get('stage') or None,
                                o.get('order_amount') or None,
                                o.get('currency_code') or None,
                            )
                        )
            logger.info(f"EMAIL_SEND issue #{issue_id} saved: {len(orders)} orders, to={recipient}")
        except Exception as _ie:
            logger.warning(f"EMAIL_SEND issue insert 실패 (무시): {_ie}")
        # ────────────────────────────────────────────────────────

        return jsonify({'success': True, 'to': recipient, 'cc': cc_recipient or '',
                        'attached': bool(xlsx_b64), 'rows': total_rows})
    except Exception as e:
        logger.error(f"❌ send-grid-email error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Failed to send email: {e}'}), 500


@order_bp.route('/active-raw', methods=['GET'])
def get_order_active_raw():
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-raw - {filters}")
        return ok_stream(run_query(QUERY_ORDER_ACTIVE_RAW, filters, query_name="Order Active Raw"))
    except Exception as e:
        return err(e)


@order_bp.route('/active-hold', methods=['GET'])
def get_order_active_hold():
    try:
        filters = get_active_filters()
        logger.info(f"📊 /api/order/active-hold - {filters}")
        return ok(run_query(QUERY_ORDER_HOLD_DETAIL, filters, query_name="Order Hold Detail"))
    except Exception as e:
        return err(e)


@order_bp.route('/order-types', methods=['GET'])
def get_order_types():
    try:
        legal_entity = request.args.get('legal_entity', 'ALL')
        df = run_query(QUERY_ORDER_TYPE_LIST, {'legal_entity': legal_entity}, query_name="Order Type List")
        types = df['ORDER_TYPE_NAME'].dropna().tolist() if df is not None and not df.empty else []
        return jsonify({'success': True, 'data': types})
    except Exception as e:
        return err(e)


@order_bp.route('/billto-biz-names', methods=['GET'])
def get_billto_biz_names():
    try:
        legal_entity = request.args.get('legal_entity', 'ALL')
        sql = (
            "SELECT DISTINCT billto_biz_name"
            "  FROM d_billto_biz_mst"
            " WHERE billto_biz_name IS NOT NULL AND billto_biz_name <> ''"
        )
        params = []
        if legal_entity and legal_entity != 'ALL':
            sql += " AND subsdr_name = %s"
            params.append(legal_entity)
        sql += " ORDER BY billto_biz_name"
        rows = pg.query(sql, params if params else None)
        names = [r['billto_biz_name'] for r in rows]
        return jsonify({'success': True, 'data': names})
    except Exception as e:
        return err(e)


@order_bp.route('/data-timestamp', methods=['GET'])
def get_data_timestamp():
    try:
        from utils.subsdr_cache import get_subsdr_info
        legal_entity = request.args.get('legal_entity', 'ALL')
        df = run_query(QUERY_DATA_TIMESTAMP, {'legal_entity': legal_entity}, query_name="Data Timestamp")
        log_ts = None
        if df is not None and not df.empty:
            val = df.iloc[0]['LOG_TS']
            if val is not None:
                log_ts = str(val)
        # 법인 timezone 조회 (ALL 이면 None → 프론트에서 UTC 표시)
        timezone = None
        if legal_entity and legal_entity != 'ALL':
            info = get_subsdr_info(legal_entity)
            timezone = info.get('timezone') or None
        return jsonify({'success': True, 'log_ts': log_ts, 'timezone': timezone})
    except Exception as e:
        return err(e)


@order_bp.route('/currencies', methods=['GET'])
def get_currencies():
    try:
        legal_entity = request.args.get('legal_entity', 'ALL')
        # PostgreSQL d_subsdr_mst.currency_list 에서 조회 (subsdr_cache 캐시 활용)
        if legal_entity and legal_entity != 'ALL':
            currencies = get_currency_list(legal_entity)
        else:
            currencies = []
        # USD 는 항상 첫번째, 나머지 알파벳 정렬
        currencies = [c for c in currencies if c != 'USD']
        currencies = ['USD'] + sorted(currencies)
        return jsonify({'success': True, 'data': currencies})
    except Exception as e:
        return err(e)
