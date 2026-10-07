"""
Subsidiary Master Cache  (PostgreSQL 버전)
──────────────────────────────────────────────────────────────────────────────
앱 기동 시 PostgreSQL d_subsdr_mst 테이블을 1회 조회하여 메모리에 캐싱합니다.
캐시 새로고침은 reload_subsdr_list() 를 호출하면 됩니다.

캐시 구조 (subsdr_list):
  [
    {"region": "Asia",   "subsidiaries": [{"code": "LGEAP", "display": "LGEAP — 호주/뉴질랜드 (Asia)"}, ...]},
    {"region": "Europe", "subsidiaries": [...]},
    ...
  ]

원시 데이터 (subsdr_map):
  {"LGEAP": {"region_name": "Asia", "display_name": "...", "timezone": "...",
             "currency_list": ["USD","AUD"]}, ...}
"""
import logging

logger = logging.getLogger(__name__)

# ── 모듈 레벨 캐시 ────────────────────────────────────────────────────────────
_subsdr_list: list = []   # [{region, subsidiaries:[{code, display}]}]  ※ 가상 법인 제외
_subsdr_map:  dict = {}   # {subsdr_name: {region_name, display_name, timezone,
                          #                currency_list, child_subsdr_list, virtual_yn}}


# ── 내부: DB rows → 캐시 갱신 ────────────────────────────────────────────────
def _build_cache(rows: list) -> None:
    """DB rows(list[dict]) → _subsdr_list / _subsdr_map 갱신
    - _subsdr_list : 가상 법인 포함 전체 셀렉터 목록 (지역별 sort_order 정렬)
    - _subsdr_map  : 가상 법인 포함 전체 (접근 권한 조회용)
    """
    global _subsdr_list, _subsdr_map

    grouped: dict    = {}   # region_name → [{"code": ..., "display": ...}]
    region_sort: dict = {}  # region_name → min(sort_order) — 지역 간 정렬 기준
    new_map:  dict   = {}

    for row in rows:
        name       = row['subsdr_name']
        region     = row.get('region_name') or '기타'
        display    = row.get('display_name') or name
        sort_order = row.get('sort_order') or 999

        # 가상 법인 포함 모두 셀렉터 목록에 추가
        if region not in grouped:
            grouped[region]    = []
            region_sort[region] = sort_order
        else:
            # 지역 내 첫 번째 항목의 sort_order를 지역 대표 순서로 사용
            region_sort[region] = min(region_sort[region], sort_order)
        grouped[region].append({"code": name, "display": display})

        new_map[name] = {
            "region_name":       region,
            "display_name":      display,
            "timezone":          row.get('timezone'),
            "currency_list":     row.get('currency_list') or [],
            "child_subsdr_list": row.get('child_subsdr_list') or [],
            "virtual_yn":        row.get('virtual_yn') or 'N',
        }

    # 지역을 min(sort_order) 기준으로 정렬, 동률이면 region_name 알파벳 순
    _subsdr_list = [
        {"region": region, "subsidiaries": subs}
        for region, subs in sorted(
            grouped.items(),
            key=lambda x: (region_sort[x[0]], x[0])
        )
    ]
    _subsdr_map = new_map


# ── 공개 API ──────────────────────────────────────────────────────────────────

def load_subsdr_list() -> list:
    """
    PostgreSQL d_subsdr_mst 에서 법인 목록을 조회하여 캐시에 저장합니다.
    앱 기동 시 1회 호출하세요.
    실패하더라도 예외를 전파하지 않고 빈 리스트를 반환합니다.
    """
    try:
        from utils.pg_db import pg
        rows = pg.query(
            "SELECT subsdr_name, region_name, display_name, timezone,"
            "       currency_list, child_subsdr_list, virtual_yn, sort_order"
            "  FROM d_subsdr_mst"
            " WHERE use_yn = 'Y'"
            " ORDER BY sort_order, region_name, subsdr_name"
        )
        if not rows:
            logger.warning("⚠️ d_subsdr_mst 조회 결과가 비어 있습니다.")
            return _subsdr_list

        _build_cache(rows)
        total = sum(len(g['subsidiaries']) for g in _subsdr_list)
        logger.info(
            f"✅ 법인 마스터 캐시 로드 완료 (PostgreSQL): "
            f"{total}개 법인, {len(_subsdr_list)}개 리전"
        )
    except Exception as e:
        logger.error(f"❌ 법인 마스터 캐시 로드 실패 (PostgreSQL): {e}")

    return _subsdr_list


def reload_subsdr_list() -> list:
    """캐시를 강제로 새로고침합니다."""
    return load_subsdr_list()


def get_subsdr_list() -> list:
    """캐시된 법인 목록을 반환합니다. 캐시가 없으면 자동 로드합니다."""
    if not _subsdr_list:
        load_subsdr_list()
    return _subsdr_list


def get_subsdr_map() -> dict:
    """
    법인 코드 → 상세 정보 dict 반환.
    예) get_subsdr_map()['LGEAP']['timezone']  →  'Australia/Sydney'
    """
    if not _subsdr_map:
        load_subsdr_list()
    return _subsdr_map


def get_subsdr_info(subsdr_name: str) -> dict:
    """
    특정 법인의 상세 정보를 반환합니다.
    없으면 {} 반환.
    """
    return get_subsdr_map().get(subsdr_name, {})


def get_currency_list(subsdr_name: str) -> list:
    """
    특정 법인의 통화 목록을 반환합니다.
    예) get_currency_list('LGEAP')  →  ['USD', 'AUD']
    """
    return get_subsdr_info(subsdr_name).get('currency_list', [])


def get_accessible_subsdrs(subsdr_name: str) -> list:
    """
    로그인한 사용자가 접근 가능한 법인 코드 목록을 반환합니다.

    규칙:
      - [자신] + child_subsdr_list (virtual_yn 무관)
      - child_subsdr_list 없음 : [자신] 만 (단일 법인 사용자)

    캐시가 비어있으면 자동 로드합니다.
    """
    if not _subsdr_map:
        load_subsdr_list()
    info     = _subsdr_map.get(subsdr_name, {})
    children = info.get('child_subsdr_list') or []
    return [subsdr_name] + [c for c in children if c != subsdr_name]
