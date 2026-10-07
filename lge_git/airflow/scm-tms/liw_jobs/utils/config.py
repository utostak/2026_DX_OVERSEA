"""
jobs/utils/config.py
─────────────────────────────────────────────────────────────
.env.<env> 파일을 **직접** 읽어 설정값을 반환하는 모듈.

os.getenv() 를 사용하면 Airflow / systemd / docker 등 외부에서
주입한 동일 이름의 환경변수(예: DB_PORT=8110 → 메타 DB 포트)에
오염될 수 있습니다. 이 모듈은 os.environ 을 거치지 않고
.env 파일에서 읽은 값을 최우선으로 사용합니다.

우선순위:
  1. .env.<env> 파일 값        ← 최우선 (환경변수 오염 방지)
  2. os.environ 값 (폴백)      ← 파일에 없을 때만
  3. 함수 호출 시 default 인자

사용:
    from utils.config import getenv

    port = getenv('DB_PORT', 5432, cast=int)
    host = getenv('DB_HOSTNAME', 'localhost')
"""
import os
import logging

logger = logging.getLogger(__name__)

# jobs/utils/config.py → dirname = jobs/utils → dirname = jobs
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# .env 파일 파싱 결과 캐시 (파일당 1회만 읽음)
_file_cache: dict = {}

_FILE_ALIAS = {'development': 'dev', 'production': 'prd', 'prod': 'prd'}


def _resolve_env_name(env: str = None) -> str:
    """환경 이름을 파일 접미어(dev/prd 등)로 정규화."""
    if env is None:
        env = os.environ.get('APP_ENV', 'prd')
    env_key = env.lower()
    return _FILE_ALIAS.get(env_key, env_key)


def _parse_env_file(path: str) -> dict:
    """단순 KEY=VALUE 파서 (주석·빈줄 무시, 따옴표 제거)."""
    result = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            result[key] = value
    return result


def _load_file(env: str = None) -> dict:
    """.env.<env> 파일을 읽어 dict 로 반환 (캐시됨)."""
    file_key = _resolve_env_name(env)
    if file_key in _file_cache:
        return _file_cache[file_key]

    env_path = os.path.join(_BASE_DIR, f'.env.{file_key}')
    if not os.path.exists(env_path):
        logger.warning(f"환경설정 파일 없음: {env_path}")
        _file_cache[file_key] = {}
        return {}

    values = _parse_env_file(env_path)
    _file_cache[file_key] = values
    logger.info(f"✅ 설정 파일 로드: .env.{file_key} ({len(values)}개 항목)")
    return values


def getenv(key: str, default=None, cast=None, env: str = None):
    """
    설정값을 반환한다.

    조회 순서:
      1. .env.<env> 파일 값 (최우선 — 환경변수 오염 방지)
      2. os.environ 값 (파일에 없을 때만 폴백)
      3. default 인자

    Args:
        key:     조회할 키 이름
        default: 값이 없을 때 반환할 기본값
        cast:    변환 함수 (예: int, float, bool). None 이면 문자열 그대로.
        env:     환경 이름 강제 지정 (기본: APP_ENV 환경변수)

    Returns:
        조회된 값 (cast 지정 시 변환된 값)
    """
    values = _load_file(env)

    if key in values:
        raw = values[key]
    elif key in os.environ:
        raw = os.environ[key]
    else:
        return default

    if cast is None:
        return raw

    if cast is bool:
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    try:
        return cast(raw)
    except (ValueError, TypeError):
        logger.warning(f"설정 '{key}' 변환 실패({cast.__name__}): {raw!r} → default 사용")
        return default


def reload(env: str = None) -> None:
    """캐시를 비워 파일을 다시 읽도록 한다 (테스트/재로드용)."""
    if env is None:
        _file_cache.clear()
    else:
        _file_cache.pop(_resolve_env_name(env), None)
