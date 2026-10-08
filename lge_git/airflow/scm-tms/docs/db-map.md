# LIW (SCM-TMS) DB 맵 (원천~타겟 전체 계보, `프로젝트.데이터셋.테이블` 완전판)

[screen-map.md](screen-map.md)(화면 쪽 분석)와 이름/구조를 맞췄습니다. 모든 테이블/뷰는 `프로젝트.데이터셋.테이블`까지 풀어서 표기했고, 확정하지 못한 부분은 "unknown/추정"으로 명시했습니다. 파일별 상세는 `db_batch/`, `db/`의 **전체 라인을 직접 읽어 검증**했으며 위치(파일:줄)를 남겼습니다.

**핵심 카운트**
| 구분 | 개수 |
|---|---:|
| 확인된 GCP 프로젝트 | **3개** (`pjt-lge-oversea-sales-olap`, `pjt-lge-global-olap`, `pjt-lge-edl-ob`) + ⚠️ 미확정 1개(`pj-lge-edl`) |
| 진짜 상류 원천 뷰/테이블 (배치가 읽기만 함) | **28개** (프로젝트 불명 3개 포함) |
| 배치가 만드는 BigQuery 타겟 (SCM_OLAP, 중간 포함) | **12개** + SCM_DEV 미러 7개 |
| 앱(`queries/*.py`)이 직접 쿼리하는 최종 테이블 | **14개** |
| PostgreSQL 메타 테이블 | **15개** |

---

## 1. 확인된 GCP 프로젝트

| 프로젝트 ID | 용도 | 근거 |
|---|---|---|
| `pjt-lge-oversea-sales-olap` | 이 앱의 메인 BigQuery 프로젝트 (SCM_OLAP/SCM_DEV/PRD_OLAP 데이터셋) | `config/bigquery.py` 인증 대상, 대부분 쿼리 파일의 backtick 명시 |
| `pjt-lge-edl-ob` | EDL(Enterprise Data Lake) 원천 미러 — 데이터셋 `OB_00030`, `OB_00069` | `queries/*.py`, `db_batch/*.sql`의 backtick 명시 다수 |
| `pjt-lge-global-olap` | NERP 적재용 별도 프로젝트 — 데이터셋 `L1_SCM_`, `L1_COMM` | `db_batch/TRSCM__NERP_SO_LINE_DW_DO_S.sp:6` 헤더 주석, `:402`/`:1032` 본문에 명시적 backtick 확인 |
| `pj-lge-edl` ⚠️ | `OB_00069` 데이터셋의 뷰 3개에서 발견 — `pjt-lge-edl-ob`와 철자가 다름(t 없음, `-ob` 없음) | `db_batch/TRSCM__NERP_SO_LINE_DW_DO_S.sp:384,409,412` (및 대응 라인 1014,1039,1042). **오타인지 실제 별도 프로젝트인지 미확정 — unknown, 원 개발자 확인 필요** |

---

## 2. 배치 파이프라인 상세 (파일별, 전체 라인 읽어서 검증)

### 2-1. `db_batch/liw.job_M_SO_LINE.sql` (454줄)
- **TARGET**: `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE `` — 1행 CREATE OR REPLACE, 211행 INSERT INTO 추가 적재 (전반부는 T01/T03 기반, 후반부는 T11/T13 기반인 **이중 파이프라인 구조**)
- **SOURCE**: `SCM_OLAP.M_SO_LINE_T01`(146행), `SCM_OLAP.M_SO_LINE_T03`(147행, T02 파일 내부 산출물), `SCM_OLAP.D_SO_REM_DAYS`(202,205,445,448행), `SCM_OLAP.M_SO_LINE_T11`(413행), `SCM_OLAP.M_SO_LINE_T13`(414행, T12 파일 내부 산출물) — 전부 `pjt-lge-oversea-sales-olap` 프로젝트

### 2-2. `db_batch/liw.job_M_SO_LINE_BACK_PO_MAP.sql` (420줄, CREATE OR REPLACE 2개)
- **TARGET1**: `SCM_OLAP.M_SO_LINE_BACK_PO_MAP`(22행) ← `SCM_OLAP.M_SO_LINE`(40행), `SCM_OLAP.M_CURINV_SNAPSHOT_S`(57행), `SCM_OLAP.TB_SCM_PO_TRACKING`(100행)
- **TARGET2**: `SCM_OLAP.M_SO_LINE_BACK`(226행) ← `SCM_OLAP.M_SO_LINE`(261행), `SCM_OLAP.M_CURINV_SNAPSHOT_S`(274행), `SCM_OLAP.TB_SCM_PO_TRACKING`(290행), `SCM_OLAP.M_SO_LINE_BACK_PO_MAP`(338행, 파일 내부 TARGET1 재사용)

### 2-3. `db_batch/liw.job_M_SEA_SHIPMENT_INFO.sql` (70줄)
- **TARGET**: `SCM_OLAP.M_SEA_SHIPMENT_INFO` — 당일 파티션 DELETE(18행) 후 INSERT(23행)
- **SOURCE**: `` `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSLEI1021 ``(52행), `` `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST ``(53행)
- **⚠️ 자기참조(증분)**: 55행에서 자기 자신(전일 파티션, 별칭 `BF`)을 LEFT JOIN해 ETA 변경여부(`CHANGE_YN`)/변경일수(`DFF_DAYS`) 계산 — 이 파일 세트에서 유일한 스냅샷 비교형 증분 로직

### 2-4. `db_batch/liw.job_D_SO_REM_DAYS.sql` (61줄)
- **TARGET**: `SCM_OLAP.D_SO_REM_DAYS`(1행) ← `SCM_OLAP.M_SO_LINE`(25,55행, UNION ALL 양쪽 동일 소스)
- **⚠️ 순환 의존**: `M_SO_LINE`(§2-1)이 `D_SO_REM_DAYS`를 입력으로 쓰고, `D_SO_REM_DAYS`도 `M_SO_LINE`을 입력으로 씀 → 두 배치는 정해진 순서로 실행되어야 함(순서 정의는 이 저장소 밖, unknown)

### 2-5. `db_batch/liw.job_M_SO_LINE_T01.sql` (200줄)
- **TARGET**: `SCM_OLAP.M_SO_LINE_T01`(1행)
- **SOURCE**: `` `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S ``(3,4,7,13행), `PRD_OLAP.D_SUBSDR_MST`(138행), `SCM_OLAP.D_USD_CONVERSION_RATE_MST`(140행), `PRD_OLAP.D_NPT_MDL_NEW_MST`(143행), `` `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V ``(169,182행 — deep CTE 내부)

### 2-6. `db_batch/liw.job_M_SO_LINE_T02.sql` (189줄, CREATE OR REPLACE 2개)
- **TARGET1**: `SCM_OLAP.M_SO_LINE_T02`(1행) ← `V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`(16행), `V_L0TMS__TB_GTM_ORDERS_GERP_R_IF_OS`(17행), `V_L0TMS__LD_LEG_DETL_T_OS`(36행), `V_L0TMS__LD_LEG_T_OS`(37행), `V_L0TMS__TB_GTM_LOAD_OS`(54행), `SCM_OLAP.TB_GTM_ORDER_OLAP_S_IF_OS`(59행), `V_L0TMS__TDR_REQ_T_OS`(66행), `V_L0TMS__TB_GTM_IOD_OS`(89행) — `V_L0TMS__*`는 전부 `` `pjt-lge-edl-ob`.OB_00030 ``
- **TARGET2**: `SCM_OLAP.M_SO_LINE_T03`(136행, **파일 내부에서 별도 CREATE — T03은 별도 파일 아님, 확인됨**) ← `SCM_OLAP.M_SO_LINE_T02`(176행, 파일 내부 산출물)

### 2-7. `db_batch/liw.job_M_SO_LINE_T11.sql` (700줄, 1~443행은 컬럼설명 주석)
- **TARGET**: `SCM_OLAP.M_SO_LINE_T11`(445행)
- **SOURCE**: `` `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDS0226 ``(525행, 메인), `V_L0NEDW_ZSSDI1002`(551행, deep CTE), `PRD_OLAP.D_SUBSDR_MST`(687행), `SCM_OLAP.D_USD_CONVERSION_RATE_MST`(692행), `PRD_OLAP.D_NPT_MDL_NEW_MST`(695행)

### 2-8. `db_batch/liw.job_M_SO_LINE_T12.sql` (175줄, CREATE OR REPLACE 2개)
- **TARGET1**: `SCM_OLAP.M_SO_LINE_T12`(1행) ← `SCM_OLAP.TB_GTM_ORDER_OLAP_S_IF_OS`(20행), `PRD_OLAP.D_SUBSDR_MST`(21행), `V_L0TMS__LD_LEG_DETL_T_OS`(42행), `V_L0TMS__LD_LEG_T_OS`(43행), `V_L0TMS__TB_GTM_LOAD_OS`(60행), `V_L0TMS__TDR_REQ_T_OS`(67행), `V_L0TMS__TB_GTM_IOD_OS`(90행)
- **TARGET2**: `SCM_OLAP.M_SO_LINE_T13`(134행, **파일 내부에서 별도 CREATE — T13은 별도 파일 아님, 확인됨**) ← `SCM_OLAP.M_SO_LINE_T12`(169행, 파일 내부 산출물)

### 2-9. `db_batch/TRSCM__NERP_SO_LINE_DW_DO_S.sp` (1330줄, BigQuery Stored Procedure)
- **TARGET**: 본문 DELETE/INSERT(73,100,693,729행)엔 프로젝트 접두사 없이 `L1_SCM_.TRSCM__NERP_SO_LINE_DW_DO_S`로만 기술. **헤더 주석 6행**에 `` `pjt-lge-global-olap.L1_SCM_.TRSCM__NERP_SO_LINE_DW_DO_S` `` 완전정규화 표기 있음 → 이 근거로 `pjt-lge-global-olap`로 표기하되, 본문 DML 자체엔 미명시(추정 표시 유지)
- **SOURCE** (backtick으로 완전정규화 확인됨):
  - `pjt-lge-edl-ob.OB_00069`: `V_L0NEDW_ZSSDI1018`(69,375행), `V_L0MDM3_V_EDL_MDMS_BP_CUST_MST_SND_INF_ALL`(228,857행), `V_L0NEDW_ZSSDI1008_X2076054_60114`(230,859행), `V_L0MDM3_V_EDL_MDMS3_COMPANY_MASTER`(231,860행), `V_L0NEDW_ZFGLA0012_X2076054_57768`(394,1024행), `V_L0NEDW_ZSSDI1002_X2076054_59978`(436,1066행), `V_L0NEDW_ZSSDI1017`(697,1004행)
  - `pj-lge-edl.OB_00069` ⚠️: `V_L0GSCP_IFS_VD_PRODUCT_GROUP_MAP`(384,1014행), `V_L0ILDB_XXWOMS_SMS_GRADE_MST`(409,1039행), `V_L0ILDB_XXWOMS_PRD_CONTRI_PER_TB_230927_14883`(412,1042행)
  - `pjt-lge-global-olap.L1_COMM`: `TMCOMM_SUBSDR_M`(402,1032행)
- **프로젝트 불명(dataset.table만 기술, unknown)**: `L1_COMM.TL_L1_SCM__LOG`(41행), `L1_SCM_.TMSCM__GCSP_DIV_M`(392,1022행), `L1_SCM_.TRSCM__SO_LINE_DW_AMOUNT_EXCEPT_M`(401,1031행) — 같은 파일에서 `L1_COMM`/`L1_SCM_`가 `pjt-lge-global-olap`로 명시된 사례가 있어 문맥상 추정되나, 이 3개 자체는 확정 아님

### 2-10. `db_batch/dev_copy.sql` (60줄) — SCM_OLAP → SCM_DEV 미러 (dev 환경 새로고침용, 원본 생성 로직 아님)
전부 `pjt-lge-oversea-sales-olap` 프로젝트 내:
`SCM_DEV.D_USD_CONVERSION_RATE_MST`←`SCM_OLAP.D_USD_CONVERSION_RATE_MST`, `SCM_DEV.M_SO_LINE_BACK_PO_MAP`←`SCM_OLAP.M_SO_LINE_BACK_PO_MAP`, `SCM_DEV.M_SO_LINE_BACK`←`SCM_OLAP.M_SO_LINE_BACK`, `SCM_DEV.M_SO_LINE`←`SCM_OLAP.M_SO_LINE`, `SCM_DEV.M_SO_LINE_INVOICE_NERP`←`SCM_OLAP.M_SO_LINE_INVOICE_NERP`(⚠️생성스크립트 unknown), `SCM_DEV.M_PO_TRACKING`←`SCM_OLAP.M_PO_TRACKING`(⚠️생성스크립트 unknown), `SCM_DEV.M_CURINV_SNAPSHOT_S`←`SCM_OLAP.M_CURINV_SNAPSHOT_S`

### 2-11. `db/M_SO_LINE.sql` (378줄) — ⚠️ **db_batch와 다른 별도/구버전 파이프라인으로 추정**
`db_batch/liw.job_M_SO_LINE.sql`(§2-1)과 **동일 타겟**(`SCM_OLAP.M_SO_LINE`)을 만들지만, T01/T03/T11/T13 체계를 쓰지 않고 자체 `M_SO_LINE_T` 단일 CTE + TMS 원본 뷰를 직접 JOIN하는 **완전히 다른 로직**. 어느 쪽이 실제 운영 중인지는 이 저장소만으로 확정 불가(unknown).
- **TARGET1**: `SCM_OLAP.M_SO_LINE_T`(2행) ← `V_L1SCM__TRSCM__SO_LINE_DW_S`(4,5,8,14행), `V_L1SALE_TMSALE_NERP_NDGS_SUBSDR_M`(23행)
- **TARGET2**: `SCM_OLAP.M_SO_LINE`(135행) ← `SCM_OLAP.M_SO_LINE_T`(280,307,319행, 파일 내부 산출물), `V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V`(305,318행), `V_L0TMS__TB_GTM_LOAD_OS`(347행), `V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`(349행), `V_L0TMS__LD_LEG_T_OS`(352행), `V_L0TMS__TDR_REQ_T_OS`(357행), `V_L0TMS__TB_GTM_CODE_MST_OS`(362행), `V_L0TMS__STAT_T_OS`(366행), `PRD_OLAP.D_FX_MM`(369행)

---

## 3. 전체 확정 SOURCE 목록 (이 파일 세트의 타겟이 아닌 진짜 상류 원천, project.dataset별 그룹)

**`pjt-lge-edl-ob`.`OB_00030`** (15개)
`V_L1SCM__TRSCM__SO_LINE_DW_S`, `V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V`, `V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`, `V_L0TMS__TB_GTM_ORDERS_GERP_R_IF_OS`, `V_L0TMS__LD_LEG_DETL_T_OS`, `V_L0TMS__LD_LEG_T_OS`, `V_L0TMS__TB_GTM_LOAD_OS`, `V_L0TMS__TDR_REQ_T_OS`, `V_L0TMS__TB_GTM_IOD_OS`, `V_L0NEDW_ZSSDS0226`, `V_L0NEDW_ZSSDI1002`, `V_L0NEDW_ZSLEI1021`, `V_L1SALE_TMSALE_NERP_NDGS_SUBSDR_M`, `V_L0TMS__TB_GTM_CODE_MST_OS`, `V_L0TMS__STAT_T_OS`

**`pjt-lge-edl-ob`.`OB_00069`** (7개)
`V_L0NEDW_ZSSDI1018`, `V_L0MDM3_V_EDL_MDMS_BP_CUST_MST_SND_INF_ALL`, `V_L0NEDW_ZSSDI1008_X2076054_60114`, `V_L0MDM3_V_EDL_MDMS3_COMPANY_MASTER`, `V_L0NEDW_ZFGLA0012_X2076054_57768`, `V_L0NEDW_ZSSDI1002_X2076054_59978`, `V_L0NEDW_ZSSDI1017`

**`pj-lge-edl`.`OB_00069`** ⚠️ 프로젝트 미확정 (3개)
`V_L0GSCP_IFS_VD_PRODUCT_GROUP_MAP`, `V_L0ILDB_XXWOMS_SMS_GRADE_MST`, `V_L0ILDB_XXWOMS_PRD_CONTRI_PER_TB_230927_14883`

**`pjt-lge-oversea-sales-olap`.`PRD_OLAP`** (3개)
`D_SUBSDR_MST`, `D_NPT_MDL_NEW_MST`, `D_FX_MM`

**`pjt-lge-oversea-sales-olap`.`SCM_OLAP`** (이 파일 세트 밖에서 생성되는 것으로 추정되는 진짜 소스, 6개)
`D_USD_CONVERSION_RATE_MST`, `TB_GTM_ORDER_OLAP_S_IF_OS`, `M_CURINV_SNAPSHOT_S`, `TB_SCM_PO_TRACKING`, `M_SO_LINE_INVOICE_NERP`(⚠️생성스크립트 unknown), `M_PO_TRACKING`(⚠️생성스크립트 unknown)

**`pjt-lge-global-olap`.`L1_COMM`** (1개)
`TMCOMM_SUBSDR_M`

**프로젝트 불명** (3개, `dataset.table`만 확인, unknown)
`L1_COMM.TL_L1_SCM__LOG`, `L1_SCM_.TMSCM__GCSP_DIV_M`, `L1_SCM_.TRSCM__SO_LINE_DW_AMOUNT_EXCEPT_M`

**합계: 15+7+3+3+6+1+3 = 28개**

---

## 4. 배치가 만드는 BigQuery 타겟 (SCM_OLAP, 12개 + SCM_DEV 미러 7개)

| 테이블 (`pjt-lge-oversea-sales-olap`.SCM_OLAP.*) | 생성 파일 |
|---|---|
| `M_SO_LINE` | [liw.job_M_SO_LINE.sql](../db_batch/liw.job_M_SO_LINE.sql) **및** [M_SO_LINE.sql](../db/M_SO_LINE.sql) ⚠️(이중 소스, §2-11 참조) |
| `M_SO_LINE_BACK`, `M_SO_LINE_BACK_PO_MAP` | [liw.job_M_SO_LINE_BACK_PO_MAP.sql](../db_batch/liw.job_M_SO_LINE_BACK_PO_MAP.sql) |
| `M_SEA_SHIPMENT_INFO` | [liw.job_M_SEA_SHIPMENT_INFO.sql](../db_batch/liw.job_M_SEA_SHIPMENT_INFO.sql) |
| `D_SO_REM_DAYS` | [liw.job_D_SO_REM_DAYS.sql](../db_batch/liw.job_D_SO_REM_DAYS.sql) |
| `M_SO_LINE_T01` | [liw.job_M_SO_LINE_T01.sql](../db_batch/liw.job_M_SO_LINE_T01.sql) (중간) |
| `M_SO_LINE_T02`, `M_SO_LINE_T03` | [liw.job_M_SO_LINE_T02.sql](../db_batch/liw.job_M_SO_LINE_T02.sql) (중간, 둘 다 이 파일 안에서 생성) |
| `M_SO_LINE_T11` | [liw.job_M_SO_LINE_T11.sql](../db_batch/liw.job_M_SO_LINE_T11.sql) (중간) |
| `M_SO_LINE_T12`, `M_SO_LINE_T13` | [liw.job_M_SO_LINE_T12.sql](../db_batch/liw.job_M_SO_LINE_T12.sql) (중간, 둘 다 이 파일 안에서 생성) |
| `M_SO_LINE_T` | [db/M_SO_LINE.sql](../db/M_SO_LINE.sql) (중간, legacy 파이프라인 전용) |

`SCM_DEV.*` 7개(`D_USD_CONVERSION_RATE_MST`,`M_SO_LINE_BACK_PO_MAP`,`M_SO_LINE_BACK`,`M_SO_LINE`,`M_SO_LINE_INVOICE_NERP`,`M_PO_TRACKING`,`M_CURINV_SNAPSHOT_S`)는 [dev_copy.sql](../db_batch/dev_copy.sql)이 `SCM_OLAP→SCM_DEV`로 단순 복사하는 dev 새로고침용 — 원본 생성 로직 아님.

---

## 5. 앱(`queries/*.py`)이 실제 쿼리하는 최종 테이블 (14개, 완전정규화)

| # | 테이블 (전체 경로) | 사용 쿼리 파일 | 이 저장소에 생성 스크립트 있음? |
|---|---|---|:---:|
| 1 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE `` | active_orders, order | ✅ (이중, §4 참조) |
| 2 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_BACK `` | active_orders | ✅ |
| 3 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_INVOICE_NERP `` | active_orders | ❌ unknown |
| 4 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SEA_SHIPMENT_INFO `` | po, eta_change | ✅ |
| 5 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING `` | po, active_orders, eta_change | ❌ unknown |
| 6 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S `` | inventory | ❌ unknown |
| 7 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_USD_CONVERSION_RATE_MST `` | active_orders, order | ❌ unknown |
| 8 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SUBSDR_MST `` | bigquery_queries_v2 | ❌ unknown |
| 9 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_SALES_TARGET_MST `` | active_orders | ❌ (PG `d_sales_target_mst` 미러 추정, 미확정) |
| 10 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST `` | active_orders | ❌ (PG `d_billto_biz_mst` 미러 추정) |
| 11 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_SUBSDR_MST `` | active_orders | ❌ (PG `d_subsdr_mst` 미러 추정) |
| 12 | `` `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_PRODUCT_MST `` | eta_change | ❌ (PG `d_product_mst` 미러 추정) |
| 13 | `` `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM `` | active_orders | ❌ unknown |
| 14 | `` `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST `` | eta_change | ❌ unknown |

레거시 대시보드(`apis/api.py`)는 위 14개와 별개로 `` `pjt-lge-edl-ob`.OB_00030.V_L0TMS__* `` 뷰 13종을 [queries/bigquery_queries_v2.py](../queries/bigquery_queries_v2.py)에서 원천 직접 조회(중간 배치 없음): `CNCY_T_OS`, `LD_LEG_DETL_T_OS`, `LD_LEG_T_OS`, `STAT_T_OS`, `TB_GTM_CODE_MST_OS`, `TB_GTM_CONTAINER_TMS_S_IF_OS`, `TB_GTM_LOADADJUST_REQUEST_OS`, `TB_GTM_LOAD_OS`, `TB_GTM_MODEL_OS`, `TB_GTM_SHIPMENT_TMS_S_IF_OS`, `TDR_REQ_T_OS`, `TFF_T_OS`, `ZN_T_OS`.

---

## 6. PostgreSQL 메타 테이블 (15개, [db_postgre/](../db_postgre/))

스키마는 `DB_SCHEMA` 환경변수로 dev/prd 분리(`liw_dev` / `liw`, [utils/pg_db.py](../utils/pg_db.py) 참조) — 즉 실제 접속 경로는 `liw.d_user_mst`(prd) 또는 `liw_dev.d_user_mst`(dev) 형태.

| 그룹 | 테이블 |
|---|---|
| 인증/권한 (4) | `d_user_mst`, `d_user_type_mst`, `d_menu_mst`, `d_user_access_request` |
| 마스터데이터 (7) | `d_billto_mst`, `d_billto_biz_mst`, `d_shipto_mst`, `d_product_mst`, `d_subsdr_mst`, `d_sales_target_mst`, `d_sales_team_mst` |
| 이슈 관리 (3) | `d_issue_mst`, `d_issue_order`, `d_issue_comment` |
| 로그 (1) | `m_web_log` |

생성/변경 스크립트: [create_table.sql](../db_postgre/create_table.sql), [create_table_issue.sql](../db_postgre/create_table_issue.sql), [create_table_access_request.sql](../db_postgre/create_table_access_request.sql), `alter_*.sql` 4종

---

## 7. 확인 못한/미확정 지점 정리 (추측 대신 명시)

| # | 항목 | 상태 |
|---|---|---|
| 1 | `pj-lge-edl` 프로젝트가 `pjt-lge-edl-ob`의 오타인지 실제 별도 GCP 프로젝트인지 | **unknown** — `.sp` 파일에 3개 뷰가 이 표기로 backtick 확정되어 있음, 원 개발자 확인 필요 |
| 2 | `SCM_OLAP.M_SO_LINE`을 만드는 두 스크립트(`db_batch/liw.job_M_SO_LINE.sql` vs `db/M_SO_LINE.sql`) 중 실제 운영 중인 쪽 | **unknown** — 완전히 다른 로직으로 동일 타겟을 생성, 스케줄러 설정은 이 저장소 밖 |
| 3 | `M_SO_LINE_INVOICE_NERP`, `M_PO_TRACKING`, `M_CURINV_SNAPSHOT_S`, `D_USD_CONVERSION_RATE_MST`, `SCM_OLAP.D_SUBSDR_MST`의 원본 생성 스크립트 위치 | **unknown** — 이 저장소 안에 없음(dev_copy.sql의 복사 대상으로만 등장), 다른 팀/파이프라인 추정 |
| 4 | `REF_D_SALES_TARGET_MST`/`REF_D_BILLTO_BIZ_MST`/`REF_D_SUBSDR_MST`/`REF_D_PRODUCT_MST`가 PG 동명 테이블의 미러라는 것 | **추정** — 이름 유사성 근거일 뿐, 실제 동기화 배치 확인 안 됨 |
| 5 | `M_SO_LINE`↔`D_SO_REM_DAYS` 순환 의존의 실행 순서 | **unknown** — cron/스케줄러 설정이 이 저장소에 없음 |
| 6 | `L1_COMM.TL_L1_SCM__LOG`, `L1_SCM_.TMSCM__GCSP_DIV_M`, `L1_SCM_.TRSCM__SO_LINE_DW_AMOUNT_EXCEPT_M`의 소속 프로젝트 | **추정(pjt-lge-global-olap)** — 본문에 프로젝트 접두사 없음, 문맥 근거만 있음 |

---
*코드/DB 스키마 변경 시 이 문서도 함께 갱신 필요. project.dataset.table 표기는 grep + 전체 파일 읽기로 검증했으나, 동적으로 조합되는 테이블명(f-string 등)은 반영되지 않았을 수 있습니다.*
