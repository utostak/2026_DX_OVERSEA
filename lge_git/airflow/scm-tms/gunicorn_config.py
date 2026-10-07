# ============================================================================
# Gunicorn Configuration — Dashboard Flask Application
# ============================================================================
import multiprocessing
import os
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# ── .env 파일 로드 (gunicorn 프로세스 시작 시점에 반영)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.env import load_env
load_env()

# ── 바인딩
_port = os.environ.get('APP_PORT', '9003')
bind  = f"0.0.0.0:{_port}"

# ── 워커 설정
#workers = multiprocessing.cpu_count() * 2 + 1
workers = 8
worker_class = "sync"          # sync | gevent | eventlet
worker_connections = 1000
timeout = 120                  # 초 (BigQuery 쿼리 시간 고려)
keepalive = 5

# ── 프로세스 이름
proc_name = "LIW"

# ── 로그
_log_dir  = os.environ.get('LOG_DIR', 'logs')
_backup   = 5   # 5일치 보관

# gunicorn 기본 파일 핸들러 (Logger.setup() 단계에서 사용 — 초기 에러도 파일에 기록)
# 5일 보관 롤링은 on_starting 훅에서 TimedRotatingFileHandler 로 교체
# ※ logconfig_dict 방식은 gunicorn Logger.setup() 내부 dictConfig() 충돌로
#    "Unable to configure root logger" 크래시 발생 → on_starting 훅 방식으로 대체
errorlog  = f"{_log_dir}/gunicorn.log"
accesslog = f"{_log_dir}/access.log"
loglevel  = os.environ.get('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── 재시작 / 데몬
reload        = False          # 운영환경에서는 False
daemon        = False          # supervisord / systemd 사용 시 False
preload_app   = True           # 워커 fork 전 앱 로드 → 메모리 절약

# ── 훅
def on_starting(server):
    """
    gunicorn Logger.setup() 완료 후 호출.
    gunicorn.error / gunicorn.access 핸들러를 TimedRotatingFileHandler(5일 보관)로 교체.
    ※ logconfig_dict 는 Logger.setup() 내부에서 dictConfig() 호출 → 충돌 크래시 위험.
       on_starting 훅은 setup() 이후 실행되므로 기존 핸들러를 안전하게 교체 가능.
    """
    import logging
    from logging.handlers import TimedRotatingFileHandler as _TRFH

    os.makedirs(_log_dir, exist_ok=True)

    _configs = [
        ('gunicorn.error',  f'{_log_dir}/gunicorn.log',
         '[%(asctime)s +0900] [%(process)d] [%(levelname)s] %(message)s'),
        ('gunicorn.access', f'{_log_dir}/access.log',
         '%(message)s'),
    ]
    for _name, _file, _fmt in _configs:
        _lg = logging.getLogger(_name)
        _lg.handlers.clear()
        _h = _TRFH(_file, when='midnight', interval=1,
                   backupCount=_backup, encoding='utf-8')
        _h.setFormatter(logging.Formatter(_fmt))
        _lg.addHandler(_h)
        _lg.propagate = False

    server.log.info("=" * 60)
    server.log.info(f" LIW Gunicorn Starting... [{os.environ.get('APP_ENV', '?')}]")
    server.log.info(f" Bind : {bind}")
    server.log.info("=" * 60)


def post_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")
