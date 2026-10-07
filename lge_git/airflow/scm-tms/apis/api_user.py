"""
apis/api_user.py — 사용자 관리 API (관리자 전용)
  GET    /api/users           — 자기 법인 사용자 목록
  POST   /api/users           — 사용자 생성
  PUT    /api/users/<uid>     — 사용자 수정
  DELETE /api/users/<uid>     — 사용자 삭제 (delete_flag='Y')
  POST   /api/users/<uid>/unlock — 계정 잠금 해제
  GET    /api/users/types     — 사용자 유형 목록
"""
import logging
from datetime import datetime, timezone as dt_timezone
import pytz
from flask import Blueprint, request, jsonify, session
from utils.pg_db import pg
from utils.auth_check import require_menu_access, require_menu_edit

logger   = logging.getLogger(__name__)
user_bp  = Blueprint('user', __name__, url_prefix='/api/users')

def _hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _normalize_biz_group_list(val):
    """요청의 biz_group_list 를 jsonb 저장용 값으로 정규화.
      - None / [] / '' → None (None=관리 대상 없음)
      - ['ALL'] (대소문자 무관) → ['ALL'] (전체)
      - 그 외 → 문자열 리스트 (공백 제거, 중복 제거, 순서 유지)
    반환: psycopg2 Json 어댑터 또는 None
    """
    import json
    from psycopg2.extras import Json as PgJson
    if val is None:
        return None
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except Exception:
            val = [val]
    if not isinstance(val, (list, tuple)):
        return None
    items = [str(x).strip() for x in val if str(x).strip()]
    if not items:
        return None
    # ALL 이 포함되면 ['ALL'] 로 통일
    if any(x.upper() == 'ALL' for x in items):
        return PgJson(['ALL'])
    # 중복 제거 (순서 유지)
    items = list(dict.fromkeys(items))
    return PgJson(items)

# ── 사용자 유형 목록 (고정 경로를 /<uid> 보다 먼저 선언) ──────────────────
@user_bp.route('/types', methods=['GET'])
def get_user_types():
    err = require_menu_access('users')
    if err:
        return err
    try:
        # 현재 관리자의 user_type + child_user_types 조회
        my_type = session.get('user_type', 'admin')
        my_subsdr = session.get('subsdr_name')
        me_rows = pg.query(
            "SELECT child_user_types FROM v_user_type_mst"
            " WHERE subsdr_name = %s AND user_type = %s AND delete_flag = 'N'",
            (my_subsdr, my_type)
        )
        child_types = me_rows[0].get('child_user_types') if me_rows else None
        # psycopg2 가 jsonb → list 로 자동 변환, 혹은 str 일 경우 파싱
        if isinstance(child_types, str):
            import json
            child_types = json.loads(child_types)

        if child_types is None:
            # null → 전체 허용
            rows = pg.query(
                "SELECT user_type, type_name FROM v_user_type_mst"
                " WHERE subsdr_name = %s AND delete_flag = 'N' ORDER BY user_type",
                (my_subsdr,)
            )
        else:
            # 본인 user_type + child_user_types 합집합 (중복 제거, 순서 유지)
            allowed = list(dict.fromkeys([my_type] + list(child_types)))
            if not allowed:
                rows = []
            else:
                placeholders = ','.join(['%s'] * len(allowed))
                rows = pg.query(
                    f"SELECT user_type, type_name FROM v_user_type_mst"
                    f" WHERE subsdr_name = %s AND delete_flag = 'N' AND user_type IN ({placeholders})"
                    f" ORDER BY user_type",
                    (my_subsdr, *allowed)
                )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ── Biz Group 목록 (영업사원 관리 대상 선택용) ──────────────────────────────
@user_bp.route('/biz-groups', methods=['GET'])
def get_biz_groups():
    """법인별 Biz Group(billto_biz_name) 목록. 사용자 관리 화면의 다중 선택용."""
    err = require_menu_access('users')
    if err:
        return err
    subsdr = request.args.get('legal_entity', '').strip() or session.get('subsdr_name')
    try:
        rows = pg.query(
            "SELECT DISTINCT billto_biz_name"
            "  FROM d_billto_biz_mst"
            " WHERE subsdr_name = %s"
            "   AND billto_biz_name IS NOT NULL AND billto_biz_name <> ''"
            " ORDER BY billto_biz_name",
            (subsdr,)
        )
        return jsonify({'success': True, 'data': [r['billto_biz_name'] for r in rows]})
    except Exception as e:
        logger.exception(' get_biz_groups error:')
        return jsonify({'success': False, 'message': str(e)}), 500

@user_bp.route('/search-email', methods=['GET'])
def search_user_email():
    """같은 법인의 사용자 이름+이메일 목록 반환. 메일 발송 수신자 검색 용도."""
    if not session.get('user_id'):
        return jsonify({'success': False, 'message': 'Login required'}), 401
    subsdr = request.args.get('legal_entity', '').strip() or session.get('subsdr_name')
    try:
        rows = pg.query(
            """
            SELECT user_id, user_name, email
              FROM d_user_mst
             WHERE subsdr_name = %s AND delete_flag = 'N'
               AND email IS NOT NULL AND email <> ''
             ORDER BY user_name, user_id
            """,
            (subsdr,)
        )
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        logger.exception('search_user_email error:')
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 목록 ─────────────────────────────────────────────────────────────────────
@user_bp.route('', methods=['GET'])
def list_users():
    err = require_menu_access('users')
    if err:
        return err
    # ?legal_entity= 파라미터 우선, 없으면 세션 법인 사용
    subsdr = request.args.get('legal_entity', '').strip() or session.get('subsdr_name')
    try:
        rows = pg.query(
            """
            SELECT u.subsdr_name, u.user_id, u.user_name, u.email,
                   u.user_type, t.type_name,
                   u.last_login_dt, u.login_fail_cnt, u.lock_yn,
                   u.container_mail_yn, u.container_yard_mail_yn, u.hold_order_mail_yn,
                   u.biz_group_list,
                   u.input_dt, u.update_dt
              FROM d_user_mst u
              LEFT JOIN v_user_type_mst t
                     ON u.subsdr_name = t.subsdr_name
                    AND u.user_type   = t.user_type
             WHERE u.subsdr_name = %s AND u.delete_flag = 'N'
             ORDER BY u.user_type, u.user_id
            """,
            (subsdr,)
        )
        # 법인 timezone 조회
        from utils.subsdr_cache import get_subsdr_info
        tz_name = None
        if subsdr and subsdr != 'ALL':
            info = get_subsdr_info(subsdr)
            tz_name = info.get('timezone') or None
            logger.debug(f"list_users timezone: subsdr={subsdr}, tz_name={tz_name}")
        try:
            tz = pytz.timezone(tz_name) if tz_name else dt_timezone.utc
        except Exception:
            tz = dt_timezone.utc
            tz_name = None

        # datetime → str 직렬화 (법인 타임존으로 변환)
        for r in rows:
            for k in ('last_login_dt', 'input_dt', 'update_dt'):
                val = r.get(k)
                if val and isinstance(val, datetime):
                    # DB 값이 naive이면 UTC로 간주
                    if val.tzinfo is None:
                        val = val.replace(tzinfo=dt_timezone.utc)
                    r[k] = val.astimezone(tz).strftime('%Y-%m-%d %H:%M')
                elif val:
                    r[k] = str(val)[:16]
        return jsonify({'success': True, 'data': rows, 'timezone': tz_name or 'UTC'})
    except Exception as e:
        logger.exception(f" list_users error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 생성 ─────────────────────────────────────────────────────────────────────
@user_bp.route('', methods=['POST'])
def create_user():
    err = require_menu_access('users')
    if err:
        return err
    data    = request.get_json(silent=True) or {}
    subsdr  = (data.get('legal_entity') or '').strip() or session.get('subsdr_name')
    user_id = (data.get('user_id') or '').strip()
    if not user_id:
        return jsonify({'success': False, 'message': 'user_id 는 필수입니다.'}), 400

    password = (data.get('user_password') or '').strip()
    pwd_hash = _hash_password(password) if password else '_'   # 패스워드 없으면 '_' (최초 로그인 시 설정)

    try:
        pg.insert('d_user_mst', {
            'subsdr_name':      subsdr,
            'user_id':          user_id,
            'user_name':        (data.get('user_name') or user_id).strip(),
            'user_password':    pwd_hash,
            'email':            (data.get('email') or '').strip(),
            'user_type':        data.get('user_type', 'user'),
            'container_mail_yn': data.get('container_mail_yn', 'N'),
            'container_yard_mail_yn': data.get('container_yard_mail_yn', 'N'),
            'hold_order_mail_yn':     data.get('hold_order_mail_yn', 'N'),
            'biz_group_list':   _normalize_biz_group_list(data.get('biz_group_list')),
            'input_user_id':    session.get('user_id'),
        })
        logger.info(f"CREATE USER {user_id} by {session.get('user_id')}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" create_user error:")
        msg = ('이미 존재하는 user_id 입니다.'
               if 'unique' in str(e).lower() or 'duplicate' in str(e).lower()
               else str(e))
        return jsonify({'success': False, 'message': msg}), 400


# ── 수정 ─────────────────────────────────────────────────────────────────────
@user_bp.route('/<uid>', methods=['PUT'])
def update_user(uid):
    err = require_menu_access('users')
    if err:
        return err
    data        = request.get_json(silent=True) or {}
    subsdr      = (data.get('legal_entity') or '').strip() or session.get('subsdr_name')
    update_data: dict = {}

    if 'user_name' in data:
        update_data['user_name']  = (data['user_name'] or '').strip()
    if 'email' in data:
        update_data['email']      = (data['email'] or '').strip()
    if 'user_type' in data:
        update_data['user_type']  = data['user_type']
    if 'lock_yn' in data:
        update_data['lock_yn']    = data['lock_yn']
    if 'container_mail_yn' in data and data['container_mail_yn'] in ('Y', 'N'):
        update_data['container_mail_yn'] = data['container_mail_yn']
    if 'container_yard_mail_yn' in data and data['container_yard_mail_yn'] in ('Y', 'N'):
        update_data['container_yard_mail_yn'] = data['container_yard_mail_yn']
    if 'hold_order_mail_yn' in data and data['hold_order_mail_yn'] in ('Y', 'N'):
        update_data['hold_order_mail_yn'] = data['hold_order_mail_yn']
    if 'biz_group_list' in data:
        update_data['biz_group_list'] = _normalize_biz_group_list(data.get('biz_group_list'))

    # 비밀번호: 값이 있을 때만 재해시
    new_pwd = (data.get('user_password') or '').strip()
    if new_pwd:
        update_data['user_password'] = _hash_password(new_pwd)
        update_data['login_fail_cnt'] = 0
        update_data['lock_yn']        = 'N'

    if not update_data:
        return jsonify({'success': False, 'message': '변경할 항목이 없습니다.'}), 400

    update_data['update_dt']      = datetime.now(tz=dt_timezone.utc)
    update_data['update_user_id'] = session.get('user_id')

    try:
        pg.update('d_user_mst',
                  set=update_data,
                  where={'user_id': uid})
        logger.info(f"UPDATE USER {uid} by {session.get('user_id')}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" update_user error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 삭제 (soft delete) ────────────────────────────────────────────────────────
@user_bp.route('/<uid>', methods=['DELETE'])
def delete_user(uid):
    err = require_menu_access('users')
    if err:
        return err
    if uid == session.get('user_id'):
        return jsonify({'success': False, 'message': '자기 자신은 삭제할 수 없습니다.'}), 400
    data   = request.get_json(silent=True) or {}
    subsdr = (data.get('legal_entity') or '').strip() or session.get('subsdr_name')
    try:
        pg.update('d_user_mst',
                  set={'delete_flag': 'Y', 'update_dt': datetime.now(tz=dt_timezone.utc),
                       'update_user_id': session.get('user_id')},
                  where={'user_id': uid})
        logger.info(f"DELETE USER {uid} by {session.get('user_id')}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" delete_user error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 패스워드 초기화 ───────────────────────────────────────────────────────────
@user_bp.route('/<uid>/reset-password', methods=['POST'])
def reset_password(uid):
    """user_password 를 '_' 로 초기화 → 사용자가 다음 로그인 시 비밀번호 직접 설정"""
    err = require_menu_access('users')
    if err:
        return err
    data   = request.get_json(silent=True) or {}
    subsdr = (data.get('legal_entity') or '').strip() or session.get('subsdr_name')
    try:
        pg.update('d_user_mst',
                  set={'user_password': '_',
                       'login_fail_cnt': 0,
                       'lock_yn': 'N',
                       'update_dt': datetime.now(tz=dt_timezone.utc),
                       'update_user_id': session.get('user_id')},
                  where={'user_id': uid})
        logger.info(f"RESET PASSWORD {uid} by {session.get('user_id')}")
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" reset_password error:")
        return jsonify({'success': False, 'message': str(e)}), 500


# ── 잠금 해제 ─────────────────────────────────────────────────────────────────
@user_bp.route('/<uid>/unlock', methods=['POST'])
def unlock_user(uid):
    err = require_menu_access('users')
    if err:
        return err
    data   = request.get_json(silent=True) or {}
    subsdr = (data.get('legal_entity') or '').strip() or session.get('subsdr_name')
    try:
        pg.update('d_user_mst',
                  set={'lock_yn': 'N', 'login_fail_cnt': 0,
                       'update_dt': datetime.now(tz=dt_timezone.utc),
                       'update_user_id': session.get('user_id')},
                  where={'user_id': uid})
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f" unlock_user error:")
        return jsonify({'success': False, 'message': str(e)}), 500
