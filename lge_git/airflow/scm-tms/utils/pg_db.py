"""
utils/pg_db.py
──────────────────────────────────────────────────────────────────────────────
PostgreSQL 마스터 테이블 관리 모듈

- ThreadedConnectionPool (thread-safe, 최대 10 연결)
- DB_SCHEMA 환경변수 → search_path 자동 적용 (dev: liw_dev / prd: liw)
- 지원 기능: SELECT / INSERT / UPDATE / DELETE / MERGE(UPSERT) / LOAD(bulk)
- 명시적 트랜잭션 블록 지원

사용 예:
    from utils.pg_db import pg

    rows  = pg.select('M_CODE', where={'USE_YN': 'Y'})
    pg.insert('M_CODE', {'CODE': 'A01', 'NAME': '테스트', 'USE_YN': 'Y'})
    pg.update('M_CODE', set={'NAME': '수정명'}, where={'CODE': 'A01'})
    pg.delete('M_CODE', where={'CODE': 'A01'})
    pg.merge('M_CODE', rows=[{'CODE': 'A01', 'NAME': 'UPSERT'}], conflict_cols=['CODE'])
    pg.load('M_CODE', rows=[...], truncate_first=True)
"""

import os
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── query.log 전용 로거 (지연 초기화 — setup_logging() 이후 첫 호출 시 설정됨) ──
def _get_query_logger():
    from config.logging_config import get_query_logger
    return get_query_logger()


def _qlog(op: str, sql: str, params, elapsed: float, rows: int,
           success: bool, error: str = None) -> None:
    """PostgreSQL 쿼리 실행 결과를 query.log 에 기록 (BigQuery 로그 형식과 통일)"""
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
        _get_query_logger().debug('\n'.join(lines))
    except Exception:
        pass

# ── psycopg2 임포트 (미설치 시 명확한 에러 출력) ─────────────────────────────
try:
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False
    psycopg2 = None


# ============================================================================
# Connection Pool (Singleton)
# ============================================================================

class PgConnectionPool:
    """
    Thread-safe PostgreSQL Connection Pool (Singleton).

    연결 시 `options=-c search_path=<DB_SCHEMA>,public` 으로 기본 스키마 설정.
    모든 비정규화 테이블명은 DB_SCHEMA 기준으로 해석됨.
    """

    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls):
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        if not _PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2-binary 가 설치되지 않았습니다.\n"
                "pip install psycopg2-binary"
            )

        self._schema = os.getenv('DB_SCHEMA', 'public')
        self._dsn    = self._build_dsn()
        self._pool   = self._create_pool()
        self._initialized = True

        logger.info(
            f"✅ PostgreSQL pool ready "
            f"(host={self._dsn['host']}:{self._dsn['port']} "
            f"db={self._dsn['dbname']} schema={self._schema})"
        )

    # ── DSN 구성 ─────────────────────────────────────────────────────────
    def _build_dsn(self) -> dict:
        return {
            'host':            os.getenv('DB_HOSTNAME', 'localhost'),
            'port':            int(os.getenv('DB_PORT', 5432)),
            'dbname':          os.getenv('DATABASE', 'postgres'),
            'user':            os.getenv('DB_USERNAME', 'postgres'),
            'password':        os.getenv('DB_PASSWORD', ''),
            'connect_timeout': 10,
            # 접속 시 기본 스키마 설정 → 비정규화 테이블명 자동 해석
            'options':         f'-c search_path={self._schema},public',
        }

    def _create_pool(self) -> 'psycopg2.pool.ThreadedConnectionPool':
        return psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            **self._dsn,
        )

    # ── 연결 획득 컨텍스트 ────────────────────────────────────────────────
    @contextmanager
    def acquire(self):
        """
        Pool에서 연결을 획득하여 yield.
        - with 블록 정상 종료 → commit
        - 예외 발생        → rollback
        - 항상              → putconn (반납)
        """
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

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
_pg_pool: Optional[PgConnectionPool] = None
_pg_init_lock = threading.Lock()


def _get_pool() -> PgConnectionPool:
    """Pool 싱글턴 반환 (첫 호출 시 초기화, env 로드 후에 사용해야 함)"""
    global _pg_pool
    if _pg_pool is None:
        with _pg_init_lock:
            if _pg_pool is None:
                _pg_pool = PgConnectionPool()
    return _pg_pool


# ============================================================================
# PgDb — CRUD 인터페이스
# ============================================================================

class PgDb:
    """
    PostgreSQL 마스터 테이블 CRUD 인터페이스.

    테이블명은 스키마 없이 전달해도 search_path 덕분에 올바른 스키마 적용됨.
    명시적 스키마가 필요하면 'liw.M_CODE' 형태로 전달 가능.
    """

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    @property
    def pool(self) -> PgConnectionPool:
        return _get_pool()

    @property
    def schema(self) -> str:
        return _get_pool().schema

    @staticmethod
    def _where_clause(where: Dict[str, Any]):
        """WHERE 절 문자열 + 값 목록 반환"""
        clause = ' AND '.join(f'"{k}" = %s' for k in where)
        return clause, list(where.values())

    # ──────────────────────────────────────────────────────────────────────
    # SELECT
    # ──────────────────────────────────────────────────────────────────────

    def select(
        self,
        table: str,
        where:    Optional[Dict[str, Any]] = None,
        columns:  Optional[List[str]]      = None,
        order_by: Optional[str]            = None,
        limit:    Optional[int]            = None,
    ) -> List[Dict[str, Any]]:
        """
        단순 SELECT.
        Returns: list[dict]

        예:
            pg.select('M_CODE', where={'USE_YN': 'Y'}, order_by='CODE')
        """
        col_clause = ', '.join(f'"{c}"' for c in columns) if columns else '*'
        q = f'SELECT {col_clause} FROM {table}'
        vals: list = []

        if where:
            clause, vals = self._where_clause(where)
            q += f' WHERE {clause}'
        if order_by:
            q += f' ORDER BY {order_by}'
        if limit:
            q += f' LIMIT {limit}'

        try:
            with self.pool.acquire() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    t0 = time.perf_counter()
                    cur.execute(q, vals)
                    result = [dict(r) for r in cur.fetchall()]
            _qlog('select', q, vals or None, time.perf_counter() - t0, len(result), True)
            return result
        except Exception as e:
            _qlog('select', q, vals or None, time.perf_counter() - t0 if 't0' in dir() else 0, 0, False, str(e))
            logger.error(f"❌ select [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # INSERT
    # ──────────────────────────────────────────────────────────────────────

    def insert(
        self,
        table:     str,
        data:      Dict[str, Any],
        returning: Optional[str] = None,
    ) -> Any:
        """
        단건 INSERT.

        returning: 반환할 컬럼명 (예: 'id'). None이면 영향 행수(int) 반환.

        예:
            new_id = pg.insert('M_CODE', {'CODE': 'A01', 'NAME': '테스트'}, returning='id')
        """
        cols   = list(data.keys())
        vals   = list(data.values())
        col_str = ', '.join(f'"{c}"' for c in cols)
        ph_str  = ', '.join(['%s'] * len(cols))
        q = f'INSERT INTO {table} ({col_str}) VALUES ({ph_str})'
        if returning:
            q += f' RETURNING "{returning}"'

        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(q, vals)
                    if returning:
                        row = cur.fetchone()
                        _ret = row[0] if row else None
                        _cnt = 1
                    else:
                        _ret = cur.rowcount
                        _cnt = cur.rowcount
            _qlog('insert', q, vals, time.perf_counter() - t0, _cnt, True)
            if returning:
                logger.debug(f"INSERT [{table}] → {returning}={_ret}")
            else:
                logger.debug(f"INSERT [{table}] rowcount={_ret}")
            return _ret
        except Exception as e:
            _qlog('insert', q, vals, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ insert [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # UPDATE
    # ──────────────────────────────────────────────────────────────────────

    def update(
        self,
        table: str,
        set:   Dict[str, Any],
        where: Dict[str, Any],
    ) -> int:
        """
        UPDATE. where 필수 (전체 업데이트 방지).
        Returns: 영향 행수

        예:
            pg.update('M_CODE', set={'NAME': '수정명', 'USE_YN': 'N'}, where={'CODE': 'A01'})
        """
        if not where:
            raise ValueError(
                "update(): where 조건이 비어있습니다. "
                "전체 업데이트가 필요하면 execute()를 직접 사용하세요."
            )

        set_clause   = ', '.join(f'"{k}" = %s' for k in set)
        where_clause = ' AND '.join(f'"{k}" = %s' for k in where)
        q    = f'UPDATE {table} SET {set_clause} WHERE {where_clause}'
        vals = list(set.values()) + list(where.values())

        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(q, vals)
                    _cnt = cur.rowcount
            _qlog('update', q, vals, time.perf_counter() - t0, _cnt, True)
            logger.debug(f"UPDATE [{table}] rowcount={_cnt}")
            return _cnt
        except Exception as e:
            _qlog('update', q, vals, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ update [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # DELETE
    # ──────────────────────────────────────────────────────────────────────

    def delete(
        self,
        table: str,
        where: Dict[str, Any],
    ) -> int:
        """
        DELETE. where 필수 (전체 삭제 방지).
        Returns: 영향 행수

        예:
            pg.delete('M_CODE', where={'CODE': 'A01'})
        """
        if not where:
            raise ValueError(
                "delete(): where 조건이 비어있습니다. "
                "전체 삭제가 필요하면 truncate()를 사용하세요."
            )

        where_clause, vals = self._where_clause(where)
        q = f'DELETE FROM {table} WHERE {where_clause}'

        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(q, vals)
                    _cnt = cur.rowcount
            _qlog('delete', q, vals, time.perf_counter() - t0, _cnt, True)
            logger.debug(f"DELETE [{table}] rowcount={_cnt}")
            return _cnt
        except Exception as e:
            _qlog('delete', q, vals, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ delete [{table}] failed: {e}")
            raise

    def truncate(self, table: str) -> None:
        """테이블 전체 삭제 (TRUNCATE). LOAD 전처리 등에 사용."""
        _sql = f'TRUNCATE TABLE {table}'
        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(_sql)
            _qlog('truncate', _sql, None, time.perf_counter() - t0, 0, True)
            logger.info(f"TRUNCATE [{table}] done")
        except Exception as e:
            _qlog('truncate', _sql, None, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ truncate [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # MERGE (UPSERT)  — INSERT … ON CONFLICT DO UPDATE
    # ──────────────────────────────────────────────────────────────────────

    def merge(
        self,
        table:         str,
        rows:          List[Dict[str, Any]],
        conflict_cols: List[str],
        update_cols:   Optional[List[str]] = None,
        page_size:     int = 500,
    ) -> int:
        """
        INSERT … ON CONFLICT (conflict_cols) DO UPDATE SET …

        conflict_cols : UNIQUE / PK 키 컬럼 목록
        update_cols   : 충돌 시 업데이트 컬럼. None이면 conflict_cols 제외 전체.
        Returns: 처리 행수 합계

        예:
            pg.merge(
                'M_CODE',
                rows=[{'CODE': 'A01', 'NAME': 'UPSERT', 'USE_YN': 'Y'}],
                conflict_cols=['CODE'],
            )
        """
        if not rows:
            return 0

        cols = list(rows[0].keys())
        if update_cols is None:
            update_cols = [c for c in cols if c not in conflict_cols]

        col_str      = ', '.join(f'"{c}"' for c in cols)
        conflict_str = ', '.join(f'"{c}"' for c in conflict_cols)

        if update_cols:
            update_str = ', '.join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
            do_clause  = f'DO UPDATE SET {update_str}'
        else:
            do_clause = 'DO NOTHING'

        q = (
            f'INSERT INTO {table} ({col_str}) VALUES %s '
            f'ON CONFLICT ({conflict_str}) {do_clause}'
        )

        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    values = [[row.get(c) for c in cols] for row in rows]
                    psycopg2.extras.execute_values(cur, q, values, page_size=page_size)
                    total = cur.rowcount
            _qlog('merge', q, f'{len(rows)} input rows | conflict={conflict_cols}',
                  time.perf_counter() - t0, max(total, 0), True)
            logger.info(f"MERGE [{table}] rows={total} (input={len(rows)})")
            return total
        except Exception as e:
            _qlog('merge', q, f'{len(rows)} input rows | conflict={conflict_cols}',
                  time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ merge [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # LOAD (bulk INSERT)
    # ──────────────────────────────────────────────────────────────────────

    def load(
        self,
        table:          str,
        rows:           List[Dict[str, Any]],
        truncate_first: bool = False,
        page_size:      int  = 1000,
    ) -> int:
        """
        대량 INSERT (execute_values 사용 — 단건 INSERT보다 10~100배 빠름).
        truncate_first=True: INSERT 전 TRUNCATE 실행 (전체 교체).
        Returns: 처리 행수 합계

        예:
            pg.load('M_CUSTOMER', rows=df.to_dict('records'), truncate_first=True)
        """
        if not rows:
            return 0

        cols    = list(rows[0].keys())
        col_str = ', '.join(f'"{c}"' for c in cols)
        q = f'INSERT INTO {table} ({col_str}) VALUES %s'

        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    if truncate_first:
                        cur.execute(f'TRUNCATE TABLE {table}')
                        logger.info(f"TRUNCATE [{table}] (load pre-step)")
                    values = [[row.get(c) for c in cols] for row in rows]
                    psycopg2.extras.execute_values(cur, q, values, page_size=page_size)
                    total = cur.rowcount
            _qlog('load', q, f'{len(rows)} input rows | truncate_first={truncate_first}',
                  time.perf_counter() - t0, max(total, 0), True)
            logger.info(f"LOAD [{table}] rows={total} (input={len(rows)})")
            return total
        except Exception as e:
            _qlog('load', q, f'{len(rows)} input rows | truncate_first={truncate_first}',
                  time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ load [{table}] failed: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # 임의 SQL 실행
    # ──────────────────────────────────────────────────────────────────────

    def execute(
        self,
        sql:    str,
        params: Optional[tuple] = None,
    ) -> int:
        """
        임의 DML 실행 (INSERT / UPDATE / DELETE / DDL 등).
        Returns: 영향 행수 (DDL은 -1)

        예:
            pg.execute("UPDATE M_CODE SET USE_YN = %s WHERE CODE = %s", ('N', 'A01'))
        """
        t0 = time.perf_counter()
        try:
            with self.pool.acquire() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    _cnt = cur.rowcount
            _qlog('execute', sql, params, time.perf_counter() - t0, _cnt, True)
            return _cnt
        except Exception as e:
            _qlog('execute', sql, params, time.perf_counter() - t0, 0, False, str(e))
            logger.error(f"❌ execute failed: {e}\nSQL: {sql}")
            raise

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
            with self.pool.acquire() as conn:
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
    # 명시적 트랜잭션 블록
    # ──────────────────────────────────────────────────────────────────────

    @contextmanager
    def transaction(self):
        """
        명시적 트랜잭션 블록 — 여러 작업을 원자적으로 실행.
        with 블록 정상 종료 → commit, 예외 → rollback.

        예:
            with pg.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO A ...")
                    cur.execute("UPDATE  B SET ...")
        """
        with self.pool.acquire() as conn:
            yield conn

    # ──────────────────────────────────────────────────────────────────────
    # 연결 테스트
    # ──────────────────────────────────────────────────────────────────────

    def test_connection(self) -> bool:
        return self.pool.test_connection()


# ── 모듈 레벨 싱글턴 ─────────────────────────────────────────────────────────
# Pool은 처음 사용 시 lazy 초기화 (env.py 로드 이후 시점)
pg = PgDb()


# ============================================================================
# 단독 실행 테스트
# ============================================================================
if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.env import load_env
    load_env()

    print('=' * 60)
    print('PostgreSQL 연결 테스트')
    print(f'  SCHEMA : {os.getenv("DB_SCHEMA")}')
    print(f'  HOST   : {os.getenv("DB_HOSTNAME")}:{os.getenv("DB_PORT")}')
    print(f'  DB     : {os.getenv("DATABASE")}')
    print('=' * 60)

    ok = pg.test_connection()
    print('결과:', '✅ 성공' if ok else '❌ 실패')
