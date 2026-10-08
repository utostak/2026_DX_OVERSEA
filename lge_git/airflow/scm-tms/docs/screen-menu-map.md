# LIW 메뉴바 기준 화면-쿼리-테이블 맵

[screen-map.md](screen-map.md)는 URL/라우트 기준으로 화면을 나열한 문서고, 이 문서는 **실제로 화면 상단에 보이는 메뉴바 탭 순서**를 기준으로, 그 안의 카드/탭 하나하나가 어떤 fetch → API 함수 → 쿼리 → 테이블로 이어지는지까지 추적한 문서입니다. 테이블명은 [db-map.md](db-map.md)와 동일 표기(`project.dataset.table`)를 씁니다.

메뉴바는 `templates/module/common_navbar.html`이 PG `d_menu_mst`(세션의 `nav_menus`)를 순회해서 동적으로 그리므로, 실제 노출되는 메뉴/순서는 로그인한 사용자 유형에 따라 달라질 수 있습니다. 아래는 스크린샷 기준(로고 옆부터) + 스크롤로 넘어가는 나머지 메뉴, 그리고 우측 별도 배치된 Glossary입니다.

```
[LIW] | Active Order Management | Active PO | Inventory | User Management | Master Data | (스크롤 →) System Config | Issues | Web Stats   ...... Glossary(우측 별도)
```

---

## 1. Active Order Management → `/active-orders`

- **초기 로드**: `$(document).ready()` → `onLegalEntityChange()` → `loadAll()`([active_orders.html:2474](../templates/active_orders.html#L2474))가 아래 5개를 **동시(병렬)** 호출

| 카드/화면 요소 | fetch 호출 | 렌더 함수 | API 핸들러 | 쿼리 | 테이블 |
|---|---|---|---|---|---|
| Order/Shipping Stage 퍼널 카드 | `/api/order/active-flow` | `renderSysFlow()` | `api_order.py:127 get_order_active_flow()` | `QUERY_ORDER_ACTIVE_FLOW`(:53) | `SCM_OLAP.M_SO_LINE` |
| Delivery Stage 카드 | `/api/order/active-delivery` | `renderDelivery()` | `api_order.py:160 get_order_active_delivery()` | `QUERY_ORDER_DELIVERY_FLOW` | `SCM_OLAP.M_SO_LINE` |
| Inbound Stage(Back Order) 카드 | `/api/order/active-inbound` | `renderInbound()` | `api_order.py:197 get_order_active_inbound()` | `QUERY_ORDER_INBOUND_FLOW` | `SCM_OLAP.M_SO_LINE_BACK` |
| Hold Detail 접이식 영역 | `/api/order/active-hold` | `renderHoldDetail()` | `api_order.py:527 get_order_active_hold()` | `QUERY_ORDER_HOLD_DETAIL` | `SCM_OLAP.M_SO_LINE` |
| 하단 "Active Orders(Open)" 그리드 탭(원본) | `/api/order/active-raw` | `activeGridApi.setGridOption` | `api_order.py:518 get_order_active_raw()` | `QUERY_ORDER_ACTIVE_RAW`(:418, "현재 오픈 주문 전체") | `SCM_OLAP.M_SO_LINE` |
| 컨테이너 상세 모달(그리드 셀 클릭) | `/api/order/container-detail`,`/container-detail-lines` | `container-detail-modal.js` | `api_order.py`(공유) | 전용 쿼리 | `SCM_OLAP.M_PO_TRACKING` |
| 오더 상세/고객오더 모달 | 없음 — 이미 받은 `active-raw` 데이터를 클라이언트에서 필터링만 | `order-detail-modal.js` | — | — | — |

⚠️ `QUERY_ORDER_TARGET_USD`(`@base_ym6`)는 import만 되고 실제 호출 없음 — 죽은 코드.

---

## 2. Active PO → `/active-po`

- **초기 로드**: `$(document).ready()`([active_po.html:486](../templates/active_po.html#L486)) → `initGlobalLegalEntity(loadAll)` → `loadAll()`([active_po.html:418](../templates/active_po.html#L418))

| 카드/화면 요소 | fetch 호출 | 렌더 함수 | API 핸들러 | 쿼리 | 테이블 |
|---|---|---|---|---|---|
| Data as of 배지 | `/api/po/data-timestamp` | `loadDataTimestamp()`(:388) | `api_po.py:57 get_po_data_timestamp()` | `QUERY_PO_DATA_TIMESTAMP`([po_queries.py:147](../queries/po_queries.py#L147)) | `SCM_OLAP.M_PO_TRACKING` |
| PO Tracking Stage 카드(4-Step 퍼널) | `/api/po/active-flow` | `renderPoFlow()`(:305) | `api_po.py:37 get_po_active_flow()` | `QUERY_PO_ACTIVE_FLOW`([po_queries.py:13](../queries/po_queries.py#L13)) | `SCM_OLAP.M_PO_TRACKING` |
| 하단 "Active PO" 그리드 + 행수 배지 | `/api/po/active-raw` | `poGridApi.setGridOption`(:436) | `api_po.py:47 get_po_active_raw()` | `QUERY_PO_ACTIVE_RAW`([po_queries.py:50](../queries/po_queries.py#L50), ETA 이력 서브쿼리로 `M_SEA_SHIPMENT_INFO` 조인) | `SCM_OLAP.M_PO_TRACKING` + `M_SEA_SHIPMENT_INFO` |
| 컨테이너 상세 모달 | `/api/order/container-detail`,`/container-detail-lines` | `container-detail-modal.js`(Active Orders와 공유) | `api_order.py` | 전용 쿼리 | `SCM_OLAP.M_PO_TRACKING` |

⚠️ `?change_yn=Y/N` URL 파라미터는 새 API 호출 없이 이미 로드된 그리드를 클라이언트에서만 필터링(`applyUrlFilterParams()`, :470).

---

## 3. Inventory → `/inventory`

- **초기 로드**: `$(document).ready()`([inventory.html:218](../templates/inventory.html#L218)) → `initGlobalLegalEntity(loadAll)` → `loadAll()`([inventory.html:192](../templates/inventory.html#L192)) — 3종 카드로 가장 단순한 화면

| 카드/화면 요소 | fetch 호출 | 렌더 함수 | API 핸들러 | 쿼리 | 테이블 |
|---|---|---|---|---|---|
| Data as of 배지 | `/api/inventory/data-timestamp` | `loadDataTimestamp()`(:156) | `api_inventory.py:54 get_data_timestamp()` | `QUERY_INV_DATA_TIMESTAMP`([inventory_queries.py:75](../queries/inventory_queries.py#L75)) | `SCM_OLAP.M_CURINV_SNAPSHOT_S` |
| KPI 카드 4종(Snapshot Date/Models/Onhand Qty/Available Qty) | `/api/inventory/current-summary` | `renderSummary()`(:144) | `api_inventory.py:34 get_current_summary()` | `QUERY_INV_CURRENT_SUMMARY`([inventory_queries.py:6](../queries/inventory_queries.py#L6)) | `SCM_OLAP.M_CURINV_SNAPSHOT_S`(+ `PRD_OLAP.D_NPT_MDL_NEW_MST` 모델조인) |
| "Inventory Detail" 그리드 + 행수 배지 | `/api/inventory/current-raw` | `invGridApi.setGridOption`(:211) | `api_inventory.py:44 get_current_raw()` | `QUERY_INV_CURRENT_RAW`([inventory_queries.py:29](../queries/inventory_queries.py#L29)) | `SCM_OLAP.M_CURINV_SNAPSHOT_S`(+ `PRD_OLAP.D_NPT_MDL_NEW_MST`) |

---

## 4. User Management → `/users`

⚠️ 이 화면은 Active Orders/PO/Inventory처럼 하나로 묶인 `loadAll()`이 없고, 초기화부([users.html:648-650](../templates/users.html#L648))에서 3개 함수가 개별 호출됩니다.

| 화면 요소 | fetch 호출 | 렌더 함수 | API 핸들러 | 테이블 |
|---|---|---|---|---|
| 유저 목록 그리드 + Entity 라벨 | `/api/users?legal_entity=…`(:360) | `loadUsers()`(:355) | `api_user.py:93 list_users()` (인라인 SQL :101-114) | PG `d_user_mst` ⋈ `d_user_type_mst` |
| Add/Edit 모달의 Role 드롭다운 | `/api/users/types`(:236) | `loadUserTypes()`(:234) | `api_user.py:26 get_user_types()` (:33-62, 계층적 `child_user_types` 필터) | PG `d_user_type_mst` |
| Add/Edit/Delete/Reset PW/Unlock 버튼 | `POST/PUT/DELETE /api/users(/{uid})`, `/reset-password`, `/unlock`(:453,458,483,499,514) | 각 액션 함수 | `api_user.py`: `create_user`(146)/`update_user`(182)/`delete_user`(227, soft-delete)/`reset_password`(249)/`unlock_user`(273) | PG `d_user_mst` |
| "Access Requests" 배지 | `/api/access-requests/pending-count`(:618) | `loadPendingCount()` | `api_access_request.py:158 pending_count()` | PG `d_user_access_request` |
| Access Requests 모달 목록 | `/api/access-requests?status=…`(:551) | `loadRequests()`(:545) | `api_access_request.py:91 list_requests()` | PG `d_user_access_request` |
| 승인/반려 버튼 | `POST /api/access-requests/{id}/approve`,`/reject`(:586,603) | 인라인 | `api_access_request.py:189 approve_request()`(승인 시 `d_user_mst` insert 포함), `:257 reject_request()` | PG `d_user_mst` + `d_user_access_request` |

---

## 5. Master Data → `/master-data` (6개 탭, 탭 단위 lazy-load)

⚠️ 전체를 한 번에 부르는 함수 없음 — 첫 활성 탭(기본 Bill-To)만 로드되고, 나머지는 **탭 클릭 시점에만** 로드됩니다(`switchTab()`, [master_shared.js:743](../static/js/master_shared.js#L743), `_loadedTabs` 캐시로 재방문 시 재조회 안 함).

| 탭(UI 라벨) | fetch | API 핸들러(`apis/api_master.py`) | PG 테이블 |
|---|---|---|---|
| **Bill-To** | `/api/master/billto?legal_entity=…` | `:137 list_billto()` | `d_billto_mst` |
| **Ship-To** | `/api/master/shipto?legal_entity=…` | `:245 list_shipto()` | `d_shipto_mst` |
| **Product** | `/api/master/product?legal_entity=…` | `:355 list_product()` | `d_product_mst` |
| **Sales Team** | `/api/master/sales-team?legal_entity=…` | `:605 list_sales_team()` | `d_sales_team_mst` |
| **Sales Target** | `/api/master/sales-target?...`(+보조 `/currencies`,`/biz-names`,`/divisions`) | `:513 list_sales_target()` | `d_sales_target_mst` |
| **Bill-To Biz** | `/api/master/billto-biz?...`(+보조 `/product-groups`,`/billto-list`) | `:721 list_billto_biz()` | `d_billto_biz_mst`(보조조회는 `d_product_mst`,`d_billto_mst` 참조) |

각 탭 "Save" 버튼 → `POST /api/master/{tab}/bulk-save` → `_bulk_save()` 공통 헬퍼(`api_master.py:89`, DELETE+INSERT 방식)로 동일 테이블 반영. 탭 노출/편집권한은 `apis/web.py:35-42 master_data_page()`가 PG `d_menu_mst` + 세션 `allowed_pages`로 필터링.

---

## 6. (스크롤) System Config → `/system-config` (3개 탭, 탭 단위 lazy-load)

Master Data와 동일한 lazy-load 패턴. 기본 탭(Menu)만 `DOMContentLoaded`에서 자동 로드([system_config.html:877](../templates/system_config.html#L877)).

| 탭(UI 라벨) | fetch | API 핸들러(`apis/api_system_config.py`) | PG 테이블 |
|---|---|---|---|
| **Menu**(:98) | `/api/sysconfig/menu` | `:54 list_menu()` | `d_menu_mst` |
| **User Type**(:102) | `/api/sysconfig/usertype` | `:140 list_usertype()` | `d_user_type_mst` |
| **Subsidiary**(:106) | `/api/sysconfig/subsdr` | `:218 list_subsdr()` | `d_subsdr_mst` |

각 탭 인라인 편집(Add/Update/Delete)은 `/api/sysconfig/{tab}`(POST/PUT/DELETE)이 처리, `api_system_config.py` 안에 탭당 `create_*`/`update_*`/`delete_*` 3세트.

---

## 7. (스크롤) Issues → `/issues`

⚠️ 단일 `loadAll()` 없음 — `IssueModal.init()` + `loadList()` + `refreshCounts()` 3개 개별 호출([issues.html:104-179](../templates/issues.html#L104)). 상단 4개 탭(**All/My Inbox/My Outbox/Closed**)은 페이지 이동 없이 클라이언트 상태(`curTab`)만 바꿔 동일 `loadList()`를 재호출.

| 화면 요소 | fetch | API 핸들러 | 테이블 |
|---|---|---|---|
| 이슈 리스트(탭/검색 변경 시 재호출) | `/api/issues?tab={all\|inbox\|outbox\|closed}&q=…`(:131) | `api_issue.py:444 list_issues()` (탭별 WHERE 분기, :493-514) | PG `d_issue_mst`(+검색어 있을 때 `d_issue_order` EXISTS) |
| Inbox/Outbox 카운트 배지 | `/api/issues?tab=inbox`,`tab=outbox`(:166, 병렬) | 위와 동일 함수 | PG `d_issue_mst` |
| All 카운트 | 없음 — `loadList()` 응답 길이 그대로 표시 | — | — |
| 이슈 상세 모달 | `/api/issues/{id}`([common_issue_modal.html:94](../templates/module/common_issue_modal.html#L94)) | `api_issue.py:531 get_issue()` (마스터:537, 연결오더:548, 댓글:574) | PG `d_issue_mst`+`d_issue_order`+`d_issue_comment` **+ 연결오더 진행단계 표시 시에만** BQ `SCM_OLAP.M_SO_LINE`(:558) |
| 댓글/필드수정/담당자검색 | `/comments`(POST),`/update-field`(PATCH),`/api/issues/users`(GET) | `add_comment`(673),`update_issue_field`(714),`get_issue_users`(237) | PG `d_issue_comment`,`d_issue_mst`,`d_user_mst` |

---

## 8. (스크롤) Web Stats → `/web-stats`

- **초기 로드**: `initGlobalLegalEntity(async () => { await loadMonths(); await loadStats(); })`([web_stats.html:558](../templates/web_stats.html#L558))

| 카드/화면 요소 | fetch | API 핸들러 | 테이블 |
|---|---|---|---|
| Month 드롭다운 | ⚠️ **API 호출 없음** — `loadMonths()`(:428)가 `new Date()`로 클라이언트에서 직접 월 목록 생성. `apis/api_web_log.py:119 get_months()`(PG `m_web_log`에서 `DISTINCT log_ym` 조회) 엔드포인트는 정의만 되어있고 이 화면에서 미사용 | (미사용) | (미사용) |
| 요약 카드 7종 | 별도 fetch 없음 — 아래 `/stats` 응답을 `loadStats()`(:453)가 클라이언트에서 집계 | (아래와 동일) | (아래와 동일) |
| 집계 피벗 그리드 | `/api/web-log/stats?log_ym={ym}`(:459) | `api_web_log.py:143 get_stats()` | PG `m_web_log` |
| 상세 로그 패널 | `/api/web-log/detail?…`(:496) | `api_web_log.py:189 get_detail()` | PG `m_web_log` |
| (적재측) 다른 화면들의 페이지뷰/액션 로그 | `POST /api/web-log/pageview`,`/action` | `log_pageview()`(24),`log_action()`(69) | PG `m_web_log` |

⚠️ `/api/web-log/months`는 죽은 엔드포인트로 보임(정의는 있으나 호출하는 곳 없음) — screen-map.md 요약표에 있던 표기 정정 필요.

---

## 9. Glossary (우측 별도 배치, 스크롤 메뉴 아님) → `/glossary`

API 호출 없음, 순수 정적 페이지(검색은 클라이언트 텍스트 필터링). 자세한 내용은 [screen-map.md §11](screen-map.md) 참조.

---

## 요약: 화면별 "초기화 패턴" 한눈에

| 메뉴 | 패턴 |
|---|---|
| Active Order Management | 단일 `loadAll()` — 5개 fetch 병렬 |
| Active PO | 단일 `loadAll()` — Active Orders와 거의 동일 구조 |
| Inventory | 단일 `loadAll()` — 카드 3종, 가장 단순 |
| User Management | **개별 함수 3개** (묶인 loadAll 없음) |
| Master Data | **탭 단위 lazy-load** (6탭, 방문한 탭만 조회) |
| System Config | **탭 단위 lazy-load** (3탭, Master Data와 동일 패턴) |
| Issues | **개별 함수 3개** + 탭은 클라이언트 상태 전환만 |
| Web Stats | `loadMonths()`+`loadStats()` 순차, 요약카드는 클라이언트 집계 |

---
*메뉴 구성(`d_menu_mst`)이나 화면 로직이 바뀌면 이 문서도 함께 갱신 필요. 카드 단위 라벨/줄번호는 코드 변경 시 어긋날 수 있으니 대규모 리팩터링 후엔 재검증 권장.*
