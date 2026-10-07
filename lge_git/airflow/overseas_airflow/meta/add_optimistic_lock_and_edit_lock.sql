-- ══════════════════════════════════════════════════════════════════
-- 동시 편집 안전장치: 낙관적 잠금(Optimistic Locking) + 편집 세션 락
-- ──────────────────────────────────────────────────────────────────
-- 여러 사용자가 같은 배치를 동시에 열어 저장할 때 발생하는
-- "나중 저장이 먼저 저장을 통째로 덮어쓰는(Lost Update)" 문제를 방지한다.
--   1) batch_dag.row_version : 저장 시마다 +1. 저장 요청은 자신이 읽은
--      버전과 일치할 때만 반영되고, 불일치 시 409(충돌)로 거부한다.
--   2) batch_edit_lock        : 현재 누가 편집 중인지 표시(UX 보강용).
--      하트비트로 갱신되며 TTL(기본 60초) 지나면 자동 무효화된다.
-- (멱등: 여러 번 실행해도 안전)
-- ══════════════════════════════════════════════════════════════════

-- ── 1) 낙관적 잠금용 버전 컬럼 ────────────────────────────────────
ALTER TABLE airflow_meta.batch_dag
    ADD COLUMN IF NOT EXISTS row_version INTEGER   NOT NULL DEFAULT 0;
ALTER TABLE airflow_meta.batch_dag
    ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMP NOT NULL DEFAULT NOW();

-- ── 2) 편집 세션 락(열람/편집 표시) ───────────────────────────────
-- editor_id  : 브라우저별 고유 ID(localStorage 생성) — 인증이 없으므로 클라이언트 식별용
-- editor_name: 표시용 이름(사용자가 입력, 없으면 '익명')
-- locked_at  : 하트비트 시각. NOW()-locked_at 이 TTL 초과 시 '만료'로 간주.
CREATE TABLE IF NOT EXISTS airflow_meta.batch_edit_lock (
    dag_id      VARCHAR(100) NOT NULL REFERENCES airflow_meta.batch_dag ON DELETE CASCADE,
    editor_id   VARCHAR(64)  NOT NULL,
    editor_name VARCHAR(100) NOT NULL DEFAULT '',
    locked_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dag_id, editor_id)
);

CREATE INDEX IF NOT EXISTS idx_batch_edit_lock_locked_at
    ON airflow_meta.batch_edit_lock (locked_at);
