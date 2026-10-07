"""
Inventory 쿼리 (M_CURINV_SNAPSHOT_S) - Current Stock Summary / Raw
"""
import os

QUERY_INV_CURRENT_SUMMARY = """
-- 현재고 요약 (최신 배치 기준)
WITH 
mdl_div AS (
  -- 모델 → Division 매핑 (MDL_SFFX_CD가 PK이므로 중복 없음)
  SELECT MDL_SFFX_CD, DIV_NM
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST
  WHERE MDL_SFFX_CD IS NOT NULL
)
SELECT
  ANY_VALUE(t.P_PTT)                           AS p_ptt,
  COUNT(*)                                     AS row_cnt,
  COUNT(DISTINCT t.MODEL_CODE)                 AS model_cnt,
  ROUND(SUM(CAST(t.ONHAND_QTY    AS FLOAT64)), 0) AS onhand_qty,
  ROUND(SUM(CAST(t.AVAILABLE_QTY AS FLOAT64)), 0) AS available_qty,
  ROUND(SUM(CAST(t.BOOKED_QTY    AS FLOAT64)), 0) AS booked_qty,
  ROUND(SUM(CAST(t.TOTAL_HOLD_QTY AS FLOAT64)), 0) AS hold_qty
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S t
LEFT JOIN mdl_div m ON t.MODEL_CODE = m.MDL_SFFX_CD
WHERE (@legal_entity = 'ALL' OR t.LEGAL_ENTITY_NAME = @legal_entity)
  AND (@division = '[ALL]' OR m.DIV_NM = @division)
"""

QUERY_INV_CURRENT_RAW = """
-- 현재고 상세 (최신 배치 기준, 모델/창고 단위)
WITH 
mdl_div AS (
  -- 모델 → Division 매핑 (MDL_SFFX_CD가 PK이므로 중복 없음)
  SELECT MDL_SFFX_CD, DIV_NM
  FROM `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST
  WHERE MDL_SFFX_CD IS NOT NULL
)
SELECT
  t.P_PTT,
  t.LEGAL_ENTITY_NAME,
  m.DIV_NM,
  t.INVENTORY_ORGANIZATION_CODE,
  t.SUBINVENTORY_CODE,
  t.SUBINVENTORY_NAME,
  t.MODEL_CATEGORY_NAME,
  t.MODEL_CODE,
  t.ITEM_STATUS_CODE,
  ROUND(SUM(CAST(t.ONHAND_QTY AS FLOAT64)), 0)       AS ONHAND_QTY,
  ROUND(SUM(CAST(t.AVAILABLE_QTY AS FLOAT64)), 0)    AS AVAILABLE_QTY,
  ROUND(SUM(CAST(t.BOOKED_QTY AS FLOAT64)), 0)       AS BOOKED_QTY,
  ROUND(SUM(CAST(t.TOTAL_HOLD_QTY AS FLOAT64)), 0)   AS TOTAL_HOLD_QTY,
  ROUND(SUM(CAST(t.INTRANSIT_OUT_QTY AS FLOAT64)), 0) AS INTRANSIT_OUT_QTY,
  ROUND(SUM(CAST(t.PO_ORDERED_QTY AS FLOAT64)), 0)   AS PO_ORDERED_QTY
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S t
LEFT JOIN mdl_div m ON t.MODEL_CODE = m.MDL_SFFX_CD
WHERE (@legal_entity = 'ALL' OR t.LEGAL_ENTITY_NAME = @legal_entity)
  AND (@division = '[ALL]' OR m.DIV_NM = @division)
GROUP BY
  t.P_PTT,
  t.LEGAL_ENTITY_NAME,
  m.DIV_NM,
  t.INVENTORY_ORGANIZATION_CODE,
  t.SUBINVENTORY_CODE,
  t.SUBINVENTORY_NAME,
  t.MODEL_CATEGORY_NAME,
  t.MODEL_CODE,
  t.ITEM_STATUS_CODE
HAVING
  COALESCE(SUM(CAST(t.ONHAND_QTY AS FLOAT64)), 0) != 0
  OR COALESCE(SUM(CAST(t.AVAILABLE_QTY AS FLOAT64)), 0) != 0
ORDER BY ONHAND_QTY DESC, AVAILABLE_QTY DESC
LIMIT 500000
"""

QUERY_INV_DATA_TIMESTAMP = """
-- 인벤토리 데이터 최신 기준시각
-- CREATION_DATE는 KST(+09:00) 기준 TIMESTAMP이므로 UTC로 변환해 반환
SELECT
  TIMESTAMP_SUB(MAX(CREATION_DATE), INTERVAL 9 HOUR) AS data_timestamp_utc
FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_CURINV_SNAPSHOT_S
WHERE (@legal_entity = 'ALL' OR LEGAL_ENTITY_NAME = @legal_entity)
"""

# ── 환경별 PROJECT_ID / DATASET_ID 치환 ──────────────────────────────────────
_bq_project = os.getenv('PROJECT_ID', 'pjt-lge-oversea-sales-olap')
_bq_dataset = os.getenv('DATASET_ID', 'SCM_OLAP')
_BQ_OLD = '`pjt-lge-oversea-sales-olap`.SCM_OLAP'
_BQ_NEW = f'`{_bq_project}`.{_bq_dataset}'

if _BQ_OLD != _BQ_NEW:
    import sys as _sys
    _mod = _sys.modules[__name__]
    for _qname in [n for n in vars(_mod) if n.startswith('QUERY_')]:
        setattr(_mod, _qname, getattr(_mod, _qname).replace(_BQ_OLD, _BQ_NEW))
