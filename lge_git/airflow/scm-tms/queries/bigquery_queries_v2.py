"""
Dashboard - BigQuery SQL Queries (7영역 분석)
7개 영역 End-to-End 가시성 분석 쿼리
"""
import os

# ============================================================================
# 영역 1: Shipment 기본 정보 분석
# ============================================================================

QUERY_SHIPMENT_DAILY_TREND = f"""
-- 일자/법인별 출하 건수
SELECT
  DATE(PICK_RELEASE_DATE) AS ship_dt,
  LEGAL_ENTITY_NAME,
  COUNT(DISTINCT SHIPMENTNUMBER) AS shipment_cnt,
  COUNT(DISTINCT SHIPTOLOCATIONCODE) AS destination_cnt,
  COUNT(DISTINCT SHIPFROMLOCATIONCODE) AS warehouse_cnt
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
WHERE PICK_RELEASE_DATE >= @start_date
  AND PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2
ORDER BY 1 DESC, 2
"""

QUERY_SHIPMENT_BY_ZONE = f"""
-- Zone별 출하 분포
SELECT
  COALESCE(Z.ZN_DESC, S.ZONE_CODE, 'Unknown') AS zone_name,
  S.LEGAL_ENTITY_NAME,
  COUNT(DISTINCT S.SHIPMENTNUMBER) AS shipment_cnt,
  COUNT(DISTINCT S.SHIPTOLOCATIONCODE) AS destination_cnt
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__ZN_T_OS` Z
  ON S.ZONE_CODE = Z.ZN_CD
WHERE S.PICK_RELEASE_DATE >= @start_date
  AND S.PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR S.LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2
ORDER BY shipment_cnt DESC
"""

QUERY_SHIPMENT_RAD_URGENCY = f"""
-- RAD 대비 출하 긴급도
SELECT
  SHIPMENTNUMBER,
  LEGAL_ENTITY_NAME,
  DATE(PICK_RELEASE_DATE) AS pick_release_dt,
  DATE(ORI_DELY_TO) AS rad_dt,
  DATE_DIFF(DATE(ORI_DELY_TO), DATE(PICK_RELEASE_DATE), DAY) AS days_to_rad,
  CASE
    WHEN DATE_DIFF(DATE(ORI_DELY_TO), DATE(PICK_RELEASE_DATE), DAY) < 0 THEN 'Past RAD'
    WHEN DATE_DIFF(DATE(ORI_DELY_TO), DATE(PICK_RELEASE_DATE), DAY) <= 3 THEN 'Urgent (≤3days)'
    WHEN DATE_DIFF(DATE(ORI_DELY_TO), DATE(PICK_RELEASE_DATE), DAY) <= 7 THEN 'Normal (4-7days)'
    ELSE 'Comfortable (>7days)'
  END AS urgency_level
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
WHERE PICK_RELEASE_DATE >= @start_date
  AND PICK_RELEASE_DATE < @end_date
  AND ORI_DELY_TO IS NOT NULL
  AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
ORDER BY days_to_rad
"""

QUERY_SHIPMENT_BY_WAREHOUSE = f"""
-- 출발 창고별 출하 비중
SELECT
  SHIPFROMLOCATIONCODE AS warehouse_code,
  LEGAL_ENTITY_NAME,
  COUNT(DISTINCT SHIPMENTNUMBER) AS shipment_cnt,
  COUNT(DISTINCT SHIPTOLOCATIONCODE) AS destination_cnt
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
WHERE PICK_RELEASE_DATE >= @start_date
  AND PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2
ORDER BY shipment_cnt DESC
"""

# ============================================================================
# 영역 2: 품목/컨테이너 타입·수량·부피(CBM) 분석
# ============================================================================

QUERY_ITEM_VOLUME_BY_TYPE = f"""
-- 컨테이너 타입별 물량 구조
SELECT
  CONTAINERTYPECODE,
  MODEL_GRADE,
  COUNT(DISTINCT SHIPMENTNUMBER) AS shipment_cnt,
  SUM(QUANTITY) AS qty,
  SUM(QUANTITY * VOLUME) AS total_cbm,
  AVG(QUANTITY * VOLUME) AS avg_cbm_per_shipment
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_CONTAINER_TMS_S_IF_OS`
WHERE SHIPMENTNUMBER IN (
  SELECT DISTINCT SHIPMENTNUMBER
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
  WHERE PICK_RELEASE_DATE >= @start_date
    AND PICK_RELEASE_DATE < @end_date
    AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
)
GROUP BY 1, 2
ORDER BY total_cbm DESC
"""

QUERY_ITEM_SHIPMENT_SUMMARY = f"""
-- Shipment별 총 물량/총 부피
SELECT
  C.SHIPMENTNUMBER,
  S.LEGAL_ENTITY_NAME,
  S.ZONE_CODE,
  SUM(C.QUANTITY) AS total_qty,
  SUM(C.QUANTITY * C.VOLUME) AS total_cbm,
  COUNT(DISTINCT C.CONTAINERTYPECODE) AS container_type_cnt,
  MAX(C.QUANTITY * C.VOLUME) AS max_cbm_per_type
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_CONTAINER_TMS_S_IF_OS` C
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
  ON C.SHIPMENTNUMBER = S.SHIPMENTNUMBER
WHERE S.PICK_RELEASE_DATE >= @start_date
  AND S.PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR S.LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2, 3
ORDER BY total_cbm DESC
"""

QUERY_ITEM_MODEL_ANALYSIS = f"""
-- 패키지 모델 코드 기준 모델 마스터 조인
SELECT
  C.PACKAGE_MODEL_CODE,
  M.MODEL_DESC,
  M.MODEL_CATEGORY_CODE,
  COUNT(DISTINCT C.SHIPMENTNUMBER) AS shipment_cnt,
  SUM(C.QUANTITY) AS qty,
  SUM(C.QUANTITY * C.VOLUME) AS total_cbm
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_CONTAINER_TMS_S_IF_OS` C
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_MODEL_OS` M
  ON C.PACKAGE_MODEL_CODE = M.MODEL_CODE
WHERE C.SHIPMENTNUMBER IN (
  SELECT DISTINCT SHIPMENTNUMBER
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
  WHERE PICK_RELEASE_DATE >= @start_date
    AND PICK_RELEASE_DATE < @end_date
    AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
)
  AND C.PACKAGE_MODEL_CODE IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY total_cbm DESC
LIMIT 100
"""

# ============================================================================
# 영역 3: 차량(Load) · 배차 분석
# ============================================================================

QUERY_LOAD_DAILY_TREND = f"""
-- Load 생성 추이 (법인 필터 포함)
SELECT
  DATE(L.CRTD_DTT) AS load_create_dt,
  L.CARR_CD,
  L.EQMT_TYP,
  L.SRVC_CD,
  COUNT(DISTINCT L.LD_LEG_ID) AS load_cnt,
  AVG(L.CHGD_AMT_DLR) AS avg_freight,
  SUM(L.CHGD_AMT_DLR) AS total_freight
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@carrier = 'ALL' OR L.CARR_CD = @carrier)
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, load_cnt DESC
"""

QUERY_LOAD_BY_CARRIER = f"""
-- 운송사/차량유형별 평균 운임 (법인 필터 포함)
SELECT
  L.CARR_CD,
  L.SRVC_CD,
  L.EQMT_TYP,
  COUNT(DISTINCT L.LD_LEG_ID) AS load_cnt,
  AVG(L.CHGD_AMT_DLR * FX.FX_RATE) AS avg_freight,
  SUM(L.CHGD_AMT_DLR * FX.FX_RATE) AS total_freight,
  MIN(L.CHGD_AMT_DLR * FX.FX_RATE) AS min_freight,
  MAX(L.CHGD_AMT_DLR * FX.FX_RATE) AS max_freight
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
  ON L.TFF_ID = T.TFF_ID
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
  ON T.CNCY_TYP = C.CNCY_TYP
JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
  ON C.CNCY_CD = FX.CURRENCY_CD
 AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@carrier = 'ALL' OR L.CARR_CD = @carrier)
  AND L.CHGD_AMT_DLR IS NOT NULL
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1, 2, 3
ORDER BY total_freight DESC
"""

QUERY_CARRIER_LIST = f"""
-- 운송사 목록 조회 (법인 필터 포함)
SELECT DISTINCT
  L.CARR_CD
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
WHERE L.CARR_CD IS NOT NULL
  AND L.CARR_CD != ''
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
ORDER BY L.CARR_CD
"""

QUERY_LOAD_BY_ROUTE = f"""
-- Route Zone별 Load 분포 (법인 필터 포함)
SELECT
  L.RUTD_ORI_ZN_CD AS origin_zone,
  L.RUTD_DEST_ZN_CD AS dest_zone,
  L.CARR_CD,
  L.EQMT_TYP,
  COUNT(DISTINCT L.LD_LEG_ID) AS load_cnt,
  AVG(L.CHGD_AMT_DLR) AS avg_freight
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@carrier = 'ALL' OR L.CARR_CD = @carrier)
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1, 2, 3, 4
ORDER BY load_cnt DESC
"""

# ============================================================================
# 영역 4: Shipment ↔ Load 연결 분석(적재 구조)
# ============================================================================

QUERY_LOADING_SHIPMENT_PER_LOAD = f"""
-- Load당 Shipment 수 (법인/날짜 필터 포함)
SELECT
  D.LD_LEG_ID,
  COUNT(DISTINCT D.SHPM_NUM) AS shipment_per_load,
  COUNT(*) AS leg_detail_cnt,
  STRING_AGG(DISTINCT D.FRM_SHPG_LOC_CD, ', ') AS from_locations,
  STRING_AGG(DISTINCT D.TO_SHPG_LOC_CD, ', ') AS to_locations
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON D.LD_LEG_ID = L.LD_LEG_ID
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@legal_entity = 'ALL' OR D.SHPM_NUM IN (
    SELECT DISTINCT SHIPMENTNUMBER
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
    WHERE LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1
ORDER BY shipment_per_load DESC
LIMIT 1000
"""

QUERY_LOADING_LEG_STRUCTURE = f"""
-- Shipment별 분할 여부 / 다중 Leg 여부 (법인/날짜 필터 포함)
SELECT
  D.SHPM_NUM,
  COUNT(DISTINCT D.LD_LEG_ID) AS load_cnt,
  COUNT(*) AS leg_cnt,
  MAX(D.SEQ_NUM) AS max_seq_num,
  CASE
    WHEN COUNT(*) > 1 THEN 'MULTI_LEG'
    ELSE 'DIRECT_OR_SINGLE_LEG'
  END AS leg_type,
  STRING_AGG(DISTINCT D.LD_LEG_ID, ', ') AS load_ids
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON D.LD_LEG_ID = L.LD_LEG_ID
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@legal_entity = 'ALL' OR D.SHPM_NUM IN (
    SELECT DISTINCT SHIPMENTNUMBER
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
    WHERE LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1
ORDER BY leg_cnt DESC, load_cnt DESC
LIMIT 1000
"""

QUERY_LOADING_WITH_ROUTE = f"""
-- 적재 구조 + 라우팅 Zone 결합 (법인/날짜 필터 포함)
SELECT
  D.SHPM_NUM,
  D.LD_LEG_ID,
  D.SEQ_NUM,
  D.FRM_SHPG_LOC_CD,
  D.TO_SHPG_LOC_CD,
  L.RUTD_ORI_ZN_CD,
  L.RUTD_DEST_ZN_CD,
  L.CARR_CD,
  L.EQMT_TYP,
  L.CHGD_AMT_DLR
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON D.LD_LEG_ID = L.LD_LEG_ID
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@legal_entity = 'ALL' OR D.SHPM_NUM IN (
    SELECT DISTINCT SHIPMENTNUMBER
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
    WHERE LEGAL_ENTITY_NAME = @legal_entity
  ))
ORDER BY D.SHPM_NUM, D.SEQ_NUM
LIMIT 5000
"""

QUERY_LOADING_MULTI_LEG_ANALYSIS = f"""
-- Multi-leg 구조 상세 분석 (법인/날짜 필터 포함)
WITH LegStructure AS (
  SELECT
    D.SHPM_NUM,
    COUNT(DISTINCT D.LD_LEG_ID) AS load_cnt,
    COUNT(*) AS leg_cnt
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
    ON D.LD_LEG_ID = L.LD_LEG_ID
  WHERE L.CRTD_DTT >= @start_date
    AND L.CRTD_DTT < @end_date
    AND (@legal_entity = 'ALL' OR D.SHPM_NUM IN (
      SELECT DISTINCT SHIPMENTNUMBER
      FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
      WHERE LEGAL_ENTITY_NAME = @legal_entity
    ))
  GROUP BY 1
)
SELECT
  CASE
    WHEN leg_cnt = 1 THEN '1_Direct'
    WHEN leg_cnt = 2 THEN '2_Two_Legs'
    WHEN leg_cnt <= 5 THEN '3-5_Legs'
    ELSE '6+_Complex'
  END AS leg_complexity,
  COUNT(*) AS shipment_cnt,
  AVG(load_cnt) AS avg_loads_per_shipment
FROM LegStructure
GROUP BY 1
ORDER BY 1
"""

# ============================================================================
# 영역 5: 출고 실적 / 창고 릴리즈 분석
# ============================================================================

QUERY_WAREHOUSE_RELEASE_STATUS = f"""
-- 출고 완료 Shipment 수
SELECT
  LEGAL_ENTITY_NAME,
  COUNT(DISTINCT SHIPMENTNUMBER) AS total_shipment_cnt,
  COUNT(DISTINCT CASE WHEN SHIPPING_DATE IS NOT NULL THEN SHIPMENTNUMBER END) AS completed_shipment_cnt,
  SAFE_DIVIDE(
    COUNT(DISTINCT CASE WHEN SHIPPING_DATE IS NOT NULL THEN SHIPMENTNUMBER END),
    COUNT(DISTINCT SHIPMENTNUMBER)
  ) AS completion_rate,
  SUM(DELIVERY_QTY) AS total_delivery_qty
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS`
WHERE SHIPMENTNUMBER IN (
  SELECT DISTINCT SHIPMENTNUMBER
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
  WHERE PICK_RELEASE_DATE >= @start_date
    AND PICK_RELEASE_DATE < @end_date
    AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
)
GROUP BY 1
ORDER BY total_shipment_cnt DESC
"""

QUERY_WAREHOUSE_LEADTIME = f"""
-- 출고 리드타임
SELECT
  L.SHIPMENTNUMBER,
  L.LEGAL_ENTITY_NAME,
  DATE(S.PICK_RELEASE_DATE) AS pick_release_dt,
  DATE(L.RELEASE_TO_WH_DATE) AS release_to_wh_dt,
  DATE(L.SHIPPING_DATE) AS shipping_dt,
  DATE_DIFF(DATE(L.RELEASE_TO_WH_DATE), DATE(S.PICK_RELEASE_DATE), DAY) AS pick_to_release_days,
  DATE_DIFF(DATE(L.SHIPPING_DATE), DATE(L.RELEASE_TO_WH_DATE), DAY) AS release_to_ship_days,
  DATE_DIFF(DATE(L.SHIPPING_DATE), DATE(S.PICK_RELEASE_DATE), DAY) AS total_leadtime_days
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS` L
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
  ON L.SHIPMENTNUMBER = S.SHIPMENTNUMBER
WHERE S.PICK_RELEASE_DATE >= @start_date
  AND S.PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR S.LEGAL_ENTITY_NAME = @legal_entity)
  AND L.SHIPPING_DATE IS NOT NULL
ORDER BY total_leadtime_days DESC
LIMIT 1000
"""

QUERY_WAREHOUSE_PROCESSING = f"""
-- 창고 릴리즈 처리 현황
SELECT
  LEGAL_ENTITY_NAME,
  COUNT(DISTINCT SHIPMENTNUMBER) AS shipment_cnt,
  AVG(DATE_DIFF(DATE(SHIPPING_DATE), DATE(RELEASE_TO_WH_DATE), DAY)) AS avg_wh_to_ship_gap,
  COUNT(DISTINCT CASE WHEN RELEASE_TO_WH_DATE IS NULL THEN SHIPMENTNUMBER END) AS not_released_cnt,
  COUNT(DISTINCT CASE WHEN SHIPPING_DATE IS NULL THEN SHIPMENTNUMBER END) AS not_shipped_cnt
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS`
WHERE SHIPMENTNUMBER IN (
  SELECT DISTINCT SHIPMENTNUMBER
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
  WHERE PICK_RELEASE_DATE >= @start_date
    AND PICK_RELEASE_DATE < @end_date
    AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
)
GROUP BY 1
ORDER BY shipment_cnt DESC
"""

# ============================================================================
# 영역 6: 운임 변경 / 비용 통제 분석
# ============================================================================

QUERY_COST_ADJUSTMENT_SUMMARY = f"""
-- 운임 변경 건수와 Spot 비율 (법인/날짜 필터 포함)
    SELECT
      COUNT(DISTINCT LOAD_ID) AS adjusted_load_cnt,
      COUNT(*) AS adjustment_req_cnt,
      SUM(CHANGE_FREIGHT_COST) AS total_changed_cost,
      SAFE_DIVIDE(
        SUM(CASE WHEN SPOT_RATE_FLAG = 'Y' THEN 1 ELSE 0 END),
        COUNT(*)
      ) AS spot_rate_ratio,
      AVG(CHANGE_FREIGHT_COST) AS avg_changed_cost, 
    FROM ( 
        SELECT A.LOAD_ID
             , A.CHANGE_FREIGHT_COST * FX.FX_RATE AS CHANGE_FREIGHT_COST
             , A.SPOT_RATE_FLAG
             , C.CNCY_CD
             --, ROW_NUMBER() OVER(PARTITION BY A.LOAD_ID ORDER BY A.REQUEST_ID DESC) AS IDX
        FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOADADJUST_REQUEST_OS` A
        JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
          ON A.LOAD_ID = L.LD_LEG_ID
        JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
          ON L.TFF_ID = T.TFF_ID
        JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
          ON T.CNCY_TYP = C.CNCY_TYP
        JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
          ON C.CNCY_CD = FX.CURRENCY_CD
         AND FX.BASE_YYMM = format_date('%Y%m',L.CRTD_DTT)
        WHERE L.CRTD_DTT >= @start_date
          AND L.CRTD_DTT < @end_date
          AND A.REQUEST_TYPE IN ('LC','LM') 
          AND A.LAST_UPDATE_DATE < CURRENT_DATETIME()
          AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
            SELECT DISTINCT D.LD_LEG_ID
            FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
            JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
              ON D.SHPM_NUM = S.SHIPMENTNUMBER
            WHERE S.LEGAL_ENTITY_NAME = @legal_entity
          ))
         ) 
"""

QUERY_COST_ADJUSTMENT_BY_REASON = f"""
-- 사유 카테고리별 변경 비용 (법인/날짜 필터 포함)
SELECT
  CHANGE_REASON_CATEGORY,
  CHANGE_REASON,
  COUNT(*) AS req_cnt,
  SUM(CHANGE_FREIGHT_COST) AS changed_freight_cost,
  AVG(CHANGE_FREIGHT_COST) AS avg_changed_cost,
  SUM(CASE WHEN SPOT_RATE_FLAG = 'Y' THEN 1 ELSE 0 END) AS spot_cnt
FROM (
  SELECT
    A.CHANGE_REASON_CATEGORY,
    A.CHANGE_REASON,
    A.CHANGE_FREIGHT_COST * FX.FX_RATE AS CHANGE_FREIGHT_COST,
    A.SPOT_RATE_FLAG
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOADADJUST_REQUEST_OS` A
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
    ON A.LOAD_ID = L.LD_LEG_ID
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
    ON L.TFF_ID = T.TFF_ID
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
    ON T.CNCY_TYP = C.CNCY_TYP
  JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
    ON C.CNCY_CD = FX.CURRENCY_CD
   AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
  WHERE L.CRTD_DTT >= @start_date
    AND L.CRTD_DTT < @end_date
    AND A.REQUEST_TYPE IN ('LC', 'LM')
    AND A.LAST_UPDATE_DATE < CURRENT_DATETIME()
    AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
      SELECT DISTINCT D.LD_LEG_ID
      FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
      JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
        ON D.SHPM_NUM = S.SHIPMENTNUMBER
      WHERE S.LEGAL_ENTITY_NAME = @legal_entity
    ))
)
GROUP BY 1, 2
ORDER BY changed_freight_cost DESC
LIMIT 50
"""

QUERY_COST_WITH_FREIGHT = f"""
-- 실제 운임 수준 결합 (법인 필터 포함)
SELECT
  A.LOAD_ID,
  A.CHANGE_REASON_CATEGORY,
  A.CHANGE_REASON,
  A.CHANGE_FREIGHT_COST * FX.FX_RATE AS CHANGE_FREIGHT_COST,
  A.SPOT_RATE_FLAG,
  L.CARR_CD,
  L.SRVC_CD,
  L.EQMT_TYP,
  L.CHGD_AMT_DLR AS current_freight,
  L.RUTD_ORI_ZN_CD,
  L.RUTD_DEST_ZN_CD
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOADADJUST_REQUEST_OS` A
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON A.LOAD_ID = L.LD_LEG_ID
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
  ON L.TFF_ID = T.TFF_ID
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
  ON T.CNCY_TYP = C.CNCY_TYP
JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
  ON C.CNCY_CD = FX.CURRENCY_CD
 AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND A.REQUEST_TYPE IN ('LC', 'LM')
  AND A.LAST_UPDATE_DATE < CURRENT_DATETIME()
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
ORDER BY CHANGE_FREIGHT_COST DESC
LIMIT 1000
"""

# ============================================================================
# 영역 7: 지역(Zone) / 운송 네트워크 분석
# ============================================================================

QUERY_NETWORK_SHIPMENT_ZONE = f"""
-- Shipment Zone별 출하 건수
SELECT
  COALESCE(Z.ZN_DESC, S.ZONE_CODE, 'Unknown') AS zone_name,
  S.ZONE_CODE,
  S.LEGAL_ENTITY_NAME,
  COUNT(DISTINCT S.SHIPMENTNUMBER) AS shipment_cnt,
  COUNT(DISTINCT S.SHIPTOLOCATIONCODE) AS destination_cnt,
  COUNT(DISTINCT S.SHIPFROMLOCATIONCODE) AS warehouse_cnt
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__ZN_T_OS` Z
  ON S.ZONE_CODE = Z.ZN_CD
WHERE S.PICK_RELEASE_DATE >= @start_date
  AND S.PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR S.LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2, 3
ORDER BY shipment_cnt DESC
"""

QUERY_NETWORK_ROUTE_ZONE = f"""
-- Route Zone 네트워크 흐름 (법인 필터 포함)
SELECT
  L.RUTD_ORI_ZN_CD AS origin_zone,
  L.RUTD_DEST_ZN_CD AS dest_zone,
  L.CARR_CD,
  COUNT(DISTINCT L.LD_LEG_ID) AS load_cnt,
  AVG(L.CHGD_AMT_DLR * FX.FX_RATE) AS avg_freight,
  SUM(L.CHGD_AMT_DLR * FX.FX_RATE) AS total_freight
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
  ON L.TFF_ID = T.TFF_ID
JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
  ON T.CNCY_TYP = C.CNCY_TYP
JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
  ON C.CNCY_CD = FX.CURRENCY_CD
 AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
WHERE L.CRTD_DTT >= @start_date
  AND L.CRTD_DTT < @end_date
  AND (@carrier = 'ALL' OR L.CARR_CD = @carrier)
  AND L.RUTD_ORI_ZN_CD IS NOT NULL
  AND L.RUTD_DEST_ZN_CD IS NOT NULL
  AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
    SELECT DISTINCT D.LD_LEG_ID
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
    JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
      ON D.SHPM_NUM = S.SHIPMENTNUMBER
    WHERE S.LEGAL_ENTITY_NAME = @legal_entity
  ))
GROUP BY 1, 2, 3
ORDER BY load_cnt DESC
LIMIT 100
"""

QUERY_NETWORK_COMBINED = f"""
-- Shipment Zone + Load Route 결합
SELECT
  S.LEGAL_ENTITY_NAME,
  S.ZONE_CODE AS shipment_zone,
  L.RUTD_ORI_ZN_CD,
  L.RUTD_DEST_ZN_CD,
  L.CARR_CD,
  COUNT(DISTINCT S.SHIPMENTNUMBER) AS shipment_cnt,
  COUNT(DISTINCT TL.LD_LEG_ID) AS load_cnt,
  AVG(L.CHGD_AMT_DLR * FX.FX_RATE) AS avg_freight
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS` TL
  ON S.SHIPMENTNUMBER = TL.SHIPMENTNUMBER
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON TL.LD_LEG_ID = L.LD_LEG_ID
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
  ON L.TFF_ID = T.TFF_ID
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
  ON T.CNCY_TYP = C.CNCY_TYP
LEFT JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
  ON C.CNCY_CD = FX.CURRENCY_CD
 AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
WHERE S.PICK_RELEASE_DATE >= @start_date
  AND S.PICK_RELEASE_DATE < @end_date
  AND (@legal_entity = 'ALL' OR S.LEGAL_ENTITY_NAME = @legal_entity)
GROUP BY 1, 2, 3, 4, 5
ORDER BY shipment_cnt DESC
LIMIT 500
"""

# ============================================================================
# Dashboard Main KPI (7영역 통합 요약)
# ============================================================================

QUERY_MAIN_DASHBOARD_KPI = f"""
-- 메인 대시보드 KPI (7영역 통합)
WITH ShipmentBase AS (
  SELECT
    COUNT(DISTINCT SHIPMENTNUMBER) AS total_shipment_cnt,
    COUNT(DISTINCT LEGAL_ENTITY_NAME) AS legal_entity_cnt,
    COUNT(DISTINCT ZONE_CODE) AS zone_cnt,
    COUNT(DISTINCT SHIPTOLOCATIONCODE) AS destination_cnt
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
  WHERE PICK_RELEASE_DATE >= @start_date
    AND PICK_RELEASE_DATE < @end_date
    AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
),
LoadBase AS (
  SELECT
    COUNT(DISTINCT L.LD_LEG_ID) AS total_load_cnt,
    COUNT(DISTINCT L.CARR_CD) AS carrier_cnt,
    SUM(L.CHGD_AMT_DLR * FX.FX_RATE) AS total_freight_cost,
    AVG(L.CHGD_AMT_DLR * FX.FX_RATE) AS avg_freight_cost
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TFF_T_OS` T
    ON L.TFF_ID = T.TFF_ID
  JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__CNCY_T_OS` C
    ON T.CNCY_TYP = C.CNCY_TYP
  JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
    ON C.CNCY_CD = FX.CURRENCY_CD
   AND FX.BASE_YYMM = format_date('%Y%m', L.CRTD_DTT)
  WHERE L.CRTD_DTT >= @start_date
    AND L.CRTD_DTT < @end_date
    AND (@carrier = 'ALL' OR L.CARR_CD = @carrier)
    AND (@legal_entity = 'ALL' OR L.LD_LEG_ID IN (
      SELECT DISTINCT D.LD_LEG_ID
      FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS` D
      JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
        ON D.SHPM_NUM = S.SHIPMENTNUMBER
      WHERE S.LEGAL_ENTITY_NAME = @legal_entity
    ))
),
VolumeBase AS (
  SELECT
    SUM(QUANTITY) AS total_quantity,
    SUM(QUANTITY * VOLUME) AS total_cbm
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_CONTAINER_TMS_S_IF_OS`
  WHERE SHIPMENTNUMBER IN (
    SELECT DISTINCT SHIPMENTNUMBER
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
    WHERE PICK_RELEASE_DATE >= @start_date
      AND PICK_RELEASE_DATE < @end_date
      AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
  )
),
WarehouseBase AS (
  SELECT
    COUNT(DISTINCT CASE WHEN SHIPPING_DATE IS NOT NULL THEN SHIPMENTNUMBER END) AS completed_shipment_cnt
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS`
  WHERE SHIPMENTNUMBER IN (
    SELECT DISTINCT SHIPMENTNUMBER
    FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS`
    WHERE PICK_RELEASE_DATE >= @start_date
      AND PICK_RELEASE_DATE < @end_date
      AND (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
  )
)
SELECT
  -- 영역1: Shipment 기본
  S.total_shipment_cnt,
  S.legal_entity_cnt,
  S.zone_cnt,
  S.destination_cnt,
  -- 영역2: 물량
  V.total_quantity,
  ROUND(V.total_cbm, 2) AS total_cbm,
  -- 영역3: Load
  L.total_load_cnt,
  L.carrier_cnt,
  ROUND(L.total_freight_cost, 2) AS total_freight_cost,
  ROUND(L.avg_freight_cost, 2) AS avg_freight_cost,
  -- 영역5: 출고 실적
  W.completed_shipment_cnt,
  SAFE_DIVIDE(W.completed_shipment_cnt, S.total_shipment_cnt) AS completion_rate,
  -- 파생 지표
  SAFE_DIVIDE(L.total_load_cnt, S.total_shipment_cnt) AS load_per_shipment,
  SAFE_DIVIDE(V.total_cbm, L.total_load_cnt) AS cbm_per_load
FROM ShipmentBase S, LoadBase L, VolumeBase V, WarehouseBase W
"""

# ============================================================================
# 특정 법인 / 날짜 기준 Load 소요일 분석
# ============================================================================

QUERY_LOAD_LEADTIME_BY_LEGAL_ENTITY = f"""
-- Load별 소요일 분석 (TB_GTM_LOAD 기준 / 법인 + Load 생성일 필터)
-- 날짜 발생 순서: 수주입력 → Pick Release → RAD → Load생성 → Tender마감 → 예정출발 → 예정도착
--              → 창고릴리즈 → 실제출고(Ship Confirm) → 출고완료 → 송장발행
SELECT
  -- ── 식별자  
  GL.LD_LEG_ID                                                    AS load_id,
  GL.LEGAL_ENTITY_NAME                                            AS legal_entity,
  GL.SHIPMENTNUMBER                                               AS shipment_number,
  GL.FRM_SHPG_LOC_CD                                              AS origin_wh,
  GL.DELIVERY_NO                                                  AS delivery_no,
  -- GL.INVO_NO                                                      AS invoice_no,
  -- GL.LOAD_STATUS                                                  AS wms_status,
  WMS.CD_NM                                                       AS wms_status_name,
  GL.CANCEL_FLAG                                                  AS cancel_flag,
  GL.DELIVERY_QTY                                                 AS delivery_qty,
  -- ── 금액 정보
  GL.CURRENCY_CODE                                                AS currency_code,
  GL.UNIT_SELLING_PRICE                                           AS unit_selling_price,
  ROUND(GL.DELIVERY_QTY * GL.UNIT_SELLING_PRICE, 2)              AS local_amount,
  ROUND(GL.DELIVERY_QTY * GL.UNIT_SELLING_PRICE * COALESCE(FX.FX_RATE, 1), 2) AS usd_amount,
  -- Load 마스터 추가 정보
  L.CARR_CD                                                       AS carrier,
  L.SRVC_CD                                                       AS service_cd,
  L.EQMT_TYP                                                      AS vehicle_type,
  L.LAST_SHPG_LOC_CD                                              AS dest_loc,
  --L.CUR_OPTLSTAT_ID                                               AS load_status_id,
  ST.STAT_SHRT_DESC                                               AS load_status_name,
  -- ── [1] 수주 입력일  
  DATE(S.SALES_ORDER_DATE)                                        AS dt_01_sales_order,
  -- ── [2] Pick Release일 (ERP 출고 지시)  
  DATE(S.PICK_RELEASE_DATE)                                       AS dt_02_pick_release,
  -- ── [3] Load 생성일 (TB_GTM_LOAD 기준)  
  DATE(GL.LOAD_CREATION_DATE)                                     AS dt_03_load_created,
  -- ── [4] Tender 응답 마감일  
  DATE(TDR.TDR_RSPS_BY_DTT)                                       AS dt_04_tender_due,
  -- ── [5] 거리 기반 예정 출발일  
  DATE(L.STRD_DTT)                                                AS dt_05_sched_depart,
  -- ── [6] 거리 기반 예정 도착일 (ETA)  
  DATE(L.END_DTT)                                                 AS dt_06_sched_arrive,
  -- ── [7] 창고 릴리즈일 (WH Release)  
  DATE(GL.RELEASE_TO_WH_DATE)                                     AS dt_07_wh_release,
  -- ── [8] 실제 출고일 (Ship Confirm)  
  DATE(GL.SHIPPING_DATE)                                          AS dt_08_ship_confirm,
  -- ── [9] 출고 완료일 (LD_LEG_T.SHPD_DTT)  
  DATE(L.SHPD_DTT)                                                AS dt_09_shipped,
  -- ── [10] RAD (요청 도착일)  
  DATE(S.ORI_DELY_TO)                                             AS dt_10_rad,
  -- ── 소요일 계산 (DATE_DIFF, 단위: 일)  
  DATE_DIFF(DATE(S.PICK_RELEASE_DATE), DATE(S.SALES_ORDER_DATE), DAY)      AS days_order_to_pick,
  DATE_DIFF(DATE(GL.LOAD_CREATION_DATE), DATE(S.PICK_RELEASE_DATE), DAY)   AS days_pick_to_load_create,
  DATE_DIFF(DATE(TDR.TDR_RSPS_BY_DTT), DATE(GL.LOAD_CREATION_DATE), DAY)   AS days_load_to_tender_due,
  DATE_DIFF(DATE(GL.RELEASE_TO_WH_DATE), DATE(GL.LOAD_CREATION_DATE), DAY) AS days_load_to_wh_release,
  DATE_DIFF(DATE(GL.SHIPPING_DATE), DATE(GL.RELEASE_TO_WH_DATE), DAY)      AS days_wh_release_to_ship,
  DATE_DIFF(DATE(GL.SHIPPING_DATE), DATE(S.PICK_RELEASE_DATE), DAY)        AS days_pick_to_ship_total,
  DATE_DIFF(DATE(S.ORI_DELY_TO), DATE(GL.SHIPPING_DATE), DAY)              AS days_ship_to_rad_margin,
  -- ── RAD 준수 여부  
  CASE
    WHEN GL.SHIPPING_DATE IS NULL                                  THEN 'Not Shipped'
    WHEN S.ORI_DELY_TO    IS NULL                                  THEN 'No RAD'
    WHEN DATE(GL.SHIPPING_DATE) <= DATE(S.ORI_DELY_TO)            THEN 'On-Time'
    ELSE 'Late'
  END                                                             AS rad_compliance
FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_LOAD_OS` GL   -- ← 기준 테이블
-- Shipment 마스터 (수주일·Pick Release·RAD)
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS` S
  ON GL.SHIPMENTNUMBER = S.SHIPMENTNUMBER
-- Load 마스터 (운송사·차량·예정출발도착·출고완료)
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__LD_LEG_T_OS` L
  ON GL.LD_LEG_ID = L.LD_LEG_ID
-- Tender 응답 마감일 (Load당 최신 1건)
LEFT JOIN (
  SELECT LD_LEG_ID, MAX(TDR_RSPS_BY_DTT) AS TDR_RSPS_BY_DTT
  FROM `pjt-lge-edl-ob.OB_00030.V_L0TMS__TDR_REQ_T_OS`
  GROUP BY LD_LEG_ID
) TDR
  ON GL.LD_LEG_ID = TDR.LD_LEG_ID
-- WMS 상태 코드 명칭
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__TB_GTM_CODE_MST_OS` WMS
  ON WMS.CD_TYPE = 'WMS_STATUS'
 AND WMS.CD      = GL.LOAD_STATUS
-- Load 상태 단축 설명
LEFT JOIN `pjt-lge-edl-ob.OB_00030.V_L0TMS__STAT_T_OS` ST
  ON ST.STAT_ID = L.CUR_OPTLSTAT_ID
-- 환율 (Load 생성월 기준, 로컬통화 → USD)
LEFT JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_FX_MM FX
  ON FX.CURRENCY_CD = GL.CURRENCY_CODE
 AND FX.BASE_YYMM   = FORMAT_DATE('%Y%m', DATE(GL.LOAD_CREATION_DATE))
WHERE DATE(GL.LOAD_CREATION_DATE) >= @start_date
  AND DATE(GL.LOAD_CREATION_DATE) < @end_date
  AND (@legal_entity = 'ALL' OR GL.LEGAL_ENTITY_NAME = @legal_entity)
  AND GL.CANCEL_FLAG = 'N'   
  -- AND GL.LD_LEG_SEQ_NO = 100    -- Load당 첫 번째 Leg 기준 (중복 제거)
ORDER BY GL.LOAD_CREATION_DATE
    , GL.LD_LEG_ID
    , GL.SHIPMENTNUMBER
"""

# ============================================================================
# 법인(Subsidiary) 마스터 목록 조회
# ============================================================================

QUERY_SUBSDR_LIST = """
-- 법인 마스터 목록 (D_SUBSDR_MST)
SELECT
  SUBSDR_NAME,
  REGION_NAME,
  DISPLAY_NAME
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SUBSDR_MST
ORDER BY REGION_NAME, SUBSDR_NAME
"""

# ── 환경별 PROJECT_ID / DATASET_ID 치환 ──────────────────────────────────────
# .env.dev 에 PROJECT_ID / DATASET_ID 가 설정된 경우 하드코딩된 값을 대체합니다.
_bq_project = os.getenv('PROJECT_ID', 'pjt-lge-oversea-sales-olap')
_bq_dataset = os.getenv('DATASET_ID', 'SCM_OLAP')
_BQ_OLD = '`pjt-lge-oversea-sales-olap`.SCM_OLAP'
_BQ_NEW = f'`{_bq_project}`.{_bq_dataset}'

if _BQ_OLD != _BQ_NEW:
    import sys as _sys
    _mod = _sys.modules[__name__]
    for _qname in [n for n in vars(_mod) if n.startswith('QUERY_')]:
        setattr(_mod, _qname, getattr(_mod, _qname).replace(_BQ_OLD, _BQ_NEW))
