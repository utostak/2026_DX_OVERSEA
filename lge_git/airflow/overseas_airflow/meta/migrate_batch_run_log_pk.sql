-- ══════════════════════════════════════════════════════════════════
-- batch_run_log PK 변경: run_id 단독 → (run_id, dag_id) 복합
-- 동시간 스케줄 배치의 run_id 충돌 문제 해결
--
-- 실행 전 주의:
--   1. 중복 데이터 확인 (아래 SELECT 결과가 0이어야 정상 진행 가능)
--   2. 짧은 서비스 중단 또는 배치 비활성화 후 실행 권장
-- ══════════════════════════════════════════════════════════════════

-- ── 1. 중복 run_id 확인 ──────────────────────────────────────────
-- 아래 쿼리 결과가 있으면 중복 행 처리 후 진행
SELECT run_id, COUNT(*) AS cnt
  FROM airflow_meta.batch_run_log
 GROUP BY run_id
HAVING COUNT(*) > 1;

-- ── 2. PK 변경 (트랜잭션) ────────────────────────────────────────
BEGIN;

-- 기존 단독 PK 제약 제거
ALTER TABLE airflow_meta.batch_run_log
    DROP CONSTRAINT IF EXISTS batch_run_log_pkey;

-- (run_id, dag_id) 복합 PK 추가
ALTER TABLE airflow_meta.batch_run_log
    ADD CONSTRAINT batch_run_log_pkey PRIMARY KEY (run_id, dag_id);

COMMIT;

-- ── 3. 확인 ─────────────────────────────────────────────────────
SELECT conname, contype, array_agg(a.attname ORDER BY array_position(conkey, a.attnum))
  FROM pg_constraint c
  JOIN pg_attribute  a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
 WHERE c.conrelid = 'airflow_meta.batch_run_log'::regclass
   AND c.contype  = 'p'
 GROUP BY conname, contype;
-- 결과: batch_run_log_pkey | p | {run_id, dag_id}
