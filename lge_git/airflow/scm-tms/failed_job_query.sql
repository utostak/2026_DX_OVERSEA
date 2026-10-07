-- =====================================================================================
-- M_SO_LINE_BACK : 백오더(Back Order) 라인 공급 할당/도착예상 분석 테이블
-- -------------------------------------------------------------------------------------
--  ▷ 모수      : 백오더 걸린 오픈 오더만 (BACK_ORDER_HOLD = 'Y')
--  ▷ 점검 기준 : 모델(MODEL_CODE) + 법인(SUBSDR_NAME) 단위
--  ▷ 공급 원천 : ① 현재고(`pjt-lge-oversea-sales-olap`.SCM_DEV.M_CURINV_SNAPSHOT_S.AVAILABLE_QTY)
--                ② 인커밍 PO(M_PO_TRACKING) — 4개 진행단계 물량
--  ▷ 선행 테이블 : `pjt-lge-oversea-sales-olap`.SCM_DEV.M_SO_LINE_BACK_PO_MAP (주문라인↔PO/컨테이너 할당 매핑)
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
CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_DEV.M_SO_LINE_BACK
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
      FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_SO_LINE T
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
      FROM pjt-lge-oversea-sales-olap.SCM_DEV.M_SO_LINE T
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
      FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_CURINV_SNAPSHOT_S I
      JOIN (SELECT LEGAL_ENTITY_NAME, MAX(P_PTT) AS MX_PTT
              FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_CURINV_SNAPSHOT_S GROUP BY 1) F
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
      FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_PO_TRACKING P
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
      FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_SO_LINE_BACK_PO_MAP m
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
       `pjt-lge-oversea-sales-olap`.SCM_DEV.REF_D_BILLTO_BIZ_MST B
   ON  r.SUBSDR_NAME            = B.SUBSDR_NAME
  AND  r.BILL_TO_CUSTOMER_CODE  = B.BILLTO_CODE
  AND  r.PRDT_GRP_CD            = B.PRODUCT_GROUP_CODE
 WHERE tt.TIER_QTY > 0