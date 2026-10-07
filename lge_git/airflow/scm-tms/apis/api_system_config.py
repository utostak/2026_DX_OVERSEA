"""
apis/api_system_config.py 
  d_menu_mst      : GET/POST/PUT/DELETE  /api/sysconfig/menu
  d_user_type_mst : GET/POST/PUT/DELETE  /api/sysconfig/usertype
  d_subsdr_mst    : GET/POST/PUT/DELETE  /api/sysconfig/subsdr
"""
import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from psycopg2.extras import Json as PgJson
from utils.pg_db import pg
from utils.auth_check import require_menu_access, require_menu_edit

logger       = logging.getLogger(__name__)
sysconfig_bp = Blueprint('sysconfig', __name__, url_prefix='/api/sysconfig')


def _parse_jsonb(val):
    """JSONB 
    """
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return PgJson(val) 
    s = str(val).strip()
    if not s or s.lower() == 'null':
        return None
    try:
        parsed = json.loads(s)
        return PgJson(parsed) if isinstance(parsed, (list, dict)) else parsed
    except Exception:
        return val


def _rows_to_dict(rows): 
    result = []
    for r in rows:
        row = dict(r)
        for k, v in row.items():
            if isinstance(v, datetime):
                row[k] = v.strftime('%Y-%m-%d %H:%M')
            elif isinstance(v, (list, dict)):
                row[k] = json.dumps(v, ensure_ascii=False)
        result.append(row)
    return result


# ============================================================================
# d_menu_mst
# ============================================================================

@sysconfig_bp.route('/menu', methods=['GET'])
def list_menu():
    err = require_menu_access('system-config')
    if err: return err
    try:
        rows = pg.query(
            "SELECT menu_id, page_id, page_name, menu_name, menu_desc,"
            "       menu_url, icon_class, sort_order, use_yn, delete_flag"
            "  FROM d_menu_mst"
            " ORDER BY sort_order, menu_id, page_id"
        )
        return jsonify({'success': True, 'data': _rows_to_dict(rows)})
    except Exception as e:
        logger.exception("list_menu error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/menu', methods=['POST'])
def create_menu():
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        pg.insert('d_menu_mst', {
            'menu_id':    (data.get('menu_id') or '').strip(),
            'page_id':    (data.get('page_id') or '_').strip(),
            'page_name':  (data.get('page_name') or '').strip() or None,
            'menu_name':  (data.get('menu_name') or '').strip() or None,
            'menu_desc':  (data.get('menu_desc') or '').strip() or None,
            'menu_url':   (data.get('menu_url') or '').strip() or None,
            'icon_class': (data.get('icon_class') or '').strip() or None,
            'sort_order': int(data.get('sort_order') or 0),
            'use_yn':     data.get('use_yn') or 'Y',   # None ë°©ì–´ (NOT NULL)
            'delete_flag': 'N',
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("create_menu error")
        msg = 'Duplicate key.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


@sysconfig_bp.route('/menu/<menu_id>/<path:page_id>', methods=['PUT'])
def update_menu(menu_id, page_id):
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    upd = {}
    for f in ('page_name', 'menu_name', 'menu_desc', 'menu_url', 'icon_class'):
        if f in data:
            upd[f] = (data[f] or '').strip() or None
    # NOT NULL 
    if 'use_yn' in data and data['use_yn']:
        upd['use_yn'] = str(data['use_yn']).strip()
    if 'delete_flag' in data and data['delete_flag']:
        upd['delete_flag'] = str(data['delete_flag']).strip()
    if 'sort_order' in data:
        upd['sort_order'] = int(data['sort_order'] or 0)
    if not upd:
        return jsonify({'success': False, 'message': 'No fields to update.'}), 400
    try:
        pg.update('d_menu_mst', set=upd, where={'menu_id': menu_id, 'page_id': page_id})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("update_menu error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/menu/<menu_id>/<path:page_id>', methods=['DELETE'])
def delete_menu(menu_id, page_id):
    err = require_menu_access('system-config')
    if err: return err
    try:
        pg.update('d_menu_mst',
                  set={'delete_flag': 'Y', 'use_yn': 'N'},
                  where={'menu_id': menu_id, 'page_id': page_id})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("delete_menu error")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# d_user_type_mst
# ============================================================================

@sysconfig_bp.route('/usertype', methods=['GET'])
def list_usertype():
    err = require_menu_access('system-config')
    if err: return err
    try:
        rows = pg.query(
            "SELECT subsdr_name, user_type, type_name, allowed_menus, child_user_types, delete_flag"
            "  FROM d_user_type_mst"
            " ORDER BY subsdr_name, user_type"
        )
        return jsonify({'success': True, 'data': _rows_to_dict(rows)})
    except Exception as e:
        logger.exception("list_usertype error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/usertype', methods=['POST'])
def create_usertype():
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        pg.insert('d_user_type_mst', {
            'subsdr_name':      (data.get('subsdr_name') or '').strip() or '[ALL]',
            'user_type':        (data.get('user_type') or '').strip(),
            'type_name':        (data.get('type_name') or '').strip() or None,
            'allowed_menus':    _parse_jsonb(data.get('allowed_menus')),
            'child_user_types': _parse_jsonb(data.get('child_user_types')),
            'delete_flag':      'N',
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("create_usertype error")
        msg = 'Duplicate key.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


@sysconfig_bp.route('/usertype/<subsdr_name>/<user_type>', methods=['PUT'])
def update_usertype(subsdr_name, user_type):
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    upd = {}
    if 'type_name' in data:
        upd['type_name'] = (data['type_name'] or '').strip() or None
    if 'allowed_menus' in data:
        upd['allowed_menus'] = _parse_jsonb(data['allowed_menus'])
    if 'child_user_types' in data:
        upd['child_user_types'] = _parse_jsonb(data['child_user_types'])
    if 'delete_flag' in data:
        upd['delete_flag'] = data['delete_flag']
    if not upd:
        return jsonify({'success': False, 'message': 'No fields to update.'}), 400
    try:
        pg.update('d_user_type_mst', set=upd,
                  where={'subsdr_name': subsdr_name, 'user_type': user_type})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("update_usertype error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/usertype/<subsdr_name>/<user_type>', methods=['DELETE'])
def delete_usertype(subsdr_name, user_type):
    err = require_menu_access('system-config')
    if err: return err
    try:
        pg.update('d_user_type_mst',
                  set={'delete_flag': 'Y'},
                  where={'subsdr_name': subsdr_name, 'user_type': user_type})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("delete_usertype error")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# d_subsdr_mst
# ============================================================================

@sysconfig_bp.route('/subsdr', methods=['GET'])
def list_subsdr():
    err = require_menu_access('system-config')
    if err: return err
    try:
        rows = pg.query(
            "SELECT subsdr_name, region_name, display_name, timezone,"
            "       currency_list, child_subsdr_list, config_info, sort_order,"
            "       nerp_yn, virtual_yn, use_yn, open_yn, nerp_open_ymd"
            "  FROM d_subsdr_mst"
            " ORDER BY sort_order"
        )
        return jsonify({'success': True, 'data': _rows_to_dict(rows)})
    except Exception as e:
        logger.exception("list_subsdr error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/subsdr', methods=['POST'])
def create_subsdr():
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    try:
        pg.insert('d_subsdr_mst', {
            'subsdr_name':       (data.get('subsdr_name') or '').strip(),
            'region_name':       (data.get('region_name') or '').strip() or None,
            'display_name':      (data.get('display_name') or '').strip() or None,
            'timezone':          (data.get('timezone') or '').strip() or None,
            'currency_list':     _parse_jsonb(data.get('currency_list')),
            'child_subsdr_list': _parse_jsonb(data.get('child_subsdr_list')),
            'config_info':       _parse_jsonb(data.get('config_info')),
            'sort_order':        int(data.get('sort_order') or 0),
            'nerp_yn':           data.get('nerp_yn') or 'N',   # None 방어 (NOT NULL)
            'virtual_yn':        data.get('virtual_yn') or 'N',
            'use_yn':            data.get('use_yn') or 'Y',
            'open_yn':           data.get('open_yn') or 'N',
            'nerp_open_ymd':     (data.get('nerp_open_ymd') or '').strip() or None,
        })
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("create_subsdr error")
        msg = 'Duplicate key.' if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() else str(e)
        return jsonify({'success': False, 'message': msg}), 400


@sysconfig_bp.route('/subsdr/<subsdr_name>', methods=['PUT'])
def update_subsdr(subsdr_name):
    err = require_menu_access('system-config')
    if err: return err
    data = request.get_json(silent=True) or {}
    upd = {}
    for f in ('region_name', 'display_name', 'timezone', 'nerp_open_ymd'):
        if f in data:
            upd[f] = (data[f] or '').strip() or None
            
    for f in ('nerp_yn', 'virtual_yn', 'use_yn', 'open_yn'):
        if f in data and data[f]:
            upd[f] = str(data[f]).strip()
    if 'sort_order' in data:
        upd['sort_order'] = int(data['sort_order'] or 0)
    if 'currency_list' in data:
        upd['currency_list'] = _parse_jsonb(data['currency_list'])
    if 'child_subsdr_list' in data:
        upd['child_subsdr_list'] = _parse_jsonb(data['child_subsdr_list'])
    if 'config_info' in data:
        upd['config_info'] = _parse_jsonb(data['config_info'])
    if not upd:
        return jsonify({'success': False, 'message': 'No fields to update.'}), 400
    try:
        pg.update('d_subsdr_mst', set=upd, where={'subsdr_name': subsdr_name})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("update_subsdr error")
        return jsonify({'success': False, 'message': str(e)}), 500


@sysconfig_bp.route('/subsdr/<subsdr_name>', methods=['DELETE'])
def delete_subsdr(subsdr_name):
    err = require_menu_access('system-config')
    if err: return err
    try:
        pg.update('d_subsdr_mst',
                  set={'use_yn': 'N'},
                  where={'subsdr_name': subsdr_name})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception("delete_subsdr error")
        return jsonify({'success': False, 'message': str(e)}), 500


