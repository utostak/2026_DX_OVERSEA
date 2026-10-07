"""
PO Tracking 쿼리 (M_PO_TRACKING) - Active Flow / Active Raw
po_status 단계:
  On factory Processing → Factory Ship Out → Intransit (POL~POD)
  → Intransit (POD~FDEST) → F Dest Arrival
※ 'Cancelled' 및 'F Dest Arrival' 은 Active 대상에서 제외
"""
import os

# ─────────────────────────────────────────────────────────────────────────────
# Active PO 파이프라인 단계별 집계 (System Flow & Performance)
# ─────────────────────────────────────────────────────────────────────────────
QUERY_PO_ACTIVE_FLOW = """
-- Active PO 파이프라인 단계별 현황 집계
WITH lt_benchmark AS (
  -- ── Lead Time 벤치마크: 완료 건(F Dest Arrival) 기준으로 계산 ──
  SELECT
    ROUND(AVG(DATE_DIFF(DATE(FACTORY_SHIP_OUT_DATE), DATE(PO_CREATION_DATE), DAY)), 1) AS avg_po_factory_lt,
    ROUND(AVG(DATE_DIFF(DATE(POL_ATD_DATE), DATE(FACTORY_SHIP_OUT_DATE), DAY)), 1)    AS avg_ship_wh_lt,
    ROUND(AVG(DATE_DIFF(DATE(POD_ATA_DATE), DATE(POL_ATD_DATE), DAY)), 1)             AS avg_pod_lt,
    ROUND(AVG(DATE_DIFF(DATE(FDEST_ATA_DATE), DATE(POD_ATA_DATE), DAY)), 1)           AS avg_fdest_pod_lt
  FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING
  WHERE TRIM(PO_STATUS) = 'F Dest Arrival'
    AND (@legal_entity = 'ALL' OR SUBSDR_NM = @legal_entity)
    AND (@division = '[ALL]' OR DIVISION_NAME = @division)
)
SELECT
  TRIM(t.PO_STATUS)                       AS po_status,
  COUNT(*)                                AS line_cnt,
  COUNT(DISTINCT t.BL_NO)                 AS bl_cnt,
  COUNT(DISTINCT t.INVOICE_NO)            AS invoice_cnt,
  SUM(t.QTY)                              AS total_qty,
  ANY_VALUE(b.avg_po_factory_lt)          AS avg_po_factory_lt,
  ANY_VALUE(b.avg_ship_wh_lt)             AS avg_ship_wh_lt,
  ANY_VALUE(b.avg_pod_lt)                 AS avg_pod_lt,
  ANY_VALUE(b.avg_fdest_pod_lt)           AS avg_fdest_pod_lt,
  COUNTIF(t.RSD_DATE IS NOT NULL AND DATE(t.RSD_DATE) < CURRENT_DATE()) AS over_rsd_cnt
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING t
CROSS JOIN lt_benchmark b
WHERE TRIM(t.PO_STATUS) NOT IN ('Cancelled', 'F Dest Arrival')
  AND (@legal_entity = 'ALL' OR t.SUBSDR_NM = @legal_entity)
  AND (@division = '[ALL]' OR t.DIVISION_NAME = @division)
GROUP BY TRIM(t.PO_STATUS)
ORDER BY po_status
"""

# ─────────────────────────────────────────────────────────────────────────────
# Active PO Raw 데이터 (AG Grid)
# ─────────────────────────────────────────────────────────────────────────────
QUERY_PO_ACTIVE_RAW = """
-- Active PO Raw 데이터 (현재 진행중인 PO 전체)
WITH T_SEA_LATEST AS (
  -- M_SEA_SHIPMENT_INFO 최신 스냅샷 (가장 최근 P_PPT)
  SELECT
    CONTAINER_NO,
    HOUSE_BL_NO,
    BF_FDEST_ETA_DATE,
    CHANGE_YN,
    DFF_DAYS
  FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SEA_SHIPMENT_INFO
  WHERE P_PPT = (
    SELECT MAX(P_PPT)
    FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SEA_SHIPMENT_INFO
  )
)
SELECT
  T.DIV_CD                              AS div_cd,
  T.DIVISION_NAME                       AS division_name,
  T.FROM_SITE_NAME                      AS from_site_name,
  T.TO_SITE_NAME                        AS to_site_name,
  T.TO_SUBSDR_CD                        AS to_subsdr_cd,
  T.SUBSDR_NM                           AS subsdr_nm,
  T.SHIP_TO_CUSTOMER                    AS ship_to_customer,
  T.BIZ_TYPE                            AS biz_type,
  T.OTD_BIZ_TYPE                        AS otd_biz_type,
  T.MDL_SFFX_CD                         AS mdl_sffx_cd,
  DATE(T.RSD_DATE)                      AS rsd_date,
  T.BL_NO                               AS bl_no,
  DATE(T.BL_DATE)                       AS bl_date,
  T.MASTER_BL_NO                        AS master_bl_no,
  T.INVOICE_NO                          AS invoice_no,
  DATE(T.INVOICE_DATE)                  AS invoice_date,
  T.CNTR_NO                             AS cntr_no,
  T.CNTR_TYPE                           AS cntr_type,
  T.SHIPPING_METHOD                     AS shipping_method,
  T.PO_NO                               AS po_no,
  T.PO_LINE_NO                          AS po_line_no,
  TRIM(T.PO_STATUS)                     AS po_status,
  DATE(T.PO_CREATION_DATE)             AS po_creation_date,
  T.QTY                                 AS qty,
  DATE(T.STUFFING_DATE)                 AS stuffing_date,
  DATE(T.CC_DATE)                       AS cc_date,
  DATE(T.FACTORY_SHIP_OUT_DATE)         AS factory_ship_out_date,
  DATE(T.POL_ETD_DATE)                  AS pol_etd_date,
  DATE(T.POL_ATD_DATE)                  AS pol_atd_date,
  DATE(T.POD_ETA_DATE)                  AS pod_eta_date,
  DATE(T.POD_ATA_DATE)                  AS pod_ata_date,
  DATE(T.CY1_ETA_DATE)                  AS cy1_eta_date,
  DATE(T.CY1_ATA_DATE)                  AS cy1_ata_date,
  DATE(T.CY1_ETD_DATE)                  AS cy1_etd_date,
  DATE(T.CY1_ATD_DATE)                  AS cy1_atd_date,
  DATE(T.FDEST_ETA_DATE)                AS fdest_eta_date,
  DATE(T.FDEST_ATA_DATE)                AS fdest_ata_date,
  T.ZCCREQDAT                            AS ZCCREQDAT,
  T.ZIMDEC                              AS zimdec,
  T.ZCCCOMPT                            AS zcccompt,
  T.ZCCSTCD                             AS zccstcd,
  T.ZCCSTCD_TX                          AS zccstcd_tx,
  T.PO_DETAIL_STATUS                      AS PO_DETAIL_STATUS,
  -- 진행 단계 정렬용 순번
  CASE TRIM(T.PO_STATUS)
    WHEN 'On factory Processing'    THEN 1
    WHEN 'Factory Ship Out'         THEN 2
    WHEN 'Intransit (POL~POD)'      THEN 3
    WHEN 'Intransit (POD~FDEST)'    THEN 4
    WHEN 'F Dest Arrival'           THEN 5
    ELSE 9
  END                                   AS po_status_seq,
  -- RSD 경과 여부 (현재일 기준)
  CASE
    WHEN T.RSD_DATE IS NOT NULL AND DATE(T.RSD_DATE) < CURRENT_DATE() THEN 'Y'
    ELSE NULL
  END                                   AS risk_alert,
  -- RSD 까지 잔여일 (양수=여유, 음수=경과)
  CASE WHEN T.RSD_DATE IS NOT NULL
    THEN DATE_DIFF(DATE(T.RSD_DATE), CURRENT_DATE(), DAY)
  END                                   AS days_to_rsd,
  -- RSD vs 예상 도착일 여유
  DATE_DIFF(DATE(T.RSD_DATE), DATE(T.FDEST_ETA_DATE), DAY) AS rsd_margin_by_est,
  -- ETA 변경 이력 (M_SEA_SHIPMENT_INFO)
  DATE(S.BF_FDEST_ETA_DATE)            AS bf_fdest_eta_date,
  S.CHANGE_YN                          AS change_yn,
  S.DFF_DAYS                           AS dff_days
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING T
LEFT JOIN T_SEA_LATEST S
  ON T.CNTR_NO = S.CONTAINER_NO
 AND T.BL_NO   = S.HOUSE_BL_NO
WHERE TRIM(T.PO_STATUS) NOT IN ('Cancelled', 'F Dest Arrival')
  AND (@legal_entity = 'ALL' OR T.SUBSDR_NM = @legal_entity)
  AND (@division = '[ALL]' OR T.DIVISION_NAME = @division)
ORDER BY
  po_status_seq,
  rsd_date ASC
LIMIT 500000
"""

QUERY_PO_DATA_TIMESTAMP = """
-- PO 데이터 최신 기준시각
-- ZLOADTMP9은 'YYYYMMDDHHmmss' 형식의 STRING, KST 기준이므로 UTC로 변환해 반환
SELECT
  TIMESTAMP_SUB(
    PARSE_TIMESTAMP('%Y%m%d%H%M%S', MAX(TRIM(ZLOADTMP9))),
    INTERVAL 9 HOUR
  ) AS data_timestamp_utc
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_PO_TRACKING
WHERE 1=1 
  AND (@legal_entity = 'ALL' OR SUBSDR_NM = @legal_entity)
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
