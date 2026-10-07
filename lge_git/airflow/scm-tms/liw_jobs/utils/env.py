"""
jobs/utils/env.py
─────────────────────────────────────────────────────────────
APP_ENV 환경변수(또는 인자)에 따라 .env.dev / .env.prd 를 로드합니다.
※ 독립 실행용: jobs 폴더를 기준(_BASE_DIR)으로 .env.<env> 파일을 찾습니다.

우선순위:
  1. 이미 설정된 os.environ 값 (systemd / docker 등 외부 주입 우선)
  2. .env.<env> 파일 값

사용:
  from utils.env import load_env
  load_env()          # APP_ENV 환경변수 자동 감지
  load_env('prd')     # 강제 지정
"""
import os
import logging

logger = logging.getLogger(__name__)

# jobs/utils/env.py → dirname = jobs/utils → dirname = jobs
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_loaded = False


def _parse_env_file(path: str) -> dict:
    """단순 KEY=VALUE 파서 (주석·빈줄 무시, 따옴표 제거)"""
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


def load_env(env: str = None) -> str:
    """
    .env.<env> 파일을 로드하고 os.environ 에 반영합니다.
    이미 로드된 경우 스킵합니다 (중복 방지).

    Returns:
        로드된 환경 이름
    """
    global _loaded
    if _loaded:
        return os.environ.get('APP_ENV', 'unknown')

    # ── 환경 결정 (인자 > APP_ENV > 기본값 prd)
    if env is None:
        env = os.environ.get('APP_ENV', 'prd')

    env_key  = env.lower()
    # 'development' → 'dev' / 'production' → 'prd' 로 파일명 정규화
    _FILE_ALIAS = {'development': 'dev', 'production': 'prd', 'prod': 'prd'}
    env_file_key = _FILE_ALIAS.get(env_key, env_key)
    env_file = f'.env.{env_file_key}'
    env_path = os.path.join(_BASE_DIR, env_file)
    if not os.path.exists(env_path):
        logger.warning(f"환경설정 파일 없음: {env_path}")
        _loaded = True
        return env_key

    values = _parse_env_file(env_path)

    applied = []
    skipped = []
    for key, value in values.items():
        if key in os.environ:
            # 외부(systemd/docker)에서 이미 주입된 값은 덮어쓰지 않음
            skipped.append(key)
        else:
            os.environ[key] = value
            applied.append(key)

    _loaded = True

    msg = (
        f"✅ 환경설정 로드 완료: {env_file} "
        f"(적용 {len(applied)}개, 외부주입 스킵 {len(skipped)}개)"
    )
    logger.info(msg)

    return os.environ.get('APP_ENV', env_key)
