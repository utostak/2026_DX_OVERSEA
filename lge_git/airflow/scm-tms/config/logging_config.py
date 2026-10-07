"""
Logging Configuration
- logs/app.log   : LOG_LEVEL 이상 전체 로그 (1일 단위 롤링, 5일 보관)
- logs/error.log : ERROR 이상 에러 로그 (1일 단위 롤링, 5일 보관)
- logs/query.log : DB 쿼리 상세 로그  (1일 단위 롤링, 5일 보관) — 항상 DEBUG
- 콘솔           : LOG_LEVEL 이상 출력
※ LOG_LEVEL 환경변수(debug/info/warning/error)로 제어, 기본값 DEBUG.
   .env.prd → LOG_LEVEL=info : INFO 이상만 기록 (DEBUG 로그 생성 안 됨)

[멀티프로세스 안전]
  TimedRotatingFileHandler 는 멀티프로세스(gunicorn worker 등)에서
  자정 rotation 시 경쟁 조건이 발생합니다.
  → _MPTimedRotatingFileHandler 로 대체:
      emit() 마다 portalocker 로 파일 잠금 → rotation 직렬화
      rotation 후 잠금 해제 → 다른 worker 는 이미 회전된 파일 확인 후 skip
"""
import logging
import os
import re
import time
from logging.handlers import TimedRotatingFileHandler

import portalocker  # pip install portalocker

# ============================================================================
# 경로 설정
# ============================================================================
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR  = os.path.join(_BASE_DIR, 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)

APP_LOG_FILE   = os.path.join(_LOG_DIR, 'app.log')
ERROR_LOG_FILE = os.path.join(_LOG_DIR, 'error.log')
QUERY_LOG_FILE = os.path.join(_LOG_DIR, 'query.log')

# 날짜별 백업 로그 보관 개수 (5일치)
BACKUP_COUNT = 5
# 회전 파일 접미 형식(%Y%m%d) → 삭제 대상 식별용 정규식
_SUFFIX_FMT   = '%Y%m%d'
_SUFFIX_REGEX = re.compile(r'^\d{8}$', re.ASCII)        # 핸들러 extMatch 용 (부분 매칭)
_BACKUP_REGEX = re.compile(r'\.\d{8}$')                 # 파일명 ".YYYYMMDD" 식별용

# ============================================================================
# 포맷
# ============================================================================
_FMT_DETAIL = '%(asctime)s [%(levelname)-8s] %(name)s - %(message)s'
_FMT_SIMPLE = '%(asctime)s [%(levelname)-8s] %(message)s'
_DATE_FMT   = '%Y-%m-%d %H:%M:%S'

_detail_formatter = logging.Formatter(_FMT_DETAIL, datefmt=_DATE_FMT)
_simple_formatter = logging.Formatter(_FMT_SIMPLE, datefmt=_DATE_FMT)

# 중복 초기화 방지 플래그
_initialized = False


# ============================================================================
# 멀티프로세스 안전 TimedRotatingFileHandler
# ============================================================================
class _MPTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    portalocker 를 이용해 emit / doRollover 를 프로세스 간 직렬화합니다.

    동작 원리:
      1. emit() 진입 시 <파일명>.lock 을 exclusive lock
      2. rolloverAt 이 지난 경우: 아직 rotate 안 된 경우에만 doRollover() 실행
         (다른 worker 가 이미 회전했으면 rolloverAt 재계산 후 skip)
      3. 로그 레코드 기록
      4. lock 해제

    [Windows 호환]
      os.rename() 은 열린 파일에 대해 PermissionError 를 발생시킵니다.
      → rotate() 를 오버라이드하여 shutil.copy2 + truncate 방식으로 대체합니다.
    """

    def _lock_path(self) -> str:
        return self.baseFilename + '.lock'

    def rotate(self, source: str, dest: str) -> None:
        """Windows: 열린 파일 rename 불가 → copy + truncate 방식"""
        import shutil
        try:
            shutil.copy2(source, dest)
            with open(source, 'w', encoding='utf-8'):
                pass  # 원본 파일 내용 비우기 (핸들 유지)
        except Exception as e:
            self.handleError(logging.makeLogRecord({'msg': f'rotate error: {e}'}))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with open(self._lock_path(), 'a', encoding='utf-8') as lf:
                portalocker.lock(lf, portalocker.LOCK_EX)
                try:
                    # rotation 필요 여부 재확인 (lock 획득 후)
                    if self.shouldRollover(record):
                        # 다른 worker 가 이미 회전했는지 확인
                        # → 파일 수정 시각이 rolloverAt 이후면 이미 처리됨
                        try:
                            mtime = os.path.getmtime(self.baseFilename)
                        except FileNotFoundError:
                            mtime = 0
                        if mtime < self.rolloverAt:
                            self.doRollover()
                        else:
                            # 이미 다른 worker 가 rotate → 다음 시각 재계산
                            self.rolloverAt = self.computeRollover(int(time.time()))
                    logging.FileHandler.emit(self, record)
                finally:
                    portalocker.unlock(lf)
        except Exception:
            self.handleError(record)


def _make_handler(filepath: str, level: int,
                  formatter: logging.Formatter) -> _MPTimedRotatingFileHandler:
    """멀티프로세스 안전 1일 롤링 핸들러 생성 (5일 보관)"""
    handler = _MPTimedRotatingFileHandler(
        filepath,
        when='midnight',
        interval=1,
        backupCount=BACKUP_COUNT,
        encoding='utf-8',
        utc=False,
    )
    handler.suffix = _SUFFIX_FMT
    # ※ suffix 를 '%Y%m%d' 로 바꾸면 extMatch(기본: 대시 형식 \d{4}-\d{2}-\d{2})와
    #    불일치하여 getFilesToDelete() 가 회전 파일을 못 찾아 backupCount 가 무시된다.
    #    → suffix 에 맞는 정규식으로 교체해야 5일 보관이 정상 동작한다.
    handler.extMatch = _SUFFIX_REGEX
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _prune_old_logs(backup_count: int = BACKUP_COUNT) -> None:
    """
    기존에 쌓인 날짜별 백업 로그를 최신 N개만 남기고 정리.
    (과거 suffix/extMatch 불일치로 미삭제되어 누적된 파일까지 즉시 정리)
    - 현재 활성 로그(app.log 등)와 .lock 파일은 절대 건드리지 않는다.
    - 파일명이 ".YYYYMMDD" 로 끝나는 백업만 대상 (사전식 정렬 = 시간순).
    """
    for base in (APP_LOG_FILE, ERROR_LOG_FILE, QUERY_LOG_FILE):
        dir_name  = os.path.dirname(base)
        base_name = os.path.basename(base)
        prefix    = base_name + '.'
        try:
            backups = sorted(
                f for f in os.listdir(dir_name)
                if f.startswith(prefix) and _BACKUP_REGEX.search(f)
            )
        except FileNotFoundError:
            continue
        for old in backups[:max(0, len(backups) - backup_count)]:
            try:
                os.remove(os.path.join(dir_name, old))
            except OSError:
                pass


# ============================================================================
# 공개 API
# ============================================================================
def setup_logging() -> None:
    """
    루트 로거 초기화.  app.py 최상단에서 1회 호출하세요.
    gunicorn pre-fork 환경에서는 각 worker 가 독립적으로 호출해도
    _MPTimedRotatingFileHandler 가 파일 잠금으로 rotation 을 직렬화합니다.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.handlers.clear()

    # 환경설정에서 로그레벨 읽기 (LOG_LEVEL env: debug/info/warning/error → 기본 DEBUG)
    # ※ load_env() 가 setup_logging() 보다 먼저 호출되어야 env 파일 값이 반영됨 (app.py 순서 확인)
    _level_name = os.getenv('LOG_LEVEL', 'DEBUG').upper()
    _app_level  = getattr(logging, _level_name, logging.DEBUG)
    root.setLevel(_app_level)

    # 콘솔 (LOG_LEVEL 이상)
    console = logging.StreamHandler()
    console.setLevel(_app_level)
    console.setFormatter(_simple_formatter)

    # app.log  (LOG_LEVEL 이상 전체)
    app_fh = _make_handler(APP_LOG_FILE, _app_level, _detail_formatter)

    # error.log (ERROR 이상만)
    err_fh = _make_handler(ERROR_LOG_FILE, logging.ERROR, _detail_formatter)

    root.addHandler(console)
    root.addHandler(app_fh)
    root.addHandler(err_fh)

    # 시작 시 기존 누적 백업 즉시 정리 (5일치만 유지)
    _prune_old_logs()

    # 외부 라이브러리 노이즈 억제
    for noisy in ('werkzeug', 'urllib3', 'google', 'grpc'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── watchdog 무한 피드백 루프 3중 차단 ──────────────────────────────
    # 증상: Flask 리로더가 logs/ 를 감시하는 동안 app.log 에 뭔가 쓸 때마다
    #       inotify 이벤트 → watchdog DEBUG 기록 → app.log 에 씀 → 또 이벤트 → ...
    # ① setLevel(WARNING) : 로거 레벨에서 DEBUG 차단 (자식 로거 상속)
    # ② propagate=False   : root 핸들러 전파 완전 차단 (라이브러리 내부 레벨 재설정 대비)
    # ③ 핸들러 Filter     : root 핸들러까지 도달한 경우 최후 방어선 (타이밍 이슈 대비)
    for _wdn in ('watchdog', 'watchdog.observers', 'watchdog.observers.inotify_buffer'):
        _wdl = logging.getLogger(_wdn)
        _wdl.setLevel(logging.WARNING)
        _wdl.propagate = False

    class _NoWatchdogFilter(logging.Filter):
        """root 핸들러 최후 방어선: watchdog.* 레코드를 모두 차단"""
        def filter(self, record: logging.LogRecord) -> bool:
            return not record.name.startswith('watchdog')

    for _h in root.handlers:
        _h.addFilter(_NoWatchdogFilter())

    # 주요 앱 로거 명시적 활성화
    for name in ('app', 'utils.db_query', 'utils.subsdr_cache',
                 'apis.api_order', 'apis.api', 'apis.web', 'config'):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True

    logging.getLogger(__name__).info(
        f"✅ Logging initialized (multiprocess-safe) | "
        f"pid={os.getpid()} | level={_level_name} | "
        f"app={APP_LOG_FILE} | error={ERROR_LOG_FILE} | query={QUERY_LOG_FILE}"
    )


def get_query_logger() -> logging.Logger:
    """
    query.log 전용 로거 반환.
    - query.log : 쿼리 상세 (raw 포맷)
    - app.log   : propagate=True → DEBUG 레벨로 동시 기록
    utils/db_query.py 에서 지연 호출합니다.
    """
    ql = logging.getLogger('scm.query')
    if ql.handlers:
        return ql

    ql.setLevel(logging.DEBUG)
    ql.propagate = True

    qfh = _make_handler(QUERY_LOG_FILE, logging.DEBUG,
                        logging.Formatter('%(message)s'))
    ql.addHandler(qfh)
    return ql

