-- ══════════════════════════════════════════════════════════════════
-- airflow_meta 스키마 전체 권한 부여
-- ──────────────────────────────────────────────────────────────────
-- 목적: 앱 접속 유저(.env 의 META_PG_USER, 기본 'airflow')가 airflow_meta
--       스키마의 모든 테이블을 읽고/쓰고, 런타임에 새 테이블(batch_layout 등)을
--       생성할 수 있도록 전체 권한을 부여한다.
--
-- 실행 주체: 슈퍼유저(postgres) 또는 airflow_meta 스키마 소유자로 접속해서 실행.
--           (권한을 "주는" 쪽이 권한을 가지고 있어야 함)
--
-- 대상 유저: 아래 :airflow 를 실제 접속 유저로 바꾸세요. 기본은 airflow.
--           psql 변수로 한 번에 적용하려면:
--             psql -v airflow=airflow -d airflow_db -f grant_permissions.sql
--           (psql 변수를 못 쓰는 환경이면 본문의 :"airflow" 를 airflow 로 치환)
-- ══════════════════════════════════════════════════════════════════

\set airflow airflow

-- 1) 스키마 사용(USAGE) + 객체 생성(CREATE) 권한
--    CREATE 가 있어야 앱이 batch_layout 같은 테이블을 직접 만들 수 있음
GRANT ALL ON SCHEMA airflow_meta TO :"airflow";

-- 2) 기존 모든 테이블/시퀀스에 전체 권한 (SELECT/INSERT/UPDATE/DELETE 등)
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA airflow_meta TO :"airflow";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA airflow_meta TO :"airflow";
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA airflow_meta TO :"airflow";

-- 3) 앞으로 "이 스크립트를 실행한 롤"이 만들 테이블/시퀀스에도 자동 전체 권한
--    (예: postgres 가 init_meta_tables.sql 로 새 테이블을 추가해도 airflow 가 바로 사용 가능)
ALTER DEFAULT PRIVILEGES IN SCHEMA airflow_meta
    GRANT ALL PRIVILEGES ON TABLES TO :"airflow";
ALTER DEFAULT PRIVILEGES IN SCHEMA airflow_meta
    GRANT ALL PRIVILEGES ON SEQUENCES TO :"airflow";

-- ── (선택) 더 근본적인 방법: 스키마/테이블 소유권을 airflow 로 이전 ──────
-- 위 GRANT 만으로 충분하지만, 소유권까지 넘기면 DDL(ALTER/DROP)도 자유로움.
-- 필요 시 주석을 해제해서 실행하세요.
--
-- ALTER SCHEMA airflow_meta OWNER TO airflow;
-- DO $$
-- DECLARE r record;
-- BEGIN
--   FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'airflow_meta' LOOP
--     EXECUTE format('ALTER TABLE airflow_meta.%I OWNER TO airflow;', r.tablename);
--   END LOOP;
-- END $$;

-- ── 확인 ───────────────────────────────────────────────────────────
-- 부여 결과 확인:
--   \dn+ airflow_meta
--   \dp airflow_meta.*
