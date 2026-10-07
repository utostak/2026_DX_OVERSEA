"""
utils/auth_check.py — 공통 권한 체크 유틸리티

세션의 allowed_menus (d_user_type_mst.allowed_menus) 기반으로
메뉴 접근 및 편집 권한을 체크하는 공통 함수들
"""
import logging
from flask import session, request, jsonify

logger = logging.getLogger(__name__)


def require_login():
    """로그인 체크 - 401 반환"""
    if not session.get('user_id'):
        logger.warning(f"❌ Access denied: not logged in (IP: {request.remote_addr})")
        return jsonify({'success': False, 'message': 'Login required.'}), 401
    return None


def require_menu_access(menu_id: str, page_id: str = '_'):
    """
    메뉴 접근 권한 체크 (읽기 권한)
    - allowed_menus가 None → 전체 허용 (admin/owner 등)
    - allowed_menus가 list → 해당 menu_id가 있는지 확인
    
    Returns:
        None if allowed, (response, 403) if forbidden
    """
    err = require_login()
    if err:
        return err
    
    allowed_menus = session.get('allowed_menus')
    
    # None = 전체 허용
    if allowed_menus is None:
        return None
    
    # 빈 배열 = 아무것도 허용 안함
    if not allowed_menus:
        logger.warning(f"❌ Menu access denied: no menus allowed (user_id={session.get('user_id')}, menu_id={menu_id}, IP: {request.remote_addr})")
        return jsonify({'success': False, 'message': f'접근 권한이 없습니다.'}), 403
    
    # allowed_menus 구조: [{"id":"menu_id", "edit":bool, "pages":[{"id":"page_id", "edit":bool}]}]
    for menu in allowed_menus:
        if menu.get('id') == menu_id:
            # 최상위 메뉴 접근 (page_id='_')
            if page_id == '_':
                return None
            
            # 서브페이지 체크
            pages = menu.get('pages', [])
            if not pages:  # pages 없으면 전체 서브페이지 허용
                return None
            
            for pg in pages:
                if pg.get('id') == page_id:
                    return None
            
            # 서브페이지 목록에 없음
            logger.warning(f"❌ Page access denied: user_id={session.get('user_id')}, menu_id={menu_id}, page_id={page_id}, IP: {request.remote_addr}")
            return jsonify({'success': False, 'message': f'{menu_id}/{page_id} 접근 권한이 없습니다.'}), 403
    
    # menu_id 자체가 allowed_menus에 없음
    logger.warning(f"❌ Menu access denied: user_id={session.get('user_id')}, menu_id={menu_id}, IP: {request.remote_addr}")
    return jsonify({'success': False, 'message': f'{menu_id} 접근 권한이 없습니다.'}), 403


def require_menu_edit(menu_id: str, page_id: str = '_'):
    """
    메뉴 편집 권한 체크 (쓰기 권한)
    - allowed_menus가 None → 전체 허용
    - allowed_menus의 각 메뉴/페이지의 "edit":true 인지 확인
    
    Returns:
        None if allowed, (response, 403) if forbidden
    """
    err = require_login()
    if err:
        return err
    
    allowed_menus = session.get('allowed_menus')
    
    # None = 전체 허용
    if allowed_menus is None:
        return None
    
    # 빈 배열 = 아무것도 허용 안함
    if not allowed_menus:
        logger.warning(f"❌ Edit access denied: no menus allowed (user_id={session.get('user_id')}, menu_id={menu_id}, IP: {request.remote_addr})")
        return jsonify({'success': False, 'message': f'편집 권한이 없습니다.'}), 403
    
    for menu in allowed_menus:
        if menu.get('id') == menu_id:
            # 최상위 메뉴 편집권한
            if page_id == '_':
                if menu.get('edit', False):
                    return None
                logger.warning(f"❌ Edit access denied: user_id={session.get('user_id')}, menu_id={menu_id}, edit=False, IP: {request.remote_addr}")
                return jsonify({'success': False, 'message': f'{menu_id} 편집 권한이 없습니다.'}), 403
            
            # 서브페이지 편집권한 체크
            pages = menu.get('pages', [])
            if not pages:  # pages 없으면 메뉴 레벨 edit 권한 사용
                if menu.get('edit', False):
                    return None
                logger.warning(f"❌ Edit access denied: user_id={session.get('user_id')}, menu_id={menu_id}, page_id={page_id}, menu.edit=False, IP: {request.remote_addr}")
                return jsonify({'success': False, 'message': f'{menu_id} 편집 권한이 없습니다.'}), 403
            
            for pg in pages:
                if pg.get('id') == page_id:
                    if pg.get('edit', False):
                        return None
                    logger.warning(f"❌ Edit access denied: user_id={session.get('user_id')}, menu_id={menu_id}, page_id={page_id}, page.edit=False, IP: {request.remote_addr}")
                    return jsonify({'success': False, 'message': f'{menu_id}/{page_id} 편집 권한이 없습니다.'}), 403
            
            # 서브페이지 목록에 없음
            logger.warning(f"❌ Edit access denied: page not in allowed list (user_id={session.get('user_id')}, menu_id={menu_id}, page_id={page_id}, IP: {request.remote_addr})")
            return jsonify({'success': False, 'message': f'{menu_id}/{page_id} 편집 권한이 없습니다.'}), 403
    
    # menu_id 자체가 allowed_menus에 없음
    logger.warning(f"❌ Edit access denied: menu not in allowed list (user_id={session.get('user_id')}, menu_id={menu_id}, IP: {request.remote_addr})")
    return jsonify({'success': False, 'message': f'{menu_id} 편집 권한이 없습니다.'}), 403


def has_menu_access(menu_id: str, page_id: str = '_') -> bool:
    """
    메뉴 접근 권한 여부 반환 (boolean)
    - 에러 응답 대신 True/False만 반환
    """
    if not session.get('user_id'):
        return False
    
    allowed_menus = session.get('allowed_menus')
    if allowed_menus is None:
        return True
    
    if not allowed_menus:
        return False
    
    for menu in allowed_menus:
        if menu.get('id') == menu_id:
            if page_id == '_':
                return True
            pages = menu.get('pages', [])
            if not pages:
                return True
            for pg in pages:
                if pg.get('id') == page_id:
                    return True
            return False
    
    return False


def has_menu_edit(menu_id: str, page_id: str = '_') -> bool:
    """
    메뉴 편집 권한 여부 반환 (boolean)
    """
    if not session.get('user_id'):
        return False
    
    allowed_menus = session.get('allowed_menus')
    if allowed_menus is None:
        return True
    
    if not allowed_menus:
        return False
    
    for menu in allowed_menus:
        if menu.get('id') == menu_id:
            if page_id == '_':
                return menu.get('edit', False)
            pages = menu.get('pages', [])
            if not pages:
                return menu.get('edit', False)
            for pg in pages:
                if pg.get('id') == page_id:
                    return pg.get('edit', False)
            return False
    
    return False
