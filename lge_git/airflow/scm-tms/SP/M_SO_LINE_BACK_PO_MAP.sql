-- =====================================================================================
-- M_SO_LINE_BACK_PO_MAP : 백오더 "주문라인 ↔ 공급원(현재고/PO)" 할당 매핑 테이블
-- -------------------------------------------------------------------------------------
--  ▷ 목적   : M_SO_LINE_BACK 생성 "전 단계" 선행 테이블.
--             각 백오더 주문라인이 "어느 공급원(현재고 / 어느 PO·컨테이너)에서 몇 개를
--             가져왔는지"를 수량(ALLOC_QTY)까지 매핑한다.
--             → 오더키(SALES_ORDER_NO + LINE) 기준으로 PO키(PO_NO + PO_LINE_NO + CONTAINER_NO)별
--                할당수량(ALLOC_QTY)을 바로 조회 가능.
--  ▷ 그레인 : 법인 + 모델 + 주문라인 + 공급원(현재고 / 개별 PO키) = 1행
--  ▷ 할당   : 모델별 "가까운 공급원부터(현재고→PO단계)" 정렬한 누적공급 구간과
--             주문일자 우선순위로 정렬한 누적수요 구간을 교차(overlap)시켜 겹치는 수량을 할당.
--             ALLOC_QTY = LEAST(수요끝, 공급끝) − GREATEST(수요시작, 공급시작)
--  ▷ PO키   : PO_NO + PO_LINE_NO + CONTAINER_NO (현재고 공급원은 셋 다 NULL)
--  ▷ 정렬   : PRIORITY(현재고1 → POD~FDEST2 → POL~POD3 → 출하4 → 공장5)
--             → UNIT_ETA(빠른 도착 우선) → CONTAINER_NO → PO_NO → PO_LINE_NO
--  ▷ 모수   : 백오더가 존재하는 주문라인만 (BACK_ORDER_HOLD='Y' 오픈오더)
--  ▷ 공급 원천 : ① 현재고(`pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S.AVAILABLE_QTY)
--                ② 인커밍 PO(M_PO_TRACKING) — 4개 진행단계 PO·컨테이너 물량
--  ▷ 비고   : 공급 부족(PO Required) 잔량은 매핑되는 공급원이 없으므로 행이 생성되지 않음.
-- =====================================================================================
-- ※ 파티셔닝 스펙(ORDERED_DATE) 추가로 기존 테이블과 스펙이 달라 REPLACE 불가 → 선 DROP 후 재생성
CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_BACK_PO_MAP
    PARTITION BY ORDERED_DATE
    CLUSTER BY SUBSDR_NAME, MODEL_CODE
    OPTIONS (
      require_partition_filter = FALSE
    )
    AS
WITH
-- ① 백오더 주문라인 모수 (라인별 백오더 수량)
back_orders AS (
    SELECT
          T.SUBSDR_NAME
        , T.MODEL_CODE
        , T.SALES_ORDER_NO
        , T.SALES_ORDER_LINE_NO
        , T.ORDERED_DATE
        , DATE(T.RAD_DATE) AS RAD_DATE
        , T.ORDER_QTY      AS BACK_QTY
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE T
     WHERE T.OPEN_FLAG       = 'Y'
       AND T.LINE_CATEGORY_CODE NOT IN ('RETURN','Returns')
       AND T.LINE_STATUS_CODE   NOT IN ('CANCELLED','CLOSED','Fully Cancelled','Completed')
       AND T.BACK_ORDER_HOLD       = 'Y'
),
-- ①-2 점검 대상 법인+모델 (공급단위 적재 범위 한정)
back_models AS (
    SELECT DISTINCT SUBSDR_NAME, MODEL_CODE FROM back_orders
),
-- ② 현재고 공급 (법인+모델 단위 가용수량, 음수는 0으로 처리)
stock AS (
    SELECT
          I.LEGAL_ENTITY_NAME                                          AS SUBSDR_NAME
        , I.MODEL_CODE
        , GREATEST(IFNULL(SUM(CAST(I.AVAILABLE_QTY AS FLOAT64)), 0), 0) AS STOCK_QTY
        , MAX(I.P_PTT)                                                  AS STOCK_ETA
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S I
      JOIN (SELECT LEGAL_ENTITY_NAME, MAX(P_PTT) AS MX_PTT
              FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S GROUP BY 1) F
        ON I.LEGAL_ENTITY_NAME = F.LEGAL_ENTITY_NAME AND I.P_PTT = F.MX_PTT
     WHERE I.LEGAL_ENTITY_NAME <> 'LGEPH' OR I.SUBINVENTORY_CODE = '5000'
     GROUP BY 1, 2
),
-- ③ 개별 공급단위 (현재고 1건 + 인커밍 PO 컨테이너 N건)
--    현재고는 PO·컨테이너 없음(즉시 출고 가능, 우선순위 1), PO는 PO라인·컨테이너 단위 개별 물량(우선순위 2~5)
supply_units AS (
    -- 현재고: PO·컨테이너 없음(즉시 출고 가능), 우선순위 1
    SELECT
          m.SUBSDR_NAME
        , m.MODEL_CODE
        , 1                      AS PRIORITY
        , 'STOCK'                AS SUPPLY_TYPE
        , 'From Stock'           AS BACK_STATUS
        , CAST(NULL AS STRING)   AS PO_NO
        , CAST(NULL AS STRING)   AS PO_LINE_NO
        , CAST(NULL AS STRING)   AS CONTAINER_NO
        , IFNULL(s.STOCK_QTY, 0) AS UNIT_QTY
        , s.STOCK_ETA            AS UNIT_ETA
      FROM back_models m
      LEFT JOIN stock s
        ON s.SUBSDR_NAME = m.SUBSDR_NAME
       AND s.MODEL_CODE = m.MODEL_CODE
    UNION ALL
    -- 인커밍 PO: PO라인·컨테이너 단위 개별 물량 (진행단계 → 우선순위 2~5)
    SELECT
          P.subsdr_nm   AS SUBSDR_NAME
        , P.mdl_sffx_cd AS MODEL_CODE
        , CASE TRIM(P.po_status)
            WHEN 'Intransit (POD~FDEST)' THEN 2
            WHEN 'Intransit (POL~POD)'   THEN 3
            WHEN 'Factory Ship Out'      THEN 4
            WHEN 'On factory Processing' THEN 5
          END                              AS PRIORITY
        , 'PO'                             AS SUPPLY_TYPE
        , CASE TRIM(P.po_status)
            WHEN 'Intransit (POD~FDEST)' THEN 'POD → FDEST'
            WHEN 'Intransit (POL~POD)'   THEN 'POL → POD'
            WHEN 'Factory Ship Out'      THEN 'Ship Out'
            WHEN 'On factory Processing' THEN 'On Factory'
          END                              AS BACK_STATUS
        , CAST(P.po_no AS STRING)          AS PO_NO
        , CAST(P.po_line_no AS STRING)     AS PO_LINE_NO
        , NULLIF(TRIM(P.cntr_no), '')      AS CONTAINER_NO
        , SUM(CAST(P.qty AS FLOAT64))           AS UNIT_QTY
        , max(P.FDEST_ETA_DATE)         AS UNIT_ETA
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING P
      JOIN back_models m
        ON m.SUBSDR_NAME = P.subsdr_nm
       AND m.MODEL_CODE = P.mdl_sffx_cd
     WHERE TRIM(P.po_status) IN ('Intransit (POD~FDEST)','Intransit (POL~POD)','Factory Ship Out','On factory Processing')
     GROUP BY P.subsdr_nm , P.mdl_sffx_cd, P.po_status , P.po_no, P.po_line_no, P.cntr_no
),
-- ④ 공급단위 누적 경계 (가까운 공급원부터: 우선순위 → ETA → 컨테이너 → PO)
--    SUP_START ~ SUP_END = 해당 공급단위가 점유하는 누적공급 물량 구간
supply_cum AS (
    SELECT
          SUBSDR_NAME
        , MODEL_CODE
        , PRIORITY
        , SUPPLY_TYPE
        , BACK_STATUS
        , PO_NO
        , PO_LINE_NO
        , CONTAINER_NO
        , UNIT_ETA
        , SUM(UNIT_QTY) OVER w            AS SUP_END
        , SUM(UNIT_QTY) OVER w - UNIT_QTY AS SUP_START
      FROM supply_units
      WINDOW w AS (
          PARTITION BY SUBSDR_NAME, MODEL_CODE
          ORDER BY PRIORITY ASC,
                   UNIT_ETA ASC NULLS LAST,
                   CONTAINER_NO ASC NULLS LAST,
                   PO_NO ASC NULLS LAST,
                   PO_LINE_NO ASC NULLS LAST
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      )
),
-- ⑤ 주문라인별 누적 수요 (주문일자 우선순위: 먼저 주문한 건부터 가까운 공급원 점유)
ranked AS (
    SELECT
          b.*
        , SUM(b.BACK_QTY) OVER (
              PARTITION BY b.SUBSDR_NAME, b.MODEL_CODE
              ORDER BY b.ORDERED_DATE ASC NULLS LAST,
                       b.RAD_DATE ASC NULLS LAST,
                       b.SALES_ORDER_NO,
                       b.SALES_ORDER_LINE_NO
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
          ) AS CUM_BACK_QTY
      FROM back_orders b
),
-- ⑥ 라인 수요구간 ∩ 공급단위 구간 교차 → 겹치는 수량(ALLOC_QTY) 할당
--    수요구간 (CUM_BACK_QTY - BACK_QTY, CUM_BACK_QTY] , 공급구간 (SUP_START, SUP_END]
allocation AS (
    SELECT
          r.SUBSDR_NAME
        , r.MODEL_CODE
        , r.ORDERED_DATE
        , r.SALES_ORDER_NO
        , r.SALES_ORDER_LINE_NO
        , r.BACK_QTY
        , r.CUM_BACK_QTY
        , su.PRIORITY
        , su.SUPPLY_TYPE
        , su.BACK_STATUS
        , su.PO_NO
        , su.PO_LINE_NO
        , su.CONTAINER_NO
        , su.UNIT_ETA
        , LEAST(r.CUM_BACK_QTY, su.SUP_END)
            - GREATEST(r.CUM_BACK_QTY - r.BACK_QTY, su.SUP_START) AS ALLOC_QTY
      FROM ranked r
      JOIN supply_cum su
        ON su.SUBSDR_NAME = r.SUBSDR_NAME
       AND su.MODEL_CODE  = r.MODEL_CODE
       AND su.SUP_START < r.CUM_BACK_QTY                    -- 공급시작 < 수요끝
       AND su.SUP_END   > (r.CUM_BACK_QTY - r.BACK_QTY)     -- 공급끝   > 수요시작
)
-- ⑦ 오더키 ↔ PO키 최종 매핑 (동일 PO키에 다중 공급단위가 걸리면 수량 합산)
SELECT
      SUBSDR_NAME
    , MODEL_CODE
    , ORDERED_DATE
    , SALES_ORDER_NO
    , SALES_ORDER_LINE_NO
    , PRIORITY
    , BACK_STATUS
    , SUPPLY_TYPE
    , PO_NO
    , PO_LINE_NO
    , CONTAINER_NO
    , MAX(UNIT_ETA)           AS UNIT_ETA
    , ANY_VALUE(BACK_QTY)     AS BACK_QTY
    , ANY_VALUE(CUM_BACK_QTY) AS CUM_BACK_QTY
    , SUM(ALLOC_QTY)          AS ALLOC_QTY
  FROM allocation
 WHERE ALLOC_QTY > 0
 GROUP BY
       SUBSDR_NAME
     , MODEL_CODE
     , ORDERED_DATE
     , SALES_ORDER_NO
     , SALES_ORDER_LINE_NO
     , PRIORITY
     , BACK_STATUS
     , SUPPLY_TYPE
     , PO_NO
     , PO_LINE_NO
     , CONTAINER_NO
;


-- =====================================================================================
-- M_SO_LINE_BACK : 백오더(Back Order) 라인 공급 할당/도착예상 분석 테이블
-- -------------------------------------------------------------------------------------
--  ▷ 모수      : 백오더 걸린 오픈 오더만 (BACK_ORDER_HOLD = 'Y')
--  ▷ 점검 기준 : 모델(MODEL_CODE) + 법인(SUBSDR_NAME) 단위
--  ▷ 공급 원천 : ① 현재고(`pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S.AVAILABLE_QTY)
--                ② 인커밍 PO(M_PO_TRACKING) — 4개 진행단계 물량
--  ▷ 선행 테이블 : `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_BACK_PO_MAP (주문라인↔PO/컨테이너 할당 매핑)
--                 → 라인별 컨테이너 집계에 사용. M_SO_LINE_BACK 생성 전 반드시 먼저 적재.
--  ▷ 할당 방식 : 모델별 수요를 주문일자(ORDERED_DATE) 우선순위로 정렬 → 누적수요(CUM_BACK_QTY)를
--                공급 누적 임계값과 비교하여 가장 가까운(=빠른) 공급원부터 워터폴 할당
--                (먼저 주문한 건이 가까운 공급원을 먼저 점유 / 동일 주문일은 RAD 빠른 순)
--  ▷ 상태값(우선순위 순):
--        From Stock  →  POD → FDEST  →  POL → POD  →  Ship Out  →  On Factory  →  PO Required
--        (현재고)       (POD~FDEST)     (POL~POD)     (공장출하)    (공장처리중)   (공급없음·신규PO필요)
--  ▷ EST_ARRIVAL_DATE : 할당된 공급원의 도착예상일
--        - From Stock : NULL (이미 창고 보유분·즉시 출고 가능 → 도착예정 개념 없음)
--        - PO 단계    : 해당 단계 PO의 est_fdest_arrival_date 중 MAX (전량 도착 기준·보수적)
--        - PO Required: NULL (아직 발주 전이라 ETA 없음)
-- =====================================================================================
CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_BACK
    PARTITION BY ORDERED_DATE
    CLUSTER BY SUBSDR_NAME
    OPTIONS (
      require_partition_filter = FALSE
    )
    AS
WITH
-- ① 백오더 모수 (모델 단위 점검을 위해 라인별 백오더 수량 산출)
back_orders AS (
    SELECT
          T.P_PTT
        , T.SUBSDR_NAME
        , T.DIV_NM
        , T.MODEL_CODE
        , T.MODEL_CATEGORY
        , T.SALES_ORDER_NO
        , T.SALES_ORDER_LINE_NO
        , T.ORDER_TYPE_NAME
        , T.BILL_TO_CUSTOMER_CODE
        , T.BILL_TO_CUSTOMER_NAME
        , T.SHIP_TO_CUSTOMER_CODE
        , T.SHIP_TO_CUSTOMER_NAME
        , T.ORDERED_DATE
        , T.BOOKED_DATE
        , DATE(T.RAD_DATE)   AS RAD_DATE
        , DATE(T.HOLD_DATE)  AS HOLD_DATE
        , T.HOLD_NAME
        , T.HOLD_IN_DAYS
        , T.CURRENCY_CODE
        , T.ORDER_AMOUNT
        , T.USD_ORDER_AMOUNT
        , T.ORDER_QTY
        , T.CANCEL_QTY
        , T.ORDER_QTY AS BACK_QTY
        , T.PRDT_GRP_CD
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE T
     WHERE T.OPEN_FLAG       = 'Y'
       AND T.LINE_CATEGORY_CODE NOT IN ('RETURN','Returns')
       AND T.LINE_STATUS_CODE   NOT IN ('CANCELLED','CLOSED','Fully Cancelled','Completed')
       AND T.BACK_ORDER_HOLD       = 'Y'
),
zplant AS (
    SELECT CAST(SAFE_CAST(DOC_NUMBER AS INT64) AS STRING) SO
         , CAST(SAFE_CAST(S_ORD_ITEM AS INT64) AS STRING) LI
         , PLANT
      FROM `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDA0226
     WHERE SALESORG LIKE '%00'
    QUALIFY ROW_NUMBER() OVER(PARTITION BY DOC_NUMBER, S_ORD_ITEM ORDER BY ZLOGSTMP DESC) = 1
),
open_plants AS (
    SELECT DISTINCT T.SUBSDR_NAME, T.MODEL_CODE, COALESCE(z.PLANT, T.WAREHOUSE_CODE) AS PLANT
      FROM pjt-lge-oversea-sales-olap.SCM_OLAP.M_SO_LINE T
      LEFT JOIN zplant z
        ON CAST(SAFE_CAST(T.SALES_ORDER_NO AS INT64) AS STRING) = z.SO
       AND CAST(SAFE_CAST(T.SALES_ORDER_LINE_NO AS INT64) AS STRING) = z.LI
     WHERE T.OPEN_FLAG = 'Y'
       AND COALESCE(z.PLANT, T.WAREHOUSE_CODE) IS NOT NULL
),
-- ③ 현재고 공급 (법인+모델 단위 가용수량, 음수는 0으로 처리)
stock AS (
    SELECT
          I.LEGAL_ENTITY_NAME                AS SUBSDR_NAME
        , I.MODEL_CODE
        , I.INVENTORY_ORGANIZATION_CODE      AS PLANT
        , GREATEST(IFNULL(SUM(CAST(I.AVAILABLE_QTY AS FLOAT64)), 0), 0) AS STOCK_QTY
        , MAX(I.P_PTT)                       AS STOCK_ETA
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S I
      JOIN (SELECT LEGAL_ENTITY_NAME, MAX(P_PTT) AS MX_PTT
              FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S GROUP BY 1) F
        ON I.LEGAL_ENTITY_NAME = F.LEGAL_ENTITY_NAME AND I.P_PTT = F.MX_PTT
     WHERE I.LEGAL_ENTITY_NAME <> 'LGEPH' OR I.SUBINVENTORY_CODE = '5000'
     GROUP BY 1, 2, 3
),
-- ④ 인커밍 PO 공급 (법인+모델 단위, 4개 진행단계별 물량 / 단계별 도착예상 MAX)
po AS (
    SELECT
          P.subsdr_nm   AS SUBSDR_NAME
        , P.mdl_sffx_cd AS MODEL_CODE
        , CAST(SUM(IF(TRIM(P.po_status) = 'Intransit (POD~FDEST)', P.qty, 0)) AS FLOAT64) AS POD_FDEST_QTY
        , CAST(SUM(IF(TRIM(P.po_status) = 'Intransit (POL~POD)',  P.qty, 0)) AS FLOAT64) AS POL_POD_QTY
        , CAST(SUM(IF(TRIM(P.po_status) = 'Factory Ship Out',      P.qty, 0)) AS FLOAT64) AS SHIPOUT_QTY
        , CAST(SUM(IF(TRIM(P.po_status) = 'On factory Processing', P.qty, 0)) AS FLOAT64) AS ONFACTORY_QTY
        , MAX(IF(TRIM(P.po_status) = 'Intransit (POD~FDEST)', P.FDEST_ETA_DATE, NULL)) AS POD_FDEST_ETA
        , MAX(IF(TRIM(P.po_status) = 'Intransit (POL~POD)',  P.FDEST_ETA_DATE, NULL)) AS POL_POD_ETA
        , MAX(IF(TRIM(P.po_status) = 'Factory Ship Out',      P.FDEST_ETA_DATE, NULL)) AS SHIPOUT_ETA
        , MAX(IF(TRIM(P.po_status) = 'On factory Processing', P.FDEST_ETA_DATE, NULL)) AS ONFACTORY_ETA
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING P
     WHERE TRIM(P.po_status) IN ('Intransit (POD~FDEST)','Intransit (POL~POD)','Factory Ship Out','On factory Processing')
     GROUP BY 1, 2
),
-- ⑤ 모델별 공급 통합 (백오더가 존재하는 법인+모델 기준)
supply AS (
    SELECT
          m.SUBSDR_NAME
        , m.MODEL_CODE
        , IFNULL(s.STOCK_QTY,     0) AS STOCK_QTY
        , s.STOCK_ETA
        , IFNULL(p.POD_FDEST_QTY, 0) AS POD_FDEST_QTY
        , IFNULL(p.POL_POD_QTY,   0) AS POL_POD_QTY
        , IFNULL(p.SHIPOUT_QTY,   0) AS SHIPOUT_QTY
        , IFNULL(p.ONFACTORY_QTY, 0) AS ONFACTORY_QTY
        , p.POD_FDEST_ETA
        , p.POL_POD_ETA
        , p.SHIPOUT_ETA
        , p.ONFACTORY_ETA
      FROM (SELECT DISTINCT SUBSDR_NAME, MODEL_CODE FROM back_orders) m
      LEFT JOIN (SELECT op.SUBSDR_NAME, op.MODEL_CODE, SUM(COALESCE(stk.STOCK_QTY,0)) AS STOCK_QTY, MAX(stk.STOCK_ETA) AS STOCK_ETA
                   FROM open_plants op
                   LEFT JOIN stock stk ON stk.SUBSDR_NAME=op.SUBSDR_NAME AND stk.MODEL_CODE=op.MODEL_CODE AND stk.PLANT=op.PLANT
                  GROUP BY 1,2) s
        ON s.SUBSDR_NAME = m.SUBSDR_NAME AND s.MODEL_CODE = m.MODEL_CODE
      LEFT JOIN po    p ON p.SUBSDR_NAME = m.SUBSDR_NAME AND p.MODEL_CODE = m.MODEL_CODE
),
model_back AS (
    SELECT SUBSDR_NAME, MODEL_CODE, SUM(BACK_QTY) AS MBACK FROM back_orders GROUP BY 1, 2
),
tier_qty AS (
    SELECT
          mb.SUBSDR_NAME, mb.MODEL_CODE, mb.MBACK
        , sup.STOCK_QTY, sup.POD_FDEST_QTY, sup.POL_POD_QTY, sup.SHIPOUT_QTY, sup.ONFACTORY_QTY
        , sup.POD_FDEST_ETA, sup.POL_POD_ETA, sup.SHIPOUT_ETA, sup.ONFACTORY_ETA
        , LEAST(mb.MBACK, sup.STOCK_QTY) AS FS
        , LEAST(GREATEST(mb.MBACK-sup.STOCK_QTY,0), sup.POD_FDEST_QTY) AS PODF
        , LEAST(GREATEST(mb.MBACK-sup.STOCK_QTY-sup.POD_FDEST_QTY,0), sup.POL_POD_QTY) AS POL
        , LEAST(GREATEST(mb.MBACK-sup.STOCK_QTY-sup.POD_FDEST_QTY-sup.POL_POD_QTY,0), sup.SHIPOUT_QTY) AS SHIP
        , LEAST(GREATEST(mb.MBACK-sup.STOCK_QTY-sup.POD_FDEST_QTY-sup.POL_POD_QTY-sup.SHIPOUT_QTY,0), sup.ONFACTORY_QTY) AS FAC
        , GREATEST(mb.MBACK-sup.STOCK_QTY-sup.POD_FDEST_QTY-sup.POL_POD_QTY-sup.SHIPOUT_QTY-sup.ONFACTORY_QTY,0) AS POREQ
      FROM model_back mb
      JOIN supply sup ON sup.SUBSDR_NAME=mb.SUBSDR_NAME AND sup.MODEL_CODE=mb.MODEL_CODE
),
-- ⑦ 라인별 컨테이너 할당 (해당 라인이 실제 걸려있는 컨테이너만)
--    선행 테이블 M_SO_LINE_BACK_PO_MAP 가 이미 "라인 ↔ 공급원(PO/컨테이너)" 할당을
--    수량까지 산출해 두었으므로, 여기서는 라인별 컨테이너만 콤마 결합한다.
--    → 같은 단계라도 라인마다 실제 할당된 컨테이너만 표시 (누적 표시 X)
line_containers AS (
    SELECT
          m.SUBSDR_NAME
        , m.MODEL_CODE
        , m.SALES_ORDER_NO
        , m.SALES_ORDER_LINE_NO
        , STRING_AGG(DISTINCT m.CONTAINER_NO, ', ' ORDER BY m.CONTAINER_NO) AS CONTAINER_NO
      FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_BACK_PO_MAP m
     WHERE m.CONTAINER_NO IS NOT NULL
     GROUP BY 1, 2, 3, 4
)
SELECT
      r.P_PTT
    , r.SUBSDR_NAME
    , r.DIV_NM
    , r.MODEL_CODE
    , r.MODEL_CATEGORY
    , r.SALES_ORDER_NO
    , r.SALES_ORDER_LINE_NO
    , r.ORDER_TYPE_NAME
    , r.BILL_TO_CUSTOMER_CODE
    , r.BILL_TO_CUSTOMER_NAME
    , r.SHIP_TO_CUSTOMER_CODE
    , r.SHIP_TO_CUSTOMER_NAME
    , r.ORDERED_DATE
    , r.BOOKED_DATE
    , r.RAD_DATE
    , r.HOLD_DATE
    , r.HOLD_NAME
    , r.HOLD_IN_DAYS
    , r.CURRENCY_CODE
    , r.PRDT_GRP_CD
    , B.BILLTO_BIZ_NAME
    , B.TEAM_NAME
    , CAST(ROUND(r.ORDER_AMOUNT     * SAFE_DIVIDE(tt.TIER_QTY, t.MBACK), 2) AS NUMERIC) AS ORDER_AMOUNT
    , CAST(ROUND(r.USD_ORDER_AMOUNT * SAFE_DIVIDE(tt.TIER_QTY, t.MBACK), 2) AS NUMERIC) AS USD_ORDER_AMOUNT
    , r.ORDER_QTY
    , r.CANCEL_QTY
    , CAST(ROUND(r.BACK_QTY * SAFE_DIVIDE(tt.TIER_QTY, t.MBACK), 3) AS NUMERIC)         AS BACK_QTY
    , CAST(r.BACK_QTY AS NUMERIC)                                                       AS CUM_BACK_QTY
    , t.STOCK_QTY
    , t.POD_FDEST_QTY
    , t.POL_POD_QTY
    , t.SHIPOUT_QTY
    , t.ONFACTORY_QTY
    , tt.BACK_STATUS
    , tt.ETA AS EST_ARRIVAL_DATE
    , IF(tt.BACK_STATUS IN ('POD → FDEST','POL → POD','Ship Out','On Factory'), lc.CONTAINER_NO, NULL) AS CONTAINER_NO
    , CASE
        WHEN me.ENABLED_FLAG = 'N' THEN 'Y'
        WHEN me.ENABLED_FLAG = 'Y' THEN 'N'
        ELSE NULL
      END AS EOL_YN
  FROM back_orders r
  JOIN tier_qty t
    ON t.SUBSDR_NAME = r.SUBSDR_NAME AND t.MODEL_CODE = r.MODEL_CODE
  CROSS JOIN UNNEST([
         STRUCT('From Stock'  AS BACK_STATUS, t.FS   AS TIER_QTY, CAST(NULL AS DATE) AS ETA),
         STRUCT('POD → FDEST', t.PODF, t.POD_FDEST_ETA),
         STRUCT('POL → POD',   t.POL,  t.POL_POD_ETA),
         STRUCT('Ship Out',    t.SHIP, t.SHIPOUT_ETA),
         STRUCT('On Factory',  t.FAC,  t.ONFACTORY_ETA),
         STRUCT('PO Required', t.POREQ, CAST(NULL AS DATE))
       ]) tt
  LEFT JOIN line_containers lc
    ON lc.SUBSDR_NAME         = r.SUBSDR_NAME
   AND lc.MODEL_CODE          = r.MODEL_CODE
   AND lc.SALES_ORDER_NO      = r.SALES_ORDER_NO
   AND lc.SALES_ORDER_LINE_NO = r.SALES_ORDER_LINE_NO
  LEFT OUTER JOIN 
         `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST B
    ON  r.SUBSDR_NAME            = B.SUBSDR_NAME
   AND  r.BILL_TO_CUSTOMER_CODE  = B.BILLTO_CODE
   AND  r.PRDT_GRP_CD            = B.PRODUCT_GROUP_CODE
  LEFT JOIN (
      SELECT s.SUBSDR_NM AS SUBSDR_NAME, m.MODEL_CODE, m.SUFFIX_CODE,
             MIN(m.ENABLED_FLAG) AS ENABLED_FLAG
        FROM `pjt-lge-edl-ob`.OB_00030.V_L0MDM3_V_EDL_MDMS3_MODEL_MASTER m
        JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST s
          ON s.SUBSDR_CD = m.COMPANY_CODE
        GROUP BY 1, 2, 3
      ) me
    ON me.SUBSDR_NAME = r.SUBSDR_NAME
   AND CONCAT(me.MODEL_CODE, '.', me.SUFFIX_CODE) = r.MODEL_CODE
 WHERE tt.TIER_QTY > 0
;