"""
apis/api_mail_file.py — 메일 배치 첨부(ETA 변경 목록) 다운로드 (로그인 필요)
  GET /mail-download/eta                 — 다운로드 안내 페이지(HTML)
  GET /api/mail-file/eta/download        — ETA_CHANGE_QUERY 기반 엑셀 생성/다운로드

별도 파일 저장 테이블(m_mail_file) 없이, 요청 시점에 ETA_CHANGE_QUERY 를
실행하여 엑셀을 생성해 내려준다. 다운로드 이력/횟수는 m_web_log(MAIL_DOWNLOAD)로 집계.
"""
import io
import json
import os
import math
import logging
from datetime import datetime, timezone, timedelta

import pandas as pd

from flask import (Blueprint, render_template, request, session,
                   send_file, abort)
from utils.pg_db import pg

logger = logging.getLogger(__name__)
mail_file_bp = Blueprint('mail_file', __name__)

KST = timezone(timedelta(hours=9))
DEFAULT_SUBSDR = 'LGEPH'

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


# ══════════════════════════════════════════════════════════════════════════
# 엑셀 생성 유틸 (기존 liw_jobs 모듈에서 복사 — 외부 의존 제거)
# ══════════════════════════════════════════════════════════════════════════
def _is_na(v):
    """None / NaN 여부"""
    if v is None:
        return True
    try:
        return isinstance(v, float) and math.isnan(v)
    except Exception:
        return False


def _fmt_date(v):
    """date/datetime/str → 'YYYY-MM-DD'"""
    if v is None:
        return '-'
    try:
        if hasattr(v, 'strftime'):
            return v.strftime('%Y-%m-%d')
        return str(v)[:10]
    except Exception:
        return str(v)


# ── ETA 변경 목록 엑셀 정의 ────────────────────────────────────────────────
ETA_EXCEL_COLUMNS = [
    ('PO_NO',              'PO No.'),
    ('PO_LINE_NO',         'Line'),
    ('PRODUCT_GROUP_CODE', 'Product Group'),
    ('TO_INV_ORG',         'To Inv Org'),
    ('MDL_SFFX_CD',        'Model'),
    ('PO_STATUS',          'PO Status'),
    ('QTY',                'Qty'),
    ('HOUSE_BL_NO',        'House BL No.'),
    ('BL_DATE',            'BL Date'),
    ('CONTAINER_NO',       'Container No.'),
    ('CONTAINER_SIZE',     'Container Size'),
    ('MASTER_BL_NO',       'Master BL No.'),
    ('INVOICE_NO',         'Invoice No.'),
    ('INVOICE_DATE',       'Invoice Date'),
    ('POL_ETD_DATE',       'POL ETD'),
    ('POL_ATD_DATE',       'POL ATD'),
    ('POD_ETA_DATE',       'POD ETA'),
    ('POD_ATA_DATE',       'POD ATA'),
    ('CY1_ETA_DATE',       'CY ETA'),
    ('CY1_ATA_DATE',       'CY ATA'),
    ('CY1_ETD_DATE',       'CY ETD'),
    ('CY1_ATD_DATE',       'CY ATD'),
    ('DFF_DAYS',           'ETA Change (Days)'),
    ('FDEST_ETA_DATE',     'FDEST ETA (New)'),
    ('BF_FDEST_ETA_DATE',  'FDEST ETA (Prev)'),
    ('CHANGE_YN',          'Changed'),
]


def _eta_diff_int(rec):
    """DFF_DAYS → int (없으면 None)"""
    v = rec.get('DFF_DAYS')
    if _is_na(v):
        return None
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None


def build_eta_excel_bytes(df):
    """ETA 변경 목록 DataFrame 을 표시 라벨/포맷으로 정리하여 xlsx 바이트로 반환."""
    records = df.to_dict('records')
    rows = []
    for rec in records:
        row = {}
        for col, label in ETA_EXCEL_COLUMNS:
            if col == 'QTY':
                v = rec.get(col)
                try:
                    row[label] = None if _is_na(v) else int(round(float(v)))
                except (ValueError, TypeError):
                    row[label] = v
            elif col == 'DFF_DAYS':
                row[label] = _eta_diff_int(rec)
            elif col.endswith('_DATE') or col == 'P_PPT':
                v = rec.get(col)
                row[label] = None if _is_na(v) else _fmt_date(v)
            else:
                v = rec.get(col)
                row[label] = None if _is_na(v) else v
        rows.append(row)

    out_df = pd.DataFrame(rows, columns=[label for _, label in ETA_EXCEL_COLUMNS])

    # Product Group → To Inv Org → Model 알파벳 오름차순 정렬
    pg_col  = next((label for col, label in ETA_EXCEL_COLUMNS if col == 'PRODUCT_GROUP_CODE'), None)
    org_col = next((label for col, label in ETA_EXCEL_COLUMNS if col == 'TO_INV_ORG'), None)
    mdl_col = next((label for col, label in ETA_EXCEL_COLUMNS if col == 'MDL_SFFX_CD'), None)
    sort_by = [c for c in (pg_col, org_col, mdl_col) if c and c in out_df.columns]
    if sort_by:
        out_df = out_df.sort_values(by=sort_by, key=lambda s: s.str.upper(), ignore_index=True)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out_df.to_excel(writer, index=False, sheet_name='ETA List')
        ws = writer.sheets['ETA List']
        for idx, (_, label) in enumerate(ETA_EXCEL_COLUMNS, start=1):
            max_len = len(str(label))
            for cell_val in out_df[label].astype(str).values[:200]:
                max_len = max(max_len, len(cell_val))
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = min(max_len + 2, 40)
    buf.seek(0)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
# Container Yard Delay 목록 쿼리/엑셀 정의
# 기존 ETA/Hold 로직은 수정하지 않고 Container Yard 기능만 추가
# ══════════════════════════════════════════════════════════════════════════
CONTAINER_YARD_PROJECT = os.getenv(
    'PROJECT_ID',
    'pjt-lge-oversea-sales-olap',
)

CONTAINER_YARD_DATASET = os.getenv(
    'DATASET_ID',
    'SCM_OLAP',
)

CONTAINER_YARD_DEFAULT_WAIT_DAYS = 5

CONTAINER_YARD_EXCEL_COLUMNS = [
    ('PRODUCT_GROUP_CODE', 'Product Group'),
    ('TO_INV_ORG',         'To Inv Org'),
    ('MDL_SFFX_CD',        'Model'),
    ('QTY',                 'Qty'),
    ('CONTAINER_NO',        'Container No.'),
    ('CY1_ATA_DATE',        'CY ATA Date'),
    ('CY1_ETD_DATE', 'CY ETD Date'),
    ('WAIT_DAYS',           'Waiting Days'),
]

CONTAINER_YARD_DELAY_QUERY = f"""
SELECT
      COALESCE(PG.PRODUCT_GROUP_CODE, 'None') AS PRODUCT_GROUP_CODE
    , T.TO_INV_ORG
    , T.MDL_SFFX_CD
    , T.QTY
    , T.CNTR_NO AS CONTAINER_NO
    , DATE(T.CY1_ATA_DATE) AS CY1_ATA_DATE
    , DATE(T.CY1_ETD_DATE) AS CY1_ETD_DATE
    , DATE_DIFF(
          DATE(@base_date),
          DATE(T.CY1_ATA_DATE),
          DAY
      ) AS WAIT_DAYS
FROM `{CONTAINER_YARD_PROJECT}`.{CONTAINER_YARD_DATASET}.M_PO_TRACKING T
LEFT JOIN `{CONTAINER_YARD_PROJECT}`.PRD_OLAP.D_NPT_MDL_NEW_MST M
  ON T.MDL_SFFX_CD = M.MDL_SFFX_CD
LEFT JOIN `{CONTAINER_YARD_PROJECT}`.{CONTAINER_YARD_DATASET}.REF_D_PRODUCT_MST PG
  ON T.SUBSDR_NM = PG.SUBSDR_NAME
 AND M.PROD_LVL4_CD = PG.PRODUCT_CODE
WHERE T.SUBSDR_NM = @subsdr_nm
  AND TRIM(T.PO_STATUS) NOT IN (
      'Cancelled',
      'F Dest Arrival'
  )
  AND T.CY1_ATA_DATE IS NOT NULL
  AND T.CY1_ATD_DATE IS NULL
ORDER BY
      PRODUCT_GROUP_CODE
    , T.TO_INV_ORG
    , T.MDL_SFFX_CD
    , WAIT_DAYS DESC
    , T.CNTR_NO
"""


def _get_container_yard_wait_days(subsdr_name):
    try:
        rows = pg.query(
            """
            SELECT config_info
              FROM d_subsdr_mst
             WHERE subsdr_name = %s
               AND use_yn = 'Y'
            """,
            (subsdr_name,),
        )

        if not rows:
            return CONTAINER_YARD_DEFAULT_WAIT_DAYS

        config_info = rows[0].get('config_info')

        if not config_info:
            return CONTAINER_YARD_DEFAULT_WAIT_DAYS

        if isinstance(config_info, str):
            config_info = json.loads(config_info)

        wait_days = int(
            config_info.get(
                'container_yard_wait_days',
                CONTAINER_YARD_DEFAULT_WAIT_DAYS,
            )
        )

        if wait_days < 0:
            return CONTAINER_YARD_DEFAULT_WAIT_DAYS

        return wait_days

    except Exception:
        logger.exception(
            'Container Yard wait days 조회 실패 '
            '(subsdr=%s)',
            subsdr_name,
        )
        return CONTAINER_YARD_DEFAULT_WAIT_DAYS


def _parse_container_yard_wait_days(subsdr_name):
    raw_value = (
        request.args.get('wait_days')
        or ''
    ).strip()

    if raw_value:
        try:
            wait_days = int(raw_value)

            if wait_days >= 0:
                return wait_days

        except (TypeError, ValueError):
            pass

    return _get_container_yard_wait_days(
        subsdr_name
    )


def build_container_yard_excel_bytes(df):
    """Container Yard Delay DataFrame을 메일과 동일한 7개 컬럼의 xlsx로 반환."""
    records = df.to_dict('records')
    rows = []

    for rec in records:
        row = {}

        for col, label in CONTAINER_YARD_EXCEL_COLUMNS:
            v = rec.get(col)

            if col in ('QTY', 'WAIT_DAYS'):
                try:
                    row[label] = None if _is_na(v) else int(round(float(v)))
                except (ValueError, TypeError):
                    row[label] = v

            elif col in ('CY1_ATA_DATE', 'CY1_ETD_DATE'):
                row[label] = None if _is_na(v) else _fmt_date(v)

            else:
                row[label] = None if _is_na(v) else v

        rows.append(row)

    out_df = pd.DataFrame(
        rows,
        columns=[label for _, label in CONTAINER_YARD_EXCEL_COLUMNS],
    )

    if not out_df.empty:
        out_df = out_df.sort_values(
            by=[
                'Product Group',
                'To Inv Org',
                'Model',
                'Waiting Days',
                'Container No.',
            ],
            ascending=[True, True, True, False, True],
            key=lambda s: (
                s
                if s.name == 'Waiting Days'
                else s.fillna('').astype(str).str.upper()
            ),
            ignore_index=True,
        )

    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        sheet_name = 'Container Yard Delay'
        out_df.to_excel(
            writer,
            index=False,
            sheet_name=sheet_name,
        )

        ws = writer.sheets[sheet_name]
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

        for idx, (_, label) in enumerate(
            CONTAINER_YARD_EXCEL_COLUMNS,
            start=1,
        ):
            max_len = len(str(label))

            for cell_val in out_df[label].astype(str).values[:200]:
                max_len = max(max_len, len(cell_val))

            ws.column_dimensions[
                ws.cell(row=1, column=idx).column_letter
            ].width = min(max_len + 2, 40)

    buf.seek(0)
    return buf.getvalue()


def _container_yard_download_total(
    subsdr_name,
    ppt_str,
    wait_days,
):
    try:
        rows = pg.query(
            """
            SELECT COUNT(*) AS cnt
              FROM m_web_log
             WHERE log_type = 'MAIL_DOWNLOAD'
               AND log_detail = %s
            """,
            (
                f"CONTAINER_YARD|"
                f"{subsdr_name}|"
                f"{ppt_str}|"
                f"{wait_days}",
            ),
        )

        return int(rows[0]['cnt']) if rows else 0

    except Exception:
        return 0


# ── Hold Order 목록 쿼리/엑셀 정의 ─────────────────────────────────────────
HOLD_PROJECT = os.getenv('PROJECT_ID', 'pjt-lge-oversea-sales-olap')

HOLD_COLUMNS = [
    ('BACK_ORDER_HOLD',   'Back Order'),
    ('CREDIT_HOLD',       'Credit'),
    ('OVERDUE_HOLD',      'Overdue'),
    ('CUSTOMER_HOLD',     'Customer'),
    ('PAYTERM_TERM_HOLD', 'Payterm'),
    ('FP_HOLD',           'FP'),
    ('MINIMUM_HOLD',      'Minimum'),
    ('FUTURE_HOLD',       'Future'),
    ('RESERVE_HOLD',      'Reserve'),
    ('MANUAL_HOLD',       'Manual'),
    ('AUTO_PENDING_HOLD', 'Auto Pending'),
    ('ETC_HOLD',          'Etc'),
]

HOLD_QUERY = f"""
SELECT T.SALES_ORDER_NO
     , T.SALES_ORDER_LINE_NO
     , T.ORDER_TYPE_NAME
     , T.MODEL_CODE
     , T.ORDER_QTY
     , T.ORDER_AMOUNT
     , T.BILL_TO_CUSTOMER_NAME
     , T.SHIP_TO_CUSTOMER_NAME
     , T.BILLTO_BIZ_NAME
     , T.ORDERED_DATE
     , DATE(T.HOLD_DATE) AS HOLD_DATE
     , T.HOLD_IN_DAYS AS HOLD_DAYS
     , T.BACK_ORDER_HOLD
     , T.CREDIT_HOLD
     , T.OVERDUE_HOLD
     , T.CUSTOMER_HOLD
     , T.PAYTERM_TERM_HOLD
     , T.FP_HOLD
     , T.MINIMUM_HOLD
     , T.FUTURE_HOLD
     , T.RESERVE_HOLD
     , T.MANUAL_HOLD
     , T.AUTO_PENDING_HOLD
     , T.ETC_HOLD
  FROM `{HOLD_PROJECT}`.SCM_OLAP.M_SO_LINE T
 WHERE T.OPEN_FLAG = 'Y'
   AND T.PROGRESS_STATUS = 'HOLD'
   AND T.SUBSDR_NAME = @subsdr_nm
 ORDER BY
       T.ORDERED_DATE
     , T.SALES_ORDER_NO
     , T.SALES_ORDER_LINE_NO
"""

HOLD_TABLE_COLUMNS = [
    ('STATUS',                  'Status'),
    ('SHIP_TO_CUSTOMER_NAME',   'Ship-To'),
    ('BILL_TO_CUSTOMER_NAME',   'Bill-To'),
    ('MODEL_CODE',              'Model'),
    ('ORDER_QTY',               'Qty'),
    ('ORDER_AMOUNT',            'Amount'),
    ('ORDERED_DATE',            'Ordered Date'),
    ('HOLD_DATE',               'Hold Date'),
    ('HOLD_DAYS',               'Hold Days'),
    ('HOLD_TYPES',              'Hold Types'),
    ('SALES_ORDER_NO',          'SO No.'),
    ('SALES_ORDER_LINE_NO',     'Line'),
]


def _is_y(v):
    if _is_na(v):
        return False
    return str(v).strip().upper() == 'Y'


def _hold_types_text(rec):
    labels = [label for col, label in HOLD_COLUMNS if _is_y(rec.get(col))]
    return ', '.join(labels) if labels else '-'

HOLD_STATUS_THRESHOLD_DAYS = 4

def _get_hold_status_text(hold_days):
    if _is_na(hold_days):
        return 'Hold'

    try:
        hold_days = int(round(float(hold_days)))
    except (TypeError, ValueError):
        return 'Hold'

    return 'Hold'

def build_hold_excel_bytes(records):
    """Hold Order 레코드 목록을 표시 라벨/포맷으로 정리하여 xlsx 바이트로 반환."""
    rows = []
    for rec in records:
        row = {}
        for col, label in HOLD_TABLE_COLUMNS:
            if col == 'STATUS':
                row[label] = _get_hold_status_text(
                    rec.get('HOLD_DAYS')
                )

            elif col == 'HOLD_TYPES':
                row[label] = _hold_types_text(rec)

            elif col in ('ORDER_QTY', 'ORDER_AMOUNT'):
                v = rec.get(col)
                try:
                    row[label] = None if _is_na(v) else int(round(float(v)))
                except (ValueError, TypeError):
                    row[label] = v
            elif col.endswith('_DATE'):
                v = rec.get(col)
                row[label] = None if _is_na(v) else _fmt_date(v)
            else:
                v = rec.get(col)
                row[label] = None if _is_na(v) else v
        rows.append(row)

    out_df = pd.DataFrame(rows, columns=[label for _, label in HOLD_TABLE_COLUMNS])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        out_df.to_excel(writer, index=False, sheet_name='Hold List')
        ws = writer.sheets['Hold List']
        for idx, (_, label) in enumerate(HOLD_TABLE_COLUMNS, start=1):
            max_len = len(str(label))
            for cell_val in out_df[label].astype(str).values[:200]:
                max_len = max(max_len, len(cell_val))
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = min(max_len + 2, 50)
    buf.seek(0)
    return buf.getvalue()


# ── 파라미터 파싱 ─────────────────────────────────────────────────────────
def _parse_params():
    """요청 파라미터에서 법인(le)·기준일(ppt) 파싱. ppt 미지정 시 오늘(KST).
    Returns: (subsdr_nm, ppt_date, ppt_str)
    """
    subsdr = (request.args.get('le') or DEFAULT_SUBSDR).strip()
    ppt    = (request.args.get('ppt') or '').strip()
    if ppt:
        try:
            ppt_date = datetime.strptime(ppt[:10].replace('-', ''), '%Y%m%d').date()
        except ValueError:
            ppt_date = datetime.now(KST).date()
    else:
        ppt_date = datetime.now(KST).date()
    return subsdr, ppt_date, ppt_date.strftime('%Y%m%d')


def _download_total(subsdr_nm, ppt_str) -> int:
    """m_web_log 기준 해당 파일(법인+기준일) 총 다운로드 횟수."""
    try:
        rows = pg.query(
            """
            SELECT COUNT(*) AS cnt
              FROM m_web_log
             WHERE log_type = 'MAIL_DOWNLOAD'
               AND log_detail = %s
            """,
            (f"{subsdr_nm}|{ppt_str}",)
        )
        return int(rows[0]['cnt']) if rows else 0
    except Exception:
        return 0


# ── 다운로드 안내 페이지 ──────────────────────────────────────────────────
@mail_file_bp.route('/mail-download/eta', methods=['GET'])
def mail_download_page():
    """로그인 사용자에게 파일 정보를 보여주고 다운로드 버튼을 제공."""
    subsdr, ppt_date, ppt_str = _parse_params()
    file_info = {
        'file_name':   f"ETA_List_{subsdr}_{ppt_str}.xlsx",
        'subsdr_name': subsdr,
        'ppt_str':     ppt_date.strftime('%Y-%m-%d'),
        'le':          subsdr,
        'ppt':         ppt_str,
    }
    return render_template('mail_download.html', file=file_info,
                           download_count=_download_total(subsdr, ppt_str),
                           active_page='mail-download')


# ── 실제 파일 다운로드 + 로그 ─────────────────────────────────────────────
@mail_file_bp.route('/api/mail-file/eta/download', methods=['GET'])
def mail_file_download():
    subsdr, ppt_date, ppt_str = _parse_params()

    try:
        from config.bigquery import run_query
        from queries.eta_change_queries import ETA_CHANGE_QUERY
        df = run_query(ETA_CHANGE_QUERY, params={'subsdr_nm': subsdr, 'p_ppt': ppt_date})
    except Exception:
        logger.exception("ETA 목록 조회 실패 (le=%s, ppt=%s)", subsdr, ppt_str)
        abort(500)

    if df is None or df.empty:
        return render_template('mail_download.html', file={
            'file_name': f"ETA_List_{subsdr}_{ppt_str}.xlsx",
            'subsdr_name': subsdr, 'ppt_str': ppt_date.strftime('%Y-%m-%d'),
            'le': subsdr, 'ppt': ppt_str, 'empty': True,
        }, download_count=_download_total(subsdr, ppt_str),
           active_page='mail-download'), 404

    # ETA_CHANGE_QUERY 는 이미 CHANGE_YN='Y' 만 반환하므로 df 전체를 엑셀로 생성
    excel_bytes = build_eta_excel_bytes(df)
    file_name = f"ETA_List_{subsdr}_{ppt_str}.xlsx"

    # 다운로드 로그 기록 (m_web_log) — log_detail = '법인|기준일'
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        pg.insert('m_web_log', {
            'log_ym':       datetime.now().strftime('%Y%m'),
            'log_type':     'MAIL_DOWNLOAD',
            'subsdr_name':  session.get('subsdr_name'),
            'user_id':      session.get('user_id'),
            'user_name':    session.get('user_name'),
            'menu_id':      'mail-download',
            'page_id':      '_',
            'request_path': request.path,
            'log_detail':   f"{subsdr}|{ppt_str}",
            'ip_address':   ip,
        })
    except Exception:
        logger.exception("다운로드 로그 기록 실패 (le=%s, ppt=%s)", subsdr, ppt_str)

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=file_name,
        mimetype=XLSX_MIME,
    )


# ══════════════════════════════════════════════════════════════════════════
# Hold Order 목록 다운로드 (M_SO_LINE, PROGRESS_STATUS='HOLD')
#   GET /mail-download/hold            — 다운로드 안내 페이지(HTML)
#   GET /api/mail-file/hold/download   — HOLD_QUERY 기반 엑셀 생성/다운로드
# ══════════════════════════════════════════════════════════════════════════
def _hold_download_total(subsdr_nm, ppt_str) -> int:
    """m_web_log 기준 해당 Hold 파일(법인+기준일) 총 다운로드 횟수."""
    try:
        rows = pg.query(
            """
            SELECT COUNT(*) AS cnt
              FROM m_web_log
             WHERE log_type = 'MAIL_DOWNLOAD'
               AND log_detail = %s
            """,
            (f"HOLD|{subsdr_nm}|{ppt_str}",)
        )
        return int(rows[0]['cnt']) if rows else 0
    except Exception:
        return 0


@mail_file_bp.route('/mail-download/hold', methods=['GET'])
def mail_download_hold_page():
    """로그인 사용자에게 Hold 파일 정보를 보여주고 다운로드 버튼을 제공."""
    subsdr, ppt_date, ppt_str = _parse_params()
    biz = (request.args.get('biz') or '').strip()

    download_api = (
        f"/api/mail-file/hold/download"
        f"?le={subsdr}"
        f"&ppt={ppt_str}"
    )

    if biz:
        from urllib.parse import quote
        download_api += f"&biz={quote(biz)}"

    file_info = {
        'file_name': f"Hold_List_{subsdr}_{ppt_str}.xlsx",
        'subsdr_name': subsdr,
        'ppt_str': ppt_date.strftime('%Y-%m-%d'),
        'le': subsdr,
        'ppt': ppt_str,
        'download_api': download_api,
    }

    return render_template(
        'mail_download.html',
        file=file_info,
        download_count=_hold_download_total(
            subsdr,
            ppt_str,
        ),
        active_page='mail-download',
    )


@mail_file_bp.route('/api/mail-file/hold/download', methods=['GET'])
def mail_file_hold_download():
    subsdr, ppt_date, ppt_str = _parse_params()

    try:
        from config.bigquery import run_query

        df = run_query(
            HOLD_QUERY,
            params={
                'subsdr_nm': subsdr,
            },
        )

    except Exception:
        logger.exception(
            "Hold 목록 조회 실패 (le=%s)",
            subsdr,
        )
        abort(500)

    biz = (request.args.get('biz') or '').strip()

    if df is not None and not df.empty and biz and biz.upper() != 'ALL':
        biz_groups = [
            value.strip()
            for value in biz.split('|')
            if value.strip()
        ]

        if biz_groups:
            df = df[
                df['BILLTO_BIZ_NAME']
                .fillna('')
                .astype(str)
                .isin(biz_groups)
            ]

    if df is None or df.empty:
        return render_template(
            'mail_download.html',
            file={
                'file_name': f"Hold_List_{subsdr}_{ppt_str}.xlsx",
                'subsdr_name': subsdr,
                'ppt_str': ppt_date.strftime('%Y-%m-%d'),
                'le': subsdr,
                'ppt': ppt_str,
                'empty': True,
            },
            download_count=_hold_download_total(
                subsdr,
                ppt_str,
            ),
            active_page='mail-download',
        ), 404

    excel_bytes = build_hold_excel_bytes(df.to_dict('records'))
    file_name = f"Hold_List_{subsdr}_{ppt_str}.xlsx"

    # 다운로드 로그 기록 (m_web_log) — log_detail = 'HOLD|법인|기준일'
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        pg.insert('m_web_log', {
            'log_ym':       datetime.now().strftime('%Y%m'),
            'log_type':     'MAIL_DOWNLOAD',
            'subsdr_name':  session.get('subsdr_name'),
            'user_id':      session.get('user_id'),
            'user_name':    session.get('user_name'),
            'menu_id':      'mail-download',
            'page_id':      '_',
            'request_path': request.path,
            'log_detail':   f"HOLD|{subsdr}|{ppt_str}",
            'ip_address':   ip,
        })
    except Exception:
        logger.exception("다운로드 로그 기록 실패 (le=%s, ppt=%s)", subsdr, ppt_str)

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=file_name,
        mimetype=XLSX_MIME,
    )


# ══════════════════════════════════════════════════════════════════════════
# Container Yard Delay 목록 다운로드
#   GET /mail-download/container-yard
#   GET /api/mail-file/container-yard/download
# ══════════════════════════════════════════════════════════════════════════
@mail_file_bp.route(
    '/mail-download/container-yard',
    methods=['GET'],
)
def mail_download_container_yard_page():
    subsdr, ppt_date, ppt_str = _parse_params()
    wait_days = _parse_container_yard_wait_days(subsdr)

    file_info = {
        'file_name': (
            f"Container_Yard_Delay_List_"
            f"{subsdr}_{ppt_str}.xlsx"
        ),
        'subsdr_name': subsdr,
        'ppt_str': ppt_date.strftime('%Y-%m-%d'),
        'le': subsdr,
        'ppt': ppt_str,
        'wait_days': wait_days,
        'download_api': (
            f"/api/mail-file/container-yard/download"
            f"?le={subsdr}"
            f"&ppt={ppt_str}"
            f"&wait_days={wait_days}"
        ),
    }

    return render_template(
        'mail_download.html',
        file=file_info,
        download_count=_container_yard_download_total(
            subsdr,
            ppt_str,
            wait_days,
        ),
        active_page='mail-download',
    )


@mail_file_bp.route(
    '/api/mail-file/container-yard/download',
    methods=['GET'],
)
def mail_file_container_yard_download():
    subsdr, ppt_date, ppt_str = _parse_params()
    wait_days = _parse_container_yard_wait_days(subsdr)

    download_api = (
        f"/api/mail-file/container-yard/download"
        f"?le={subsdr}"
        f"&ppt={ppt_str}"
        f"&wait_days={wait_days}"
    )

    try:
        from config.bigquery import run_query

        df = run_query(
            CONTAINER_YARD_DELAY_QUERY,
            params={
                'subsdr_nm': subsdr,
                'base_date': ppt_date.strftime('%Y-%m-%d'),
            },
        )

    except Exception:
        logger.exception(
            'Container Yard Delay 목록 조회 실패 '
            '(le=%s, ppt=%s, wait_days=%s)',
            subsdr,
            ppt_str,
            wait_days,
        )
        abort(500)

    if df is None or df.empty:
        return render_template(
            'mail_download.html',
            file={
                'file_name': (
                    f"Container_Yard_Delay_List_"
                    f"{subsdr}_{ppt_str}.xlsx"
                ),
                'subsdr_name': subsdr,
                'ppt_str': ppt_date.strftime('%Y-%m-%d'),
                'le': subsdr,
                'ppt': ppt_str,
                'wait_days': wait_days,
                'download_api': download_api,
                'empty': True,
            },
            download_count=_container_yard_download_total(
                subsdr,
                ppt_str,
                wait_days,
            ),
            active_page='mail-download',
        ), 404

    excel_bytes = build_container_yard_excel_bytes(df)
    file_name = (
        f"Container_Yard_Delay_List_"
        f"{subsdr}_{ppt_str}.xlsx"
    )

    log_detail = (
        f"CONTAINER_YARD|"
        f"{subsdr}|"
        f"{ppt_str}|"
        f"{wait_days}"
    )

    try:
        ip = request.headers.get(
            'X-Forwarded-For',
            request.remote_addr or '',
        )

        if ',' in ip:
            ip = ip.split(',')[0].strip()

        pg.insert('m_web_log', {
            'log_ym':       datetime.now().strftime('%Y%m'),
            'log_type':     'MAIL_DOWNLOAD',
            'subsdr_name':  session.get('subsdr_name'),
            'user_id':      session.get('user_id'),
            'user_name':    session.get('user_name'),
            'menu_id':      'mail-download',
            'page_id':      '_',
            'request_path': request.path,
            'log_detail':   log_detail,
            'ip_address':   ip,
        })

    except Exception:
        logger.exception(
            'Container Yard Delay 다운로드 로그 기록 실패 '
            '(le=%s, ppt=%s, wait_days=%s)',
            subsdr,
            ppt_str,
            wait_days,
        )

    return send_file(
        io.BytesIO(excel_bytes),
        as_attachment=True,
        download_name=file_name,
        mimetype=XLSX_MIME,
    )
