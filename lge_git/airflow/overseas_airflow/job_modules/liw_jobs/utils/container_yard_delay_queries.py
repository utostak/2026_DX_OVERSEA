"""
Container Yard Delay Notification query.

- Source: BigQuery SCM_OLAP.M_PO_TRACKING
- Scope: LGEPH active PO lines
- Condition: CY ATA exists, CY ATD is null, waiting days meet configured threshold
- Output grain: PO line, matching the existing ETA digest email
"""
import os

PROJECT = "pjt-lge-oversea-sales-olap"

CONTAINER_YARD_DELAY_QUERY = f"""
SELECT
      COALESCE(PG.PRODUCT_GROUP_CODE, 'None') AS PRODUCT_GROUP_CODE
    , T.TO_INV_ORG
    , T.MDL_SFFX_CD
    , T.QTY
    , T.CNTR_NO AS CONTAINER_NO
    , DATE(T.CY1_ATA_DATE) AS CY1_ATA_DATE
    , DATE(T.CY1_ETD_DATE) AS CY1_ETD_DATE
    , DATE_DIFF(
          CURRENT_DATE('Asia/Seoul'),
          DATE(T.CY1_ATA_DATE),
          DAY
      ) AS WAIT_DAYS
FROM `{PROJECT}`.SCM_OLAP.M_PO_TRACKING T
LEFT JOIN `{PROJECT}`.PRD_OLAP.D_NPT_MDL_NEW_MST M
  ON T.MDL_SFFX_CD = M.MDL_SFFX_CD
LEFT JOIN `{PROJECT}`.SCM_OLAP.REF_D_PRODUCT_MST PG
  ON T.SUBSDR_NM = PG.SUBSDR_NAME
 AND M.PROD_LVL4_CD = PG.PRODUCT_CODE
WHERE T.SUBSDR_NM = @subsdr_nm
  AND TRIM(T.PO_STATUS) NOT IN ('Cancelled', 'F Dest Arrival')
  AND T.CY1_ATA_DATE IS NOT NULL
  AND T.CY1_ATD_DATE IS NULL
  AND DATE_DIFF(
        CURRENT_DATE('Asia/Seoul'),
        DATE(T.CY1_ATA_DATE),
        DAY
      ) >= @wait_days
ORDER BY
      PRODUCT_GROUP_CODE
    , T.TO_INV_ORG
    , T.MDL_SFFX_CD
    , WAIT_DAYS DESC
    , T.CNTR_NO
"""

# Replace the default SCM project/dataset when configured for another environment.
_bq_project = os.getenv('PROJECT_ID', PROJECT)
_bq_dataset = os.getenv('DATASET_ID', 'SCM_OLAP')
_BQ_OLD = f'`{PROJECT}`.SCM_OLAP'
_BQ_NEW = f'`{_bq_project}`.{_bq_dataset}'
if _BQ_OLD != _BQ_NEW:
    CONTAINER_YARD_DELAY_QUERY = CONTAINER_YARD_DELAY_QUERY.replace(_BQ_OLD, _BQ_NEW)
