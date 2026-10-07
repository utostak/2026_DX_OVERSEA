-- ══════════════════════════════════════════════════════════════════
-- Airflow 배치 메타 관리 테이블 DDL
-- ══════════════════════════════════════════════════════════════════
CREATE SCHEMA IF NOT EXISTS airflow_meta;

-- ── job DAG 정의 ──────────────────────────────────────────────────
-- func_name: execute_sql_ptg | replicate_bq_to_ptg | replicate_ptg_to_bq_table
--
-- params_json 구조 (func_name 별):
--   execute_sql_ptg        : {}
--   replicate_bq_to_ptg    : {"if_table": "schema.tbl_if", "dst_table": "schema.tbl"}
--   replicate_ptg_to_bq_table : {"bq_table_id": "project.dataset.table"}
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS airflow_meta.job_dag (
    job_id        VARCHAR(100) PRIMARY KEY,
    func_name     VARCHAR(50)  NOT NULL,
    sql_text      TEXT         NOT NULL,
    params_json   JSONB        NOT NULL DEFAULT '{}',
    description   TEXT,
    owner_emails  TEXT[]       NOT NULL DEFAULT '{}',
    used_vars     TEXT[]       NOT NULL DEFAULT '{}',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    retries INTEGER NOT NULL DEFAULT 1,
    retry_delay_minutes INTEGER NOT NULL DEFAULT 1
);

-- 기존 배포 대비 컬럼 추가 (멱등)
ALTER TABLE airflow_meta.job_dag
    ADD COLUMN IF NOT EXISTS owner_emails TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE airflow_meta.job_dag
    ADD COLUMN IF NOT EXISTS used_vars TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE airflow_meta.job_dag
    ADD COLUMN IF NOT EXISTS retries INTEGER NOT NULL DEFAULT 1;
ALTER TABLE airflow_meta.job_dag
    ADD COLUMN IF NOT EXISTS retry_delay_minutes INTEGER NOT NULL DEFAULT 1;

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION airflow_meta.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_job_dag_updated_at ON airflow_meta.job_dag;
CREATE TRIGGER trg_job_dag_updated_at
    BEFORE UPDATE ON airflow_meta.job_dag
    FOR EACH ROW EXECUTE FUNCTION airflow_meta.set_updated_at();

-- ── batch DAG 정의 ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS airflow_meta.batch_dag (
    dag_id        VARCHAR(100) PRIMARY KEY,
    schedule      VARCHAR(50)  NOT NULL,
    tags          TEXT[]       NOT NULL DEFAULT '{}',
    description   TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    used_vars     TEXT[]       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- 기존 배포 대비 컬럼 추가 (멱등)
ALTER TABLE airflow_meta.batch_dag
    ADD COLUMN IF NOT EXISTS used_vars TEXT[] NOT NULL DEFAULT '{}';

-- 동시 편집 안전장치: 낙관적 잠금용 버전 컬럼 (멱등)
ALTER TABLE airflow_meta.batch_dag
    ADD COLUMN IF NOT EXISTS row_version INTEGER   NOT NULL DEFAULT 0;
ALTER TABLE airflow_meta.batch_dag
    ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMP NOT NULL DEFAULT NOW();

-- 편집 세션 락(현재 편집 중인 사용자 표시, UX 보강) — TTL 지나면 자동 무효
CREATE TABLE IF NOT EXISTS airflow_meta.batch_edit_lock (
    dag_id      VARCHAR(100) NOT NULL REFERENCES airflow_meta.batch_dag ON DELETE CASCADE,
    editor_id   VARCHAR(64)  NOT NULL,
    editor_name VARCHAR(100) NOT NULL DEFAULT '',
    locked_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dag_id, editor_id)
);
CREATE INDEX IF NOT EXISTS idx_batch_edit_lock_locked_at
    ON airflow_meta.batch_edit_lock (locked_at);

-- ── batch task (job_dag 참조) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS airflow_meta.batch_task (
    dag_id        VARCHAR(100) NOT NULL REFERENCES airflow_meta.batch_dag  ON DELETE CASCADE,
    task_id       VARCHAR(100) NOT NULL,
    job_id        VARCHAR(100) NOT NULL REFERENCES airflow_meta.job_dag,
    -- 사용자 정의 변수 값 (task 단위 고정값): {"MY_VAR": "값", ...}
    -- 실행 시 SQL/params 의 {MY_VAR} 플레이스홀더를 이 값으로 치환한다.
    task_vars     JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (dag_id, task_id)
);

-- 기존 배포 대비 컬럼 추가 (멱등)
ALTER TABLE airflow_meta.batch_task
    ADD COLUMN IF NOT EXISTS task_vars JSONB NOT NULL DEFAULT '{}';

-- ── task 의존관계 ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS airflow_meta.batch_task_dep (
    dag_id        VARCHAR(100) NOT NULL REFERENCES airflow_meta.batch_dag  ON DELETE CASCADE,
    upstream      VARCHAR(100) NOT NULL,
    downstream    VARCHAR(100) NOT NULL,
    trigger_type  VARCHAR(20)  NOT NULL DEFAULT 'on_success',
    -- on_success: 선행 성공 시 실행 (기본)
    -- on_failure: 선행 실패 시 실행
    -- on_result:  선행 쿼리 결과가 trigger_value 와 일치 시 실행
    trigger_value TEXT,        -- on_result 시 비교할 기대값
    PRIMARY KEY (dag_id, upstream, downstream)
);

-- 기존 배포 대비 컬럼 추가 (멱등)
ALTER TABLE airflow_meta.batch_task_dep
    ADD COLUMN IF NOT EXISTS trigger_type  VARCHAR(20) NOT NULL DEFAULT 'on_success',
    ADD COLUMN IF NOT EXISTS trigger_value TEXT;

-- ── 실행 흐름도(Cytoscape) 레이아웃 저장 (DAG당 1행, 확장 가능한 JSON) ──
-- 노드 위치 + 확대/이동(viewport)을 저장 → 재방문 시 동일하게 복원.
-- layout JSON 구조 (version 으로 향후 마이그레이션 관리):
--   {
--     "version": 1,
--     "viewport": {"zoom": 1.2, "pan": {"x": 0, "y": 0}},
--     "nodes":    {"task_id": {"x": 0, "y": 0}, ...},
--     "notes":    [ ... ]        ← 향후 설명 창 등 UI 요소 확장용
--   }
CREATE TABLE IF NOT EXISTS airflow_meta.batch_layout (
    dag_id     VARCHAR(100) PRIMARY KEY REFERENCES airflow_meta.batch_dag ON DELETE CASCADE,
    layout     JSONB        NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ── 배치 실행 로그 ────────────────────────────────────────────────
-- batch DAG run 단위 (1회 실행 = 1행)
-- PK = (run_id, dag_id) : 동시간 스케줄 배치는 run_id가 같을 수 있음
CREATE TABLE IF NOT EXISTS airflow_meta.batch_run_log (
    run_id          VARCHAR(250) NOT NULL,               -- Airflow dag_run.run_id
    dag_id          VARCHAR(100) NOT NULL,
    run_type        VARCHAR(20)  NOT NULL DEFAULT 'manual',   -- scheduled | manual
    scheduled_at    TIMESTAMP,                           -- 정기 배치의 data_interval_start
    started_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMP,
    duration_sec    NUMERIC(12,3),
    status          VARCHAR(20)  NOT NULL DEFAULT 'running',  -- running | success | failed
    conf_json       JSONB        NOT NULL DEFAULT '{}',  -- batch_vars 등 실행 파라미터
    airflow_run_url TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, dag_id)
);
-- 기존 배포 대비: run_id 단독 PK → (run_id, dag_id) 복합 PK 마이그레이션 (멱등)
DO $$
BEGIN
    -- 단독 PK 제약이 남아 있으면 제거 후 복합 PK 추가
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'airflow_meta.batch_run_log'::regclass
           AND contype  = 'p'
           AND array_length(conkey, 1) = 1
    ) THEN
        ALTER TABLE airflow_meta.batch_run_log DROP CONSTRAINT IF EXISTS batch_run_log_pkey;
        ALTER TABLE airflow_meta.batch_run_log
            ADD CONSTRAINT batch_run_log_pkey PRIMARY KEY (run_id, dag_id);
    END IF;
END;
$$;
CREATE INDEX IF NOT EXISTS idx_brl_dag_id
    ON airflow_meta.batch_run_log (dag_id, created_at DESC);

-- ── 잡/태스크 실행 로그 ───────────────────────────────────────────
-- job DAG 단독 실행 및 batch 내 task 실행 모두 기록 (1 task 실행 = 1행)
CREATE TABLE IF NOT EXISTS airflow_meta.job_run_log (
    log_id          BIGSERIAL    PRIMARY KEY,
    run_id          VARCHAR(250),                        -- batch_run_log.run_id (배치 실행 시)
    dag_id          VARCHAR(100),                        -- 배치 dag_id (배치 실행 시)
    task_id         VARCHAR(100),                        -- task_id (배치 실행 시)
    job_id          VARCHAR(100) NOT NULL,
    source_type     VARCHAR(10)  NOT NULL DEFAULT 'job', -- batch | job
    run_type        VARCHAR(20)  NOT NULL DEFAULT 'manual', -- scheduled | manual
    resolved_sql    TEXT,                                -- 변수 치환 후 실제 실행된 SQL
    params_json     JSONB        NOT NULL DEFAULT '{}',
    started_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMP,
    duration_sec    NUMERIC(12,3),
    status          VARCHAR(20)  NOT NULL DEFAULT 'running', -- running|success|failed|skipped
    error_msg       TEXT,
    result_value    TEXT,                                -- 쿼리 결과 첫 번째 행/열 (on_result 조건용)
    airflow_log_url TEXT,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jrl_job_id
    ON airflow_meta.job_run_log (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jrl_run_id
    ON airflow_meta.job_run_log (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jrl_dag_id
    ON airflow_meta.job_run_log (dag_id, created_at DESC) WHERE dag_id IS NOT NULL;


-- ══════════════════════════════════════════════════════════════════
-- Seed: 현재 운영 중인 job 데이터
-- ══════════════════════════════════════════════════════════════════
INSERT INTO airflow_meta.job_dag (job_id, func_name, sql_text, params_json, description) VALUES

-- ── PTG → BQ ────────────────────────────────────────────────────
('spw.job_d_customers',
 'replicate_ptg_to_bq_table',
 'SELECT * FROM spms.d_customers',
 '{"bq_table_id": "pjt-lge-oversea-sales-olap.SPW_OLAP.D_CUSTOMERS"}',
 'D_CUSTOMERS PG → BQ'),

('spw.job_d_billto_store_mst',
 'replicate_ptg_to_bq_table',
 $SQL$SELECT subsdr_nm, billto_cust_cd, channel_nm, sub_channel_nm, channel_cd,
       attribute1, attribute2, attribute3, attribute4, attribute5,
       input_user, input_dt, division_nm, delete_flag, billto_channel_seq
  FROM spms.d_billto_store_mst$SQL$,
 '{"bq_table_id": "pjt-lge-oversea-sales-olap.SPW_OLAP.D_BILLTO_STORE_MST"}',
 'D_BILLTO_STORE_MST PG → BQ'),

('spw.job_d_lumpsum_daily_weight',
 'replicate_ptg_to_bq_table',
 'SELECT * FROM spms.d_lumpsum_daily_weight',
 '{"bq_table_id": "pjt-lge-oversea-sales-olap.SPW_OLAP.D_LUMPSUM_DAILY_WEIGHT"}',
 'D_LUMPSUM_DAILY_WEIGHT PG → BQ'),

-- ── BQ → PTG ────────────────────────────────────────────────────
('spw.job_m_gdmi_fr_europe_ana',
 'replicate_bq_to_ptg',
 $SQL$SELECT PLAN_YMD, NORMAL_WK, PARTIAL_YMD, REGION_NM, SUBSDR_NM, SO_FCST_YN,
       P_UNIT_ID, P_UNIT_NM, DIVISION_CD, DIVISION_NM,
       PRODUCT_GR1_NM, PRODUCT_GR2_NM, PRODUCT_CAT, MDL_SFFX_CD,
       SI_RSLT_QTY, SO_RSLT_QTY, SI_FCST_QTY, SO_FCST_QTY,
       SI_RSLT_G_AMT, SO_RSLT_G_AMT, SI_FCST_G_AMT, SO_FCST_G_AMT,
       SI_RSLT_N_AMT, SO_RSLT_N_AMT, SI_FCST_N_AMT, SO_FCST_N_AMT,
       CH_INV_RSLT_QTY, CH_INV_FCST_QTY,
       SO_RSLT_KAM_W1, SO_FCST_KAM_W1, SO_RSLT_KAM_W4, SO_FCST_KAM_W4,
       SO_RSLT_KAM_W8, SO_FCST_KAM_W8, BATCH_YMD
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.V_GDMI_FR_EUROPE_ANA$SQL$,
 '{"if_table": "spms.m_gdmi_fr_europe_ana_if", "dst_table": "spms.m_gdmi_fr_europe_ana"}',
 'V_GDMI_FR_EUROPE_ANA BQ → PG'),

('spw.job_m_gdmi_channel_psi_result',
 'replicate_bq_to_ptg',
 $SQL$SELECT SUBSDR_NM, PARTIAL_YMD, NORMAL_YMD, CHANNEL_ID, CHANNEL_NM,
       SUB_CHANNEL_ID, SUB_CHANNEL_NM, P_UNIT_NM, MDL_SFFX_CD,
       SO_TOTAL_QTY, SO_AMT, SO_AMT_USD, SO_QTY,
       TOTAL_INV, SELLABLE_INV, DISP_INV, INPUT_DATE
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.V_GDMI_CHANNEL_PSI_RESULT$SQL$,
 '{"if_table": "spms.m_gdmi_channel_psi_result_if", "dst_table": "spms.m_gdmi_channel_psi_result"}',
 'V_GDMI_CHANNEL_PSI_RESULT BQ → PG'),

('spw.job_m_spms_selling_price_ana',
 'replicate_bq_to_ptg',
 $SQL$SELECT SUBSDR_NM, AFFILIATE_CODE, ACCOUNTING_UNIT_CODE, MODEL_CODE,
       BILL_TO_CUSTOMER_CODE, BILL_TO_CUSTOMER_NAME, CURRENCY_CODE,
       LAST_UNIT_PRICE, INVENTORY_QTY, SELLABLE_QTY,
       INVENTORY_UNIT_LIST_PRICE, CHANGE_DATA
  FROM `pjt-lge-oversea-sales-olap`.SPW_OLAP.M_SPMS_SELLING_PRICE_ANA$SQL$,
 '{"if_table": "spms.m_spms_selling_price_ana_if", "dst_table": "spms.m_spms_selling_price_ana"}',
 'M_SPMS_SELLING_PRICE_ANA BQ → PG'),

('spw.job_m_promo_spms_result_ana',
 'replicate_bq_to_ptg',
 $SQL$SELECT SUBSDR_NM, P_PTT, PROMO_HEADER_ID, PROMO_TYPE, HEAD_STATUS_CODE,
       PROMOTION_NO, SALES_PGM_NO, PROMOTION_NAME, REQUESTOR_ID,
       CURRENCY_CODE, INPUT_SOURCE, LINE_NO, PROMO_LINE_ID,
       PROMOTION_START_DATE, PROMOTION_END_DATE, APPLY_YYYYMM,
       EXPECTED_QTY, EXPECTED_GROSS_SALES, EXPECTED_COST, DC_OPERAND_AMT,
       SALES_PGM_NAME, AU_CODE, CUSTOMER_TYPE, CUSTOMER_CODE, CUSTOMER_NAME,
       PRODUCT_TYPE, PRODUCT_CODE, DIVISION_CD, LINE_STATUS_CODE,
       CANCEL_FLAG, UNFOLD_FLAG, QP_LIST_HEADER_ID, REASON_CD,
       EFFECTIVE_PERIOD_FROM, EFFECTIVE_PERIOD_TO, OFFER_ID, ORG_ID,
       LINE_REMARK, CREATION_YMD, LAST_UPDATE_YMD,
       LAST_EXPECTED_COST, LAST_EXPECTED_QTY, LAST_DC_OPERAND_AMT,
       LUMPSUM_LINE_CNT
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.M_PROMO_SPMS_RESULT_ANA
 WHERE SUBSDR_NM IN ('LGEFS','LGEUK','LGETH','LGEIS','LGEBN','LGEAP')
   AND LINE_STATUS_CODE IN (
       'CANCEL','REJECTED','SP_CREATE','APPROVED',
       'CANCEL_REQUESTED','REQUESTED','SELF_REJECT'
   )$SQL$,
 '{"if_table": "spms.m_promo_spms_result_ana_if", "dst_table": "spms.m_promo_spms_result_ana"}',
 'M_PROMO_SPMS_RESULT_ANA BQ → PG'),

('spw.job_m_uk_ha_promo_calendar_ana',
 'replicate_bq_to_ptg',
 $SQL$SELECT BU, CATEGORY, MDL_NEW_CD, MDL_OLD_CD, STATUS, CHANNEL_NM, YMD,
       `pjt-lge-oversea-sales-olap.PRD_OLAP.parse_flexible_date`(YMD) AS BASE_DT,
       WEEK_NO, YYYY, MM, SRP, SOA, INVOICE,
       INPUT_YMD, INPUT_USER, REVISION_CNT
  FROM `pjt-lge-uk-olap`.PRD_OLAP.M_UK_HA_PROMO_CALENDAR_ANA
 WHERE YYYY >= '2026'$SQL$,
 '{"if_table": "spms.m_uk_ha_promo_calendar_ana_if", "dst_table": "spms.m_uk_ha_promo_calendar_ana"}',
 'M_UK_HA_PROMO_CALENDAR_ANA BQ → PG'),

('spw.job_d_subsdr_mst',
 'replicate_bq_to_ptg',
 $SQL$SELECT SUBSDR_CD, SUBSDR_NM, REGION, SHRT_REGION_NM, CURRENCY_CD,
       LOCAL_CURRENCY_CD, NERP_OPEN_YMD, DISPLAY_RANK, USE_YN,
       DATA_AGG_YN, PROMOTION_CURRENCY_CD
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST$SQL$,
 '{"if_table": "spms.d_subsdr_mst_if", "dst_table": "spms.d_subsdr_mst"}',
 'D_SUBSDR_MST BQ → PG'),

-- ── PG SQL 실행 ──────────────────────────────────────────────────
('spw.job_sp_snps_finished_proc',
 'execute_sql_ptg',
 'CALL spms.sp_snps_finished_proc()',
 '{}',
 'SP_SNPS_FINISHED_PROC 프로시저 실행'),

('spw.job_v_snps_effects_ana',
 'execute_sql_ptg',
 'REFRESH MATERIALIZED VIEW spms.v_snps_effects_ana',
 '{}',
 'V_SNPS_EFFECTS_ANA 뷰 리프레시')

ON CONFLICT (job_id) DO UPDATE
    SET func_name   = EXCLUDED.func_name,
        sql_text    = EXCLUDED.sql_text,
        params_json = EXCLUDED.params_json,
        description = EXCLUDED.description,
        updated_at  = NOW();


-- ══════════════════════════════════════════════════════════════════
-- Seed: batch DAG
-- ══════════════════════════════════════════════════════════════════
INSERT INTO airflow_meta.batch_dag (dag_id, schedule, tags, description) VALUES
('spw.batch.0200', '0 2 * * *',  ARRAY['spw','ptg_to_bq'],  'PG → BQ 마스터 데이터'),
('spw.batch.0230', '30 2 * * *', ARRAY['spw','bq_to_ptg'],  'BQ → PG GDMI FR Europe'),
('spw.batch.0930', '30 9 * * *', ARRAY['spw','bq_to_ptg'],  'BQ → PG 판매가격/프로모'),
('spw.batch.1400', '0 14 * * *', ARRAY['spw','bq_to_ptg'],  'BQ → PG UK HA 프로모 달력'),
('spw.batch.1430', '30 14 * * *',ARRAY['spw','bq_to_ptg'],  'BQ → PG GDMI Channel PSI'),
('spw.batch.1500', '0 15 * * *', ARRAY['spw','sp'],         'SP 실행'),
('spw.batch.1530', '30 15 * * *',ARRAY['spw','refresh'],    '뷰 리프레시')
ON CONFLICT (dag_id) DO NOTHING;


-- ══════════════════════════════════════════════════════════════════
-- Seed: batch task
-- ══════════════════════════════════════════════════════════════════
INSERT INTO airflow_meta.batch_task (dag_id, task_id, job_id) VALUES
-- 0200
('spw.batch.0200', 'd_customers',           'spw.job_d_customers'),
('spw.batch.0200', 'd_billto_store_mst',    'spw.job_d_billto_store_mst'),
('spw.batch.0200', 'd_lumpsum_daily_weight','spw.job_d_lumpsum_daily_weight'),
-- 0230
('spw.batch.0230', 'm_gdmi_fr_europe_ana',  'spw.job_m_gdmi_fr_europe_ana'),
-- 0930
('spw.batch.0930', 'm_spms_selling_price_ana',  'spw.job_m_spms_selling_price_ana'),
('spw.batch.0930', 'm_promo_spms_result_ana',   'spw.job_m_promo_spms_result_ana'),
-- 1400
('spw.batch.1400', 'm_uk_ha_promo_calendar_ana','spw.job_m_uk_ha_promo_calendar_ana'),
-- 1430
('spw.batch.1430', 'm_gdmi_channel_psi_result', 'spw.job_m_gdmi_channel_psi_result'),
-- 1500
('spw.batch.1500', 'sp_snps_finished_proc',     'spw.job_sp_snps_finished_proc'),
-- 1530
('spw.batch.1530', 'v_snps_effects_ana_refresh','spw.job_v_snps_effects_ana')
ON CONFLICT DO NOTHING;

-- ══════════════════════════════════════════════════════════════════
-- Seed: batch task 의존관계 (없는 배치는 모든 task 병렬 실행)
-- ══════════════════════════════════════════════════════════════════
-- 현재 batch들은 모두 독립 병렬 실행이므로 dep 없음
-- liw.batch.0600 은 batches.py 에서 직접 관리 (복잡한 의존관계)
