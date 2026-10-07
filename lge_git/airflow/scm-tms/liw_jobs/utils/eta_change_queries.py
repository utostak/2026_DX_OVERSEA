"""
jobs/utils/eta_change_queries.py
─────────────────────────────────────────────────────────────
해상배송(M_SEA_SHIPMENT_INFO)의 최종 목적지 ETA(FDEST_ETA_DATE)가
변경된 컨테이너 목록과, 해당 컨테이너의 PO 라인 정보를 조회하는 쿼리 모음.
BF_FDEST_ETA_DATE / CHANGE_YN / DFF_DAYS 는 테이블에 직접 저장된 컬럼을 사용.
"""
import os

PROJECT = "pjt-lge-oversea-sales-olap"

# ── 1) 배송 목록 (PO 라인 단위) + FDEST ETA 변경 여부 ─────────────────
#    CHANGE_YN = 'Y' 인 행이 FDEST ETA 가 변경된 항목.
#    BF_FDEST_ETA_DATE / DFF_DAYS 는 M_SEA_SHIPMENT_INFO 에 저장된 값 사용.
ETA_CHANGE_QUERY = f"""
WITH T_LIST AS (
    SELECT *
      FROM `{PROJECT}`.SCM_OLAP.M_SEA_SHIPMENT_INFO
     WHERE P_PPT = @p_ppt
)
SELECT
       T.P_PPT
     , T.SUBSDR_NM
     , P.PO_NO
     , P.PO_LINE_NO
     , P.TO_INV_ORG
     , P.PO_STATUS
     , COALESCE( PG.PRODUCT_GROUP_CODE,'None') AS PRODUCT_GROUP_CODE
     , P.MDL_SFFX_CD
     , P.QTY
     , T.HOUSE_BL_NO
     , T.BL_DATE
     , T.CONTAINER_NO
     , T.CONTAINER_SIZE
     , T.MASTER_BL_NO
     , T.INVOICE_NO
     , T.INVOICE_DATE
     , T.POL_ETD_DATE
     , T.POL_ATD_DATE
     , T.POD_ETA_DATE
     , T.POD_ATA_DATE
     , T.CY1_ETA_DATE
     , T.CY1_ATA_DATE
     , T.CY1_ETD_DATE
     , T.CY1_ATD_DATE
     , T.FDEST_ETA_DATE
     , T.BF_FDEST_ETA_DATE
     , T.CHANGE_YN
     , T.DFF_DAYS
  FROM T_LIST T
  JOIN `{PROJECT}`.SCM_OLAP.M_PO_TRACKING P
    ON T.CONTAINER_NO = P.CNTR_NO
   AND T.HOUSE_BL_NO  = P.BL_NO
   AND P.PO_STATUS NOT IN ('Cancelled', 'F Dest Arrival')
  LEFT JOIN `{PROJECT}`.PRD_OLAP.D_NPT_MDL_NEW_MST M
    ON P.MDL_SFFX_CD = M.MDL_SFFX_CD
  LEFT JOIN `{PROJECT}`.SCM_OLAP.REF_D_PRODUCT_MST PG
    ON P.SUBSDR_NM    = PG.SUBSDR_NAME
   AND M.PROD_LVL4_CD = PG.PRODUCT_CODE
 WHERE 1=1
   AND T.SUBSDR_NM = @subsdr_nm
   -- FDEST ETA 가 실제로 변경된 라인만 조회
   AND T.CHANGE_YN = 'Y'
   -- 이전 FDEST ETA 가 없다가(NULL) 새로 생긴 라인은 제외
   AND T.BF_FDEST_ETA_DATE IS NOT NULL
   AND T.FDEST_ETA_DATE     IS NOT NULL
 ORDER BY T.DFF_DAYS DESC
"""

# ── 환경별 PROJECT_ID / DATASET_ID 치환 ──────────────────────────────────────
# .env 에 PROJECT_ID / DATASET_ID 가 설정된 경우 하드코딩된 값을 대체합니다.
from utils.config import getenv
_bq_project = getenv('PROJECT_ID', 'pjt-lge-oversea-sales-olap')
_bq_dataset = getenv('DATASET_ID', 'SCM_OLAP')
_BQ_OLD = '`pjt-lge-oversea-sales-olap`.SCM_OLAP'
_BQ_NEW = f'`{_bq_project}`.{_bq_dataset}'

if _BQ_OLD != _BQ_NEW:
    import sys as _sys
    _mod = _sys.modules[__name__]
    for _qname in [n for n in vars(_mod) if n.endswith('_QUERY')]:
        setattr(_mod, _qname, getattr(_mod, _qname).replace(_BQ_OLD, _BQ_NEW))
