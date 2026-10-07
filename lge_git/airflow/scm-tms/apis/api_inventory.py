"""
API Routes - Current Inventory (D_PROD_INV)
"""
from flask import Blueprint, jsonify, request
from utils.auth_check import require_login

from utils.db_query import run_query, dataframe_to_dict, logger
from queries.inventory_queries import (
    QUERY_INV_CURRENT_SUMMARY,
    QUERY_INV_CURRENT_RAW,
    QUERY_INV_DATA_TIMESTAMP,
)

inv_bp = Blueprint('inventory', __name__, url_prefix='/api/inventory')


def get_inv_filters():
    return {
        'legal_entity': request.args.get('legal_entity', 'ALL'),
        'division':     request.args.get('division', '[ALL]'),
    }


def ok(df):
    return jsonify({'success': True, 'data': dataframe_to_dict(df)})


def err(e):
    logger.exception(f"❌ API Error:")
    return jsonify({'success': False, 'error': str(e)}), 500


@inv_bp.route('/current-summary', methods=['GET'])
def get_current_summary():
    try:
        filters = get_inv_filters()
        logger.info(f"📦 /api/inventory/current-summary - {filters}")
        return ok(run_query(QUERY_INV_CURRENT_SUMMARY, filters, query_name="Inventory Current Summary"))
    except Exception as e:
        return err(e)


@inv_bp.route('/current-raw', methods=['GET'])
def get_current_raw():
    try:
        filters = get_inv_filters()
        logger.info(f"📦 /api/inventory/current-raw - {filters}")
        return ok(run_query(QUERY_INV_CURRENT_RAW, filters, query_name="Inventory Current Raw"))
    except Exception as e:
        return err(e)


@inv_bp.route('/data-timestamp', methods=['GET'])
def get_data_timestamp():
    try:
        from utils.subsdr_cache import get_subsdr_info
        filters = get_inv_filters()
        logger.info(f"📦 /api/inventory/data-timestamp - {filters}")
        df = run_query(QUERY_INV_DATA_TIMESTAMP, filters, query_name="Inventory Data Timestamp")
        log_ts = None
        if df is not None and not df.empty:
            val = df.iloc[0]['data_timestamp_utc']
            if val is not None:
                log_ts = str(val)
        # 법인 timezone 조회 (ALL이면 None → 프론트에서 UTC 표시)
        timezone = None
        legal_entity = filters.get('legal_entity', 'ALL')
        if legal_entity and legal_entity != 'ALL':
            info = get_subsdr_info(legal_entity)
            timezone = info.get('timezone') or None
        return jsonify({'success': True, 'log_ts': log_ts, 'timezone': timezone})
    except Exception as e:
        return err(e)
