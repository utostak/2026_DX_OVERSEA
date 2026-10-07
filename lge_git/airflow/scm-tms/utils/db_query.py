"""
Dashboard - Database Query Utility Module
BigQuery 쿼리 실행 및 로깅 유틸리티
"""
import os
import threading
import logging
from contextlib import contextmanager
from datetime import datetime, date as _date
from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd

# ============================================================================
# Logger  (설정은 config/logging_config.py 에서 일괄 관리)
# ============================================================================
logger = logging.getLogger(__name__)

# query.log 전용 로거 (지연 초기화 — setup_logging() 이후 첫 호출 시 설정됨)
def _get_query_logger():
    from config.logging_config import get_query_logger
    return get_query_logger()

# ============================================================================
# Query Log Configuration
# ============================================================================
# 하위 호환용 — 기존 코드에서 직접 참조하는 경우 대비
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def _write_query_log(query, params, query_name, timestamp, execution_time,
                     rows_returned, columns, success, error=None,
                     bytes_processed=None, bytes_billed=None):
    """
    쿼리 실행 완료 후 query.log (+ app.log DEBUG) 에 기록
    """
    try:
        lines = []
        lines.append("=" * 80)
        lines.append(f"[{datetime.strptime(timestamp, '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')}]  {query_name}")
        lines.append(f"  Status    : {'SUCCESS' if success else 'FAILED'}")
        lines.append(f"  Elapsed   : {execution_time:.2f}s")
        lines.append(f"  Rows      : {rows_returned:,}  |  Columns: {columns}")

        if bytes_processed:
            lines.append(f"  Processed : {bytes_processed / (1024 * 1024):.2f} MB")
        if bytes_billed:
            lines.append(f"  Billed    : {bytes_billed / (1024 * 1024):.2f} MB")

        if params:
            lines.append("  Params    :")
            for k, v in params.items():
                lines.append(f"    @{k} = '{v}'")

        if error:
            lines.append(f"  Error     : {error}")

        lines.append("  SQL:")
        for line in query.strip().split('\n'):
            lines.append(f"    {line}")

        lines.append("")  # 빈 줄로 구분

        _get_query_logger().debug('\n'.join(lines))

    except Exception as e:
        logger.warning(f"⚠️ Failed to write query log: {e}")


# ============================================================================
# BigQuery Connection Pool
# ============================================================================
import time as _time

class BigQueryConnectionPool:
    """
    Thread-safe BigQuery Client Manager (Single-Client Singleton)

    BigQuery Python Client는 자체적으로 thread-safe하고 내부 urllib3 connection
    pool을 사용합니다. 별도의 클라이언트 pool 대신 단일 클라이언트를 공유하며,
    credentials refresh를 Lock으로 직렬화하여 동시 /token 요청(SSL EOF)을 방지합니다.

    - SSL/EOF 에러 발생 시 클라이언트를 재생성
    - credentials.refresh()는 항상 Lock 내에서 직렬 실행
    """

    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls, **kwargs):
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, **kwargs):
        if self._initialized:
            return
        self._refresh_lock = threading.Lock()   # /token 요청 직렬화
        self._client_lock  = threading.Lock()   # 클라이언트 교체 보호
        self._credentials  = self._load_credentials()
        self._client       = self._create_client()
        self._initialized  = True
        logger.info("✅ BigQuery client ready (single shared client, thread-safe)")

    # ------------------------------------------------------------------
    # Credentials  – refresh 는 반드시 Lock 안에서
    # ------------------------------------------------------------------
    def _load_credentials(self):
        credentials_path = os.getenv(
            'GOOGLE_APPLICATION_CREDENTIALS',
            './.streamlit/svcac-if-gmc-birpt.pjt-lge-oversea-sales-olap.json'
        )
        if not os.path.isabs(credentials_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            credentials_path = os.path.join(project_root, credentials_path)

        if os.path.exists(credentials_path):
            try:
                # BigQuery 사용에 필요한 scope 명시 (refresh 시 invalid_scope 방지)
                creds = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/bigquery',
                            'https://www.googleapis.com/auth/cloud-platform']
                )
                # 앱 시작 시 단 1회, Lock 안에서 토큰 갱신 → 이후 동시 refresh 없음
                with self._refresh_lock:
                    from google.auth.transport.requests import Request as _GAuthRequest
                    creds.refresh(_GAuthRequest())
                logger.info(f"🔑 Credentials loaded & pre-refreshed: {credentials_path}")
                return creds
            except Exception as e:
                logger.error(f"❌ Failed to load/refresh credentials: {e}")
                raise RuntimeError(
                    f"BigQuery credentials 로드 실패: {e}\n"
                    f"파일 경로: {credentials_path}"
                ) from e
        else:
            logger.warning(f"⚠️ Credentials file not found: {credentials_path} → using default credentials")
        return None

    def _ensure_fresh_token(self):
        """
        토큰 만료 임박(5분 이내) 시 직렬 refresh.
        여러 스레드가 동시에 호출해도 Lock 덕분에 1번만 실제 refresh 실행.
        """
        if self._credentials is None:
            return
        from google.auth.transport.requests import Request as _GAuthRequest
        import datetime, pytz
        expiry = getattr(self._credentials, 'expiry', None)
        if expiry is None:
            return
        # expiry는 naive UTC datetime
        now_utc = datetime.datetime.utcnow()
        if (expiry - now_utc).total_seconds() < 300:   # 5분 이내 만료
            with self._refresh_lock:
                # double-check: 다른 스레드가 이미 refresh 했을 수 있음
                expiry = getattr(self._credentials, 'expiry', None)
                now_utc = datetime.datetime.utcnow()
                if expiry is None or (expiry - now_utc).total_seconds() < 300:
                    try:
                        self._credentials.refresh(_GAuthRequest())
                        logger.debug("🔑 Token refreshed (expiry < 5 min)")
                    except Exception as e:
                        logger.warning(f"⚠️ Token refresh failed: {e}")

    # ------------------------------------------------------------------
    # Client 생성 / 교체
    # ------------------------------------------------------------------
    def _create_client(self) -> bigquery.Client:
        if self._credentials:
            return bigquery.Client(credentials=self._credentials)
        # credentials 파일이 없을 때만 ADC 시도
        logger.warning("⚠️ No service account credentials – attempting Application Default Credentials")
        return bigquery.Client()

    def _replace_client(self):
        """SSL 에러 등으로 클라이언트가 깨진 경우 새 것으로 교체"""
        with self._client_lock:
            logger.warning("🔄 Replacing broken BigQuery client...")
            try:
                self._client = self._create_client()
                logger.info("✅ BigQuery client replaced successfully")
            except Exception as e:
                logger.error(f"❌ Failed to replace client: {e}")

    # ------------------------------------------------------------------
    # acquire (기존 코드와 호환되는 context manager)
    # ------------------------------------------------------------------
    @contextmanager
    def acquire(self):
        """
        단일 공유 클라이언트를 yield.
        SSL/연결 에러 발생 시 클라이언트를 교체하고 예외를 다시 raise.
        """
        self._ensure_fresh_token()
        client = self._client
        try:
            yield client
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ('ssl', 'eof', 'connection', 'broken pipe')):
                logger.warning(f"⚠️ SSL/Connection error – replacing client: {e}")
                self._replace_client()
            raise

    @property
    def status(self) -> dict:
        expiry = getattr(self._credentials, 'expiry', None)
        return {
            "mode":    "single-client",
            "client":  "ok" if self._client else "none",
            "token_expiry": str(expiry) if expiry else "unknown",
        }


# 싱글턴 인스턴스
_pool = BigQueryConnectionPool()


def get_pool() -> BigQueryConnectionPool:
    """Connection Pool 인스턴스 반환"""
    return _pool

def run_query(query: str, params: dict = None, query_name: str = "Query"):
    """
    Connection Pool에서 Client를 획득하여 쿼리 실행.
    완료 후 tms_query.log 에 한 번만 기록하고 Client를 Pool에 반환.

    Args:
        query: SQL query string
        params: Query parameters dictionary
        query_name: Name of the query for logging

    Returns:
        pandas.DataFrame or None
    """
    start_time = datetime.now()
    timestamp = start_time.strftime('%Y%m%d_%H%M%S')

    try:
        # Configure query parameters
        job_config = bigquery.QueryJobConfig()
        if params:
            query_parameters = []
            for key, value in params.items():
                if isinstance(value, bool):
                    param_type = "BOOL"
                elif isinstance(value, str):
                    param_type = "STRING"
                elif isinstance(value, int):
                    param_type = "INT64"
                elif isinstance(value, float):
                    param_type = "FLOAT64"
                elif isinstance(value, _date):
                    param_type = "DATE"
                else:
                    param_type = "STRING"
                    value = str(value)
                query_parameters.append(
                    bigquery.ScalarQueryParameter(key, param_type, value)
                )
            job_config.query_parameters = query_parameters

        # Pool에서 Client 획득 → 쿼리 실행 → 자동 반환
        logger.info(f"⏳ [{query_name}] start")
        with _pool.acquire() as client:
            query_job = client.query(query, job_config=job_config)
            df = query_job.to_dataframe()
            bytes_processed = query_job.total_bytes_processed
            bytes_billed = query_job.total_bytes_billed

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        logger.info(f"✅ [{query_name}] end {len(df):,} rows | {execution_time:.2f}s")
        _write_query_log(
            query=query, params=params, query_name=query_name,
            timestamp=timestamp, execution_time=execution_time,
            rows_returned=len(df), columns=len(df.columns),
            success=True,
            bytes_processed=bytes_processed, bytes_billed=bytes_billed
        )

        return df

    except Exception as e:
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        _write_query_log(
            query=query, params=params, query_name=query_name,
            timestamp=timestamp, execution_time=execution_time,
            rows_returned=0, columns=0, success=False, error=str(e)
        )

        logger.error(f"❌ [{query_name}] FAILED ({execution_time:.2f}s) - {str(e)}")
        return None

def test_connection():
    """Test BigQuery connection via Pool"""
    logger.info("🔌 Testing BigQuery connection pool...")

    try:
        with _pool.acquire() as client:
            query_job = client.query("SELECT 1 AS test, CURRENT_TIMESTAMP() AS ts")
            result = query_job.to_dataframe()

        if result is not None and len(result) == 1:
            logger.info(f"✅ Connection pool test passed! {_pool.status}")
            return True
        else:
            logger.error("❌ Connection pool test failed: unexpected result")
            return False
    except Exception as e:
        logger.error(f"❌ Connection pool test failed: {e}")
        return False

# ============================================================================
# Query Result Processing
# ============================================================================
def _make_safe_val_fn():
    """_safe_val 함수를 클로저로 반환 (import 반복 방지)"""
    import datetime as _dt
    import math
    try:
        import numpy as np
        _np = np
    except ImportError:
        _np = None

    def _safe_val(v):
        if v is None:
            return None
        if isinstance(v, float):
            return None if math.isnan(v) else v
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, _dt.datetime):
            return v.strftime('%Y-%m-%d')
        if isinstance(v, _dt.date):
            return v.strftime('%Y-%m-%d')
        if _np is not None:
            if isinstance(v, _np.integer):
                return int(v)
            if isinstance(v, _np.floating):
                return None if math.isnan(float(v)) else float(v)
            if isinstance(v, _np.bool_):
                return bool(v)
        return v
    return _safe_val


def dataframe_iter_rows(df):
    """DataFrame 행을 하나씩 JSON 직렬화 가능한 dict로 yield (메모리 효율)"""
    if df is None or len(df) == 0:
        return
    _safe_val = _make_safe_val_fn()
    cols = list(df.columns)
    for row in df.itertuples(index=False, name=None):
        yield {cols[i]: _safe_val(row[i]) for i in range(len(cols))}


def dataframe_to_dict(df):
    """Convert DataFrame to JSON-serializable dict"""
    if df is None or len(df) == 0:
        return []
    return list(dataframe_iter_rows(df))

# ============================================================================
# Module Test
# ============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("Dashboard - Database Query Utility Test")
    print("=" * 80)
    print()
    
    # Test connection
    test_connection()
