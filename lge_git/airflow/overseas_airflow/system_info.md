# Overseas Airflow 개발 구성 설명서

> LGE 해외판매(SPW) 데이터 배치 파이프라인 개발자 참조 문서
> DB 메타 기반으로 Job / Batch DAG 를 동적 생성하는 구조입니다.

---

## 1. 시스템 개요

- **DB 메타 기반 동적 DAG 생성** 방식입니다.
  - `airflow_meta` 스키마의 테이블 내용을 읽어 Airflow DAG 를 코드 수정 없이 자동 생성합니다.
  - `jobs_dynamic.py` : `airflow_meta.job_dag` 각 행 → **수동 실행 Job DAG** 생성 (`schedule=None`)
  - `batches_dynamic.py` : `airflow_meta.batch_dag` 각 행 → **스케줄 Batch DAG** 생성 (여러 Job 을 Task 로 묶어 실행)
- **관리 UI** : `plugins/` 의 Flask 기반 플러그인(`batch_meta_plugin.py`, `app.py`)에서 Job / Batch / Connection 을 웹으로 관리합니다.
- **데이터 이동 로직** : `utils/db_util.py` 가 실제 BQ ↔ PG 복제 / SQL 실행을 담당합니다.

```
┌──────────────┐   읽기    ┌────────────────────┐
│ airflow_meta │──────────▶│ jobs_dynamic.py    │──▶ Job DAG (수동)
│  (메타 DB)    │           │ batches_dynamic.py │──▶ Batch DAG (스케줄)
└──────────────┘           └────────────────────┘
       ▲                             │ 실행
       │ 관리                         ▼
┌──────────────┐            ┌────────────────────┐
│ plugins (UI) │            │ utils/db_util.py    │──▶ BigQuery / PostgreSQL
└──────────────┘            └────────────────────┘
```

---

## 2. 접속 DB

### 2-1. 메타 DB (PostgreSQL) — DAG 정의 저장소

`airflow_meta` 스키마가 위치한 DB 로, DAG 정의/실행 로그를 저장합니다.
`.env` 의 `META_PG_*` 값으로 접속합니다. (`jobs_dynamic.py`, `batches_dynamic.py` 에서 `psycopg2` 직접 접속)

| 항목 | 환경변수 | 기본값 |
|------|----------|--------|
| Host | `META_PG_HOST` | `10.182.32.210` |
| Port | `META_PG_PORT` | `8110` |
| Database | `META_PG_DB` | `airflow_db` |
| User | `META_PG_USER` | `airflow` |
| Password | `META_PG_PASSWORD` | (`.env` 참조) |
| SSL Mode | `META_PG_SSLMODE` | `disable` |

### 2-2. 데이터 처리 대상 DB (Airflow Connection)

실제 데이터 복제/SQL 실행 대상은 **Airflow Connection** 으로 관리합니다. (`utils/db_util.py`)

| 구분 | Connection ID (기본값) | 용도 |
|------|------------------------|------|
| PostgreSQL | `postgres_spw` | 업무 데이터 저장 (`spms` 스키마) |
| BigQuery | `pjt-lge-oversea-sales-olap` | OLAP 데이터 원천 (GCP) |

- 코드 상수 : `PG_CONN_ID_DEFAULT = "postgres_spw"`, `BQ_CONN_ID_DEFAULT = "pjt-lge-oversea-sales-olap"`
- Connection 자체는 Airflow UI 또는 관리 플러그인의 Connection 메뉴에서 등록/수정합니다.

---

## 3. 메타 테이블 목록 및 설명

모든 메타 테이블은 `airflow_meta` 스키마에 있으며, DDL 은 `meta/init_meta_tables.sql` 에 정의되어 있습니다.

### 3-1. `job_dag` — Job(단위 작업) 정의
개별 실행 단위(Job)를 정의합니다. 각 행이 하나의 수동 실행 Job DAG 가 됩니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `job_id` | VARCHAR PK | Job 식별자 (예: `spw.job_d_customers`) |
| `func_name` | VARCHAR | 실행 함수 유형 (아래 4장 참조) |
| `sql_text` | TEXT | 실행할 SQL (원천 조회 또는 프로시저 호출) |
| `params_json` | JSONB | 함수 유형별 파라미터 (대상 테이블 등) |
| `description` | TEXT | 설명 |
| `owner_emails` | TEXT[] | 실패 알림 수신 이메일 목록 |
| `used_vars` | TEXT[] | SQL 내 사용된 사용자 변수 목록 |
| `is_active` | BOOLEAN | 활성 여부 |
| `retries` | INTEGER | 재시도 횟수 (기본 1) |
| `retry_delay_minutes` | INTEGER | 재시도 간격(분, 기본 1) |
| `created_at` / `updated_at` | TIMESTAMP | 생성/수정 시각 (수정 시 트리거 자동 갱신) |

### 3-2. `batch_dag` — Batch(스케줄 묶음) 정의
여러 Job 을 스케줄에 따라 묶어 실행하는 Batch DAG 를 정의합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `dag_id` | VARCHAR PK | Batch 식별자 (예: `spw.batch.0200`) |
| `schedule` | VARCHAR | Cron 표현식 (예: `0 2 * * *`) |
| `tags` | TEXT[] | Airflow 태그 |
| `description` | TEXT | 설명 |
| `is_active` | BOOLEAN | 활성 여부 |
| `used_vars` | TEXT[] | 배치 단위 사용자 변수 목록 |
| `created_at` | TIMESTAMP | 생성 시각 |

### 3-3. `batch_task` — Batch 내 Task (Job 참조)
Batch 안에서 실행할 Task 를 정의하며 `job_dag` 를 참조합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `dag_id` | VARCHAR (FK→batch_dag) | 소속 Batch |
| `task_id` | VARCHAR | Task 식별자 |
| `job_id` | VARCHAR (FK→job_dag) | 실행할 Job |
| `task_vars` | JSONB | Task 단위 고정 변수값. SQL/params 의 `{VAR}` 치환 |
| PK | (dag_id, task_id) | |

### 3-4. `batch_task_dep` — Task 의존 관계
Task 간 실행 순서/조건 분기를 정의합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `dag_id` | VARCHAR (FK) | 소속 Batch |
| `upstream` | VARCHAR | 선행 Task |
| `downstream` | VARCHAR | 후행 Task |
| `trigger_type` | VARCHAR | `on_success`(선행 성공 시)·`on_failure`(선행 실패 시)·`on_result`(결과 일치 시) |
| `trigger_value` | TEXT | `on_result` 시 비교할 기대값 |
| PK | (dag_id, upstream, downstream) | |

### 3-5. `batch_layout` — 실행 흐름도 레이아웃
관리 UI 의 흐름도(Cytoscape) 노드 위치/뷰포트를 저장합니다. (DAG당 1행, `layout` JSONB)

### 3-6. `batch_run_log` — Batch 실행 로그
Batch DAG Run 단위 로그 (1회 실행 = 1행). PK = (run_id, dag_id).
주요 컬럼: `run_type`(scheduled/manual), `status`(running/success/failed), `duration_sec`, `conf_json`, `airflow_run_url`.

### 3-7. `job_run_log` — Job/Task 실행 로그
Job 단독 실행 및 Batch 내 Task 실행을 모두 기록 (1 Task 실행 = 1행). PK = `log_id`(BIGSERIAL).
주요 컬럼: `source_type`(batch/job), `resolved_sql`(변수 치환 후 실제 SQL), `status`, `error_msg`, `result_value`(on_result 조건 판단용).

---

## 4. Job 유형별 설명 (`func_name`)

`job_dag.func_name` 값에 따라 `utils/db_util.py` 의 해당 함수가 실행됩니다.

### 4-1. `execute_sql_ptg` — PG SQL 실행
- **용도** : PostgreSQL 에서 SQL/프로시저/뷰 리프레시 실행
- **`params_json`** : `{}` (파라미터 없음)
- **예시**
  - `CALL spms.sp_snps_finished_proc()` — 프로시저 실행
  - `REFRESH MATERIALIZED VIEW spms.v_snps_effects_ana` — 뷰 리프레시

### 4-2. `replicate_bq_to_ptg` — BigQuery → PostgreSQL 복제
- **용도** : BQ 조회 결과를 PG 로 복제 (스테이징 IF 테이블 → 본 테이블)
- **`params_json`** :
  ```json
  {"if_table": "spms.tbl_if", "dst_table": "spms.tbl"}
  ```
  - `if_table` : 임시(스테이징) 적재 테이블
  - `dst_table` : 최종 반영 대상 테이블
- **처리 방식** : BQ Storage Read API(Arrow) + Producer/Consumer 파이프라인으로 대용량 고속 복제
- **예시** : `spw.job_m_gdmi_fr_europe_ana`, `spw.job_d_subsdr_mst`

### 4-3. `replicate_ptg_to_bq_table` — PostgreSQL → BigQuery 복제
- **용도** : PG 조회 결과를 BQ 테이블로 복제 (TRUNCATE 후 APPEND)
- **`params_json`** :
  ```json
  {"bq_table_id": "project.dataset.table"}
  ```
- **처리 방식** : PG `get_pandas_df` → 타입 정규화(float→NUMERIC 등) → BQ TRUNCATE → `load_table_from_dataframe`
- **예시** : `spw.job_d_customers`, `spw.job_d_billto_store_mst`

### SQL 변수 치환
SQL/params 안에 `{VAR}` 형식 플레이스홀더를 사용할 수 있습니다.
- **내장 변수** : `{BATCH_DT}`, `{PREV_BATCH_DT}`, `{NEXT_BATCH_DT}`
- **사용자 변수** : `{ANY_UPPER_NAME}` — `batch_task.task_vars` 또는 수동 실행 입력값으로 치환

---

## 5. 주요 환경 설정 (`.env`)

> `.env` 는 버전관리에서 제외하세요. UI 플러그인 설정은 `plugins/.env` 에서 별도 관리합니다.

### [1] 메타 DB 접속
`META_PG_HOST`, `META_PG_PORT`, `META_PG_DB`, `META_PG_USER`, `META_PG_PASSWORD`, `META_PG_SSLMODE` — 2-1 절 참조.

### [2] Batch DAG 실행 제어
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_CONCURRENT_BATCHES` | 4 | 동시 실행 가능한 최대 Batch DAG 수 (0=무제한) |
| `MAX_ACTIVE_TASKS_PER_BATCH` | 2 | Batch 1개당 동시 실행 Task 수 (`max_active_tasks`) |
| `MAX_ACTIVE_RUNS_PER_BATCH` | 1 | Batch 1개당 동시 DAG Run 수 (중복 방지 위해 1 권장) |

> 공용 Pool(`batch_concurrency_pool`) 슬롯 수 = `MAX_CONCURRENT_BATCHES × MAX_ACTIVE_TASKS_PER_BATCH`
> 예) 4 × 2 = 전체 동시 Task 최대 8개

### [3] Job DAG 실행 제어
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_ACTIVE_RUNS_PER_JOB` | 1 | Job 1개당 동시 DAG Run 수 |

### [4] 메일 발송 (SMTP) — 정기 배치 실패 알림
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_DEFAULT_TO`(폴백 수신자, `utils/mail_util.py`).

### [5] Airflow URL
`AIRFLOW_URL` — 실패 메일 내 링크 생성용 (예: `http://10.182.33.70:8115`).

### [6] 쿼리 실행 타임아웃 (`utils/db_util.py`)
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `QUERY_TIMEOUT_SEC` | 600 | BQ `job_timeout_ms` / PG `statement_timeout` 최대 실행 시간(초). 0=기본값 |
| `BQ_READ_TIMEOUT_SEC` | 300 | BQ Storage Read API 스트림 읽기 타임아웃(초). gRPC stall 방지 |

---

## 6. 디렉터리 구조 요약

| 경로 | 설명 |
|------|------|
| `jobs_dynamic.py` | 메타 기반 Job DAG 동적 생성 |
| `batches_dynamic.py` | 메타 기반 Batch DAG 동적 생성 |
| `utils/db_util.py` | BQ ↔ PG 복제 / SQL 실행 로직 |
| `utils/log_util.py` | 실행 로그 기록 유틸 |
| `utils/mail_util.py` | 실패 알림 메일 발송 |
| `meta/init_meta_tables.sql` | 메타 테이블 DDL + 시드 데이터 |
| `meta/grant_permissions.sql` | 권한 부여 스크립트 |
| `meta/seed_batch.sql` | 배치 시드 데이터 |
| `plugins/` | 관리 UI (Flask 플러그인, 정적/템플릿 리소스) |
| `.env` | 운영 환경설정 (버전관리 제외) |

---

## 7. 개발 시 참고 사항

1. **새 Job 추가** : `airflow_meta.job_dag` 에 행 추가 → 자동으로 수동 실행 Job DAG 생성. (코드 배포 불필요)
2. **새 Batch 추가** : `batch_dag` + `batch_task` (+ 필요 시 `batch_task_dep`) 등록.
3. **함수 로직 변경** : `utils/db_util.py` 수정 후 배포 (모든 Job 에 공통 반영).
4. **DDL 변경** : `meta/init_meta_tables.sql` 은 멱등(`IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS`)하게 작성되어 재실행 안전.
5. **실행 이력 조회** : `batch_run_log`(배치 단위), `job_run_log`(Task 단위) 로 상태/에러/실행 SQL 확인.

---

## 8. Airflow / Docker 운영 (서버)

> 운영 서버 : `oversea-sales-olap-batch-server`
> Airflow 는 Docker Compose 로 여러 컨테이너(scheduler / api-server / triggerer / dag-processor)로 구동됩니다.
> 대부분의 명령은 `sudo` 권한이 필요하며, `docker-compose.yml` 이 위치한 디렉터리에서 실행합니다.
>
> **Compose 파일 위치 : `/root/airflow`** (root 소유 → `sudo` 필요)
>
> ```bash
> sudo ls -al /root/airflow
> # docker-compose.yml   ← 실제 Compose 정의 파일
> # docker-compose.yml.bak
> # Dockerfile           ← 커스텀 이미지 빌드 정의
> # .env                 ← 환경변수
> # backup_20260504/     ← 백업 디렉터리
> ```

### 8-1. 실행 중인 컨테이너 구성

| 컨테이너 (NAMES) | 역할 | 포트 |
|------------------|------|------|
| `airflow-api-server` | 웹 UI / REST API 서버 | `0.0.0.0:8115 -> 8080` |
| `airflow-scheduler` | DAG 스케줄링 / 실행 트리거 | 8080 (내부) |
| `airflow-triggerer` | Deferrable Operator 트리거 처리 | 8080 (내부) |
| `airflow-dag-processor` | DAG 파일 파싱 / 직렬화 | 8080 (내부) |
| `squid-proxy` | 아웃바운드 프록시 (부가 컨테이너) | `0.0.0.0:8106 -> 3128` |

- Airflow 웹 UI 접속 : `http://<서버IP>:8115` (예: `http://10.182.33.70:8115`)

### 8-2. Docker 상태 확인

```bash
# 실행 중인 컨테이너 확인
sudo docker ps

# 전체 컨테이너(중지 포함) 확인
sudo docker ps -a

# 컨테이너 로그 실시간 확인 (예: 스케줄러)
sudo docker logs -f airflow-scheduler

# Compose 기준 전체 상태 확인 (docker-compose.yml 위치에서)
sudo docker compose ps
```

### 8-3. Airflow 도커 내렸다가 올리기 (재시작)

> `docker-compose.yml` 이 있는 `/root/airflow` 디렉터리로 먼저 이동한 뒤 실행합니다.

```bash
# 0) compose 파일이 있는 디렉터리로 이동
cd /root/airflow         # docker-compose.yml 위치

# 1) 전체 내리기 (컨테이너 중지 + 제거, 네트워크 정리)
sudo docker compose down

# 2) 전체 올리기 (백그라운드 -d)
sudo docker compose up -d

# 3) 상태 확인
sudo docker compose ps
```

- **볼륨(DB 데이터)까지 초기화**하려면(주의: 메타DB 데이터 삭제) :
  ```bash
  sudo docker compose down -v
  ```
- **이미지 변경/재빌드 후 반영**하려면 :
  ```bash
  sudo docker compose up -d --build
  ```

### 8-4. 특정 컨테이너만 재시작

전체를 내리지 않고 개별 서비스만 재시작할 때 사용합니다. (DAG/코드 반영, 프리즈 복구 등)

```bash
# 컨테이너 이름으로 재시작
sudo docker restart airflow-scheduler
sudo docker restart airflow-api-server airflow-dag-processor

# Compose 서비스 단위 재시작
sudo docker compose restart scheduler
sudo docker compose restart api-server
```

### 8-5. Airflow 명령 실행 (컨테이너 내부)

```bash
# 스케줄러 컨테이너 안으로 진입
sudo docker exec -it airflow-scheduler bash

# 컨테이너에 들어가지 않고 Airflow CLI 바로 실행
sudo docker exec -it airflow-scheduler airflow version
sudo docker exec -it airflow-scheduler airflow dags list                 # DAG 목록
sudo docker exec -it airflow-scheduler airflow dags list-import-errors   # 파싱 에러 확인
sudo docker exec -it airflow-scheduler airflow dags trigger <dag_id>     # DAG 수동 실행
```

### 8-6. 코드/DAG 변경 반영 절차

1. DAG/유틸 코드(`jobs_dynamic.py`, `batches_dynamic.py`, `utils/*.py`) 를 서버의 `dags` 볼륨 경로에 반영.
2. **메타(DB) 변경만** 한 경우 → 별도 재시작 불필요 (DAG 프로세서가 주기적으로 재파싱).
3. **파이썬 코드 변경** 한 경우 → `dag-processor` / `scheduler` 재시작 권장 :
   ```bash
   sudo docker restart airflow-dag-processor airflow-scheduler
   ```
4. **의존성/이미지 변경** 한 경우 → `sudo docker compose up -d --build` 로 전체 재빌드.
5. 반영 후 `airflow dags list-import-errors` 로 파싱 오류 여부 확인.
