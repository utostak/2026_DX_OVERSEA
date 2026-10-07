import io
import os
import pandas as pd
import datetime
from decimal import Decimal

# Use Airflow hooks instead of hard-coded credentials.
# Defaults set to the connection IDs you provided.
BQ_CONN_ID_DEFAULT = "pjt-lge-edl-ob"
BQ_CONN_ID_OVERSEA  = "pjt-lge-oversea-sales-olap"   # 변경 전 기존 값 (백업용, 미사용)
PG_CONN_ID_DEFAULT = "postgres_spw"

# 쿼리 실행 타임아웃(초). 환경변수 QUERY_TIMEOUT_SEC 로 설정 가능(기본 600초 = 10분).
QUERY_TIMEOUT_SEC = int(os.environ.get("QUERY_TIMEOUT_SEC", "600") or "600")

# .result() 클라이언트측 폴링 타임아웃(초).
# BQ 서버측 job_timeout(QUERY_TIMEOUT_SEC)이 '먼저' 발동하여 의미있는 에러 메시지
# ("Job timed out after N min ...")를 남기도록, 클라이언트측 폴링은 여유(120초)를 둔다.
# (두 값이 같으면 client-side TimeoutError 가 먼저 터져 str(e)가 빈 문자열이 되어
#  에러 메시지가 저장되지 않는 문제가 발생한다.)
# 단, 서버가 무응답(hang)일 때를 대비한 상한선으로만 동작한다.
BQ_RESULT_TIMEOUT_SEC = (QUERY_TIMEOUT_SEC + 120) if (QUERY_TIMEOUT_SEC and QUERY_TIMEOUT_SEC > 0) else None


def _fmt_exc(e) -> str:
    """예외 메시지를 사람이 읽을 수 있는 문자열로 변환한다.
    concurrent.futures.TimeoutError 처럼 str(e)가 빈 문자열인 경우 타입명으로 대체하여
    에러 메시지가 빈 값으로 저장되는 것을 방지한다."""
    msg = (str(e) or "").strip()
    if msg:
        return msg
    name = type(e).__name__
    if "Timeout" in name:
        return (f"{name}: BigQuery 쿼리 응답 대기 타임아웃 "
                f"(client-side {BQ_RESULT_TIMEOUT_SEC}s 초과 — 쿼리 취소/장기 실행 추정)")
    return f"{name} (상세 메시지 없음)"

# BQ Storage Read API 스트림 읽기 타임아웃(초). 환경변수 BQ_READ_TIMEOUT_SEC 로 설정 가능(기본 300초 = 5분).
# gRPC 스트림이 stall 되어 무한 대기(hang)하는 것을 방지한다.
BQ_READ_TIMEOUT_SEC = int(os.environ.get("BQ_READ_TIMEOUT_SEC", "300") or "300")


def _bq_query(client, sql, **kwargs):
    """QUERY_TIMEOUT_SEC 를 적용해 BigQuery 쿼리를 실행하고 QueryJob 을 반환한다.

    - job_timeout_ms 로 BQ 서버측 최대 실행 시간을 제한한다.
    """
    from google.cloud import bigquery
    job_config = kwargs.pop("job_config", None) or bigquery.QueryJobConfig()
    if QUERY_TIMEOUT_SEC and QUERY_TIMEOUT_SEC > 0:
        job_config.job_timeout_ms = QUERY_TIMEOUT_SEC * 1000
    return client.query(sql, job_config=job_config, **kwargs)


def _set_pg_statement_timeout(cursor):
    """PG 세션에 statement_timeout(밀리초) 을 설정한다."""
    if QUERY_TIMEOUT_SEC and QUERY_TIMEOUT_SEC > 0:
        cursor.execute(f"SET statement_timeout = {QUERY_TIMEOUT_SEC * 1000}")

def _log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def replicate_ptg_to_bq_table(ptg_sql, bq_table_id, pg_conn_id=None, bq_conn_id=None):
    _start = datetime.datetime.now()
    # Resolve connection ids
    pg_conn_id = pg_conn_id or PG_CONN_ID_DEFAULT
    bq_conn_id = bq_conn_id or BQ_CONN_ID_DEFAULT

    # 1. PostgreSQL에서 데이터 가져오기 (Airflow PostgresHook 사용)
    # Lazy import to avoid hard dependency at module import time
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    pg_hook = PostgresHook(postgres_conn_id=pg_conn_id)
    query = ptg_sql
    # PostgresHook provides get_pandas_df which returns a DataFrame
    df = pg_hook.get_pandas_df(sql=query)

    # INPUT_DT 컬럼 변환
    if 'INPUT_DT' in df.columns:
        # 만약 INPUT_DT가 int 또는 str로 들어온다면
        try:
            df['INPUT_DT'] = pd.to_datetime(df['INPUT_DT'].astype(str), format='%Y%m%d%H%M')
        except Exception as e:
            _log(f"INPUT_DT 변환 오류: {e}")

    # float 컬럼 → NUMERIC(Decimal) 변환: BigQuery NUMERIC 타입 불일치 방지
    float_cols = df.select_dtypes(include=['float64', 'float32']).columns.tolist()
    for col in float_cols:
        df[col] = df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) else None)

    # 2. BigQuery 클라이언트 생성 (Airflow BigQueryHook 사용)
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    bq_hook = BigQueryHook(gcp_conn_id=bq_conn_id)
    client = bq_hook.get_client()
    # 3. BigQuery 테이블 TRUNCATE
    truncate_query = f"TRUNCATE TABLE `{bq_table_id}`"
    _bq_query(client, truncate_query).result(timeout=BQ_RESULT_TIMEOUT_SEC)

    # 4. BigQuery에 데이터 업로드 (기존 테이블 스키마를 명시해 타입 불일치 방지)
    from google.cloud import bigquery
    existing_table = client.get_table(bq_table_id)

    # PG 컬럼(소문자) → BQ 스키마 필드명(대문자) 으로 맞추기
    bq_field_map = {f.name.upper(): f.name for f in existing_table.schema}
    df.columns = [bq_field_map.get(c.upper(), c) for c in df.columns]

    # DataFrame에 실제 존재하는 컬럼만 스키마에 포함 (컬럼 수 불일치 방지)
    df_cols = set(df.columns)
    filtered_schema = [f for f in existing_table.schema if f.name in df_cols]

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        schema=filtered_schema,
    )
    job = client.load_table_from_dataframe(df, bq_table_id, job_config=job_config)
    job.result()

    _log(f"✅   {bq_table_id} 복제 완료: {len(df)} rows ({(datetime.datetime.now()-_start).total_seconds():.1f}s)")

def _replicate_bq_to_ptg_table(bq_sql, pg_table, truncate=True, chunk_size=50000,
                              pg_conn_id=None, bq_conn_id=None):
    """
    BQ Storage Read API(Arrow) + Producer/Consumer 파이프라인으로 PG에 복제합니다.

    [Producer thread]  BQ stream → Arrow page → DataFrame → Queue
    [Consumer thread]  Queue → PG COPY

    Storage Read API는 gRPC + Arrow 포맷으로 REST보다 처리량이 빠릅니다.
    청크 크기는 BQ가 자동 결정(스트림 수 × 페이지 단위).
    """
    import queue
    import threading

    _start = datetime.datetime.now()
    pg_conn_id = pg_conn_id or PG_CONN_ID_DEFAULT
    bq_conn_id = bq_conn_id or BQ_CONN_ID_DEFAULT

    _log(f"  🔍  BQ SQL:\n{bq_sql.strip()}")

    # ── BQ 쿼리 실행 & 임시 테이블 확정 ─────────────────────────────────────
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    bq_hook   = BigQueryHook(gcp_conn_id=bq_conn_id)
    client    = bq_hook.get_client()
    query_job = _bq_query(client, bq_sql)
    query_job.result(timeout=BQ_RESULT_TIMEOUT_SEC)  # 쿼리 완료 대기
    table_ref = query_job.destination           # TableReference (임시 테이블)

    # ── Storage Read API 세션 생성 ────────────────────────────────────────────
    from google.cloud.bigquery_storage import BigQueryReadClient
    from google.cloud.bigquery_storage_v1.types import DataFormat, ReadSession

    bqs_client   = BigQueryReadClient(credentials=client._credentials)
    read_session = bqs_client.create_read_session(
        parent=f"projects/{client.project}",
        read_session=ReadSession(
            table=(
                f"projects/{table_ref.project}"
                f"/datasets/{table_ref.dataset_id}"
                f"/tables/{table_ref.table_id}"
            ),
            data_format=DataFormat.ARROW,
        ),
        max_stream_count=80,   # 0 = BQ 가 스트림 수 자동 결정 , 80로 설정하여 병렬 처리 가능
    )
    streams = read_session.streams
    _log(f"  🔗  Storage Read API 세션 생성: streams={len(streams)}")

    # ── PG 연결 & TRUNCATE ────────────────────────────────────────────────────
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    pg_hook = PostgresHook(postgres_conn_id=pg_conn_id)
    pg_conn = pg_hook.get_conn()
    cursor  = pg_conn.cursor()
    _set_pg_statement_timeout(cursor)

    if truncate:
        cursor.execute(f"TRUNCATE TABLE {pg_table}")
        pg_conn.commit()
        _log(f"✅   {pg_table} TRUNCATE 완료")

    # PG integer 계열 컬럼 목록 (한 번만 조회)
    if '.' in pg_table:
        schema, tbl = pg_table.split('.', 1)
    else:
        schema, tbl = 'public', pg_table
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
          AND data_type IN ('integer','bigint','smallint','int2','int4','int8')
    """, (schema, tbl))
    pg_int_cols = {row[0] for row in cursor.fetchall()}

    # ── 파이프라인 설정 ───────────────────────────────────────────────────────
    _SENTINEL = object()
    buf_queue: queue.Queue = queue.Queue(maxsize=2)
    producer_error: list   = []

    def _producer():
        """BQ Storage 스트림 → Arrow page → DataFrame → Queue"""
        try:
            chunk_num = 0
            for stream in streams:
                reader = bqs_client.read_rows(stream.name, timeout=BQ_READ_TIMEOUT_SEC)
                for page in reader.rows(read_session).pages:
                    df = page.to_arrow().to_pandas()
                    if df.empty:
                        continue
                    df.columns = [c.lower() for c in df.columns]
                    for col in df.columns:
                        if col in pg_int_cols:
                            df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')
                    chunk_num += 1
                    buf_queue.put((chunk_num, df))
        except Exception as e:
            producer_error.append(e)
        finally:
            buf_queue.put(_SENTINEL)

    producer_thread = threading.Thread(target=_producer, name="bq-producer", daemon=True)
    producer_thread.start()

    # ── Consumer: 메인 스레드에서 PG COPY 수행 ────────────────────────────────
    total_rows = 0
    _LOG_EVERY = 100000           # 10만 행 단위로만 로그 출력
    _next_log  = _LOG_EVERY
    try:
        while True:
            # 생산자(BQ 스트림)가 멈추면 큐가 비어 무한 대기(hang) 하므로
            # BQ_READ_TIMEOUT_SEC 안에 다음 청크가 오지 않으면 강제 실패시킨다.
            try:
                item = buf_queue.get(timeout=BQ_READ_TIMEOUT_SEC)
            except queue.Empty:
                raise TimeoutError(
                    f"BQ 스트림 읽기 {BQ_READ_TIMEOUT_SEC}s 초과 (생산자 응답 없음)"
                )
            if item is _SENTINEL:
                break
            chunk_num, df = item

            csv_buf = io.StringIO()
            df.to_csv(csv_buf, index=False, header=False, na_rep='\\N')
            csv_buf.seek(0)
            cols = ', '.join(df.columns)
            cursor.copy_expert(
                f"COPY {pg_table} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                csv_buf
            )
            pg_conn.commit()
            total_rows += len(df)
            if total_rows >= _next_log:
                _log(f"  📦  [{pg_table}] 누적 {total_rows:,} rows 인서트 완료")
                _next_log += _LOG_EVERY

        if producer_error:
            raise producer_error[0]

        _log(f"✅   {pg_table} 복제 완료: 총 {total_rows:,} rows ({(datetime.datetime.now()-_start).total_seconds():.1f}s)")
    except Exception as e:
        pg_conn.rollback()
        _log(f"❌   {pg_table} 복제 실패: {e}")
        raise
    finally:
        producer_thread.join(timeout=30)
        cursor.close()
        pg_conn.close()


def _replicate_bq_to_ptg_table2(bq_sql, pg_table, truncate=True, rows_per_file=100000,
                                dump_workers=4, load_workers=4,
                                pg_conn_id=None, bq_conn_id=None):
    """
    BQ Storage Read API(Arrow) → CSV 파일 분할 저장 → PG 병렬 COPY 로드 방식.

    [1단계] BQ 스트림들을 여러 워커로 '병렬' 읽어서 CSV 파일로 저장
            - 파일 하나당 최대 rows_per_file(기본 10만) row
            - 파일이 꽉 차면 새 파일로 롤오버
    [2단계] 저장된 여러 CSV 파일을 여러 PG 커넥션으로 '병렬' COPY 로드

    ※ _replicate_bq_to_ptg_table 과 결과는 동일하나, 디스크 경유 + 병렬 COPY 로
      PG 서버 리소스가 충분할 때 처리량이 올라갈 수 있습니다.

    :param rows_per_file: 파일 하나당 최대 row 수 (기본 100000)
    :param dump_workers:  BQ → CSV 저장 병렬 워커 수
    :param load_workers:  CSV → PG COPY 병렬 워커 수
    """
    import os
    import time
    import queue
    import shutil
    import tempfile
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _start = datetime.datetime.now()
    pg_conn_id = pg_conn_id or PG_CONN_ID_DEFAULT
    bq_conn_id = bq_conn_id or BQ_CONN_ID_DEFAULT

    _log(f"  🔍  BQ SQL:\n{bq_sql.strip()}")

    # ── BQ 쿼리 실행 & 임시 테이블 확정 ─────────────────────────────────────
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    bq_hook   = BigQueryHook(gcp_conn_id=bq_conn_id)
    client    = bq_hook.get_client()
    query_job = _bq_query(client, bq_sql)
    query_job.result(timeout=BQ_RESULT_TIMEOUT_SEC)  # 쿼리 완료 대기
    table_ref = query_job.destination           # TableReference (임시 테이블)

    # ── Storage Read API 세션 생성 ───────────────────────────────────────────
    # ※ dump_workers 개수만큼 워커 스레드를 두고, 스트림을 워커에 분배하여
    #   '병렬' 로 read_rows → CSV 파일 저장한다. (워커마다 독립 파일 생성)
    from google.cloud.bigquery_storage import BigQueryReadClient
    from google.cloud.bigquery_storage_v1.types import DataFormat, ReadSession

    bqs_client   = BigQueryReadClient(credentials=client._credentials)
    read_session = bqs_client.create_read_session(
        parent=f"projects/{client.project}",
        read_session=ReadSession(
            table=(
                f"projects/{table_ref.project}"
                f"/datasets/{table_ref.dataset_id}"
                f"/tables/{table_ref.table_id}"
            ),
            data_format=DataFormat.ARROW,
        ),
        max_stream_count=dump_workers * 20,   # 0 = BQ 가 스트림 수 자동 결정 , dump_workers * 20로 설정하여 병렬 처리 가능
    )
    streams = read_session.streams
    _log(f"  🔗  Storage Read API 세션 생성: streams={len(streams)}")

    # ── PG 연결 & TRUNCATE + integer 컬럼 조회 ───────────────────────────────
    from airflow.providers.postgres.hooks.postgres import PostgresHook
    import psycopg2
    pg_hook = PostgresHook(postgres_conn_id=pg_conn_id)
    pg_dsn  = pg_hook.get_uri()   # "postgresql://user:pass@host:port/dbname"
    pg_conn = pg_hook.get_conn()
    cursor  = pg_conn.cursor()
    _set_pg_statement_timeout(cursor)

    if truncate:
        cursor.execute(f"TRUNCATE TABLE {pg_table}")
        pg_conn.commit()
        _log(f"✅   {pg_table} TRUNCATE 완료")

    if '.' in pg_table:
        schema, tbl = pg_table.split('.', 1)
    else:
        schema, tbl = 'public', pg_table
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
          AND data_type IN ('integer','bigint','smallint','int2','int4','int8')
    """, (schema, tbl))
    pg_int_cols = {row[0] for row in cursor.fetchall()}
    cursor.close()
    pg_conn.close()

    # ── 임시 디렉터리 ─────────────────────────────────────────────────────────
    tmp_dir = tempfile.mkdtemp(prefix="bq2pg_")
    _log(f"  📂  임시 디렉터리: {tmp_dir}")

    # 파일 이름 충돌 방지용 카운터/락
    _file_seq_lock = threading.Lock()
    _file_seq      = {"n": 0}
    file_paths_lock = threading.Lock()
    file_paths      = []   # (path, rows, columns) 목록

    def _next_file_path():
        with _file_seq_lock:
            _file_seq["n"] += 1
            n = _file_seq["n"]
        return os.path.join(tmp_dir, f"part_{n:05d}.csv")

    # ── 1단계: BQ 스트림 → CSV 파일 저장 (dump_workers 병렬 읽기) ────────────
    #   스트림을 dump_workers 개의 워커에 라운드로빈 분배하여 '병렬' 로 읽고,
    #   워커마다 독립적인 CSV 파일(part_*.csv)을 생성한다.
    #   컬럼명은 최초로 페이지를 받은 워커가 확정한다.
    stream_columns = None
    _cols_lock     = threading.Lock()

    def _set_columns(cols):
        nonlocal stream_columns
        with _cols_lock:
            if stream_columns is None:
                stream_columns = cols
                _log(f"  ✅  첫 페이지 수신 (columns={len(cols)})")

    # 워커에 스트림 라운드로빈 분배
    n_workers      = max(1, min(dump_workers, len(streams))) if streams else 1
    worker_streams = [[] for _ in range(n_workers)]
    for i, stream in enumerate(streams):
        worker_streams[i % n_workers].append(stream)

    # ── 벽시계 데드라인 감시용 상태 ───────────────────────────────────────────
    #   read_rows 의 timeout 은 gRPC 재시도로 인해 벽시계 기준으로 지켜지지
    #   않으므로, 워커가 페이지를 받을 때마다 last_activity 를 갱신하고
    #   메인 스레드에서 BQ_READ_TIMEOUT_SEC 를 초과하면 강제 실패시킨다.
    stop_event       = threading.Event()
    activity_lock    = threading.Lock()
    last_activity    = {"t": time.monotonic()}

    def _touch():
        with activity_lock:
            last_activity["t"] = time.monotonic()

    def _worker(wid, my_streams):
        """할당된 스트림들을 읽어 워커 전용 CSV 파일로 분할 저장한다."""
        cur_path = None
        cur_file = None
        cur_rows = 0

        def _open_new():
            nonlocal cur_path, cur_file, cur_rows
            cur_path = _next_file_path()
            cur_file = open(cur_path, "w", newline="", encoding="utf-8")
            cur_rows = 0

        def _close_cur():
            nonlocal cur_file, cur_path, cur_rows
            if cur_file is not None:
                cur_file.close()
                with file_paths_lock:
                    file_paths.append((cur_path, cur_rows, stream_columns))
                _log(f"  💾  [w{wid}] 파일 저장 완료: {os.path.basename(cur_path)} ({cur_rows:,} rows)")
                cur_file = None

        try:
            for stream in my_streams:
                if stop_event.is_set():
                    break
                reader = bqs_client.read_rows(stream.name, timeout=BQ_READ_TIMEOUT_SEC)
                for page in reader.rows(read_session).pages:
                    if stop_event.is_set():
                        break
                    _touch()
                    df = page.to_arrow().to_pandas()
                    if df.empty:
                        continue
                    df.columns = [c.lower() for c in df.columns]
                    for col in df.columns:
                        if col in pg_int_cols:
                            df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')
                    _set_columns(list(df.columns))

                    start = 0
                    n = len(df)
                    while start < n:
                        if cur_file is None or cur_rows >= rows_per_file:
                            _close_cur()
                            _open_new()
                        take = min(rows_per_file - cur_rows, n - start)
                        sub = df.iloc[start:start + take]
                        sub.to_csv(cur_file, index=False, header=False, na_rep='\\N')
                        cur_rows += take
                        start   += take
        finally:
            _close_cur()

    _log(f"  🔎  read_rows(gRPC) 병렬 읽기 시작... (workers={n_workers})")

    # ── 워커 실행 + 메인 스레드 벽시계 데드라인 감시 ──────────────────────────
    try:
        with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="bq-dump") as ex:
            futures = [ex.submit(_worker, wid, ws)
                       for wid, ws in enumerate(worker_streams)]

            # 모든 워커가 끝날 때까지, 일정 시간 이상 페이지 수신이 없으면 실패 처리
            while True:
                if all(f.done() for f in futures):
                    break
                with activity_lock:
                    idle = time.monotonic() - last_activity["t"]
                if idle > BQ_READ_TIMEOUT_SEC:
                    stop_event.set()
                    raise TimeoutError(
                        f"BQ 스트림 읽기 {BQ_READ_TIMEOUT_SEC}s 초과 (워커 응답 없음)"
                    )
                time.sleep(1)

            # 워커 내부 예외 전파
            for f in futures:
                f.result()
    except Exception:
        stop_event.set()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    total_files = len(file_paths)
    total_rows_est = sum(r for _, r, _ in file_paths)
    _log(f"  💾  CSV 저장 완료: {total_files} files, {total_rows_est:,} rows "
         f"({(datetime.datetime.now()-_start).total_seconds():.1f}s)")

    # ── 2단계: CSV 파일 → PG 병렬 COPY 로드 ──────────────────────────────────
    load_lock  = threading.Lock()
    loaded     = {"rows": 0}

    def _load_file(path, rows, columns):
        cols_clause = ', '.join(columns) if columns else ''
        copy_sql = (
            f"COPY {pg_table} ({cols_clause}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')"
            if cols_clause else
            f"COPY {pg_table} FROM STDIN WITH (FORMAT CSV, NULL '\\N')"
        )
        # _log(f"  ⏳  [{pg_table}] {os.path.basename(path)} 로드 시작 ({rows:,} rows)")
        # pg_hook.get_conn() 은 커넥션 풀을 공유할 수 있으므로
        # 스레드마다 psycopg2 독립 커넥션 직접 생성
        conn = psycopg2.connect(pg_dsn)
        conn.autocommit = False
        cur  = conn.cursor()
        try:
            with open(path, "r", encoding="utf-8") as f:
                cur.copy_expert(copy_sql, f)
            conn.commit()
            with load_lock:
                loaded["rows"] += rows
                _log(f"  📦  [{pg_table}] {os.path.basename(path)} 로드 완료 "
                     f"(누적 {loaded['rows']:,} rows)")
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    try:
        with ThreadPoolExecutor(max_workers=load_workers) as ex:
            futures = [ex.submit(_load_file, p, r, c) for p, r, c in file_paths]
            for f in as_completed(futures):
                f.result()   # 예외 전파
        _log(f"✅   {pg_table} 복제 완료: 총 {loaded['rows']:,} rows "
             f"({(datetime.datetime.now()-_start).total_seconds():.1f}s)")
    except Exception as e:
        _log(f"❌   {pg_table} 복제 실패: {e}")
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _replicate_ptg_copy_table(src_table, dst_table, truncate=True, pg_conn_id=None):
    """
    PostgreSQL 내에서 src_table → dst_table 복사 (Airflow PostgresHook 사용)
    truncate=True  → TRUNCATE 후 전체 INSERT (기본값, 전체 교체)
    truncate=False → INSERT만 수행 (선행쿼리에서 이미 삭제한 경우)
    pg_conn_id: Airflow Connection ID (기본값: postgres_spw)
    """
    _start = datetime.datetime.now()
    pg_conn_id = pg_conn_id or PG_CONN_ID_DEFAULT

    from airflow.providers.postgres.hooks.postgres import PostgresHook
    pg_hook = PostgresHook(postgres_conn_id=pg_conn_id)
    pg_conn = pg_hook.get_conn()
    cursor = pg_conn.cursor()
    try:
        _set_pg_statement_timeout(cursor)
        if truncate:
            cursor.execute(f"TRUNCATE TABLE {dst_table}")
        cursor.execute(f"INSERT INTO {dst_table} SELECT * FROM {src_table}")
        pg_conn.commit()
        _log(f"✅   {src_table} → {dst_table} 복사 완료 ({'TRUNCATE+INSERT' if truncate else 'INSERT'}, {(datetime.datetime.now()-_start).total_seconds():.1f}s)")
    except Exception as e:
        pg_conn.rollback()
        _log(f"❌   {src_table} → {dst_table} 복사 실패: {e}")
        raise
    finally:
        cursor.close()
        pg_conn.close()


def execute_sql_ptg(sql, params=None, pg_conn_id=None):
    """
    PostgreSQL에서 임의 SQL 실행 (INSERT / UPDATE / DELETE / CALL 등) (Airflow PostgresHook 사용)
    ';' 로 구분된 여러 SQL이 들어오면 순차적으로 실행합니다. (단일 트랜잭션으로 commit)
    :param sql:        실행할 SQL 문자열 (';' 로 여러 개 구분 가능)
    :param params:     바인딩 파라미터 (dict 또는 tuple, 없으면 None)
    :param pg_conn_id: Airflow Connection ID (기본값: postgres_spw)
    """
    _start = datetime.datetime.now()
    pg_conn_id = pg_conn_id or PG_CONN_ID_DEFAULT

    # ';' 로 구분된 다중 SQL → 공백/빈 문장 제거
    statements = [s.strip() for s in sql.split(';') if s.strip()]

    from airflow.providers.postgres.hooks.postgres import PostgresHook
    pg_hook = PostgresHook(postgres_conn_id=pg_conn_id)
    pg_conn = pg_hook.get_conn()
    cursor = pg_conn.cursor()
    try:
        _set_pg_statement_timeout(cursor)
        first_result = None
        for idx, stmt in enumerate(statements, start=1):
            cursor.execute(stmt, params)
            # SELECT 결과가 있으면 첫 행 첫 열 반환 (on_result 조건 체크용)
            if cursor.description and idx == len(statements):
                row = cursor.fetchone()
                first_result = row[0] if row else None
        pg_conn.commit()
        _log(f"✅   PG SQL {len(statements)}건 실행 완료 ({(datetime.datetime.now()-_start).total_seconds():.1f}s)")
        return first_result
    except Exception as e:
        pg_conn.rollback()
        _log(f"❌   SQL 실행 실패: {e}")
        raise
    finally:
        cursor.close()
        pg_conn.close()


def execute_sql_bq(sql, bq_conn_id=None):
    """
    BigQuery에서 임의 SQL 실행 (DDL / DML / CALL 등) (Airflow BigQueryHook 사용)
    ';' 로 구분된 여러 SQL이 들어오면 순차적으로 실행합니다.
    :param sql:        실행할 SQL 문자열 (';' 로 여러 개 구분 가능)
    :param bq_conn_id: Airflow Connection ID (기본값: pjt-lge-oversea-sales-olap)
    """
    _start = datetime.datetime.now()
    bq_conn_id = bq_conn_id or BQ_CONN_ID_DEFAULT

    # ';' 로 구분된 다중 SQL → 공백/빈 문장 제거
    statements = [s.strip() for s in sql.split(';') if s.strip()]

    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    bq_hook = BigQueryHook(gcp_conn_id=bq_conn_id)
    client = bq_hook.get_client()
    try:
        first_result = None
        for idx, stmt in enumerate(statements, start=1):
            job = _bq_query(client, stmt)
            rows = list(job.result(timeout=BQ_RESULT_TIMEOUT_SEC))  # 완료 대기
            _log(f"  ▶  [{idx}/{len(statements)}] BQ SQL 실행 완료: {stmt[:80].strip()}{'...' if len(stmt) > 80 else ''}")
            # SELECT 결과가 있으면 첫 행 첫 열 반환 (on_result 조건 체크용)
            if rows and idx == len(statements):
                try:
                    first_result = rows[0][0]
                except Exception:
                    pass
        _log(f"✅   BQ SQL {len(statements)}건 실행 완료 ({(datetime.datetime.now()-_start).total_seconds():.1f}s)")
        return first_result
    except Exception as e:
        _log(f"❌   BQ SQL 실행 실패: {_fmt_exc(e)}")
        raise


def replicate_bq_to_ptg(bq_sql, if_table, dst_table,
                        pre_sql=None, post_sql=None, chunk_size=50000,
                        pg_conn_id=None, bq_conn_id=None):
    """
    BQ → PG 스테이징(if_table) 후 본테이블(dst_table) 복사를 한 번에 처리합니다.

    실행 순서:
      1. BQ → 스테이징 테이블(if_table) TRUNCATE+적재
      2. [선행쿼리] pre_sql 실행 (PG) — 예: 조건부 DELETE 쿼리 전체 전달
         ※ pre_sql 지정 시 dst_table TRUNCATE 생략 후 INSERT만 수행
         ※ pre_sql 미지정 시 dst_table TRUNCATE 후 전체 INSERT (기존 동작)
      3. 스테이징(if_table) → 본테이블(dst_table) 복사
      4. [후행쿼리] post_sql 실행 (PG) — 예: 통계 갱신, 후처리 등

    :param bq_sql:     BQ 조회 SQL
    :param if_table:   PG 스테이징 테이블 (TRUNCATE 후 BQ 데이터 적재)
    :param dst_table:  PG 본테이블 (if_table → dst_table 복사)
    :param pre_sql:    (선행쿼리) 스테이징 전 PG에서 실행할 SQL 전체 (예: DELETE FROM ... WHERE ...)
    :param post_sql:   (후행쿼리) 복사 완료 후 PG에서 실행할 SQL 전체
    :param chunk_size: BQ 페이지 크기 힌트
    :param pg_conn_id: Airflow PG Connection ID
    :param bq_conn_id: Airflow BQ Connection ID
    """

    # 1. BQ → 스테이징 테이블
    _replicate_bq_to_ptg_table(
        bq_sql, if_table,
        truncate=True,
        chunk_size=chunk_size,
        pg_conn_id=pg_conn_id,
        bq_conn_id=bq_conn_id,
    )

    # 2. 선행쿼리
    if pre_sql:
        _log(f"  ▶  선행쿼리 실행")
        execute_sql_ptg(pre_sql, pg_conn_id=pg_conn_id)

    # 3. 스테이징 → 본테이블 (pre_sql 지정 시 INSERT만, 미지정 시 TRUNCATE+INSERT)
    _replicate_ptg_copy_table(
        if_table, dst_table,
        truncate=(pre_sql is None),
        pg_conn_id=pg_conn_id,
    )

    # 4. 후행쿼리
    if post_sql:
        _log(f"  ▶  후행쿼리 실행")
        execute_sql_ptg(post_sql, pg_conn_id=pg_conn_id)


def replicate_bq_to_ptg2(bq_sql, if_table, dst_table,
                         pre_sql=None, post_sql=None,
                         rows_per_file=100000, dump_workers=4, load_workers=4,
                         pg_conn_id=None, bq_conn_id=None):
    """
    replicate_bq_to_ptg 의 병렬 버전(테스트용).

    1단계 BQ → 스테이징(if_table) 적재를 _replicate_bq_to_ptg_table2 로 수행합니다.
    (CSV 파일 분할 저장 → PG 병렬 COPY 로드)

    나머지 흐름(선행쿼리 → 스테이징→본테이블 복사 → 후행쿼리)은 동일합니다.

    :param bq_sql:        BQ 조회 SQL
    :param if_table:      PG 스테이징 테이블 (TRUNCATE 후 BQ 데이터 적재)
    :param dst_table:     PG 본테이블 (if_table → dst_table 복사)
    :param pre_sql:       (선행쿼리) 스테이징 전 PG에서 실행할 SQL 전체
    :param post_sql:      (후행쿼리) 복사 완료 후 PG에서 실행할 SQL 전체
    :param rows_per_file: 파일 하나당 최대 row 수 (기본 100000)
    :param dump_workers:  BQ → CSV 저장 병렬 워커 수
    :param load_workers:  CSV → PG COPY 병렬 워커 수
    :param pg_conn_id:    Airflow PG Connection ID
    :param bq_conn_id:    Airflow BQ Connection ID
    """

    # 1. BQ → 스테이징 테이블 (병렬 파일 방식)
    _replicate_bq_to_ptg_table2(
        bq_sql, if_table,
        truncate=True,
        rows_per_file=rows_per_file,
        dump_workers=dump_workers,
        load_workers=load_workers,
        pg_conn_id=pg_conn_id,
        bq_conn_id=bq_conn_id,
    )

    # 2. 선행쿼리
    if pre_sql:
        _log(f"  ▶  선행쿼리 실행")
        execute_sql_ptg(pre_sql, pg_conn_id=pg_conn_id)

    # 3. 스테이징 → 본테이블 (pre_sql 지정 시 INSERT만, 미지정 시 TRUNCATE+INSERT)
    _replicate_ptg_copy_table(
        if_table, dst_table,
        truncate=(pre_sql is None),
        pg_conn_id=pg_conn_id,
    )

    # 4. 후행쿼리
    if post_sql:
        _log(f"  ▶  후행쿼리 실행")
        execute_sql_ptg(post_sql, pg_conn_id=pg_conn_id)