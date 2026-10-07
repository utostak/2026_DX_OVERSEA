"""
jobs_dynamic.py — DB 메타 기반 Job DAG 동적 생성
─────────────────────────────────────────────────────────────────
airflow_meta.job_dag 테이블의 각 행을 읽어
schedule=None (수동 실행) DAG를 자동 생성합니다.

지원 함수:
  execute_sql_ptg          : SQL 실행 (PG)
  replicate_bq_to_ptg      : BQ → PG (스테이징 → 본테이블)
  replicate_ptg_to_bq_table: PG → BQ
─────────────────────────────────────────────────────────────────
"""
import os
import re as _re
import json
import logging
import traceback
import pendulum
import psycopg2
from dotenv import load_dotenv
from airflow.sdk import dag, task

# .env 파일 로드 (DAG 폴더 내 또는 상위 폴더의 .env 파일을 읽어옵니다)
load_dotenv()

_START    = pendulum.datetime(2025, 1, 1, tz="Asia/Seoul")
_log      = logging.getLogger(__name__)

# ── 환경변수 기반 실행 제어 설정 ────────────────────────────────────
# .env 파일 또는 시스템 환경변수에서 읽어옵니다.
# ※ 동시 "실행" 수만 제어합니다. DAG 등록(로드)은 항상 전체가 됩니다.
_MAX_ACTIVE_RUNS_PER_JOB = int(os.getenv("MAX_ACTIVE_RUNS_PER_JOB", "1") or "1")

# SQL 변수 패턴 (batches_dynamic.py와 동일)
#   · 기본 변수:  {BATCH_DT} {PREV_BATCH_DT} {NEXT_BATCH_DT}
#   · 사용자 변수: {ANY_UPPER_NAME}  (수작업 실행 시 입력값으로 치환)
_VAR_RE = _re.compile(r'\{([A-Z][A-Z0-9_]*)\}')
_BUILTIN_VAR_KEYS = ('BATCH_DT', 'PREV_BATCH_DT', 'NEXT_BATCH_DT')

# ── DB에서 job 목록 조회 ───────────────────────────────────────────
def _load_jobs():
    host     = os.getenv("META_PG_HOST",     "10.182.32.210")
    port     = os.getenv("META_PG_PORT",     "8110")
    dbname   = os.getenv("META_PG_DB",       "airflow_db")
    user     = os.getenv("META_PG_USER",     "airflow")
    password = os.getenv("META_PG_PASSWORD", "oss123~!@")
    sslmode  = os.getenv("META_PG_SSLMODE",  "disable")

    conn = psycopg2.connect(
        host=host, port=port, dbname=dbname,
        user=user, password=password, sslmode=sslmode,
    )
    try:
        with conn.cursor() as cur:
            # retries/retry_delay_minutes 컬럼이 아직 없는 DB를 위해 폴백 쿼리 사용
            _queries = [
                """SELECT job_id, func_name, sql_text, params_json, description,
                          COALESCE(retries, 0)              AS retries,
                          COALESCE(retry_delay_minutes, 1)  AS retry_delay_minutes
                     FROM airflow_meta.job_dag
                    WHERE is_active
                    ORDER BY job_id""",
                """SELECT job_id, func_name, sql_text, params_json, description,
                          0 AS retries,
                          1 AS retry_delay_minutes
                     FROM airflow_meta.job_dag
                    WHERE is_active
                    ORDER BY job_id""",
            ]
            rows = None
            for _q in _queries:
                try:
                    cur.execute(_q)
                    rows = cur.fetchall()
                    break
                except Exception as _qe:
                    _log.warning(f"[jobs_dynamic] 쿼리 실패(폴백 시도): {_qe}")
                    conn.rollback()   # 오류 후 트랜잭션 롤백 후 다음 쿼리 시도
            if rows is None:
                raise RuntimeError("job 메타 조회 실패 (폴백 쿼리도 실패)")
        return rows
    except Exception as e:
        _log.error(f"메타 DB 조회 중 오류 발생: {e}")
        raise
    finally:
        conn.close()


# ── 파이썬 모듈 잡 실행 ────────────────────────────────────────────
# job_modules 폴더의 .py 모듈 동적 실행은 공용 유틸(utils.py_module_util)로 분리했습니다.
# (jobs_dynamic.py / batches_dynamic.py 중복 코드 제거)


# ── task 실행 함수 빌더 ────────────────────────────────────────────
def _make_run_fn(job_id: str, func_name: str, sql_text: str, params: dict):
    """클로저로 각 job의 실행 함수 생성 (DAG 파싱 시점에 값 캡처)"""
    # SQL 또는 params 문자열 값에 치환 변수가 있으면 변수 처리 필요
    _has_vars = bool(_VAR_RE.search(sql_text)) or any(
        _VAR_RE.search(str(v)) for v in params.values() if v
    )

    def _run():
        import signal as _signal
        from airflow.sdk import get_current_context
        ctx     = get_current_context()
        dag_run = ctx.get('dag_run')
        ti      = ctx.get('ti') or ctx.get('task_instance')

        # ── run_type 판별 ─────────────────────────────────────────
        _rt_raw      = getattr(dag_run, 'run_type', None)
        run_type_str = str(getattr(_rt_raw, 'value', _rt_raw) or '').lower()
        run_type     = 'scheduled' if 'scheduled' in run_type_str else 'manual'

        # ── job_run_log 시작 ──────────────────────────────────────
        # SIGTERM 핸들러에서 접근할 수 있도록 리스트로 관리
        _log_id_ref = [None]

        # ── SIGTERM 핸들러: Airflow 강제 종료 시 DB 로그 즉시 정리 ──
        def _sigterm_handler(signum, frame):
            _log.warning("[jobs_dynamic] ⚠️  SIGTERM 수신 → job_run_log 강제 종료 처리")
            try:
                if _log_id_ref[0] is not None:
                    from utils.log_util import end_job_run_log
                    end_job_run_log(_log_id_ref[0], 'failed',
                                    error_msg='Airflow 강제 종료 (SIGTERM)')
            except Exception as _se:
                _log.warning(f"[jobs_dynamic] SIGTERM 처리 중 오류 (무시): {_se}")
            raise SystemExit(1)

        _prev_sigterm = _signal.signal(_signal.SIGTERM, _sigterm_handler)

        # ── SQL + params 변수 치환 ────────────────────────────────
        resolved_sql    = sql_text
        resolved_params = params
        if _has_vars:
            if run_type != 'scheduled':
                conf = getattr(dag_run, 'conf', {}) or {}
                if not conf.get('batch_vars'):
                    vars_in_sql    = list(dict.fromkeys(_VAR_RE.findall(sql_text)))
                    vars_in_params = list(dict.fromkeys(
                        v for pv in params.values() if isinstance(pv, str)
                        for v in _VAR_RE.findall(pv)
                    ))
                    all_used = list(dict.fromkeys(vars_in_sql + vars_in_params))
                    raise ValueError(
                        f"변수 {all_used}가 있지만 수작업 실행 시 값을 입력하지 않았습니다.\n"
                        "Airflow UI 대신 Batch Meta UI의 ▶ 수작업 실행 버튼을 사용해 주세요."
                    )
            tz = pendulum.timezone("Asia/Seoul")
            if run_type == 'scheduled':
                start = getattr(dag_run, 'data_interval_start', None) or ctx.get('logical_date')
                end   = getattr(dag_run, 'data_interval_end', None)
                start_kst = pendulum.instance(start).in_tz(tz) if start else pendulum.now(tz)
                end_kst   = pendulum.instance(end).in_tz(tz)   if end   else start_kst
                batch_vars = {
                    'BATCH_DT':      start_kst.strftime('%Y-%m-%d %H:%M:%S'),
                    'PREV_BATCH_DT': (start_kst - (end_kst - start_kst)).strftime('%Y-%m-%d %H:%M:%S'),
                    'NEXT_BATCH_DT': end_kst.strftime('%Y-%m-%d %H:%M:%S'),
                }
            else:
                conf = getattr(dag_run, 'conf', {}) or {}
                bv = conf.get('batch_vars', {}) or {}
                # 기본 변수 + 사용자 정의 변수 모두 conf 에서 읽음
                batch_vars = dict(bv)
                for k in _BUILTIN_VAR_KEYS:
                    batch_vars.setdefault(k, bv.get(k, ''))
            _sub = lambda m: batch_vars.get(m.group(1), m.group(0))
            resolved_sql    = _VAR_RE.sub(_sub, sql_text)
            resolved_params = {
                k: (_VAR_RE.sub(_sub, v) if isinstance(v, str) else v)
                for k, v in params.items()
            }
            _log.info(f"[jobs_dynamic] SQL+params 변수 치환: {batch_vars}")

        # ── job_run_log 시작 ──────────────────────────────────────
        _log_id = None
        try:
            from utils.log_util import begin_job_run_log
            _log_id = begin_job_run_log(ctx, 'run_job', job_id, 'job', resolved_sql, resolved_params)
            _log_id_ref[0] = _log_id   # SIGTERM 핸들러에서 접근
        except Exception as _le:
            _log.warning(f"[jobs_dynamic] job_run_log 시작 실패 (무시): {_le}")

        result = None
        try:
            # ── 실제 실행 ────────────────────────────────────────
            if func_name == "execute_sql_ptg":
                from utils.db_util import execute_sql_ptg
                result = execute_sql_ptg(resolved_sql)

            elif func_name == "execute_sql_bq":
                from utils.db_util import execute_sql_bq
                result = execute_sql_bq(resolved_sql)

            elif func_name == "replicate_bq_to_ptg":
                from utils.db_util import replicate_bq_to_ptg
                _pre_sql = resolved_params.get("pre_sql") or None
                # 하위 호환: 기존 params에 where_clause가 있으면 pre_sql(DELETE)로 자동 변환
                if not _pre_sql and resolved_params.get("where_clause"):
                    _pre_sql = f"DELETE FROM {resolved_params['dst_table']} WHERE {resolved_params['where_clause']}"
                    _log.info(f"[jobs_dynamic] where_clause → pre_sql 자동 변환: {_pre_sql}")
                replicate_bq_to_ptg(
                    bq_sql    = resolved_sql,
                    if_table  = resolved_params["if_table"],
                    dst_table = resolved_params["dst_table"],
                    pre_sql   = _pre_sql,
                    post_sql  = resolved_params.get("post_sql") or None,
                )

            elif func_name == "replicate_bq_to_ptg2":
                from utils.db_util import replicate_bq_to_ptg2
                _pre_sql = resolved_params.get("pre_sql") or None
                # 하위 호환: 기존 params에 where_clause가 있으면 pre_sql(DELETE)로 자동 변환
                if not _pre_sql and resolved_params.get("where_clause"):
                    _pre_sql = f"DELETE FROM {resolved_params['dst_table']} WHERE {resolved_params['where_clause']}"
                    _log.info(f"[jobs_dynamic] where_clause → pre_sql 자동 변환: {_pre_sql}")
                _kw2 = {}
                if resolved_params.get("rows_per_file"):
                    _kw2["rows_per_file"] = int(resolved_params["rows_per_file"])
                if resolved_params.get("dump_workers"):
                    _kw2["dump_workers"] = int(resolved_params["dump_workers"])
                if resolved_params.get("load_workers"):
                    _kw2["load_workers"] = int(resolved_params["load_workers"])
                replicate_bq_to_ptg2(
                    bq_sql    = resolved_sql,
                    if_table  = resolved_params["if_table"],
                    dst_table = resolved_params["dst_table"],
                    pre_sql   = _pre_sql,
                    post_sql  = resolved_params.get("post_sql") or None,
                    **_kw2,
                )

            elif func_name == "replicate_ptg_to_bq_table":
                from utils.db_util import replicate_ptg_to_bq_table
                replicate_ptg_to_bq_table(
                    ptg_sql    = resolved_sql,
                    bq_table_id= resolved_params["bq_table_id"],
                )
            elif func_name == "execute_python_module":
                from utils.py_module_util import run_python_module
                result = run_python_module(resolved_params, resolved_sql, ctx)
            else:
                raise ValueError(f"지원하지 않는 func_name: {func_name}")

            # ── job_run_log 성공 ──────────────────────────────────
            try:
                from utils.log_util import end_job_run_log
                rv = str(result)[:500] if result is not None else None
                end_job_run_log(_log_id, 'success', result_value=rv)
            except Exception as _le:
                _log.warning(f"[jobs_dynamic] job_run_log 성공 갱신 실패 (무시): {_le}")

            return result

        except Exception as _exc:
            # ── job_run_log 실패 ──────────────────────────────────
            try:
                from utils.log_util import end_job_run_log
                _is_skip = type(_exc).__name__ == 'AirflowSkipException'
                end_job_run_log(
                    _log_id,
                    'skipped' if _is_skip else 'failed',
                    error_msg=None if _is_skip else str(_exc)[:2000],
                )
            except Exception as _le:
                _log.warning(f"[jobs_dynamic] job_run_log 실패 갱신 실패 (무시): {_le}")
            raise

        finally:
            # SIGTERM 핸들러를 원래 핸들러로 복원
            try:
                _signal.signal(_signal.SIGTERM, _prev_sigterm)
            except Exception:
                pass

    return _run


# ── Job task 강제 종료 콜백 ───────────────────────────────────────
def _on_job_failure(context):
    """Task 실패 / Airflow 강제 종료(SIGKILL 등) 시 job_run_log 'running' 상태 강제 정리.
    SIGTERM 핸들러가 처리하지 못한 경우(SIGKILL, OOM 등)의 최종 안전망."""
    try:
        dag_run = context.get('dag_run')
        ti      = context.get('task_instance') or context.get('ti')
        run_id  = getattr(dag_run, 'run_id', None)
        dag_id  = getattr(dag_run, 'dag_id', None)
        task_id = getattr(ti, 'task_id', None) if ti else None
        exc_msg = str(context.get('exception', ''))[:2000] or 'task 실패 (원인 불명)'
        if run_id and dag_id and task_id:
            from utils.log_util import fail_running_job_logs
            fail_running_job_logs(run_id, dag_id, task_id, exc_msg)
            _log.info(f"[jobs_dynamic] on_failure_callback: job_run_log 정리 완료 ({dag_id}/{task_id})")
    except Exception as _e:
        _log.warning(f"[jobs_dynamic] on_failure_callback 처리 실패 (무시): {_e}")


_META_URL = "http://10.182.33.70:8117"

# ── DAG 생성 팩토리 ────────────────────────────────────────────────
def _create_job_dag(job_id, func_name, sql_text, params_json, description, retries, retry_delay_minutes):
    run_fn = _make_run_fn(job_id, func_name, sql_text, params_json)
    run_fn.__name__ = "run_job"
    doc = f"""{description or ''}

🔧 **[메타 관리 (Job Meta UI)]({_META_URL}/batch-meta/jobs/{job_id})**
"""
    retry_delay = pendulum.duration(minutes=retry_delay_minutes)

    @dag(
        dag_id          = job_id,
        schedule        = None,
        start_date      = _START,
        catchup         = False,
        tags            = ["manual", func_name],
        description     = description or "",
        doc_md          = doc,
        max_active_runs = _MAX_ACTIVE_RUNS_PER_JOB,
    )
    def _job_dag():
        # retries/retry_delay 는 DAG가 아닌 task 레벨 파라미터 (Airflow 3.x)
        task(run_fn, retries=retries, retry_delay=retry_delay,
             on_failure_callback=_on_job_failure)()

    return _job_dag()


# ── 동적 DAG 등록 ─────────────────────────────────────────────────
# ★ 주의: 예외를 silently catch 하면 Airflow 가 기존 DAG 를 비활성화할 수 있다.
#          DB 연결 실패 등 일시 오류는 예외를 재발생시켜 Airflow "import error" 처리로 넘긴다.
try:
    _job_rows = _load_jobs()
except Exception as _e:
    _log.error(f"[jobs_dynamic.py] job 메타 로드 실패: {_e}")
    raise  # ← 재발생: Airflow 가 import error 로 기록, 기존 DAG 비활성화 방지

_ok_cnt = 0
for _job_id, _func_name, _sql, _params_json, _desc, _retries, _retry_delay_minutes in _job_rows:
    try:
        _params = _params_json if isinstance(_params_json, dict) else json.loads(_params_json or "{}")
        globals()[_job_id] = _create_job_dag(_job_id, _func_name, _sql, _params, _desc, _retries, _retry_delay_minutes)
        _ok_cnt += 1
    except Exception as _e:
        _msg = f"[JOBS-DYN] '{_job_id}' DAG 생성 실패: {_e}\n{traceback.format_exc()}"
        _log.error(_msg)
        print(_msg, flush=True)  # docker logs 확인용

print(f"[JOBS-DYN] job DAG 등록 완료: {_ok_cnt}/{len(_job_rows)}개", flush=True)