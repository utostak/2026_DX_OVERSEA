"""
Outbound Delivery Delay query for LIW email notification.

Target:
- LGEPH Active Orders
- Flow stage remains SHIPPED
- Open order
- WMS shipped date exists
- Estimated arrival date has passed
- PO line level is not used; result is Sales Order Line level

Parameters:
- @subsdr_nm
- @base_date (YYYY-MM-DD)
"""

from utils.config import getenv


PROJECT = getenv(
    'PROJECT_ID',
    'pjt-lge-oversea-sales-olap',
)

DATASET = getenv(
    'DATASET_ID',
    'SCM_OLAP',
)


OUTBOUND_DELAY_QUERY = f"""
SELECT
      T.DIV_NM AS PRODUCT_GROUP_CODE
    , T.SALES_ORDER_LINE_NO
    , T.MODEL_CODE
    , DATE(T.WMS_SHIPPED_DATE) AS WMS_SHIPPED_DATE
    , T.SALES_ORDER_NO
    , DATE(T.EST_ARRIVAL_DATE) AS EST_ARRIVAL_DATE
    , DATE_DIFF(
          DATE(@base_date),
          DATE(T.EST_ARRIVAL_DATE),
          DAY
      ) AS DELAY_DAYS
FROM `{PROJECT}`.{DATASET}.M_SO_LINE T
WHERE T.SUBSDR_NAME = @subsdr_nm
  AND UPPER(TRIM(T.PROGRESS_STATUS)) = 'SHIPPED'
  AND T.OPEN_FLAG = 'Y'
  AND T.WMS_SHIPPED_DATE IS NOT NULL
  AND T.EST_ARRIVAL_DATE IS NOT NULL
  AND DATE(T.EST_ARRIVAL_DATE) < DATE(@base_date)
ORDER BY
      PRODUCT_GROUP_CODE
    , T.SALES_ORDER_LINE_NO
    , T.MODEL_CODE
    , T.WMS_SHIPPED_DATE
    , T.SALES_ORDER_NO
"""
