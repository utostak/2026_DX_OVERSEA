"""
API Routes - OBS LMD (M_OBS_SO_LINE)
"""
from flask import Blueprint, jsonify, request
from datetime import date, timedelta
import traceback

from utils.db_query import run_query, dataframe_to_dict, logger
from queries.obs_lmd_queries import QUERY_OBS_IRAD, QUERY_OBS_LT, QUERY_OBS_RAW, QUERY_OBS_LMSP_LIST

obs_bp = Blueprint('obs', __name__, url_prefix='/api/obs')


# ============================================================================
# Helper
# ============================================================================
def get_obs_filters():
    base_ym = request.args.get('base_ym', '')
    if not base_ym:
        yesterday = date.today() - timedelta(days=1)
        base_ym = yesterday.strftime('%Y-%m')
    return {
        'base_ym':      base_ym,
        'legal_entity': request.args.get('legal_entity', 'ALL'),
        'division':     request.args.get('division', '[ALL]'),
        'lmsp_name':    request.args.get('lmsp_name', '[ALL]'),
    }


def ok(df):
    return jsonify({'success': True, 'data': dataframe_to_dict(df)})


def err(e):
    logger.error(f"❌ API Error: {e}\n{traceback.format_exc()}")
    return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Endpoints
# ============================================================================
@obs_bp.route('/irad', methods=['GET'])
def get_obs_irad():
    """최초 배송요구일 준수율 (IRAD%) — period 별 집계"""
    try:
        filters = get_obs_filters()
        logger.info(f"📊 /api/obs/irad - {filters}")
        return ok(run_query(QUERY_OBS_IRAD, filters, query_name="OBS IRAD"))
    except Exception as e:
        return err(e)


@obs_bp.route('/lt', methods=['GET'])
def get_obs_lt():
    """배송 리드타임 (배송LT / 주문전송LT) — period 별 집계"""
    try:
        filters = get_obs_filters()
        logger.info(f"📊 /api/obs/lt - {filters}")
        return ok(run_query(QUERY_OBS_LT, filters, query_name="OBS LT"))
    except Exception as e:
        return err(e)


@obs_bp.route('/raw', methods=['GET'])
def get_obs_raw():
    """화면 하단 Raw Data 그리드 — 기준월 한 달치 전체 (건수 제한 없음)"""
    try:
        filters = get_obs_filters()
        logger.info(f"📊 /api/obs/raw - {filters}")
        return ok(run_query(QUERY_OBS_RAW, filters, query_name="OBS Raw"))
    except Exception as e:
        return err(e)


@obs_bp.route('/lmsp-list', methods=['GET'])
def get_obs_lmsp_list():
    """3PL(LMSP) 필터 옵션 목록"""
    try:
        legal_entity = request.args.get('legal_entity', 'ALL')
        rows = run_query(QUERY_OBS_LMSP_LIST, {'legal_entity': legal_entity}, query_name="OBS LMSP List")
        rows = dataframe_to_dict(rows)
        return jsonify({'success': True, 'data': [r['LMSP_NAME'] for r in rows if r.get('LMSP_NAME')]})
    except Exception as e:
        return err(e)
