# LIW (SCM-TMS) 아키텍처 & 배포 흐름

## 1. 데이터 흐름 (원천 → BigQuery → PostgreSQL → 앱)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ① 원천 데이터 (LG 사내 EDL/NERP)                                     │
│     pjt-lge-edl-ob.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S 등           │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │ 배치 잡 (.sp / .sql)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ② BigQuery  (분석/리포팅용 DW, 원천)                                  │
│     - [db_batch/](../db_batch/) *.sp, *.sql → 요약 테이블 생성/갱신    │
│       (M_SO_LINE, M_SEA_SHIPMENT_INFO, D_SO_REM_DAYS ...)             │
│     - [db/M_SO_LINE.sql](../db/M_SO_LINE.sql) 같은 정의 스크립트       │
│     - 접속: [config/bigquery.py](../config/bigquery.py)               │
│       (인증: [.streamlit/svcac-if-gmc-*.json](../.streamlit/))        │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────────┐
│  ③ PostgreSQL  (앱 운영 DB, 메타 — 사람이 직접 CRUD 하는 데이터)        │
│     - [db_postgre/](../db_postgre/) create_table*.sql, alter_*.sql    │
│     - 사용자/권한, 마스터데이터(Bill-To/Ship-To/Product...),           │
│       이슈, 접근요청, 웹 접속로그(m_web_log) 등                        │
│     - 접속: [utils/pg_db.py](../utils/pg_db.py) (pg 싱글턴, connection │
│       pool, DB_SCHEMA 로 dev/prd 스키마 분리)                          │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼  (두 DB를 공통 인터페이스로 감쌈)
┌─────────────────────────────────────────────────────────────────────┐
│  ④ 쿼리/데이터 접근 레이어                                             │
│     - [queries/](../queries/) *_queries.py → SQL 문자열 정의           │
│       (order, po, inventory, active_orders, eta_change,               │
│        bigquery_queries_v2)                                           │
│     - [utils/db_query.py](../utils/db_query.py) → run_query() 로 실행,│
│       DataFrame → dict 변환                                           │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ⑤ Flask API / 화면                                                   │
│     [apis/api_*.py](../apis/) (14개 Blueprint) → [templates/](../templates/) + [static/js/](../static/js/) │
└─────────────────────────────────────────────────────────────────────┘
```

**부가 컴포넌트**
- [jobs/eta_digest_email.py](../jobs/eta_digest_email.py) + [run_eta_digest.sh](../jobs/run_eta_digest.sh) → cron/APScheduler로 실행되는 배치 (ETA 변경 요약 메일 발송, [utils/mailer.py](../utils/mailer.py) 사용)
- [tomcat9/webapps/sso/liw-sso-token-receiver.jsp](../tomcat9/webapps/sso/liw-sso-token-receiver.jsp) → 사내 SSO 인증 후 토큰을 Flask 앱으로 넘겨주는 별도 Tomcat 서블릿
- 배포: [gunicorn_config.py](../gunicorn_config.py) + [start.sh](../start.sh)/[stop.sh](../stop.sh) (운영), [start.dev.sh](../start.dev.sh)/[stop.dev.sh](../stop.dev.sh) (개발) → gunicorn 8 workers, APScheduler로 백그라운드 스케줄 작업도 포함

---

## 2. dev → main 배포 흐름

```
┌──────────────┐  push   ┌───────────────────┐  자동   ┌─────────────────┐
│  dev 브랜치   │ ──────▶ │  origin/dev        │ ──────▶ │  개발 서버 9004   │
└──────────────┘         └───────────────────┘         └─────────────────┘
                          (.gitlab-ci.yml: start-job-dev
                           → stop.dev.sh → start.dev.sh)

        │  운영 반영 결정 시, 사람이 직접 실행
        ▼
┌───────────────────────────────┐
│ [merge-dev-to-main.ps1](../merge-dev-to-main.ps1) │
│   origin/dev 를 --no-ff 로 main 에 머지 후 push    │
└───────────────┬───────────────┘
                 │ push
                 ▼
┌───────────────────┐  자동   ┌─────────────────┐
│  origin/main       │ ──────▶ │  운영 서버 9003   │
└───────────────────┘         └─────────────────┘
 (.gitlab-ci.yml: start-job-main
  → stop.sh(kill -9) → start.sh(gunicorn --daemon))
```

- `dev` push = **무조건 자동** 개발서버 재배포. `main`은 사람이 스크립트를 실행해야만 반영되는 **수동 승격** 구조.
- 반영 전 확인: `.\merge-dev-to-main.ps1 -DryRun`

---

## 3. 로그인 흐름

```
요청 → 세션가드([app.py](../app.py) before_request)
        │
        ├─ 예외경로(/login, sso-login, /static/, /api/auth/) → 통과
        ├─ 미인증 → 401 또는 /login 리다이렉트
        └─ 인증됨 → Blueprint 라우팅

  일반 로그인 [api_auth.py](../apis/api_auth.py)
    bcrypt 검증 → 5회 실패 시 계정 잠금

  SSO 로그인 [api_sso.py](../apis/api_sso.py)
    Tomcat JSP → d_user_mst 조회 → 비밀번호 검증 없이 세션 구성
    (신뢰 경계가 Tomcat/JSP 쪽에 있음)

  계정 접근 요청 [api_access_request.py](../apis/api_access_request.py)
    미가입자 신청(PENDING) → 관리자 승인 → 계정 생성
```

---

## 4. API 블루프린트 (14개)

| Blueprint | prefix | 파일 | 역할 |
|---|---|---|---|
| web_bp | `/` | [web.py](../apis/web.py) | 페이지 렌더링 |
| api_bp | `/api` | [api.py](../apis/api.py) | 범용 BQ 대시보드 |
| order_bp | `/api/order` | [api_order.py](../apis/api_order.py) | Active Orders |
| po_bp | `/api/po` | [api_po.py](../apis/api_po.py) | PO 트래킹 |
| inv_bp | `/api/inventory` | [api_inventory.py](../apis/api_inventory.py) | 재고 |
| auth_bp | `/api/auth` | [api_auth.py](../apis/api_auth.py) | 로그인/비밀번호 |
| user_bp | `/api/users` | [api_user.py](../apis/api_user.py) | 사용자 CRUD |
| master_bp | `/api/master` | [api_master.py](../apis/api_master.py) | 마스터데이터 6종 |
| web_log_bp | `/api/web-log` | [api_web_log.py](../apis/api_web_log.py) | 웹 로그 통계 |
| sysconfig_bp | `/api/sysconfig` | [api_system_config.py](../apis/api_system_config.py) | 메뉴/법인 설정 |
| issue_bp | `/api` | [api_issue.py](../apis/api_issue.py) | 이슈 관리 |
| mail_file_bp | – | [api_mail_file.py](../apis/api_mail_file.py) | 엑셀 다운로드 |
| sso_bp | – | [api_sso.py](../apis/api_sso.py) | SSO |
| access_req_bp | `/api/access-requests` | [api_access_request.py](../apis/api_access_request.py) | 계정 승인 |

---

## 5. 주의사항 (심각도순)

| 심각도 | 항목 | 권장 조치 |
|:---:|---|---|
| 🔴 | 자격정보(.env.*, 서비스계정 키)가 git에 커밋됨 | 로테이션 + .gitignore + history 정리 |
| 🔴 | main push = 운영 서버 즉시 kill & 재시작 | 반영 전 `-DryRun`으로 필수 확인 |
| 🟠 | `api_issue.py get_issue()` SQL 문자열 결합 | 파라미터 바인딩으로 전환 |
| 🟠 | 인증코드가 프로세스 인메모리 저장 (8-worker 환경) | 공유 저장소(Redis) 이전 |
| 🟠 | ETA 배치 prd 전용 가드가 주석 처리됨 | 가드 재활성화 |
| 🟡 | `api.py`/`order`/`po`/`inventory`는 메뉴 단위 권한 미체크 | 필요 시 권한체크 추가 |
| 🟡 | `web.py`의 8개 라우트가 대응 템플릿 없음(고아 라우트) | 정리 |
| 🟡 | 루트에 방치된 1회성 마이그레이션 스크립트 | 삭제 |

---
*코드 변경 시 위 다이어그램/표도 함께 갱신 필요.*
