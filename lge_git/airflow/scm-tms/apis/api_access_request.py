"""
API Routes - JSON 데이터 엔드포인트
"""
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from utils.db_query import run_query, test_connection, dataframe_to_dict, logger
from queries.bigquery_queries_v2 import (
    QUERY_MAIN_DASHBOARD_KPI,
    QUERY_SHIPMENT_DAILY_TREND, QUERY_SHIPMENT_BY_ZONE,
    QUERY_SHIPMENT_BY_WAREHOUSE, QUERY_SHIPMENT_RAD_URGENCY,
    QUERY_ITEM_VOLUME_BY_TYPE, QUERY_ITEM_SHIPMENT_SUMMARY, QUERY_ITEM_MODEL_ANALYSIS,
    QUERY_LOAD_DAILY_TREND, QUERY_CARRIER_LIST, QUERY_LOAD_BY_CARRIER, QUERY_LOAD_BY_ROUTE,
    QUERY_LOADING_SHIPMENT_PER_LOAD, QUERY_LOADING_LEG_STRUCTURE,
    QUERY_LOADING_WITH_ROUTE, QUERY_LOADING_MULTI_LEG_ANALYSIS,
    QUERY_WAREHOUSE_RELEASE_STATUS, QUERY_WAREHOUSE_LEADTIME, QUERY_WAREHOUSE_PROCESSING,
    QUERY_COST_ADJUSTMENT_SUMMARY, QUERY_COST_ADJUSTMENT_BY_REASON, QUERY_COST_WITH_FREIGHT,
    QUERY_NETWORK_SHIPMENT_ZONE, QUERY_NETWORK_ROUTE_ZONE, QUERY_NETWORK_COMBINED,
    QUERY_LOAD_LEADTIME_BY_LEGAL_ENTITY,
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================================
# Helper Functions
# ============================================================================
def get_date_range():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not start_date:
        today = datetime.now()
        first_of_last_month = today.replace(day=1) - timedelta(days=1)
        start_date = first_of_last_month.replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    end_date_exclusive = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    return start_date, end_date_exclusive


def get_filters():
    start_date, end_date = get_date_range()
    legal_entity = request.args.get('legal_entity') or (
        request.get_json(silent=True) or {}
    ).get('legal_entity', 'ALL')
    return {
        'start_date': start_date,
        'end_date': end_date,
        'legal_entity': legal_entity,
        'carrier': request.args.get('carrier', 'ALL'),
    }


# ---- 표준 JSON 응답 헬퍼 ----
def ok(df):
    return jsonify({'success': True, 'data': dataframe_to_dict(df)})


def err(e):
    logger.exception(f"❌ API Error:")
    return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Dashboard KPI
# ============================================================================
@api_bp.route('/dashboard/kpi', methods=['GET'])
def get_dashboard_kpi():
    try:
        filters = get_filters()
        logger.info(f"📊 /api/dashboard/kpi - {filters}")
        df = run_query(QUERY_MAIN_DASHBOARD_KPI, filters, query_name="Dashboard KPI")
        if df is not None and len(df) > 0:
            return jsonify({'success': True, 'data': dataframe_to_dict(df)[0]})
        return jsonify({'success': False, 'message': 'No data available'}), 404
    except Exception as e:
        return err(e)


# ============================================================================
# Shipment Analysis
# ============================================================================
@api_bp.route('/shipment/daily-trend', methods=['GET'])
def get_shipment_daily_trend():
    try:
        return ok(run_query(QUERY_SHIPMENT_DAILY_TREND, get_filters(), query_name="Shipment Daily Trend"))
    except Exception as e:
        return err(e)


@api_bp.route('/shipment/by-zone', methods=['GET'])
def get_shipment_by_zone():
    try:
        return ok(run_query(QUERY_SHIPMENT_BY_ZONE, get_filters(), query_name="Shipment by Zone"))
    except Exception as e:
        return err(e)


@api_bp.route('/shipment/by-dc', methods=['GET'])
def get_shipment_by_dc():
    try:
        return ok(run_query(QUERY_SHIPMENT_BY_WAREHOUSE, get_filters(), query_name="Shipment by Warehouse"))
    except Exception as e:
        return err(e)


@api_bp.route('/shipment/rad-urgency', methods=['GET'])
def get_shipment_rad_urgency():
    try:
        return ok(run_query(QUERY_SHIPMENT_RAD_URGENCY, get_filters(), query_name="Shipment RAD Urgency"))
    except Exception as e:
        return err(e)


# ============================================================================
# Item / Container Analysis
# ============================================================================
@api_bp.route('/item/volume-by-type', methods=['GET'])
def get_item_volume_by_type():
    try:
        return ok(run_query(QUERY_ITEM_VOLUME_BY_TYPE, get_filters(), query_name="Item Volume by Type"))
    except Exception as e:
        return err(e)


@api_bp.route('/item/shipment-summary', methods=['GET'])
def get_item_shipment_summary():
    try:
        return ok(run_query(QUERY_ITEM_SHIPMENT_SUMMARY, get_filters(), query_name="Item Shipment Summary"))
    except Exception as e:
        return err(e)


@api_bp.route('/item/model-analysis', methods=['GET'])
def get_item_model_analysis():
    try:
        return ok(run_query(QUERY_ITEM_MODEL_ANALYSIS, get_filters(), query_name="Item Model Analysis"))
    except Exception as e:
        return err(e)


# ============================================================================
# Load Analysis
# ============================================================================
@api_bp.route('/load/daily-trend', methods=['GET'])
def get_load_daily_trend():
    try:
        return ok(run_query(QUERY_LOAD_DAILY_TREND, get_filters(), query_name="Load Daily Trend"))
    except Exception as e:
        return err(e)


@api_bp.route('/load/carriers', methods=['GET'])
def get_carrier_list():
    try:
        df = run_query(QUERY_CARRIER_LIST, get_filters(), query_name="Carrier List")
        carriers = df['CARR_CD'].dropna().tolist() if not df.empty else []
        return jsonify({'success': True, 'data': carriers})
    except Exception as e:
        return err(e)


@api_bp.route('/load/by-carrier', methods=['GET'])
def get_load_by_carrier():
    try:
        return ok(run_query(QUERY_LOAD_BY_CARRIER, get_filters(), query_name="Load by Carrier"))
    except Exception as e:
        return err(e)


@api_bp.route('/load/by-route', methods=['GET'])
def get_load_by_route():
    try:
        return ok(run_query(QUERY_LOAD_BY_ROUTE, get_filters(), query_name="Load by Route"))
    except Exception as e:
        return err(e)


# ============================================================================
# Loading (Shipment-Load) Analysis
# ============================================================================
@api_bp.route('/loading/shipment-per-load', methods=['GET'])
def get_loading_shipment_per_load():
    try:
        return ok(run_query(QUERY_LOADING_SHIPMENT_PER_LOAD, get_filters(), query_name="Shipment per Load"))
    except Exception as e:
        return err(e)


@api_bp.route('/loading/leg-structure', methods=['GET'])
def get_loading_leg_structure():
    try:
        return ok(run_query(QUERY_LOADING_LEG_STRUCTURE, get_filters(), query_name="Leg Structure"))
    except Exception as e:
        return err(e)


@api_bp.route('/loading/with-route', methods=['GET'])
def get_loading_with_route():
    try:
        return ok(run_query(QUERY_LOADING_WITH_ROUTE, get_filters(), query_name="Loading with Route"))
    except Exception as e:
        return err(e)


@api_bp.route('/loading/multi-leg-analysis', methods=['GET'])
def get_loading_multi_leg_analysis():
    try:
        return ok(run_query(QUERY_LOADING_MULTI_LEG_ANALYSIS, get_filters(), query_name="Multi-leg Analysis"))
    except Exception as e:
        return err(e)


# ============================================================================
# Warehouse Analysis
# ============================================================================
@api_bp.route('/warehouse/release-status', methods=['GET'])
def get_warehouse_release_status():
    try:
        return ok(run_query(QUERY_WAREHOUSE_RELEASE_STATUS, get_filters(), query_name="Warehouse Release Status"))
    except Exception as e:
        return err(e)


@api_bp.route('/warehouse/leadtime', methods=['GET'])
def get_warehouse_leadtime():
    try:
        return ok(run_query(QUERY_WAREHOUSE_LEADTIME, get_filters(), query_name="Warehouse Leadtime"))
    except Exception as e:
        return err(e)


@api_bp.route('/warehouse/processing', methods=['GET'])
def get_warehouse_processing():
    try:
        return ok(run_query(QUERY_WAREHOUSE_PROCESSING, get_filters(), query_name="Warehouse Processing"))
    except Exception as e:
        return err(e)


# ============================================================================
# Cost Analysis
# ============================================================================
@api_bp.route('/cost/adjustment-summary', methods=['GET'])
def get_cost_adjustment_summary():
    try:
        return ok(run_query(QUERY_COST_ADJUSTMENT_SUMMARY, get_filters(), query_name="Cost Adjustment Summary"))
    except Exception as e:
        return err(e)


@api_bp.route('/cost/adjustment-by-reason', methods=['GET'])
def get_cost_adjustment_by_reason():
    try:
        return ok(run_query(QUERY_COST_ADJUSTMENT_BY_REASON, get_filters(), query_name="Cost Adjustment by Reason"))
    except Exception as e:
        return err(e)


@api_bp.route('/cost/with-freight', methods=['GET'])
def get_cost_with_freight():
    try:
        return ok(run_query(QUERY_COST_WITH_FREIGHT, get_filters(), query_name="Cost with Freight"))
    except Exception as e:
        return err(e)


# ============================================================================
# Network Analysis
# ============================================================================
@api_bp.route('/network/shipment-zone', methods=['GET'])
def get_network_shipment_zone():
    try:
        return ok(run_query(QUERY_NETWORK_SHIPMENT_ZONE, get_filters(), query_name="Network Shipment Zone"))
    except Exception as e:
        return err(e)


@api_bp.route('/network/route-zone', methods=['GET'])
def get_network_route_zone():
    try:
        return ok(run_query(QUERY_NETWORK_ROUTE_ZONE, get_filters(), query_name="Network Route Zone"))
    except Exception as e:
        return err(e)


@api_bp.route('/network/combined', methods=['GET'])
def get_network_combined():
    try:
        return ok(run_query(QUERY_NETWORK_COMBINED, get_filters(), query_name="Network Combined"))
    except Exception as e:
        return err(e)


# ============================================================================
# Leadtime Analysis
# ============================================================================
@api_bp.route('/leadtime/data', methods=['GET'])
def get_leadtime_data():
    try:
        return ok(run_query(QUERY_LOAD_LEADTIME_BY_LEGAL_ENTITY, get_filters(), query_name="Load Leadtime"))
    except Exception as e:
        return err(e)


# ============================================================================
# Utilities
# ============================================================================
@api_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'success': True, 'status': 'healthy', 'timestamp': datetime.now().isoformat()})


@api_bp.route('/test-connection', methods=['GET'])
def test_bigquery_connection():
    try:
        if test_connection():
            return jsonify({'success': True, 'message': 'BigQuery connection successful'})
        return jsonify({'success': False, 'message': 'BigQuery connection failed'}), 500
    except Exception as e:
        return err(e)
