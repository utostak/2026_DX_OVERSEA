"""
batches_dynamic.py — 지정된 PostgreSQL 메타 DB 기반 Batch DAG 동적 생성
─────────────────────────────────────────────────────────────────
지정된 외부 PostgreSQL DB의 airflow_meta schema를 읽어
스케줄 배치 DAG를 자동 생성합니다.

각 task는 airflow_meta.job_dag 에 등록된 job을 호출합니다.
의존관계가 없는 task들은 자동으로 병렬 실행됩니다.
─────────────────────────────────────────────────────────────────
"""
import os
import re as _re
import json
import logging
import traceback
from urllib.parse import quote_plus
import pendulum
from airflow.sdk import dag, task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# .env 파일 로드 — DAG 파일 위치 기준으로 탐색 (plugins/.env → dags/.env 순)
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    _here = _Path(__file__).parent
    for _env_path in [
        _here / ".env",
        _here / "plugins" / ".env",
        _here.parent / "plugins" / ".env",  # Docker: /opt/airflow/plugins/.env
    ]:
        if _env_path.exists():
            load_dotenv(_env_path, override=False)
            break
    else:
        load_dotenv(override=False)  # 환경변수에서 직접 읽기 시도
except ImportError:
    pass

_START   = pendulum.datetime(2025, 1, 1, tz="Asia/Seoul")
_log     = logging.getLogger(__name__)

# ── 환경변수 기반 실행 제어 설정 ────────────────────────────────────
# .env 파일 또는 시스템 환경변수에서 읽어옵니다.
# ※ 동시 "실행" 수만 제어합니다. DAG 등록(로드)은 항상 전체가 됩니다.
_MAX_ACTIVE_TASKS_PER_BATCH  = int(os.environ.get("MAX_ACTIVE_TASKS_PER_BATCH", "16") or "16")
_MAX_ACTIVE_RUNS_PER_BATCH   = int(os.environ.get("MAX_ACTIVE_RUNS_PER_BATCH", "1") or "1")

# 동시에 실행할 수 있는 최대 Batch DAG 수 (0 = 무제한)
# 공용 Pool 로 전체 동시 task 수를 제어한다.
#   · Pool 슬롯 수 = MAX_CONCURRENT_BATCHES × MAX_ACTIVE_TASKS_PER_BATCH
#   · 각 배치는 내부적으로 max_active_tasks(=MAX_ACTIVE_TASKS_PER_BATCH)개까지 병렬 실행
#   · 예) 4배치 × 2태스크 → Pool 슬롯 8개 = 전체 동시 task 최대 8개
_MAX_CONCURRENT_BATCHES = int(os.environ.get("MAX_CONCURRENT_BATCHES", "0") or "0")
_BATCH_POOL_NAME = "batch_concurrency_pool"
# 공용 Pool 총 슬롯 수 (동시 실행 batch × batch당 동시 task)
_BATCH_POOL_SLOTS = _MAX_CONCURRENT_BATCHES * _MAX_ACTIVE_TASKS_PER_BATCH
# Pool 준비 여부 — 생성/확인 성공 시에만 task에 pool 을 지정한다.
# (존재하지 않는 pool 을 참조하면 task 가 영원히 'scheduled' 상태로 멈춤)
_POOL_READY = False


def _ensure_batch_pool():
    """MAX_CONCURRENT_BATCHES 설정 시 공용 Pool 사용 여부를 결정한다.

    ※ Airflow 3.x 는 DAG 파싱(dag-processor) 프로세스에서 DB(ORM) 접근을 금지한다.
      따라서 Pool 은 이 파일에서 만들지 않고, **컨테이너 시작 시 1회**
      `airflow pools set` 으로 생성한다(아래 안내 참조). 파싱 단계에서는
      Pool 이 이미 존재한다고 가정하고 task 에 pool 을 지정하기만 한다.

      ┌── 컨테이너 시작 스크립트(entrypoint / docker-compose)에 1회 추가 ──┐
      │  airflow pools set batch_concurrency_pool \                        │
      │      "$((MAX_CONCURRENT_BATCHES * MAX_ACTIVE_TASKS_PER_BATCH))" \  │
      │      "동시 실행 task 수 제어"                                        │
      └──────────────────────────────────────────────────────────────────┘
      (idempotent — 이미 있으면 슬롯만 갱신)

    반환: Pool 사용 여부(bool). MAX_CONCURRENT_BATCHES>0 이면 True.
    """
    global _POOL_READY
    if _MAX_CONCURRENT_BATCHES <= 0:
        return False
    # 컨테이너 시작 시 Pool 이 생성되었다고 가정 → task 에 pool 지정 허용
    _POOL_READY = True
    return True


# ── SQL 변수 처리 ──────────────────────────────────────────────────
# SQL 내 치환 가능 변수:
#   · 기본 변수:  {BATCH_DT}  {PREV_BATCH_DT}  {NEXT_BATCH_DT}  (스케줄 기준 자동 계산)
#   · 사용자 변수: {ANY_UPPER_NAME}  (배치 task 의 task_vars 또는 수작업 입력값으로 치환)
_VAR_RE = _re.compile(r'\{([A-Z][A-Z0-9_]*)\}')
_BATCH_VAR_KEYS = ('BATCH_DT', 'PREV_BATCH_DT', 'NEXT_BATCH_DT')


def _interval_from_schedule(schedule: str) -> 'pendulum.Duration':
    """cron 문자열 → pendulum.Duration. 인식 불가 시 1일 기본값."""
    if not schedule:
        return pendulum.duration(days=1)
    s = schedule.strip()
    _aliases = {
        '@hourly': '0 * * * *', '@daily': '0 0 * * *',
        '@weekly': '0 0 * * 0', '@monthly': '0 0 1 * *',
        '@annually': '0 0 1 1 *', '@yearly': '0 0 1 1 *',
    }
    s = _aliases.get(s, s)
    pts = s.split()
    if len(pts) < 5:
        return pendulum.duration(days=1)
    min_f, hr_f, dom_f, mon_f, dow_f = pts[:5]
    m = _re.match(r'^\*/(\d+)$', min_f)
    if m and hr_f == '*':                                   # */N분
        return pendulum.duration(minutes=int(m.group(1)))
    m = _re.match(r'^\*/(\d+)$', hr_f)
    if m:                                                   # */N시간
        return pendulum.duration(hours=int(m.group(1)))
    if hr_f == '*' and _re.match(r'^\d+$', min_f):         # 매시
        return pendulum.duration(hours=1)
    if _re.match(r'^\d+$', hr_f) and dom_f == '*' and mon_f == '*':  # 매일
        return pendulum.duration(days=1)
    if dom_f == '*' and mon_f == '*' and _re.match(r'^\d+$', dow_f):  # 주간
        return pendulum.duration(weeks=1)
    if _re.match(r'^\d+$', dom_f) and mon_f == '*' and dow_f == '*':  # 월간
        return pendulum.duration(months=1)
    return pendulum.duration(days=1)


def _next_schedule_after(schedule: str, after_dt: 'pendulum.DateTime') -> 'pendulum.DateTime':
    """schedule(cron) 기준 after_dt '이후'의 다음 실행 경계 시각을 반환한다.

    등록 시각을 그대로 start_date 로 쓰면, CronDataIntervalTimetable + catchup=False
    조합에서 첫 data_interval 이 [등록시각, 다음경계) 가 되어 '이전 시간대' 구간이
    다음 경계에 바로 실행된다(예: 08:xx 등록 → 09:00 에 08시 구간 실행).

    이를 막기 위해 start_date 를 '다음 경계'로 올려, 첫 구간이 [다음경계, 그다음경계)
    가 되도록 한다. 즉 등록 이후 '다음 시간'부터 정상 실행된다.

    croniter 사용 불가/파싱 실패 시 _interval_from_schedule 기반으로 근사 계산한다.
    """
    s = (schedule or "").strip()
    if not s:
        return after_dt
    _aliases = {
        '@hourly': '0 * * * *', '@daily': '0 0 * * *',
        '@weekly': '0 0 * * 0', '@monthly': '0 0 1 * *',
        '@annually': '0 0 1 1 *', '@yearly': '0 0 1 1 *',
    }
    cron = _aliases.get(s, s)
    # @once, @continuous 등 preset 은 경계 개념이 없으므로 그대로 반환
    if cron.startswith('@'):
        return after_dt
    try:
        from croniter import croniter
        base = after_dt.in_tz("Asia/Seoul")
        # 파이썬 datetime 으로 변환 (croniter 는 tz-aware datetime 지원)
        itr = croniter(cron, base)
        nxt = itr.get_next(pendulum.DateTime)
        return pendulum.instance(nxt).in_tz("Asia/Seoul")
    except Exception as _e:
        _log.debug(f"[_next_schedule_after] croniter 실패({_e!r}) → interval 근사 사용")
        try:
            return after_dt + _interval_from_schedule(cron)
        except Exception:
            return after_dt


def _get_batch_schedule(dag_id: str) -> str:
    """meta DB에서 dag_id의 schedule 조회. 실패 시 빈 문자열."""
    try:
        import psycopg2 as _pg
        conn = _pg.connect(
            host=os.environ.get("META_PG_HOST", "10.182.32.210"),
            port=int(os.environ.get("META_PG_PORT", "8110")),
            dbname=os.environ.get("META_PG_DB", "airflow_db"),
            user=os.environ.get("META_PG_USER", "airflow"),
            password=os.environ.get("META_PG_PASSWORD", "oss123~!@"),
            sslmode=os.environ.get("META_PG_SSLMODE", "disable"),
        )
        cur = conn.cursor()
        cur.execute("SELECT schedule FROM airflow_meta.batch_dag WHERE dag_id=%s", (dag_id,))
        row = cur.fetchone()
        conn.close()
        return (row[0] or '') if row else ''
    except Exception as _e:
        _log.debug(f"[_get_batch_schedule] 조회 실패 (무시): {_e}")
        return ''


def _resolve_batch_vars(context: dict, task_vars: dict = None) -> dict:
    """
    실행 컨텍스트에서 SQL 변수 값을 해석합니다.
    ─ 정기 실행(scheduled): Airflow data_interval_start/end 기준 자동 계산
    ─ 수작업 실행(manual):  dag_run.conf['batch_vars'] 에서 읽기
    task_vars: 배치 task 에 고정된 사용자 정의 변수값 (기본 변수보다 우선하지 않고,
               기본 변수에 없는 사용자 변수를 채운다)
    반환: {'BATCH_DT': 'YYYY-MM-DD HH:MM:SS', ..., 'MY_VAR': '...'}
    """
    dag_run = context.get('dag_run')
    _rt_raw = getattr(dag_run, 'run_type', None)
    run_type_str = str(getattr(_rt_raw, 'value', _rt_raw) or '').lower()
    tz = pendulum.timezone("Asia/Seoul")

    if 'scheduled' in run_type_str:
        # dag_run 속성 → context 최상위 순서로 fallback
        start = (getattr(dag_run, 'data_interval_start', None)
                 or context.get('data_interval_start'))
        end   = (getattr(dag_run, 'data_interval_end',   None)
                 or context.get('data_interval_end'))
        if start is None:
            start = context.get('logical_date') or context.get('execution_date')
        start_kst = pendulum.instance(start).in_tz(tz) if start else pendulum.now(tz)
        end_kst   = pendulum.instance(end).in_tz(tz)   if end   else start_kst
        interval  = end_kst - start_kst
        if interval.total_seconds() <= 0:
            # data_interval_end가 없거나 start와 같으면 schedule 기반으로 interval 계산
            dag_id   = getattr(dag_run, 'dag_id', '') or ''
            schedule = _get_batch_schedule(dag_id)
            interval = _interval_from_schedule(schedule)
            _log.warning(f"[{dag_id}] data_interval_end 부재 → schedule({schedule!r}) 기준 interval={interval} 사용")
        prev_kst = start_kst - interval
        resolved = {
            'BATCH_DT':      start_kst.strftime('%Y-%m-%d %H:%M:%S'),
            'PREV_BATCH_DT': prev_kst.strftime('%Y-%m-%d %H:%M:%S'),
            'NEXT_BATCH_DT': (start_kst + interval).strftime('%Y-%m-%d %H:%M:%S'),
        }
    else:
        # 수작업 실행: conf['batch_vars'] 에서 읽기 (기본 + 사용자 변수 모두 포함 가능)
        conf = getattr(dag_run, 'conf', {}) or {}
        batch_vars = conf.get('batch_vars', {}) or {}
        resolved = dict(batch_vars)
        for k in _BATCH_VAR_KEYS:
            resolved.setdefault(k, batch_vars.get(k, ''))

    # ── 사용자 정의 변수(task_vars) 병합: 아직 값이 없는 키만 채운다 ──
    for k, v in (task_vars or {}).items():
        if not resolved.get(k):
            resolved[k] = v
    return resolved


def _substitute_vars(sql_text: str, vars_dict: dict) -> str:
    """SQL의 {변수명} 플레이스홀더를 값으로 치환합니다.
    _VAR_RE 매칭 항목만 치환하므로 다른 중괄호({})는 그대로 유지됩니다."""
    def _repl(m):
        return vars_dict.get(m.group(1), m.group(0))
    return _VAR_RE.sub(_repl, sql_text)


def _substitute_params(params: dict, vars_dict: dict) -> dict:
    """params dict의 모든 문자열 값에 변수 치환을 적용합니다.
    문자열(str) 값만 치환하고, 나머지 타입은 그대로 유지합니다."""
    return {
        k: (_substitute_vars(v, vars_dict) if isinstance(v, str) else v)
        for k, v in params.items()
    }


# ── DB 메타 일괄 조회 (지정된 PG 접속 정보 사용) ──────────────────
def _load_meta():
    # .env 환경 변수 조회 (없을 경우 기본값 적용)
    host = os.environ.get("META_PG_HOST", "10.182.32.210")
    port = os.environ.get("META_PG_PORT", "8110")
    db = os.environ.get("META_PG_DB", "airflow_db")
    user = os.environ.get("META_PG_USER", "airflow")
    password = os.environ.get("META_PG_PASSWORD", "oss123~!@")
    sslmode = os.environ.get("META_PG_SSLMODE", "disable")

    # 특수문자가 포함된 비밀번호는 URL 인코딩이 필수입니다.
    safe_password = quote_plus(password)
    db_url = f"postgresql://{user}:{safe_password}@{host}:{port}/{db}?sslmode={sslmode}"

    # 커넥션 풀 및 엔진 생성
    engine = create_engine(db_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 1. Batch DAG 메타 조회
        batch_dags_query = text("""
            SELECT dag_id, schedule, tags, description, created_at
              FROM airflow_meta.batch_dag
             WHERE is_active
             ORDER BY dag_id
        """)
        # 2. Batch Task 메타 조회 (Job 정보 조인)
        # retries/retry_delay_minutes 컬럼이 아직 없는 DB를 위해 폴백 쿼리 사용
        _batch_task_queries = [
            text("""
                SELECT bt.dag_id, bt.task_id, bt.job_id,
                       jd.func_name, jd.sql_text, jd.params_json,
                       COALESCE(jd.owner_emails, '{}')         AS owner_emails,
                       COALESCE(jd.retries, 0)                 AS retries,
                       COALESCE(jd.retry_delay_minutes, 1)     AS retry_delay_minutes,
                       COALESCE(bt.task_vars, '{}')            AS task_vars
                  FROM airflow_meta.batch_task  bt
                  JOIN airflow_meta.job_dag     jd ON jd.job_id = bt.job_id
                 ORDER BY bt.dag_id, bt.task_id
            """),
            text("""
                SELECT bt.dag_id, bt.task_id, bt.job_id,
                       jd.func_name, jd.sql_text, jd.params_json,
                       COALESCE(jd.owner_emails, '{}')  AS owner_emails,
                       0                                AS retries,
                       1                                AS retry_delay_minutes,
                       COALESCE(bt.task_vars, '{}')     AS task_vars
                  FROM airflow_meta.batch_task  bt
                  JOIN airflow_meta.job_dag     jd ON jd.job_id = bt.job_id
                 ORDER BY bt.dag_id, bt.task_id
            """),
        ]
        # 3. Task 의존성 메타 조회
        batch_deps_query = text("""
            SELECT dag_id, upstream, downstream,
                   COALESCE(trigger_type, 'on_success') AS trigger_type,
                   trigger_value
              FROM airflow_meta.batch_task_dep
             ORDER BY dag_id
        """)

        batch_dags  = session.execute(batch_dags_query).fetchall()
        batch_tasks = None
        for _btq in _batch_task_queries:
            try:
                batch_tasks = session.execute(_btq).fetchall()
                break
            except Exception as _qe:
                _log.warning(f"[batches_dynamic] batch_tasks 쿼리 폴백: {_qe}")
                session.rollback()
        if batch_tasks is None:
            raise RuntimeError("batch_tasks 메타 조회 실패 (폴백 쿼리도 실패)")
        batch_deps  = session.execute(batch_deps_query).fetchall()

        return batch_dags, batch_tasks, batch_deps
    finally:
        session.close()
        engine.dispose()  # Airflow 스케줄러가 주기적으로 파싱할 때 커넥션 누수를 방지합니다.


# ── 메일 공통 모듈 ─────────────────────────────────────────────────
from utils.mail_util import send_email as _send_email, SMTP_FROM as _SMTP_FROM, SMTP_DEFAULT_TO as _SMTP_DEFAULT_TO


# ── 정기 배치 실패 시 담당자 이메일 발송 콜백 ──────────────────────
def _make_failure_callback(emails: list):
    """정기 배치(scheduled) 실행 중 task 최종 실패 시에만 담당자에게 이메일 발송.
    retry 중에는 발송하지 않고, 최종 실패(모든 retry 소진 후)에만 발송한다.
    수동 실행(manual/backfill)은 발송하지 않는다."""
    def _on_failure(context):
        _log.info("[batches_dynamic] ▶ on_failure_callback 호출됨")
        dag_run = context.get('dag_run')
        if not dag_run:
            _log.warning("[batches_dynamic] on_failure_callback: dag_run 없음 → 종료")
            return

        # ── retry 여부 확인: retry 중이면 메일 발송 건너뜀 ────────────
        ti = context.get('task_instance') or context.get('ti')
        if ti:
            try_num = getattr(ti, 'try_number', 1)
            max_tries = getattr(ti, 'max_tries', 1)
            _log.info(f"[batches_dynamic] on_failure_callback: try_number={try_num}, max_tries={max_tries}")
            if try_num < max_tries:
                _log.info(f"[batches_dynamic] retry 중 ({try_num}/{max_tries}) → 메일 발송 건너뜀")
                return  # retry 중에는 메일 발송 안 함
        
        # ── on_failure gate 용 failure signal XCom push ───────────
        # gate task 가 이 신호를 읽어 downstream skip 여부를 결정한다
        _cb_ti = context.get('task_instance') or context.get('ti')
        if _cb_ti is not None:
            try:
                _cb_ti.xcom_push(key='_failure_signal', value=True)
                _log.info(f"[batches_dynamic] _failure_signal XCom push 완료: {_cb_ti.task_id}")
            except Exception as _xe:
                _log.warning(f"[batches_dynamic] _failure_signal XCom push 실패 (무시): {_xe}")

        # ── batch_run_log 실패 상태 갱신 ──────────────────────────
        try:
            from utils.log_util import ensure_batch_run_log, update_batch_run_log
            ensure_batch_run_log(context)   # 누락 시 INSERT 보장
            update_batch_run_log(context, 'failed')
        except Exception as _le:
            _log.warning(f"[batches_dynamic] batch_run_log 실패 갱신 실패 (무시): {_le}")

        # ── 'running' 상태로 stuck된 job_run_log 강제 종료 ────────
        # worker kill / timeout 등으로 _run() except 블록이 실행되지 못한 경우 대비
        try:
            _cb_run_id  = getattr(dag_run, 'run_id', None)
            _cb_dag_id  = getattr(dag_run, 'dag_id', None)
            _cb_task_id = getattr(_cb_ti, 'task_id', None) if _cb_ti else None
            _cb_exc     = str(context.get('exception', ''))[:2000] or 'task 실패 (원인 불명)'
            if _cb_run_id and _cb_dag_id and _cb_task_id:
                from utils.log_util import fail_running_job_logs
                fail_running_job_logs(_cb_run_id, _cb_dag_id, _cb_task_id, _cb_exc)
        except Exception as _le:
            _log.warning(f"[batches_dynamic] fail_running_job_logs 실패 (무시): {_le}")

        # run_type: str 또는 Enum(DagRunType) 모두 처리
        # - str 상속 enum: str(value) == 'scheduled'
        # - 일반 enum:      value.value == 'scheduled'
        # - 문자열:         value == 'scheduled'
        _rt_raw = getattr(dag_run, 'run_type', None)
        run_type_str = str(getattr(_rt_raw, 'value', _rt_raw) or '').lower()
        _log.info(f"[batches_dynamic] on_failure_callback: run_type={_rt_raw!r} → '{run_type_str}'")
        if 'scheduled' not in run_type_str:
            _log.info("[batches_dynamic] on_failure_callback: 수동/백필 실행 → 메일 발송 안 함")
            return

        to_list = emails or [e.strip() for e in os.environ.get("SMTP_DEFAULT_TO", "").split(",") if e.strip()]
        if not to_list:
            # 수신자가 없으면 메일만 건너뛰고 Teams 알림은 계속 진행한다.
            _log.warning(
                "[batches_dynamic] on_failure_callback: 수신자 없음 "
                "(owner_emails 미설정, SMTP_DEFAULT_TO 비어있음) → 메일 미발송 (Teams 알림은 발송)"
            )
        else:
            try:
                dag_obj   = context.get('dag')
                dag_id    = getattr(dag_obj, 'dag_id', '(unknown)') if dag_obj else '(unknown)'
                ti        = context.get('task_instance') or context.get('ti')
                task_id   = getattr(ti, 'task_id', '(unknown)') if ti else '(unknown)'
                run_id    = getattr(dag_run, 'run_id', '')
                exception = context.get('exception', '(알 수 없음)')
                log_url   = getattr(ti, 'log_url', '') if ti else ''
                # log_url의 host(localhost:8080)를 실제 Airflow URL로 교체
                _airflow_base = os.environ.get("AIRFLOW_URL", "").rstrip("/")
                if log_url and _airflow_base:
                    from urllib.parse import urlparse as _urlparse
                    _parsed = _urlparse(log_url)
                    log_url = _airflow_base + _parsed.path + (
                        ("?" + _parsed.query) if _parsed.query else ""
                    )
                subject   = f"[Airflow 오류] {dag_id} / {task_id}"
                html_content = f"""
<h3>🚨 Airflow Task 실패 알림</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse;font-size:13px">
  <tr><td><b>DAG</b></td><td>{dag_id}</td></tr>
  <tr><td><b>Task</b></td><td>{task_id}</td></tr>
  <tr><td><b>Run ID</b></td><td>{run_id}</td></tr>
  <tr><td><b>오류 내용</b></td>
      <td><pre style="color:red;white-space:pre-wrap">{exception}</pre></td></tr>
</table>
{"<p><a href='" + log_url + "'>📋 로그 보기</a></p>" if log_url else ""}
"""
                _log.info(f"[batches_dynamic] 최종 실패 알림 메일 발송 시도 → to={to_list}, dag={dag_id}, task={task_id}")
                _send_email(to_addrs=to_list, subject=subject, body=html_content)
                _log.info(f"[batches_dynamic] 최종 실패 알림 발송 완료 → {to_list} ({dag_id}/{task_id})")
            except Exception as e:
                _log.error(f"[batches_dynamic] 실패 알림 메일 발송 오류: {e}", exc_info=True)

        # ── Teams 그룹 채팅 알림 발송 (메일과 별개로 시도) ─────────
        try:
            from utils.teams import send_group_chat_message
            dag_obj   = context.get('dag')
            dag_id    = getattr(dag_obj, 'dag_id', '(unknown)') if dag_obj else '(unknown)'
            ti        = context.get('task_instance') or context.get('ti')
            task_id   = getattr(ti, 'task_id', '(unknown)') if ti else '(unknown)'
            run_id    = getattr(dag_run, 'run_id', '')
            exception = context.get('exception', '(알 수 없음)')
            teams_msg = (
                f"🚨 Airflow Task 실패 알림\n"
                f"• DAG: {dag_id}\n"
                f"• Task: {task_id}\n"
                f"• Run ID: {run_id}\n"
                f"• 오류: {str(exception)[:500]}"
            )
            _log.info(f"[batches_dynamic] Teams 실패 알림 발송 시도 → dag={dag_id}, task={task_id}")
            send_group_chat_message(message=teams_msg)
            _log.info(f"[batches_dynamic] Teams 실패 알림 발송 완료 → {dag_id}/{task_id}")
        except Exception as e:
            _log.error(f"[batches_dynamic] Teams 실패 알림 발송 오류: {e}", exc_info=True)
    return _on_failure


# ── task 실행 함수 빌더 ────────────────────────────────────────────
def _make_run_fn(task_id: str, job_id: str, func_name: str, sql_text: str, params: dict,
                 task_vars: dict = None):
    task_vars = task_vars or {}
    # SQL 또는 params 문자열 값에 치환 변수가 있으면 변수 처리 필요
    _has_vars = bool(_VAR_RE.search(sql_text)) or any(
        _VAR_RE.search(str(v)) for v in params.values() if v
    )
    # 기본 변수(BATCH_DT 등)를 제외한, task_vars 로 채워지지 않은 사용자 변수만
    # 수작업 실행 시 입력이 필요하다.

    def _run():
        import signal as _signal
        resolved_sql    = sql_text
        resolved_params = params          # 변수 치환 후 params (미치환 시 원본 그대로)
        _log_id = None
        _log_id_ref = [None]  # SIGTERM 핸들러용 mutable 참조
        result  = None

        # context 는 항상 가져옴 (변수 치환 + 로그 공통 사용)
        from airflow.sdk import get_current_context
        ctx = get_current_context()

        # ── SIGTERM 핸들러: Airflow 강제 종료 시 DB 로그 즉시 정리 ──
        def _sigterm_handler(signum, frame):
            _log.warning(f"[batches_dynamic] ⚠️  SIGTERM 수신 ({task_id}) → job_run_log 강제 종료 처리")
            try:
                if _log_id_ref[0] is not None:
                    from utils.log_util import end_job_run_log
                    end_job_run_log(_log_id_ref[0], 'failed',
                                    error_msg='Airflow 강제 종료 (SIGTERM)')
            except Exception as _se:
                _log.warning(f"[batches_dynamic] SIGTERM 처리 중 오류 (무시): {_se}")
            raise SystemExit(1)

        _prev_sigterm = _signal.signal(_signal.SIGTERM, _sigterm_handler)

        try:
            # ── 0. 배치 실행 로그 시작 ────────────────────────────
            try:
                from utils.log_util import ensure_batch_run_log
                ensure_batch_run_log(ctx)
            except Exception as _le:
                _log.warning(f"[batches_dynamic] ensure_batch_run_log 실패 (무시): {_le}")

            # ── 1. job 실행 로그 시작 (변수 치환 전 — 가능한 빨리 생성) ─
            # 변수 치환 실패 / 실행 실패 / worker kill 등 모든 경우에서
            # on_failure_callback 의 fail_running_job_logs 가 'failed' 로 갱신할 수 있도록
            # 실행 초반에 'running' 행을 INSERT 한다
            try:
                from utils.log_util import begin_job_run_log
                _log_id = begin_job_run_log(ctx, task_id, job_id, 'batch', sql_text, params)
                _log_id_ref[0] = _log_id   # SIGTERM 핸들러에서 접근
            except Exception as _le:
                _log.warning(f"[batches_dynamic] begin_job_run_log 실패 (무시): {_le}")

            # ── 2. SQL + params 변수 치환 ─────────────────────────
            if _has_vars:
                dag_run = ctx.get('dag_run')
                _rt_raw = getattr(dag_run, 'run_type', None)
                run_type_str = str(getattr(_rt_raw, 'value', _rt_raw) or '').lower()

                # SQL + params 전체에서 사용된 변수 목록
                all_vars_used = list(dict.fromkeys(
                    _VAR_RE.findall(sql_text)
                    + [v for pv in params.values() if isinstance(pv, str)
                       for v in _VAR_RE.findall(pv)]
                ))

                if 'scheduled' not in run_type_str:
                    conf = getattr(dag_run, 'conf', {}) or {}
                    # task_vars 로 값이 채워지지 않은 변수만 수작업 입력이 필요
                    _need_input = [k for k in all_vars_used if not task_vars.get(k)]
                    if _need_input and not conf.get('batch_vars'):
                        raise ValueError(
                            f"변수 {_need_input}가 있지만 수작업 실행 시 값을 입력하지 않았습니다.\n"
                            "Airflow UI 대신 Batch Meta UI의 ▶ 수작업 실행 버튼을 사용해 주세요."
                        )

                # 기본 변수 + 수작업 입력값 + task 고정 변수(task_vars) 병합
                batch_vars = _resolve_batch_vars(ctx, task_vars)
                missing = [k for k in all_vars_used if not batch_vars.get(k)]
                if missing:
                    raise ValueError(f"변수 값이 비어있습니다: {missing}")
                resolved_sql    = _substitute_vars(sql_text, batch_vars)
                resolved_params = _substitute_params(params, batch_vars)
                _log.info(f"[batches_dynamic] {task_id}: SQL+params 변수 치환 완료 → {batch_vars}")
                # 치환 후 실제 실행값으로 job_run_log 갱신 (UI/로그에 치환된 SQL 표시)
                try:
                    if _log_id is not None:
                        from utils.log_util import update_job_run_log_sql
                        update_job_run_log_sql(_log_id, resolved_sql, resolved_params)
                except Exception as _le:
                    _log.warning(f"[batches_dynamic] job_run_log SQL 갱신 실패 (무시): {_le}")

            # ── 3. 실제 실행 ─────────────────────────────────────
            if func_name == "execute_sql_ptg":
                from utils.db_util import execute_sql_ptg
                result = execute_sql_ptg(resolved_sql)

            elif func_name == "execute_sql_bq":
                from utils.db_util import execute_sql_bq
                result = execute_sql_bq(resolved_sql)

            elif func_name == "replicate_bq_to_ptg":
                from utils.db_util import replicate_bq_to_ptg
                _rp      = resolved_params
                _pre_sql = _rp.get("pre_sql") or None
                # 하위 호환: 기존 params에 where_clause가 있으면 pre_sql(DELETE)로 자동 변환
                if not _pre_sql and _rp.get("where_clause"):
                    _pre_sql = f"DELETE FROM {_rp['dst_table']} WHERE {_rp['where_clause']}"
                    _log.info(f"[batches_dynamic] {task_id}: where_clause → pre_sql 자동 변환: {_pre_sql}")
                replicate_bq_to_ptg(
                    bq_sql    = resolved_sql,
                    if_table  = _rp["if_table"],
                    dst_table = _rp["dst_table"],
                    pre_sql   = _pre_sql,
                    post_sql  = _rp.get("post_sql") or None,
                )

            elif func_name == "replicate_bq_to_ptg2":
                from utils.db_util import replicate_bq_to_ptg2
                _rp      = resolved_params
                _pre_sql = _rp.get("pre_sql") or None
                # 하위 호환: 기존 params에 where_clause가 있으면 pre_sql(DELETE)로 자동 변환
                if not _pre_sql and _rp.get("where_clause"):
                    _pre_sql = f"DELETE FROM {_rp['dst_table']} WHERE {_rp['where_clause']}"
                    _log.info(f"[batches_dynamic] {task_id}: where_clause → pre_sql 자동 변환: {_pre_sql}")
                _kw2 = {}
                if _rp.get("rows_per_file"):
                    _kw2["rows_per_file"] = int(_rp["rows_per_file"])
                if _rp.get("dump_workers"):
                    _kw2["dump_workers"] = int(_rp["dump_workers"])
                if _rp.get("load_workers"):
                    _kw2["load_workers"] = int(_rp["load_workers"])
                replicate_bq_to_ptg2(
                    bq_sql    = resolved_sql,
                    if_table  = _rp["if_table"],
                    dst_table = _rp["dst_table"],
                    pre_sql   = _pre_sql,
                    post_sql  = _rp.get("post_sql") or None,
                    **_kw2,
                )

            elif func_name == "replicate_ptg_to_bq_table":
                from utils.db_util import replicate_ptg_to_bq_table
                replicate_ptg_to_bq_table(
                    ptg_sql     = resolved_sql,
                    bq_table_id = resolved_params["bq_table_id"],
                )
            elif func_name == "execute_python_module":
                from utils.py_module_util import run_python_module
                result = run_python_module(resolved_params, resolved_sql, ctx)
            else:
                raise ValueError(f"지원하지 않는 func_name: {func_name}")

            # ── 4. 성공 로그 ─────────────────────────────────────
            try:
                if _log_id is not None:
                    from utils.log_util import end_job_run_log
                    rv = str(result)[:500] if result is not None else None
                    end_job_run_log(_log_id, 'success', result_value=rv)
            except Exception as _le:
                _log.warning(f"[batches_dynamic] 실행 로그 성공 갱신 실패 (무시): {_le}")

            return result

        except Exception as _exc:
            _is_skip = type(_exc).__name__ == 'AirflowSkipException'
            # concurrent.futures.TimeoutError 처럼 str(_exc)가 빈 문자열인 경우가 있어
            # 그대로 저장하면 error_msg 가 NULL 로 기록된다 → 타입명으로 대체하여 항상 남긴다.
            _err_msg = (str(_exc) or '').strip()
            if not _err_msg:
                _nm = type(_exc).__name__
                if 'Timeout' in _nm:
                    _err_msg = (f"{_nm}: 쿼리 응답 대기 타임아웃 "
                                f"(client-side 취소/장기 실행 추정 — Airflow/BQ 로그 확인)")
                else:
                    _err_msg = f"{_nm} (상세 메시지 없음)"
            try:
                if _log_id is not None:
                    from utils.log_util import end_job_run_log
                    end_job_run_log(
                        _log_id,
                        'skipped' if _is_skip else 'failed',
                        error_msg=None if _is_skip else _err_msg[:2000]
                    )
            except Exception as _le:
                _log.warning(f"[batches_dynamic] 실행 로그 종료 기록 실패 (무시): {_le}")
            raise

        finally:
            # SIGTERM 핸들러를 원래 핸들러로 복원
            try:
                _signal.signal(_signal.SIGTERM, _prev_sigterm)
            except Exception:
                pass

    _run.__name__ = task_id
    return _run


# ── DAG 생성 팩토리 ────────────────────────────────────────────────
_META_URL = "http://10.182.33.70:8117"

def _on_batch_success(context):
    """DAG run 전체 성공 시 batch_run_log 상태 갱신."""
    try:
        from utils.log_util import ensure_batch_run_log, update_batch_run_log
        ensure_batch_run_log(context)
        update_batch_run_log(context, 'success')
    except Exception as e:
        _log.warning(f"[batches_dynamic] batch_run_log 성공 갱신 실패 (무시): {e}")


def _on_batch_failure(context):
    """DAG run 실패 시 batch_run_log 상태 갱신 (DAG 레벨 콜백 — 가장 신뢰성 높음)."""
    try:
        from utils.log_util import ensure_batch_run_log, update_batch_run_log
        ensure_batch_run_log(context)
        update_batch_run_log(context, 'failed')
    except Exception as e:
        _log.warning(f"[batches_dynamic] batch_run_log 실패 갱신 실패 (무시): {e}")

def _normalize_schedule(schedule):
    """
    schedule 값을 검증/정규화한다. (AirflowTimetableInvalid 사전 차단)
      - None / 빈 문자열       → None (스케줄 없음, 수동 실행)
      - '@daily' 등 preset     → 그대로 사용
      - cron 5/6/7 필드        → 그대로 사용
      - 그 외(필드 수 불일치)  → ValueError 발생 → 해당 배치만 건너뜀
    """
    if schedule is None:
        return None
    s = str(schedule).strip()
    if not s:
        return None
    if s.startswith("@"):           # @daily, @hourly, @once 등 Airflow preset
        return s
    parts = s.split()
    if len(parts) in (5, 6, 7):     # 표준 cron(5) / 초 포함(6) / 초+연(7)
        return s
    raise ValueError(
        f"잘못된 cron 표현식 (필드 수 {len(parts)}개, 5/6/7 필요): '{schedule}'"
    )


def _create_batch_dag(dag_id, schedule, tags, description, task_rows, dep_rows, created_at):
    desc_with_link = description or ""
    doc = f"""{description or ''}

🔧 **[메타 관리 (Batch Meta UI)]({_META_URL}/batch-meta/batches/{dag_id})**
"""
    # created_at 기준 start_date → 등록 이후 첫 스케줄에만 실행 (즉시 실행 방지)
    #   CronDataIntervalTimetable + catchup=False 는 첫 data_interval 을
    #   [start_date, 다음경계) 로 잡아, 등록 직후 '이전 시간대' 구간이 다음 경계에
    #   바로 실행된다(예: 08:xx 등록 → 09:00 에 08시 구간 실행).
    #   → start_date 를 '등록 시각 다음 경계'로 올려, 다음 시간부터 실행되게 한다.
    _reg_dt = pendulum.instance(created_at).in_tz("Asia/Seoul") if created_at else _START
    if created_at and schedule:
        start_dt = _next_schedule_after(schedule, _reg_dt)
    else:
        start_dt = _reg_dt

    # 동시 실행 batch 수 제어가 켜져 있으면 모든 task를 공용 pool 에 배치한다.
    # 배치당 병렬성(max_active_tasks)은 MAX_ACTIVE_TASKS_PER_BATCH 로 유지하고,
    # 전체 동시 task 수는 pool 슬롯 수(= MAX_CONCURRENT_BATCHES × MAX_ACTIVE_TASKS_PER_BATCH)로 제한된다.
    _use_pool = _MAX_CONCURRENT_BATCHES > 0

    @dag(
        dag_id              = dag_id,
        schedule            = schedule,
        start_date          = start_dt,
        catchup             = False,
        tags                = list(tags or []),
        description         = desc_with_link,
        doc_md              = doc,
        max_active_tasks    = _MAX_ACTIVE_TASKS_PER_BATCH,
        max_active_runs     = _MAX_ACTIVE_RUNS_PER_BATCH,
        # 신규 배치 등록 시 DAG를 "일시정지(paused)" 상태로 만들지 않는다.
        # (Airflow 기본값 dags_are_paused_at_creation=True 때문에, 이 옵션이 없으면
        #  새 배치가 paused 로 등록되어 최초 수동 실행(=unpause) 전까지 스케줄이 동작하지 않는다)
        is_paused_upon_creation = False,
        on_success_callback = _on_batch_success,
        on_failure_callback = _on_batch_failure,
    )
    def _batch_dag():
        # ── trigger_rule 계산 (각 downstream task에 적용) ─────────
        # on_failure 의존관계만 있는 task → trigger_rule='one_failed'
        # 혼합 → 'all_done' (어떤 상태든 실행 후 내부에서 분기)
        from collections import defaultdict as _dd
        _incoming = _dd(list)
        for _, up, dn, tt, tv in dep_rows:
            _incoming[dn].append(tt)

        def _trigger_rule_for(task_id):
            types = _incoming.get(task_id, [])
            if not types:
                return 'all_success'
            # on_result / on_failure → 모두 gate task(success/skip)를 통해 전파
            # 실제 downstream 은 gate의 success/skip 결과만 보므로 all_success 로 처리
            normalized = ['on_success' if t in ('on_result', 'on_failure') else t for t in types]
            if all(t == 'on_failure' for t in normalized):
                return 'one_failed'   # ← 이 경로는 이제 도달하지 않음 (gate 가 처리)
            if all(t == 'on_success' for t in normalized):
                return 'all_success'
            return 'all_done'

        # ── task 객체 생성 ─────────────────────────────────────────
        task_objs = {}
        for _, task_id, job_id, func_name, sql_text, params_json, owner_emails, retries, retry_delay_minutes, task_vars_json in task_rows:
            params = params_json if isinstance(params_json, dict) else json.loads(params_json or "{}")
            _task_vars = task_vars_json if isinstance(task_vars_json, dict) else json.loads(task_vars_json or "{}")
            fn = _make_run_fn(task_id, job_id, func_name, sql_text, params, _task_vars)
            emails = list(owner_emails or [])
            tr = _trigger_rule_for(task_id)
            retry_delay = pendulum.duration(minutes=retry_delay_minutes or 1)
            _task_kwargs = dict(
                on_failure_callback=_make_failure_callback(emails),
                trigger_rule=tr,
                retries=retries,
                retry_delay=retry_delay,
            )
            if _use_pool and _POOL_READY:
                # Pool 이 실제로 준비된 경우에만 지정 (없는 pool 참조로 인한 멈춤 방지)
                _task_kwargs["pool"] = _BATCH_POOL_NAME  # 동시 실행 task 수 제어
            task_objs[task_id] = task(fn, **_task_kwargs)()

        # ── 의존관계 적용 ──────────────────────────────────────────
        for _, upstream, downstream, trigger_type, trigger_value in dep_rows:
            if upstream not in task_objs or downstream not in task_objs:
                continue

            if trigger_type == 'on_result':
                # ── on_result: upstream 반환값 XCom ≠ trigger_value → skip ──
                _up_id, _dn_id, _tv = upstream, downstream, (trigger_value or '')
                _gate_id = f'_gate__{_up_id}__{_dn_id}'

                def _make_gate(_uid, _tv_inner, _gid):
                    def _gate_fn():
                        from airflow.sdk import get_current_context
                        from airflow.exceptions import AirflowSkipException
                        ctx = get_current_context()
                        ti = ctx['ti']
                        result = None
                        try:
                            result = ti.xcom_pull(task_ids=_uid)
                        except Exception as _xe:
                            _log.warning(f"[gate_result] xcom_pull 실패 ({_uid}): {_xe} → None 으로 처리")
                        result_str = str(result).strip() if result is not None else ''
                        _log.info(f"[gate_result] {_uid} 결과={result_str!r}, 기대값={_tv_inner!r}")
                        if result_str != str(_tv_inner).strip():
                            raise AirflowSkipException(
                                f"on_result: {result_str!r} ≠ {_tv_inner!r} → downstream skip"
                            )
                    _gate_fn.__name__ = _gid
                    return _gate_fn

                if _gate_id not in task_objs:
                    task_objs[_gate_id] = task(
                        _make_gate(_up_id, _tv, _gate_id),
                        task_id=_gate_id,
                    )()
                task_objs[upstream] >> task_objs[_gate_id] >> task_objs[downstream]

            elif trigger_type == 'on_failure':
                # ── on_failure: upstream 실패 시에만 downstream 실행 ──
                # _make_failure_callback 이 실패 시 '_failure_signal' XCom 을 push함
                # gate(trigger_rule='all_done') → signal 있으면 pass, 없으면 AirflowSkipException
                _up_id, _dn_id = upstream, downstream
                _gate_id = f'_gate__{_up_id}__{_dn_id}'

                def _make_failure_gate(_uid, _gid):
                    def _gate_fn():
                        from airflow.sdk import get_current_context
                        from airflow.exceptions import AirflowSkipException
                        ctx = get_current_context()
                        ti = ctx['ti']
                        signal = None
                        try:
                            signal = ti.xcom_pull(task_ids=_uid, key='_failure_signal')
                        except Exception as _xe:
                            _log.warning(f"[gate_failure] xcom_pull 실패 ({_uid}): {_xe} → None 으로 처리")
                        _log.info(f"[gate_failure] upstream={_uid} failure_signal={signal!r}")
                        if not signal:
                            raise AirflowSkipException(
                                f"on_failure: upstream {_uid} 실패 없음 → downstream skip"
                            )
                    _gate_fn.__name__ = _gid
                    return _gate_fn

                if _gate_id not in task_objs:
                    task_objs[_gate_id] = task(
                        _make_failure_gate(_up_id, _gate_id),
                        task_id=_gate_id,
                        trigger_rule='all_done',   # upstream 성공/실패 모두 실행
                    )()
                task_objs[upstream] >> task_objs[_gate_id] >> task_objs[downstream]

            else:
                # on_success: 표준 >> 연결
                task_objs[upstream] >> task_objs[downstream]

    return _batch_dag()


# ── 동적 DAG 등록 ─────────────────────────────────────────────────
# ★ 주의: 예외를 silently catch 하여 빈 리스트를 반환하면
#          Airflow dag-processor 가 "DAG 전부 소멸"로 인식해 기존 DAG를 비활성화한다.
#          DB 연결 실패 등의 일시 오류는 예외를 재발생시켜 Airflow 가 "import error"
#          상태로 기록하게 해야 한다 — 그래야 기존 DAG 가 비활성화되지 않는다.
try:
    _batch_dags, _batch_tasks, _batch_deps = _load_meta()
except Exception as _e:
    _log.error(f"[batches_dynamic.py] 배치 메타 로드 실패: {_e}\n{traceback.format_exc()}")
    raise  # ← 재발생: Airflow 가 import error 로 기록, 기존 DAG 비활성화 방지

# 진단 로그는 DEBUG 레벨로 출력.
# Airflow 기본 로그 레벨(INFO)에서는 보이지 않으므로 task 실행 로그 소음 없음.
# 확인이 필요하면 AIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG 로 일시적으로 활성화 가능.
_log.debug(f"[BATCH-DYN] 메타 조회 결과: batch_dag={len(_batch_dags)}건, "
           f"batch_task={len(_batch_tasks)}건, batch_dep={len(_batch_deps)}건")

# 동시 실행 batch 수 제어용 공용 Pool 생성/갱신 (MAX_CONCURRENT_BATCHES 설정 시)
_ensure_batch_pool()

_ok_cnt = 0
for _dag_id, _schedule, _tags, _desc, _created_at in _batch_dags:
    try:
        _task_rows = [r for r in _batch_tasks if r[0] == _dag_id]
        _dep_rows  = [r for r in _batch_deps  if r[0] == _dag_id]

        if not _task_rows:
            _log.debug(f"[BATCH-DYN] '{_dag_id}' task 없음 → 건너뜀")
            continue

        # schedule(cron) 검증: 잘못된 값이면 ValueError → 이 배치만 건너뜀
        _schedule = _normalize_schedule(_schedule)

        globals()[_dag_id] = _create_batch_dag(
            _dag_id, _schedule, _tags, _desc, _task_rows, _dep_rows, _created_at
        )
        _ok_cnt += 1
        _log.debug(f"[BATCH-DYN] '{_dag_id}' 등록 완료 (task {len(_task_rows)}개)")
    except Exception as _e:
        _log.error(f"[batches_dynamic.py] '{_dag_id}' DAG 생성 실패, 건너뜀: {_e}\n{traceback.format_exc()}")

_log.debug(f"[BATCH-DYN] 최종 등록된 batch DAG: {_ok_cnt}개")