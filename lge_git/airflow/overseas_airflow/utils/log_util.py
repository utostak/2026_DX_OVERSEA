"""
log_util.py — Airflow 배치/잡 실행 로그 기록 유틸리티
──────────────────────────────────────────────────────
airflow_meta.batch_run_log / job_run_log 에 실행 이력을 기록합니다.
모든 함수는 예외를 삼켜 WARNING 로그만 남기므로, 로그 실패가
배치 실행에 영향을 주지 않습니다.
"""
from __future__ import annotations

import os
import json
import logging
import datetime
import psycopg2
from pathlib import Path
from urllib.parse import quote_plus

_log = logging.getLogger(__name__)

# ── .env 자동 로드 ─────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _here = Path(__file__).parent
    for _env_path in [
        _here / ".env",
        _here.parent / "plugins" / ".env",
        _here.parent / ".env",
    ]:
        if _env_path.resolve().exists():
            load_dotenv(_env_path.resolve(), override=False)
            break
except ImportError:
    pass


# ── 메타 DB 연결 (batches_dynamic.py 와 동일한 기본값) ─────────────
def _meta_conn():
    host     = os.environ.get("META_PG_HOST",     "10.182.32.210")
    port     = int(os.environ.get("META_PG_PORT", "8110"))
    db       = os.environ.get("META_PG_DB",       "airflow_db")
    user     = os.environ.get("META_PG_USER",     "airflow")
    password = os.environ.get("META_PG_PASSWORD", "oss123~!@")
    sslmode  = os.environ.get("META_PG_SSLMODE",  "disable")
    return psycopg2.connect(
        host=host, port=port, dbname=db,
        user=user, password=password, sslmode=sslmode,
        connect_timeout=10,
    )


import contextlib as _contextlib

@_contextlib.contextmanager
def _db():
    """연결 획득 → 커밋 → 반드시 close. 재시도 2회 포함."""
    import time as _time
    last_exc = None
    for attempt in range(3):
        conn = None
        try:
            conn = _meta_conn()
            yield conn
            conn.commit()
            return
        except Exception as e:
            last_exc = e
            if conn:
                try: conn.rollback()
                except Exception: pass
            _log.warning(f"[log_util] DB 연결/실행 실패 (시도 {attempt+1}/3): {e}")
            if attempt < 2:
                _time.sleep(0.3 * (attempt + 1))
        finally:
            if conn:
                try: conn.close()
                except Exception: pass
    raise last_exc  # 3회 모두 실패 시 상위에서 catch


# ── 내부 유틸 ──────────────────────────────────────────────────────
def _get_run_type(dag_run) -> str:
    _rt_raw = getattr(dag_run, 'run_type', None)
    run_type_str = str(getattr(_rt_raw, 'value', _rt_raw) or '').lower()
    return 'scheduled' if 'scheduled' in run_type_str else 'manual'


def _airflow_base() -> str:
    return os.environ.get("AIRFLOW_URL", "http://localhost:8080").rstrip("/")


# ══════════════════════════════════════════════════════════════════
# 배치 실행 로그
# ══════════════════════════════════════════════════════════════════

def ensure_batch_run_log(context: dict) -> None:
    """
    배치 run 시작 시 batch_run_log 행 생성.
    이미 존재하면(ON CONFLICT DO NOTHING) 아무 동작 없음.
    각 task의 _make_run_fn 시작 시 호출 → 첫 번째 task만 실제 INSERT 됨.
    """
    try:
        dag_run = context.get('dag_run')
        if not dag_run:
            return
        run_id = getattr(dag_run, 'run_id', None)
        dag_id = getattr(dag_run, 'dag_id', None)
        if not dag_id:
            dag_id = getattr(getattr(context, 'dag', None), 'dag_id', None)
        if not run_id or not dag_id:
            return

        run_type    = _get_run_type(dag_run)
        started_at  = getattr(dag_run, 'start_date', None) or datetime.datetime.now()
        scheduled_at = None

        conf = dict(getattr(dag_run, 'conf', {}) or {})

        if run_type == 'scheduled':
            dis = (getattr(dag_run, 'data_interval_start', None)
                   or context.get('data_interval_start'))
            die = (getattr(dag_run, 'data_interval_end',   None)
                   or context.get('data_interval_end'))
            if dis:
                scheduled_at = dis
                # 정기 배치 변수 3종을 conf_json 에 저장 (프론트 로그 팝업 표시용)
                try:
                    import pendulum as _pendulum
                    _tz        = _pendulum.timezone("Asia/Seoul")
                    _start_kst = _pendulum.instance(dis).in_tz(_tz)
                    _end_kst   = _pendulum.instance(die).in_tz(_tz) if die else _start_kst
                    _interval  = _end_kst - _start_kst
                    if _interval.total_seconds() <= 0:
                        # schedule 기반 interval 계산 (batches_dynamic 헬퍼 재사용)
                        try:
                            import sys as _sys, os as _os
                            _dags_dir = _os.path.dirname(_os.path.dirname(__file__))
                            if _dags_dir not in _sys.path:
                                _sys.path.insert(0, _dags_dir)
                            from batches_dynamic import _get_batch_schedule, _interval_from_schedule
                            _sched = _get_batch_schedule(dag_id)
                            _interval = _interval_from_schedule(_sched)
                        except Exception:
                            _interval = _pendulum.duration(days=1)
                    _prev_kst  = _start_kst - _interval
                    conf.setdefault('batch_vars', {
                        'BATCH_DT':      _start_kst.strftime('%Y-%m-%d %H:%M:%S'),
                        'PREV_BATCH_DT': _prev_kst.strftime('%Y-%m-%d %H:%M:%S'),
                        'NEXT_BATCH_DT': (_start_kst + _interval).strftime('%Y-%m-%d %H:%M:%S'),
                    })
                except Exception as _bve:
                    _log.debug(f"[log_util] batch_vars 계산 실패 (무시): {_bve}")

        conf_str = json.dumps(conf, default=str)
        run_url  = f"{_airflow_base()}/dags/{dag_id}/runs/{run_id}"

        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO airflow_meta.batch_run_log
                        (run_id, dag_id, run_type, scheduled_at, started_at,
                         status, conf_json, airflow_run_url)
                    VALUES (%s, %s, %s, %s, %s, 'running', %s::jsonb, %s)
                    ON CONFLICT (run_id, dag_id) DO NOTHING
                """, (run_id, dag_id, run_type, scheduled_at, started_at,
                      conf_str, run_url))
    except Exception as e:
        _log.error(f"[log_util] ensure_batch_run_log 실패 (무시): {e}", exc_info=True)


def update_batch_run_log(context: dict, status: str) -> None:
    """배치 종료(성공/실패) 시 batch_run_log 상태·종료시간 갱신"""
    try:
        dag_run = context.get('dag_run')
        if not dag_run:
            return
        run_id = getattr(dag_run, 'run_id', None)
        dag_id = getattr(dag_run, 'dag_id', None)
        if not run_id or not dag_id:
            return
        now = datetime.datetime.now()
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE airflow_meta.batch_run_log
                       SET status       = %s,
                           ended_at     = %s,
                           duration_sec = EXTRACT(EPOCH FROM (%s - started_at))
                     WHERE run_id = %s AND dag_id = %s
                """, (status, now, now, run_id, dag_id))
    except Exception as e:
        _log.error(f"[log_util] update_batch_run_log 실패 (무시): {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════════
# 잡/태스크 실행 로그
# ══════════════════════════════════════════════════════════════════

def begin_job_run_log(context: dict, task_id: str, job_id: str,
                      source_type: str, resolved_sql: str,
                      params_json: dict) -> int | None:
    """
    task 시작 시 job_run_log INSERT (첫 시도) 또는 조회 (재시도).
    retry 시에는 기존 log_id를 재사용하여 로그 행이 중복 생성되지 않도록 한다.
    실패 시 None 반환 (배치 실행 자체는 계속 진행).
    """
    try:
        dag_run = context.get('dag_run')
        run_id  = getattr(dag_run, 'run_id', None) if dag_run else None
        dag_id  = getattr(dag_run, 'dag_id', None) if dag_run else None
        if not dag_id:
            dag_id = getattr(getattr(context, 'dag', None), 'dag_id', None)
        run_type = _get_run_type(dag_run) if dag_run else 'manual'

        # Airflow task 로그 URL 생성
        ti = context.get('ti') or context.get('task_instance')
        try_num = getattr(ti, 'try_number', 1) if ti else 1
        log_url = None
        if dag_id and run_id and task_id:
            log_url = (
                f"{_airflow_base()}/dags/{dag_id}/runs/{run_id}"
                f"/tasks/{task_id}?try_number={try_num}"
            )

        params_str = json.dumps(params_json or {}, default=str)

        with _db() as conn:
            with conn.cursor() as cur:
                # retry 시 기존 로그 재사용: 이미 있으면 log_id만 반환, 없으면 INSERT
                cur.execute("""
                    SELECT log_id FROM airflow_meta.job_run_log
                     WHERE run_id = %s AND dag_id = %s AND task_id = %s
                     LIMIT 1
                """, (run_id, dag_id, task_id))
                existing = cur.fetchone()
                if existing:
                    # retry 시작: 기존 로그를 'running' 상태로 다시 설정
                    _log.info(f"[log_util] retry 감지 → 기존 log_id={existing[0]} 재사용")
                    cur.execute("""
                        UPDATE airflow_meta.job_run_log
                           SET status = 'running',
                               ended_at = NULL,
                               error_msg = NULL
                         WHERE log_id = %s
                    """, (existing[0],))
                    return existing[0]
                else:
                    # 첫 시도: INSERT
                    cur.execute("""
                        INSERT INTO airflow_meta.job_run_log
                            (run_id, dag_id, task_id, job_id, source_type, run_type,
                             resolved_sql, params_json, started_at, status, airflow_log_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), 'running', %s)
                        RETURNING log_id
                    """, (run_id, dag_id, task_id, job_id, source_type, run_type,
                          resolved_sql, params_str, log_url))
                    row = cur.fetchone()
                    return row[0] if row else None
    except Exception as e:
        _log.error(f"[log_util] begin_job_run_log 실패 (무시): {e}", exc_info=True)
        return None


def update_job_run_log_sql(log_id: int, resolved_sql: str,
                           params_json: dict = None) -> None:
    """변수 치환 완료 후 job_run_log 의 resolved_sql / params_json 을 실제 실행값으로 갱신.
    (begin_job_run_log 는 치환 전 원본을 먼저 기록하므로, 치환 후 이 함수로 덮어쓴다.)"""
    if not log_id:
        return
    try:
        params_str = json.dumps(params_json or {}, default=str)
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE airflow_meta.job_run_log
                       SET resolved_sql = %s,
                           params_json  = %s::jsonb
                     WHERE log_id = %s
                """, (resolved_sql, params_str, log_id))
    except Exception as e:
        _log.warning(f"[log_util] update_job_run_log_sql 실패 (무시): {e}")


def end_job_run_log(log_id: int, status: str,
                    result_value: str = None, error_msg: str = None) -> None:
    """task 종료 시 job_run_log 상태·결과·에러 갱신"""
    if not log_id:
        return
    try:
        now = datetime.datetime.now()
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE airflow_meta.job_run_log
                       SET status       = %s,
                           ended_at     = %s,
                           duration_sec = EXTRACT(EPOCH FROM (%s - started_at)),
                           result_value = %s,
                           error_msg    = %s
                     WHERE log_id = %s
                """, (
                    status, now, now,
                    (str(result_value)[:1000] if result_value is not None else None),
                    (str(error_msg)[:2000]    if error_msg    else None),
                    log_id
                ))
    except Exception as e:
        _log.error(f"[log_util] end_job_run_log 실패 (무시): {e}", exc_info=True)


def fail_running_job_logs(run_id: str, dag_id: str, task_id: str,
                          error_msg: str = None) -> None:
    """on_failure_callback 에서 호출 — 해당 task 의 'running' 상태 job_run_log 를 'failed' 로 강제 갱신.
    worker kill / timeout 등으로 _run() except 블록이 실행되지 못한 경우를 커버한다."""
    try:
        now = datetime.datetime.now()
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE airflow_meta.job_run_log
                       SET status       = 'failed',
                           ended_at     = %s,
                           duration_sec = EXTRACT(EPOCH FROM (%s - started_at)),
                           error_msg    = COALESCE(error_msg, %s)
                     WHERE run_id  = %s
                       AND dag_id  = %s
                       AND task_id = %s
                       AND status  = 'running'
                """, (now, now, error_msg and str(error_msg)[:2000],
                      run_id, dag_id, task_id))
                _log.info(f"[log_util] fail_running_job_logs: {cur.rowcount}건 갱신 "
                          f"({dag_id}/{task_id})")
    except Exception as e:
        _log.error(f"[log_util] fail_running_job_logs 실패 (무시): {e}", exc_info=True)
