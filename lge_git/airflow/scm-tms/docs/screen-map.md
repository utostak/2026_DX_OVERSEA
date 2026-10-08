# LIW 화면별 데이터 트레이서빌리티 맵

이 문서는 [deploy-flow.md](deploy-flow.md)(아키텍처 개요)와 [db-map.md](db-map.md)(테이블 목록)를 전제로, **화면(URL) → 템플릿/JS → API 엔드포인트 → apis/api_*.py 함수 → 조회 테이블 → (배치 대상이면) 원천 뷰**까지 실제 코드를 열어 확인한 결과입니다. 테이블명은 `db-map.md`와 동일 표기를 씁니다.

**이 문서로 답할 수 있는 질문**
- "화면 A 데이터를 원천에서 직접 보고 싶다" → 해당 화면 섹션의 "조회 테이블"→"원천까지의 체인" 따라가면 됨
- "화면 A 데이터가 이상하다" → "조회 테이블"에 적힌 정확한 테이블을 BigQuery/PostgreSQL에서 직접 확인
- "화면 A 폰트/문구/레이아웃을 바꿔달라" → "화면 수정 시 건드릴 파일"만 보면 됨 (로직 파일과 분리해서 명시)

`templates/backup/`으로 옮겨져 실제 템플릿이 없는 8개 고아 라우트(`/shipment`,`/item`,`/load`,`/loading`,`/warehouse`,`/cost`,`/network`,`/leadtime`)는 이미 [deploy-flow.md](deploy-flow.md)에 기록되어 있어 제외합니다.

---

## 0. 요약표 (빠른 조회용)

| 화면 | 템플릿 | JS 파일 | 핵심 API | 핵심 테이블(대표 1~2개) |
|---|---|---|---|---|
| 로그인 | `login.html` | (인라인, 별도 js 없음) | `/api/auth/login`, `/api/user/access-request/*` | PG `d_user_mst` |
| Active Orders | `active_orders.html` | `common-popup.js`, `model-header-comp.js`, `ag-col-helpers.js`, `order-detail-modal.js`, `container-detail-modal.js` | `/api/order/active-*` | BQ `M_SO_LINE`, `M_SO_LINE_BACK`, `M_PO_TRACKING` |
| Active PO | `active_po.html` | `common-popup.js`, `ag-col-helpers.js`, `container-detail-modal.js` | `/api/po/active-flow`, `/api/po/active-raw` | BQ `M_PO_TRACKING`, `M_SEA_SHIPMENT_INFO` |
| Inventory | `inventory.html` | `common-popup.js`, `ag-col-helpers.js` | `/api/inventory/current-*` | BQ `M_CURINV_SNAPSHOT_S` |
| Order (레거시) | `order.html` | `common-popup.js`, `model-header-comp.js`, `ag-col-helpers.js` | `/api/order/kpi`, `/api/order/raw` | BQ `M_SO_LINE` |
| Master Data (6탭) | `master_data.html` | `master_shared.js` + 탭별 `master_*.js` 6개 | `/api/master/{billto,shipto,product,sales-target,sales-team,billto-biz}` | PG `d_billto_mst` 등 6개 마스터 |
| Users | `users.html` | `common-popup.js` | `/api/users*`, `/api/access-requests*` | PG `d_user_mst`, `d_user_access_request` |
| System Config | `system_config.html` | `common-popup.js`, `ag-col-helpers.js` | `/api/sysconfig/{menu,usertype,subsdr}` | PG `d_menu_mst`, `d_subsdr_mst` |
| Issues | `issues.html` + `module/common_issue_modal.html` | `common-popup.js` | `/api/issues*` | PG `d_issue_mst`, `d_issue_order`, `d_issue_comment` |
| Web Stats | `web_stats.html` | `common-popup.js` | `/api/web-log/{stats,detail,months}` | PG `m_web_log` |
| Glossary | `glossary.html` | `common-popup.js` (API 호출 없음, 순수 정적) | 없음 | 없음 |
| Mail Download | `mail_download.html` (`mail_file_bp`) | (인라인) | `/api/mail-file/eta/download` | BQ `M_SEA_SHIPMENT_INFO`, `M_PO_TRACKING` |

---

## 1. 로그인 — `/login`

- **라우트**: [apis/web.py](../apis/web.py) `login_page()`
- **템플릿**: [templates/login.html](../templates/login.html) (공용 navbar 없음 — 로그인 전 독립 페이지)
- **JS**: 별도 파일 없음, 로그인/비밀번호초기화/계정신청/이메일인증/재설정 로직 전부 템플릿 내 인라인 `<script>`
- **호출 API**:
  - `POST /api/auth/login`, `POST /api/auth/set-initial-password`
  - `POST /api/auth/register/send-code`, `POST /api/auth/register`
  - `POST /api/auth/reset-password/send-code`, `POST /api/auth/reset-password`
  - `GET /api/user/access-request/subsdr-list`, `POST /api/user/access-request/submit`
- **처리 파일**: [apis/api_auth.py](../apis/api_auth.py)(로그인/비밀번호 계열), **[apis/api_sso.py](../apis/api_sso.py)**(`access_request_subsdr_list`, `access_request_submit` — URL은 `/api/user/access-request/*`지만 실제로는 `access_req_bp`가 아니라 `sso_bp`에 등록되어 있음, 코드로 재확인 완료)
- **조회 테이블**: PG `d_user_mst`, `d_user_type_mst`, `d_user_access_request`
- **원천 체인**: 없음 (PG 전용)
- **수정 시**: 폰트/문구/레이아웃 → `templates/login.html` 한 파일 / 로그인·잠금 정책 → `apis/api_auth.py` / 계정신청 로직 → `apis/api_sso.py`

---

## 2. Active Orders — `/active-orders`

- **라우트**: `apis/web.py` `active_orders_page()`
- **템플릿**: [templates/active_orders.html](../templates/active_orders.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_select2_init.html`, `module/order_detail_modal.html(_styles)`, `module/container_detail_modal.html(_styles)`, `module/customer_orders_modal.html(_styles)`, `module/common_issue_modal.html(_styles)`, `module/common_footer.html`
- **JS**: `common-popup.js`, `model-header-comp.js`, `ag-col-helpers.js`, `order-detail-modal.js`, `container-detail-modal.js`
- **호출 API**:
  - `GET /api/order/active-flow`(Flow 카드) · `active-raw`(원본그리드) · `active-inbound`/`active-inbound-raw`(백오더) · `active-delivery`(매출목표대비) · `active-hold` · `active-iod-raw`/`active-iod-report`/`active-flow-report`(상세보고서)
  - `GET /api/order/currencies`,`/order-types`,`/billto-biz-names`,`/data-timestamp`
  - `POST /api/order/send-grid-email`
  - `GET /api/order/container-detail`,`/container-detail-lines`
  - `GET /api/auth/me`, `POST /api/web-log/action`
  - `GET /api/orders/issue-badges`,`/api/issues/departments`,`/api/issues/users`, `POST /api/issues`
- **처리 파일**: [apis/api_order.py](../apis/api_order.py)(대부분), [apis/api_auth.py](../apis/api_auth.py)(`me`), [apis/api_web_log.py](../apis/api_web_log.py)(`log_action`), [apis/api_issue.py](../apis/api_issue.py)(배지/부서/담당자/이슈생성)

- **초기 로드 트리거**: 페이지 진입 시 `$(document).ready()` → `onLegalEntityChange()` → `loadAll()`([active_orders.html:2474](../templates/active_orders.html#L2474))가 아래 5개를 **동시(병렬)**로 호출. 카드(네모박스) 하나가 데이터 안 맞을 때 이 표에서 해당 카드 행만 보고 바로 쿼리/테이블까지 찾아가면 됨.

  | 카드/화면 요소 | fetch 호출 | 렌더 함수 | API 핸들러 | 쿼리 | 테이블 |
  |---|---|---|---|---|---|
  | Order/Shipping Stage 퍼널 카드 | `/api/order/active-flow` | `renderSysFlow()` | `api_order.py:127 get_order_active_flow()` | `QUERY_ORDER_ACTIVE_FLOW`(:53) | `SCM_OLAP.M_SO_LINE` |
  | Delivery Stage 카드 | `/api/order/active-delivery` | `renderDelivery()` | `api_order.py:160 get_order_active_delivery()` | `QUERY_ORDER_DELIVERY_FLOW` | `SCM_OLAP.M_SO_LINE` |
  | Inbound Stage(Back Order) 카드 | `/api/order/active-inbound` | `renderInbound()` | `api_order.py:197 get_order_active_inbound()` | `QUERY_ORDER_INBOUND_FLOW` | `SCM_OLAP.M_SO_LINE_BACK` |
  | Hold Detail 접이식 영역 | `/api/order/active-hold` | `renderHoldDetail()` | `api_order.py:527 get_order_active_hold()` | `QUERY_ORDER_HOLD_DETAIL` | `SCM_OLAP.M_SO_LINE` |
  | 하단 "Active Orders(Open)" 그리드 탭(원본 리스트) | `/api/order/active-raw` | `activeGridApi.setGridOption` | `api_order.py:518 get_order_active_raw()` | `QUERY_ORDER_ACTIVE_RAW`(:418, 주석 "현재 오픈 주문 전체") | `SCM_OLAP.M_SO_LINE` |

  ⚠️ `QUERY_ORDER_TARGET_USD`(`@base_ym6` 사용)는 `api_order.py`에 import만 되어 있고 실제 호출 없음 — 죽은 코드, 위 흐름과 무관.

- **조회 테이블**:
  - BQ `M_SO_LINE`(대부분 카드), `M_SO_LINE_BACK`(백오더), `M_SO_LINE_INVOICE_NERP`(IOD), `M_PO_TRACKING`(컨테이너), `D_USD_CONVERSION_RATE_MST`, `REF_D_SUBSDR_MST`, `REF_D_BILLTO_BIZ_MST`, `REF_D_SALES_TARGET_MST`
  - PG `d_sales_target_mst`(타겟 병합), `d_product_mst`, `d_issue_mst`/`d_issue_order`/`d_issue_comment`, `m_web_log`, `d_user_mst`
- **원천 체인**: `M_SO_LINE` ← [db/M_SO_LINE.sql](../db/M_SO_LINE.sql)/[liw.job_M_SO_LINE.sql](../db_batch/liw.job_M_SO_LINE.sql) ← `V_L0TMS__*`(6종)+`V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V`+`V_L1SALE_TMSALE_NERP_NDGS_SUBSDR_M`+`V_L1SCM__TRSCM__SO_LINE_DW_S` (+ `D_SO_REM_DAYS` 순환의존, [db-map.md](db-map.md) 참조). `M_SO_LINE_BACK` ← [liw.job_M_SO_LINE_BACK_PO_MAP.sql](../db_batch/liw.job_M_SO_LINE_BACK_PO_MAP.sql). `M_SO_LINE_INVOICE_NERP`/`D_USD_CONVERSION_RATE_MST`/`REF_D_*`는 이 저장소에 생성 스크립트 없음(db-map.md ❌/unknown 표시).
- **수정 시**: 폰트/문구/카드레이아웃 → `templates/active_orders.html` / 공용 네비·푸터 → `templates/module/common_navbar.html`,`common_footer.html` / 그리드 컬럼 포맷 → `static/js/ag-col-helpers.js`,`model-header-comp.js` / 데이터·로직 → `apis/api_order.py` + `queries/active_orders_queries.py` / 이슈 관련 → `apis/api_issue.py`

---

## 3. Active PO — `/active-po`

- **라우트**: `apis/web.py` `active_po_page()`
- **템플릿**: [templates/active_po.html](../templates/active_po.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/container_detail_modal.html(_styles)`, `module/common_select2_init.html`, `module/common_footer.html`
- **JS**: `common-popup.js`, `ag-col-helpers.js`, `container-detail-modal.js`
- **호출 API**: `GET /api/po/data-timestamp`,`/active-flow`,`/active-raw`, `GET /api/order/container-detail`,`/container-detail-lines`
- **처리 파일**: [apis/api_po.py](../apis/api_po.py), `apis/api_order.py`(컨테이너 모달 공유)
- **조회 테이블**: BQ `M_PO_TRACKING`(PO/Flow/컨테이너), `M_SEA_SHIPMENT_INFO`(ETA 서브쿼리)
- **원천 체인**: `M_PO_TRACKING`은 생성 스크립트 없음(❌). `M_SEA_SHIPMENT_INFO` ← [liw.job_M_SEA_SHIPMENT_INFO.sql](../db_batch/liw.job_M_SEA_SHIPMENT_INFO.sql) ← `V_L0NEDW_ZSLEI1021`
- **수정 시**: 폰트/문구/레이아웃 → `templates/active_po.html` / 데이터·로직 → `apis/api_po.py` + `queries/po_queries.py`

---

## 4. Inventory — `/inventory`

- **라우트**: `apis/web.py` `inventory_page()`
- **템플릿**: [templates/inventory.html](../templates/inventory.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_select2_init.html`, `module/common_footer.html`
- **JS**: `common-popup.js`, `ag-col-helpers.js`
- **호출 API**: `GET /api/inventory/data-timestamp`,`/current-summary`,`/current-raw`
- **처리 파일**: [apis/api_inventory.py](../apis/api_inventory.py)
- **조회 테이블**: BQ `M_CURINV_SNAPSHOT_S`, `PRD_OLAP.D_NPT_MDL_NEW_MST`(모델 조인)
- **원천 체인**: `M_CURINV_SNAPSHOT_S`는 생성 스크립트 없음(❌, `SCM_DEV` 복사본만 존재)
- **수정 시**: 폰트/문구/레이아웃 → `templates/inventory.html` / 데이터·로직 → `apis/api_inventory.py` + `queries/inventory_queries.py`

---

## 5. Order (레거시) — `/order`

- **라우트**: `apis/web.py` `order_page()` (주석: "Order (M_SO_LINE) 주문 KPI 분석")
- **템플릿**: [templates/order.html](../templates/order.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_select2_init.html`, `module/common_footer.html`
- **JS**: `common-popup.js`, `model-header-comp.js`, `ag-col-helpers.js`
- **호출 API**: `GET /api/order/currencies`,`/kpi`,`/raw`
- **처리 파일**: `apis/api_order.py`(`get_order_kpi`, `get_order_raw`) — `queries/order_queries.py` 사용 (Active Orders의 `active_orders_queries.py`와 **별도 쿼리 세트**)
- **조회 테이블**: BQ `M_SO_LINE`, `PRD_OLAP.D_NPT_MDL_NEW_MST`
- **원천 체인**: `M_SO_LINE`은 2번 화면과 동일 체인
- **레거시 판단 근거**: `/`(root) 기본 진입점이 `/active-orders`이고, `/active-orders`가 Flow/Inbound/Delivery/Hold/IOD/이슈/메일까지 포함하는 상위 기능 집합. `/order`는 KPI/Raw만 있는 구형 화면 — **기능적으로 `/active-orders`의 하위집합으로 판단되나, 완전 대체(비노출) 여부는 PG `d_menu_mst`의 실제 `use_yn` 값을 직접 확인해야 확정됨** (코드만으로는 100% 단정 불가)
- **수정 시**: 폰트/문구/레이아웃 → `templates/order.html` / 데이터·로직 → `apis/api_order.py`(`get_order_kpi`/`get_order_raw`) + `queries/order_queries.py`

---

## 6. Master Data — `/master-data` (6개 탭)

- **라우트**: `apis/web.py` `master_data_page()` — PG `d_menu_mst`에서 `menu_id='master-data'`의 서브탭 목록을 조회하고, 세션 `nav_menus[].allowed_pages`/`page_edits`로 탭별 노출·편집권한을 필터링
- **템플릿**: [templates/master_data.html](../templates/master_data.html) — 6개 탭이 한 페이지 안에서 JS로 전환(별도 URL 없음)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_footer.html`
- **JS**: `master_shared.js`(공통 CRUD/그리드/bulk-save) + 탭별 `master_billto.js`/`master_shipto.js`/`master_product.js`/`master_sales_target.js`/`master_sales_team.js`/`master_billto_biz.js`(컬럼 정의 담당), `ag-col-helpers.js`, `ag-xls-grid.js`(엑셀 내보내기)

| 탭 | API | 처리 함수 (`apis/api_master.py`) | 테이블 |
|---|---|---|---|
| Bill-To | `/api/master/billto`, `/billto/bulk-save` | `list_billto`, `bulk_save_billto` 등 | PG `d_billto_mst` |
| Ship-To | `/api/master/shipto`, `/shipto/bulk-save` | `list_shipto`, `bulk_save_shipto` 등 | PG `d_shipto_mst` |
| Product | `/api/master/product`, `/product/bulk-save` | `list_product`, `bulk_save_product` 등 | PG `d_product_mst` |
| Sales Target | `/api/master/sales-target(+currencies/biz-names/divisions)`, `/bulk-save` | `list_sales_target`, `bulk_save_sales_target` | PG `d_sales_target_mst` |
| Sales Team | `/api/master/sales-team`, `/bulk-save` | `list_sales_team`, `bulk_save_sales_team` | PG `d_sales_team_mst` |
| Bill-To Biz | `/api/master/billto-biz(+product-groups/billto-list)`, `/bulk-save` | `list_billto_biz`, `bulk_save_billto_biz` | PG `d_billto_biz_mst` |

- **원천 체인**: 6개 탭 전부 PostgreSQL 앱 운영 DB(사람이 직접 CRUD), BigQuery/원천과 무관 — **데이터가 이상하면 BigQuery가 아니라 PG의 해당 `d_*_mst`를 바로 확인**
- **수정 시**: 폰트/문구/탭전환 UI → `templates/master_data.html` / 탭별 컬럼 라벨·너비·에디터 → 탭별 `static/js/master_*.js` / 공통 그리드 동작·저장버튼·엑셀 → `static/js/master_shared.js`,`ag-xls-grid.js` / 탭 노출·편집권한 → `apis/web.py`(`master_data_page`) + PG `d_menu_mst` / 실제 저장 로직 → `apis/api_master.py`

---

## 7. Users — `/users`

- **라우트**: `apis/web.py` `users_page()`
- **템플릿**: [templates/users.html](../templates/users.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_footer.html`
- **JS**: `common-popup.js` (별도 users 전용 js 없음)
- **호출 API**: `GET /api/users/types`,`/api/users`, `POST/PUT/DELETE /api/users(/{uid})`, `POST /api/users/{uid}/reset-password`,`/unlock`, `GET /api/access-requests`, `POST /api/access-requests/{id}/approve`,`/reject`, `GET /api/access-requests/pending-count`
- **처리 파일**: [apis/api_user.py](../apis/api_user.py)(계정 CRUD), [apis/api_access_request.py](../apis/api_access_request.py)(승인/반려 — 로그인 화면의 `submit`과 달리 이 4개는 실제로 `access_req_bp`에 있음, 확인됨)
- **조회 테이블**: PG `d_user_mst`, `d_user_type_mst`, `d_user_access_request`
- **원천 체인**: 없음 (PG 전용)
- **수정 시**: 폰트/문구/레이아웃 → `templates/users.html` / 계정 생성·잠금해제·승인 로직 → `apis/api_user.py`, `apis/api_access_request.py`

---

## 8. System Config — `/system-config`

- **라우트**: `apis/web.py` `system_config_page()`
- **템플릿**: [templates/system_config.html](../templates/system_config.html)
  include: `module/common_navbar.html`, `module/common_footer.html` (법인 셀렉터 include 없음 — 시스템 설정 화면 특성상)
- **JS**: `common-popup.js`, `ag-col-helpers.js`
- **호출 API**: `GET/PUT/POST/DELETE /api/sysconfig/menu*`, `/usertype*`, `/subsdr*` (탭 전환 시 동일 패턴의 동적 엔드포인트)
- **처리 파일**: [apis/api_system_config.py](../apis/api_system_config.py)
- **조회 테이블**: PG `d_menu_mst`, `d_user_type_mst`, `d_subsdr_mst`
- **원천 체인**: 없음(PG 전용). 단 `d_subsdr_mst`는 BQ `D_SUBSDR_MST`/`REF_D_SUBSDR_MST`의 PG측 원본으로 추정 — 다른 화면의 법인 관련 BQ 데이터가 이상하면 이 탭에서 법인 설정부터 확인
- **수정 시**: 폰트/문구/레이아웃 → `templates/system_config.html` / 데이터·로직 → `apis/api_system_config.py`

---

## 9. Issues — `/issues`

- **라우트**: `apis/web.py` `issues_page()`
- **템플릿**: [templates/issues.html](../templates/issues.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_issue_modal.html(_styles)`, `module/common_footer.html`
- **JS**: `common-popup.js` (상세/댓글/필드수정 로직은 `module/common_issue_modal.html` 내부 인라인 JS — Active Orders와 공유되는 컴포넌트)
- **호출 API**: `GET /api/issues?tab=...`, `GET /api/issues/{id}`, `PATCH /api/issues/{id}`,`/update-field`, `POST /api/issues/{id}/comments`, `GET /api/issues/users`
- **처리 파일**: [apis/api_issue.py](../apis/api_issue.py)
- **조회 테이블**: PG `d_issue_mst`, `d_issue_order`, `d_issue_comment`, `d_user_mst`. 상세에서 연결 오더 표시 시 BQ `M_SO_LINE`도 조회
- **원천 체인**: 이슈 자체는 PG 전용. 연결 오더 조회 시에만 `M_SO_LINE`(2번 화면과 동일 체인)
- **⚠️ 참고**: `get_issue()`가 SQL 문자열 결합을 쓰는 부분 있음 — [deploy-flow.md](deploy-flow.md) 주의사항 표에 이미 기록됨
- **수정 시**: 폰트/문구/레이아웃(목록) → `templates/issues.html` / 상세 모달(Active Orders와 공유, 여기 고치면 두 화면 다 영향) → `templates/module/common_issue_modal.html` / 데이터·로직 → `apis/api_issue.py`

---

## 10. Web Stats — `/web-stats`

- **라우트**: `apis/web.py` `web_stats_page()` (관리자 전용)
- **템플릿**: [templates/web_stats.html](../templates/web_stats.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_footer.html`
- **JS**: `common-popup.js`
- **호출 API**: `GET /api/web-log/stats`,`/detail`,`/months`
- **처리 파일**: [apis/api_web_log.py](../apis/api_web_log.py)
- **조회 테이블**: PG `m_web_log` (다른 화면들이 `POST /api/web-log/pageview`,`/action`으로 이 테이블에 적재)
- **원천 체인**: 없음(PG 전용, 앱 자체 로그)
- **수정 시**: 폰트/문구/레이아웃 → `templates/web_stats.html` / 데이터·로직 → `apis/api_web_log.py`

---

## 11. Glossary — `/glossary`

- **라우트**: `apis/web.py` `glossary_page()`
- **템플릿**: [templates/glossary.html](../templates/glossary.html)
  include: `module/common_navbar.html`, `module/common_global_legal_entity.html`, `module/common_footer.html`
- **JS**: `common-popup.js`만 로드. 검색창은 순수 클라이언트 텍스트 필터링(`row.textContent.toLowerCase().includes(query)`) — **API 호출 없음, 확인됨**
- **호출 API**: 없음
- **조회 테이블**: 없음 (용어 목록이 템플릿에 하드코딩되어 있는 것으로 판단됨, 런타임 DB 조회 없음)
- **수정 시**: 폰트/문구/레이아웃/용어 내용 전부 → `templates/glossary.html` 한 파일만 수정하면 됨

---

## 12. Mail Download 안내 페이지 — `/mail-download/eta` (mail_file_bp, web_bp 아님)

- **라우트**: [apis/api_mail_file.py](../apis/api_mail_file.py) `mail_download_page()` — `?le=`(법인)/`?ppt=`(기준일) 쿼리로 파일명/다운로드 카운트 계산 후 렌더
- **템플릿**: [templates/mail_download.html](../templates/mail_download.html)
- **JS**: 별도 파일 없음(인라인). 다운로드는 `GET /api/mail-file/eta/download?...`로 브라우저가 직접 이동하는 링크 방식으로 추정(라우트가 `send_file`을 반환하는 구조 근거) — **100% 확정은 아님, 필요 시 템플릿 직접 재확인 권장**
- **호출 API**: `GET /api/mail-file/eta/download?le=...&ppt=...`
- **처리 파일**: `apis/api_mail_file.py`(`mail_file_download`) — `queries/eta_change_queries.py`의 `ETA_CHANGE_QUERY`를 그때그때 재실행해 엑셀 생성(별도 저장 없음), 다운로드 시 PG `m_web_log`에 `MAIL_DOWNLOAD` 기록
- **조회 테이블**: BQ `M_SEA_SHIPMENT_INFO`, `M_PO_TRACKING`, `REF_D_PRODUCT_MST`, `PRD_OLAP.D_NPT_MDL_NEW_MST` / PG `m_web_log`
- **원천 체인**: `M_SEA_SHIPMENT_INFO` ← [liw.job_M_SEA_SHIPMENT_INFO.sql](../db_batch/liw.job_M_SEA_SHIPMENT_INFO.sql) ← `V_L0NEDW_ZSLEI1021`. `M_PO_TRACKING`은 생성 스크립트 없음(❌)
- **연계**: 이 페이지로 유입되는 다이제스트 메일 자체는 [jobs/eta_digest_email.py](../jobs/eta_digest_email.py)가 발송 — 메일 문구/포맷을 바꾸려면 이 파일도 함께 확인
- **수정 시**: 폰트/문구/레이아웃 → `templates/mail_download.html` / 엑셀 생성 컬럼·포맷 → `apis/api_mail_file.py` + `queries/eta_change_queries.py` + `jobs/eta_digest_email.py`(`build_excel_bytes`)

---

## 부록: 여러 화면이 공유하는 공통 모듈

| 모듈 | 공유하는 화면 | 수정 시 영향 범위 |
|---|---|---|
| `templates/module/common_navbar.html` | 로그인 제외 전 화면 | 상단 메뉴/로그아웃/비밀번호변경 UI 전체 동시 변경. API: `/api/auth/{logout,me,change-password,preferences}` |
| `templates/module/common_global_legal_entity.html` | Active Orders/PO/Inventory/Order/Master Data/Issues/Web Stats | 법인 선택 셀렉터 전체 동시 변경 |
| `templates/module/common_issue_modal.html`(+`_styles`) | Active Orders, Issues | 이슈 상세 모달 전체 동시 변경 |
| `templates/module/container_detail_modal.html` + `static/js/container-detail-modal.js` | Active Orders, Active PO | 컨테이너 상세 모달 동시 변경, API는 `apis/api_order.py`(`container-detail`,`container-detail-lines`) 공용, BQ `M_PO_TRACKING` 조회 |
| `templates/module/order_detail_modal.html`, `customer_orders_modal.html` + `static/js/order-detail-modal.js` | Active Orders 전용 | 별도 API 호출 없이 `active-raw`로 이미 받은 데이터를 클라이언트에서 필터링해 표시 |
| `static/js/ag-col-helpers.js`, `ag-xls-grid.js`, `model-header-comp.js` | 여러 그리드 화면 | 숫자 포맷/컬럼 헤더 스타일/엑셀 내보내기 방식 전체 동시 변경 |
| `static/js/common-popup.js` | 전 화면 | alert/confirm 대체 UI 전체 동시 변경 |

---

## 명확히 확인 못한 지점 (추측 대신 명시)

1. **`templates/mail_download.html`의 다운로드 버튼이 fetch인지 단순 링크인지**: 라우트 구조(`send_file` 반환)로 미루어 단순 `<a href>` 링크로 추정했으나, 템플릿 파일을 직접 열어 100% 확정하지는 않았습니다.
2. **`/order`가 완전히 비활성화된 레거시인지**: 코드 구조상 `/active-orders`의 하위집합으로 보이지만, 실제 노출 여부는 PG `d_menu_mst`의 `use_yn` 값을 DB에서 직접 조회해야 확정됩니다.

---
*화면/파일 구조가 바뀌면 이 문서도 함께 갱신 필요.*
