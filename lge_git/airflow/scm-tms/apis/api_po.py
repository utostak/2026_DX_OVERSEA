"""
API Routes - PO Tracking (M_PO_TRACKING)
"""
from flask import Blueprint, jsonify, request

from utils.db_query import run_query, dataframe_to_dict, logger
from queries.po_queries import (
    QUERY_PO_ACTIVE_FLOW, QUERY_PO_ACTIVE_RAW, QUERY_PO_DATA_TIMESTAMP,
)

po_bp = Blueprint('po', __name__, url_prefix='/api/po')


# ============================================================================
# Helper
# ============================================================================
def get_po_filters():
    return {
        'legal_entity': request.args.get('legal_entity', 'ALL'),
        'division':     request.args.get('division', '[ALL]'),
    }


def ok(df):
    return jsonify({'success': True, 'data': dataframe_to_dict(df)})


def err(e):
    logger.exception(f"❌ API Error:")
    return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Endpoints
# ============================================================================
@po_bp.route('/active-flow', methods=['GET'])
def get_po_active_flow():
    try:
        filters = get_po_filters()
        logger.info(f"📦 /api/po/active-flow - {filters}")
        return ok(run_query(QUERY_PO_ACTIVE_FLOW, filters, query_name="PO Active Flow"))
    except Exception as e:
        return err(e)


@po_bp.route('/active-raw', methods=['GET'])
def get_po_active_raw():
    try:
        filters = get_po_filters()
        logger.info(f"📦 /api/po/active-raw - {filters}")
        return ok(run_query(QUERY_PO_ACTIVE_RAW, filters, query_name="PO Active Raw"))
    except Exception as e:
        return err(e)


@po_bp.route('/data-timestamp', methods=['GET'])
def get_po_data_timestamp():
    try:
        from utils.subsdr_cache import get_subsdr_info
        filters = get_po_filters()
        logger.info(f"📦 /api/po/data-timestamp - {filters}")
        df = run_query(QUERY_PO_DATA_TIMESTAMP, filters, query_name="PO Data Timestamp")
        log_ts = None
        if df is not None and not df.empty:
            val = df.iloc[0]['data_timestamp_utc']
            if val is not None:
                log_ts = str(val)
        timezone = None
        legal_entity = filters.get('legal_entity', 'ALL')
        if legal_entity and legal_entity != 'ALL':
            info = get_subsdr_info(legal_entity)
            timezone = info.get('timezone') or None
        return jsonify({'success': True, 'log_ts': log_ts, 'timezone': timezone})
    except Exception as e:
        return err(e)
