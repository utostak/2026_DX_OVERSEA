"""
jobs/utils/pg_db.py
──────────────────────────────────────────────────────────────────────────────
PostgreSQL 마스터 테이블 관리 모듈 (독립 실행용)

- 단일 연결(매 호출 시 connect/close) — 일회성 실행용이라 커넥션 풀 불필요
- DB_SCHEMA 환경변수 → search_path 자동 적용 (dev: liw_dev / prd: liw)
- 지원 기능: SELECT / INSERT / UPDATE / DELETE / MERGE(UPSERT) / LOAD(bulk)
- 명시적 트랜잭션 블록 지원

사용 예:
    from utils.pg_db import pg

    rows  = pg.query("SELECT * FROM d_user_mst WHERE container_mail_yn = %s", ('Y',))
"""

import os
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from utils.config import getenv

logger = logging.getLogger(__name__)

# ── query 전용 로거 (독립 실행판에서는 표준 로거 사용) ──────────────────────
_query_logger = logging.getLogger('pg.query')


def _qlog(op: str, sql: str, params, elapsed: float, rows: int,
           success: bool, error: str = None) -> None:
    """PostgreSQL 쿼리 실행 결과를 디버그 로그로 기록"""
    try:
        from datetime import datetime as _dt
        lines = [
            "=" * 80,
            f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}]  pg.{op}",
            f"  Status    : {'SUCCESS' if success else 'FAILED'}",
            f"  Elapsed   : {elapsed * 1000:.1f}ms",
        ]
        if rows is not None:
            lines.append(f"  Rows      : {rows:,}")
        if params:
            lines.append(f"  Params    : {params}")
        if error:
            lines.append(f"  Error     : {error}")
        lines.append("  SQL:")
        for line in sql.strip().split('\n'):
            lines.append(f"    {line}")
        lines.append("")
        _query_logger.debug('\n'.join(lines))
    except Exception:
        pass

# ── psycopg2 임포트 (미설치 시 명확한 에러 출력) ─────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False
    psycopg2 = None


# ============================================================================
# Connection (단순 연결 — 일회성 실행용)
# ============================================================================

class PgConnection:
    """
    PostgreSQL 단순 연결 관리자.

    커넥션 풀 없이 매 요청마다 connect/close.
    연결 시 `options=-c search_path=<DB_SCHEMA>,public` 으로 기본 스키마 설정.
    """

    def __init__(self):
        if not _PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2-binary 가 설치되지 않았습니다.\n"
                "pip install psycopg2-binary"
            )

        self._schema = getenv('DB_SCHEMA', 'public')
        self._dsn    = self._build_dsn()

        logger.info(
            f"✅ PostgreSQL ready "
            f"(host={self._dsn['host']}:{self._dsn['port']} "
            f"db={self._dsn['dbname']} schema={self._schema})"
        )

    # ── DSN 구성 ─────────────────────────────────────────────────────────
    def _build_dsn(self) -> dict:
        return {
            'host':            getenv('DB_HOSTNAME', 'localhost'),
            'port':            getenv('DB_PORT', 5432, cast=int),
            'dbname':          getenv('DATABASE', 'postgres'),
            'user':            getenv('DB_USERNAME', 'postgres'),
            'password':        getenv('DB_PASSWORD', ''),
            'connect_timeout': 10,
            # 접속 시 기본 스키마 설정 → 비정규화 테이블명 자동 해석
            'options':         f'-c search_path={self._schema},public',
        }

    # ── 연결 획득 컨텍스트 ────────────────────────────────────────────────
    @contextmanager
    def acquire(self):
        """
        새 연결을 생성하여 yield.
        - with 블록 정상 종료 → commit
        - 예외 발생        → rollback
        - 항상              → close (연결 종료)
        """
        conn = psycopg2.connect(**self._dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @property
    def schema(self) -> str:
        return self._schema

    def test_connection(self) -> bool:
        try:
            with self.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_schema(), version()")
                    row = cur.fetchone()
            logger.info(f"✅ PostgreSQL connection OK (schema={row[0]})")
            return True
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection FAILED: {e}")
            return False


# ── Lazy singleton ────────────────────────────────────────────────────────────
_pg_conn: Optional[PgConnection] = None


def _get_conn() -> PgConnection:
    """연결 관리자 반환 (첫 호출 시 초기화, env 로드 후에 사용해야 함)"""
    global _pg_conn
    if _pg_conn is None:
        _pg_conn = PgConnection()
    return _pg_conn


# ============================================================================
# PgDb — CRUD 인터페이스 (배치에서 필요한 최소 기능)
# ============================================================================

class PgDb:
    """PostgreSQL CRUD 인터페이스."""

    @property
    def conn(self) -> PgConnection:
        return _get_conn()

    @property
    def schema(self) -> str:
        return _get_conn().schema

    # ──────────────────────────────────────────────────────────────────────
    # 임의 SELECT 실행
    # ──────────────────────────────────────────────────────────────────────
    def query(
        self,
        sql:    str,
        params: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        """
        임의 SELECT 실행.
        Returns: list[dict]

        예:
            rows = pg.query("SELECT * FROM M_CODE WHERE USE_YN = %s", ('Y',))
        """
        t0 = time.perf_counter()
        try:
            with self.conn.acquire() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    result = [dict(r) for r in cur.fetchall()]
            _qlog('query', sql, params, time.perf_counter() - t0, len(result), True)
            return result
        except Exception as e:
            _qlog('query', sql, params, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ query failed: {e}\nSQL: {sql}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # 임의 DML 실행
    # ──────────────────────────────────────────────────────────────────────
    def execute(
        self,
        sql:    str,
        params: Optional[tuple] = None,
    ) -> int:
        """
        임의 DML 실행 (INSERT / UPDATE / DELETE / DDL 등).
        Returns: 영향 행수 (DDL은 -1)
        """
        t0 = time.perf_counter()
        try:
            with self.conn.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    _cnt = cur.rowcount
            _qlog('execute', sql, params, time.perf_counter() - t0, _cnt, True)
            return _cnt
        except Exception as e:
            _qlog('execute', sql, params, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ execute failed: {e}\nSQL: {sql}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # 명시적 트랜잭션 블록
    # ──────────────────────────────────────────────────────────────────────
    @contextmanager
    def transaction(self):
        """
        명시적 트랜잭션 블록 — 여러 작업을 원자적으로 실행.
        with 블록 정상 종료 → commit, 예외 → rollback.
        """
        with self.conn.acquire() as conn:
            yield conn

    def test_connection(self) -> bool:
        return self.conn.test_connection()


# ── 모듈 레벨 싱글턴 ─────────────────────────────────────────────────────────
# 연결은 처음 사용 시 lazy 초기화 (env.py 로드 이후 시점)
pg = PgDb()


# ============================================================================
# 단독 실행 테스트
# ============================================================================
if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.env import load_env
    load_env()

    print('=' * 60)
    print('PostgreSQL 연결 테스트')
    print(f'  SCHEMA : {getenv("DB_SCHEMA")}')
    print(f'  HOST   : {getenv("DB_HOSTNAME")}:{getenv("DB_PORT")}')
    print(f'  DB     : {getenv("DATABASE")}')
    print('=' * 60)

    ok = pg.test_connection()
    print('결과:', '✅ 성공' if ok else '❌ 실패')
