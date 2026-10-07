# LIW (SCM-TMS) — 시스템 아키텍처 구성 정보

> Logistics Intelligence & Warehouse / SCM-TMS Dashboard
> Updated: 2026-09-07

---

## 1. 서버 (Application Server)

| 항목 | 내용 |
|------|------|
| 도메인 | `liw.lge.com` |
| URL | `https://liw.lge.com` (`LIW_BASE_URL`) |
| OS | Ubuntu (Linux) |
| 계정 | `oss_admin` |
| 프로젝트 경로 | `/home/oss_admin/` 하위 (scm-tms) |
| 가상환경 | `/home/oss_admin/.venv` |
| 기동/중지 | `bash start.sh` / `bash stop.sh` (운영, `APP_ENV=prd`) |

---

## 2. 기술 스택

| 구분 | 내용 |
|------|------|
| Language | Python 3 |
| Framework | Flask (Blueprint 구조) |
| WSGI Server | Gunicorn |
| Web Server | Nginx (Reverse Proxy) |
| Session | Flask 서버 세션 (filesystem, 8시간 유지) |
| Frontend | Bootstrap 5, AG Grid, Vanilla JS |
| 환경변수 관리 | `.env.dev` / `.env.prd` (`config/env.py`, `APP_ENV` 자동 감지) |

---

## 3. 포트 구성

| 포트 | 용도 |
|------|------|
| 443 | Nginx HTTPS (운영) → Gunicorn 9003 포워드 |
| 80 | Nginx HTTP → `https://liw.lge.com` 리다이렉트 |
| 9003 | Gunicorn (운영 Flask App, `APP_PORT`) |
| 8114 | Flask 개발 서버 (`app.py` 직접 실행 시 기본 포트) |
| 5432 | PostgreSQL DB 포트 |
| (Tomcat) | SSO JSP 처리 (`liw-sso-token-receiver.jsp`) |

> 라우팅 규칙 (Nginx)
> - `/sso/*` → Tomcat 포워드 (SSO JSP 처리)
> - `/static/*` → Nginx 직접 서빙 (정적 파일)
> - `/*` → Gunicorn 9003 포워드 (Flask App)

---

## 4. Gunicorn 설정 (`gunicorn_config.py`)

| 항목 | 값 |
|------|-----|
| bind | `0.0.0.0:9003` (`APP_PORT` 환경변수) |
| workers | 8 |
| worker_class | `sync` |
| worker_connections | 1000 |
| timeout | 120s (BigQuery 쿼리 시간 고려) |
| keepalive | 5s |
| preload_app | `True` (워커 fork 전 앱 로드 → 메모리 절약) |
| proc_name | `LIW` |
| PID 파일 | `liw_prd.pid` |
| reload / daemon | `False` (운영) |

### 로그 (`logs/`)
- `gunicorn.log` (`errorlog`)
- `access.log` (`accesslog`)
- `app.log` (Flask 앱 로그)
- `error.log`
- `query.log` (PostgreSQL / BigQuery 쿼리 로그)

> `on_starting` 훅에서 `gunicorn.error` / `gunicorn.access` 핸들러를
> `TimedRotatingFileHandler`(midnight, **5일 보관**)로 교체.
> (`logconfig_dict` 방식은 `Logger.setup()` 내부 `dictConfig()` 충돌 위험 → 훅 방식 사용)

---

## 5. 데이터베이스

### 포탈 DB — PostgreSQL
| 항목 | 값 |
|------|-----|
| Host | `10.182.39.245` (`DB_HOSTNAME`) |
| Port | `5432` (`DB_PORT`) |
| Database | `oss_sp_db` (`DATABASE`) |
| User | `postgres` (`DB_USERNAME`) |
| Schema | `liw` (운영) / `liw_dev` (개발) — `DB_SCHEMA` |
| 연결 | `utils/pg_db.py` — `ThreadedConnectionPool` (최대 10 연결, thread-safe) |
| 용도 | 사용자/세션/마스터/이슈/접근요청 등 모든 운영 데이터 |

### 분석 DB — Google BigQuery
| 항목 | 값 |
|------|-----|
| Project | `pjt-lge-oversea-sales-olap` (`PROJECT_ID`) |
| Dataset | `SCM_OLAP` (`DATASET_ID`) |
| 인증 | 서비스계정 JSON 키 `.streamlit/svcac-if-gmc-birpt.pjt-lge-oversea-sales-olap.json` (`GOOGLE_APPLICATION_CREDENTIALS`) |
| 연결 | `utils/db_query.py` — `BigQueryConnectionPool` (single shared client, thread-safe) / `config/bigquery.py` |
| 라이브러리 | `google-cloud-bigquery` |
| 용도 | 주문/PO/재고/배송(Shipment) OLAP 분석, 대시보드 데이터 |

---

## 6. SSO 로그인 연동

```
[사용자 브라우저]
    → LGE SSO 서버 (Agentless)
    → Tomcat: liw-sso-token-receiver.jsp   (Nginx /sso/* → Tomcat)
    → POST /api/user/sso-login             (Flask, api_sso.py)
    → d_user_mst 계정 조회
        · 계정 존재 & 잠금 아님 → Flask 세션 생성 후 메인 이동
        · 계정 없음(404)        → 계정 접근 요청 팝업 노출
```

### 관련 API (`apis/api_sso.py`)
| Method | 경로 | 설명 |
|--------|------|------|
| POST | `/api/user/sso-login` | SSO 계정으로 로그인 |
| GET | `/api/user/access-request/subsdr-list` | 법인(Subsidiary) 목록 |
| POST | `/api/user/access-request/submit` | 계정 접근 요청 등록 |
| GET | `/api/user/access-request/status` | user_id 기준 기존 요청 조회 |
| POST | `/api/user/get-code` | 공통 코드 조회 |

---

## 7. Flask 앱 구조 (Blueprint)

`app.py` 에서 등록되는 Blueprint 목록:

| URL Prefix | Blueprint 파일 | 설명 |
|------------|----------------|------|
| `/` | `apis/web.py` | 페이지 라우팅 (HTML 렌더링) |
| `/api` | `apis/api.py` | 공통 API / 대시보드 |
| `/api/order` | `apis/api_order.py` | 주문(Order) |
| `/api/po` | `apis/api_po.py` | 발주(PO) |
| `/api/inventory` | `apis/api_inventory.py` | 재고 |
| `/api/auth` | `apis/api_auth.py` | 인증/로그인 |
| `/api/users` | `apis/api_user.py` | 사용자 관리 |
| `/api/master` | `apis/api_master.py` | 마스터 데이터 |
| `/api/web-log` | `apis/api_web_log.py` | 웹 접속 로그 |
| `/api/sysconfig` | `apis/api_system_config.py` | 시스템 설정 |
| `/api` | `apis/api_issue.py` | 이슈 관리 |
| (라우트별) | `apis/api_mail_file.py` | 메일/파일 (ETA 다이제스트 등) |
| (SSO) | `apis/api_sso.py` | SSO 로그인 / 계정 접근 요청 |
| `/api/access-requests` | `apis/api_access_request.py` | 계정 접근 요청 관리 |

### 페이지 라우트 (`apis/web.py`)
`/` · `/login` · `/users` · `/master-data` · `/shipment` · `/item` · `/load` ·
`/loading` · `/warehouse` · `/cost` · `/network` · `/leadtime` · `/order` ·
`/active-orders` · `/active-orders-ph` · `/active-po` · `/inventory` ·
`/glossary` · `/web-stats` · `/system-config` · `/issues`

### 요청 처리 훅 (`app.py`)
- `before_request` : 최초 요청 시 법인 마스터 캐시 로드 + 세션 인증 가드(미인증 → `/login` 리다이렉트, API 는 401)
- `after_request` : HTML 페이지 GET 200 응답을 `m_web_log` 에 비동기(Thread) 기록
- `context_processor` : 모든 템플릿에 법인 목록/Division 목록/세션 유저 정보 주입

---

## 8. 세션 / 인증

| 항목 | 값 |
|------|-----|
| SESSION_TYPE | `filesystem` (`flask_session/`) |
| 세션 유효시간 | 8시간 (`PERMANENT_SESSION_LIFETIME`) |
| 쿠키 이름 | `liw_session_prd` (`SESSION_COOKIE_NAME`) — 운영/개발 분리 |
| SECRET_KEY | `SECRET_KEY` 환경변수 |
| 인증 예외 경로 | `/login`, `/api/user/sso-login`, `/api/user/access-request/*`, `/api/user/get-code`, `/static/*`, `/api/auth/*` |

---

## 9. 메일 (SMTP) / POP3

| 구분 | 설정 |
|------|------|
| SMTP Host | `lgekrhqmh01.lge.com` : `25` |
| SMTP From | `liwadmin@lge.com` |
| SMTP TLS/SSL | `false` / `false` |
| 발송 모듈 | `utils/mailer.py` (Send To 기능) |
| POP3 Host | `lgekrhqms65.lge.com` : `110` |
| ETA 알림 관리자 수신 | `LIW_ADMIN_TO` (yunchu.jo@lge.com 외) |
| ETA 다이제스트 | `apis/api_mail_file.py` → `jobs/eta_digest_email.py` (Excel 생성/발송) |

---

## 10. 유틸리티 모듈 (`utils/`)

| 파일 | 설명 |
|------|------|
| `pg_db.py` | PostgreSQL 연결/쿼리 (ThreadedConnectionPool, SELECT/INSERT/UPDATE/MERGE/LOAD) |
| `db_query.py` | BigQuery 연결/쿼리 실행 (BigQueryConnectionPool) |
| `mailer.py` | SMTP 이메일 발송 |
| `subsdr_cache.py` | 법인(Subsidiary) 마스터 캐시 로드 |
| `auth_check.py` | 인증/권한 체크 헬퍼 |

### 설정 (`config/`)
| 파일 | 설명 |
|------|------|
| `env.py` | `.env.dev` / `.env.prd` 로드 (`APP_ENV` 감지) |
| `logging_config.py` | 로깅 설정 (app/error/query 로거) |
| `bigquery.py` | BigQuery Client Singleton |

---

## 11. 환경 파일

| 파일 | 환경 | 주요 값 |
|------|------|---------|
| `.env.prd` | 운영(production) | `APP_PORT=9003`, `DB_SCHEMA=liw`, `SESSION_COOKIE_NAME=liw_session_prd` |
| `.env.dev` | 개발(dev) | `DB_SCHEMA=liw_dev` 등 |

우선순위: `os.environ`(외부 주입) > `.env.<env>` 파일 값 > 기본값

---

## 12. 아키텍처 구성도 (텍스트)

```
[외부 사용자]                         [LGE SSO 서버]
     │                                 (Agentless)
     │ HTTPS                               │ SSO Token
     ▼                                     ▼
┌──────────────────────────────────────────────────┐
│                     Nginx                          │
│   :443 (운영)   :80 (HTTP→HTTPS)                  │
└───────┬───────────────────────┬────────────────────┘
        │ /sso/*                 │ /*
        ▼                        ▼
┌──────────────┐      ┌────────────────────────────────┐
│   Tomcat     │      │        Gunicorn (WSGI)          │
│ (SSO JSP)    │      │  :9003  workers=8  preload=True │
│ liw-sso-     │      │  proc_name: LIW                 │
│ token-       │      │  ┌───────────────────────────┐ │
│ receiver.jsp │──────┼─►│    Flask App (app.py)     │ │
└──────────────┘ 세션 │  │   Blueprint 14개 등록     │ │
                 생성 │  │   before_request: 인증가드│ │
                      │  │   after_request : 웹로깅  │ │
                      │  │  ┌─────────┐  ┌─────────┐ │ │
                      │  │  │ pg_db   │  │ db_query│ │ │
                      │  │  │(Postgre)│  │(BigQuery)│ │ │
                      │  │  └────┬────┘  └────┬────┘ │ │
                      │  └───────┼────────────┼───────┘ │
                      └──────────┼────────────┼──────────┘
                                 ▼            ▼
                   ┌─────────────────────┐  ┌─────────────────────────┐
                   │   PostgreSQL DB      │  │   Google BigQuery        │
                   │ 10.182.39.245:5432   │  │  pjt-lge-oversea-sales  │
                   │  oss_sp_db (liw)     │  │  -olap / SCM_OLAP       │
                   │  (운영 데이터)       │  │  (OLAP 분석 데이터)     │
                   └─────────────────────┘  └─────────────────────────┘

           ┌──────────────────────────┐
           │  SMTP / POP3 (lge.com)   │
           │  ETA 다이제스트 메일 발송 │
           └──────────────────────────┘
```

---
