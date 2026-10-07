"""
OBS LMD 쿼리 (obs_lmd.html 전용)
  - QUERY_OBS_IRAD          : 최초 배송요구일 준수율 (IRAD%)
  - QUERY_OBS_LT            : 배송 리드타임 (배송LT / 주문전송LT)
  - QUERY_OBS_RAW           : 화면 하단 Raw Data 테이블
  - QUERY_OBS_LMSP_LIST     : 3PL(LMSP) 필터 옵션
"""

QUERY_OBS_IRAD = """
-- 최초 배송요구일 준수율 (IRAD% = On-time + Early)
-- 기준일자: ACTUAL_ARRIAVL_DATE (실제 도착일) — IOD_CONFIRM_DATE는 확인 입력이 실도착보다
--   평균 18.5시간(59%는 익일) 늦게 찍히는 케이스가 많아 준수율을 과소평가하므로 제외
-- period(x축)만 IOD_CONFIRM_DATE 기준으로 유지 (LT 차트와 x축 정렬 목적, QUERY_OBS_LT와 동일)
-- 요구일자: UPDATED_DELIVERY_APPT_DATE_TIME 우선, 없으면 ORIGINAL_DELIVERY_APPT_DATE_TIME 로 대체
--   (ORIGINAL 쪽에 연도가 잘못 찍힌 이상치 케이스가 발견돼 UPDATED를 우선하도록 순서 변경)
WITH PARAM AS (
  SELECT REPLACE(@base_ym, '-', '')                                    AS base_ym     -- 'YYYY-MM' → 'YYYYMM'
       , CAST(CAST(SUBSTR(REPLACE(@base_ym, '-', ''),1,4) AS INT64) - 1 AS STRING)     AS prev_year   -- 작년(4자리)
       , @legal_entity                                                  AS legal_entity -- 'LGETH|LGEPS|LGEVH' 형태 또는 'ALL'
       , @division                                                      AS division     -- DIV_NM 값 또는 '[ALL]'
       , @lmsp_name                                                     AS lmsp_name    -- LMSP_NAME 값 또는 '[ALL]'
),
OBS AS (
  SELECT CASE WHEN SUBSTR(T.IOD_CONFIRM_DATE,1,4) = P.prev_year
                   AND SUBSTR(T.IOD_CONFIRM_DATE,5,2) IN ('10','11','12')
              THEN CONCAT(SUBSTR(P.prev_year,3,2), '.4Q')
              WHEN SUBSTR(T.IOD_CONFIRM_DATE,1,6) <= P.base_ym
                   AND SUBSTR(T.IOD_CONFIRM_DATE,1,4) = SUBSTR(P.base_ym,1,4)
              THEN CONCAT(SUBSTR(T.IOD_CONFIRM_DATE,3,2), '.', CAST(CAST(SUBSTR(T.IOD_CONFIRM_DATE,5,2) AS INT64) AS STRING), '월')
         ELSE NULL
         END AS period
       , COALESCE(T.UPDATED_DELIVERY_APPT_DATE_TIME, T.ORIGINAL_DELIVERY_APPT_DATE_TIME) AS req_date
       , T.IOD_CONFIRM_DATE
       , T.ACTUAL_ARRIAVL_DATE
    FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_OBS_SO_LINE T, PARAM P
    LEFT JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST M
      ON T.MODEL_SUFFIX = M.MDL_SFFX_CD
   WHERE T.ORDER_STATUS = 'Completed'
     AND (P.legal_entity = 'ALL'    OR T.SUBSIDIARY IN UNNEST(SPLIT(P.legal_entity, '|')))
     AND (P.division     = '[ALL]' OR M.DIV_NM     = P.division)
     AND (P.lmsp_name    = '[ALL]' OR T.LMSP_NAME  = P.lmsp_name)
)
  SELECT period
       , COUNT(*) AS total_cnt
       , ROUND(COUNTIF(SUBSTR(ACTUAL_ARRIAVL_DATE,1,8) <= SUBSTR(req_date,1,8)) / COUNT(*) * 100, 0) AS irad_pct
    FROM OBS
   WHERE period   IS NOT NULL
     AND req_date IS NOT NULL
     AND ACTUAL_ARRIAVL_DATE IS NOT NULL
   GROUP BY period
   ORDER BY CASE WHEN period LIKE '%4Q' THEN '0' ELSE '1' END, period
"""

QUERY_OBS_LT = """
-- 배송 리드타임: 배송LT(Pick Release → 실제 도착일 ACTUAL_ARRIAVL_DATE) / 주문전송LT(주문생성 → Pick Release)
-- 주문생성 시점: OBS_ORDER_DATE 우선, 없으면 ORDER_DATE 로 대체
--   (OBS_ORDER_DATE 가 11.2% NULL인데, 그 케이스 전부 ORDER_DATE 는 있고 평균 0.17일 차이라 사실상 동일 시점)
-- 단위: 일(Day) — 시간(HOUR) 단위로 계산 후 24로 나눠 소수점 1자리까지 표시
-- period 축은 QUERY_OBS_IRAD 와 동일하게 IOD_CONFIRM_DATE 기준으로 맞춤 (두 차트 x축 일치)
-- 음수 LT(초기 데이터 적재 이슈로 발생)는 0으로 클램프
WITH PARAM AS (
  SELECT REPLACE(@base_ym, '-', '')                                    AS base_ym     -- 'YYYY-MM' → 'YYYYMM'
       , CAST(CAST(SUBSTR(REPLACE(@base_ym, '-', ''),1,4) AS INT64) - 1 AS STRING)     AS prev_year   -- 작년(4자리)
       , @legal_entity                                                  AS legal_entity -- 'LGETH|LGEPS|LGEVH' 형태 또는 'ALL'
       , @division                                                      AS division     -- DIV_NM 값 또는 '[ALL]'
       , @lmsp_name                                                     AS lmsp_name    -- LMSP_NAME 값 또는 '[ALL]'
),
OBS AS (
  SELECT CASE WHEN SUBSTR(T.IOD_CONFIRM_DATE,1,4) = P.prev_year
                   AND SUBSTR(T.IOD_CONFIRM_DATE,5,2) IN ('10','11','12')
              THEN CONCAT(SUBSTR(P.prev_year,3,2), '.4Q')
              WHEN SUBSTR(T.IOD_CONFIRM_DATE,1,6) <= P.base_ym
                   AND SUBSTR(T.IOD_CONFIRM_DATE,1,4) = SUBSTR(P.base_ym,1,4)
              THEN CONCAT(SUBSTR(T.IOD_CONFIRM_DATE,3,2), '.', CAST(CAST(SUBSTR(T.IOD_CONFIRM_DATE,5,2) AS INT64) AS STRING), '월')
         ELSE NULL
         END AS period
       , COALESCE(T.OBS_ORDER_DATE, T.ORDER_DATE) AS ORDER_TXN_DATE
       , T.PICK_RELEASED_DATE_TIME
       , T.IOD_CONFIRM_DATE
       , T.ACTUAL_ARRIAVL_DATE
    FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_OBS_SO_LINE T, PARAM P
    LEFT JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST M
      ON T.MODEL_SUFFIX = M.MDL_SFFX_CD
   WHERE T.ORDER_STATUS = 'Completed'
     AND (P.legal_entity = 'ALL'    OR T.SUBSIDIARY IN UNNEST(SPLIT(P.legal_entity, '|')))
     AND (P.division     = '[ALL]' OR M.DIV_NM     = P.division)
     AND (P.lmsp_name    = '[ALL]' OR T.LMSP_NAME  = P.lmsp_name)
     AND COALESCE(T.OBS_ORDER_DATE, T.ORDER_DATE) IS NOT NULL
     AND T.PICK_RELEASED_DATE_TIME IS NOT NULL
     AND T.IOD_CONFIRM_DATE        IS NOT NULL
     AND T.ACTUAL_ARRIAVL_DATE     IS NOT NULL
)
  SELECT period
       , COUNT(*) AS total_cnt
       , ROUND(AVG(GREATEST(TIMESTAMP_DIFF(PARSE_TIMESTAMP('%Y%m%d%H%M', ACTUAL_ARRIAVL_DATE),
                                            PARSE_TIMESTAMP('%Y%m%d%H%M', PICK_RELEASED_DATE_TIME), HOUR), 0)) / 24.0, 1) AS delivery_lt_day
       , ROUND(AVG(GREATEST(TIMESTAMP_DIFF(PARSE_TIMESTAMP('%Y%m%d%H%M', PICK_RELEASED_DATE_TIME),
                                            PARSE_TIMESTAMP('%Y%m%d%H%M', ORDER_TXN_DATE), HOUR), 0)) / 24.0, 1) AS order_pickrelease_lt_day
    FROM OBS
   WHERE period IS NOT NULL
   GROUP BY period
   ORDER BY CASE WHEN period LIKE '%4Q' THEN '0' ELSE '1' END, period
"""

QUERY_OBS_RAW = """
-- Raw Data 그리드: 위 두 차트(IRAD%, 배송LT/주문전송LT) 계산에 쓰이는 원본 컬럼 + 계산값
-- 기준월(@base_ym) 한 달치만 노출 (전체 기간 조회 시 너무 많아짐) — 건수 제한은 없음, AG Grid 클라이언트 페이지네이션으로 처리
WITH PARAM AS (
  SELECT REPLACE(@base_ym, '-', '') AS base_ym
       , @legal_entity              AS legal_entity
       , @division                  AS division
       , @lmsp_name                 AS lmsp_name
)
  SELECT T.OBS_ORDER_NO
       , T.OBS_ORDER_LINE_NO
       , T.ORDER_TYPE
       , T.LMSP_NAME
       , T.GERP_ORDER_NO
       , T.SHIPMENT_ID
       , M.DIV_NM                                AS DIVISION
       , T.SUB_DIVISION
       , T.MODEL_SUFFIX
       , T.SERVICE_TYPE
       , T.SERVICE_TYPE_DESCRIPTION
       -- 날짜: 실제 업무 흐름 순서대로 (주문 → 요구일(최초/재조정) → 피킹 → IOD → 실도착)
       -- 주문일자: OBS_ORDER_DATE 우선, 없으면 ORDER_DATE 로 대체 (둘 다 원본 그대로도 같이 노출)
       , COALESCE(T.OBS_ORDER_DATE, T.ORDER_DATE) AS ORDER_TXN_DATE
       , T.OBS_ORDER_DATE
       , T.ORDER_DATE
       , T.ORIGINAL_DELIVERY_APPT_DATE_TIME
       , T.UPDATED_DELIVERY_APPT_DATE_TIME
       , T.PICK_RELEASED_DATE_TIME
       , T.PICK_COMPLETE_DATE
       , T.IOD_INPUT_DATE
       , T.IOD_CONFIRM_DATE
       , T.ACTUAL_ARRIAVL_DATE
       , T.ORDER_QTY
       , T.ORDER_VOLUME
       , T.VOLUME_UNIT
       , T.ORDER_WEIGHT
       , T.WEIGHT_UNIT
       , ROUND(TIMESTAMP_DIFF(PARSE_TIMESTAMP('%Y%m%d%H%M', T.ACTUAL_ARRIAVL_DATE),
                               PARSE_TIMESTAMP('%Y%m%d%H%M', T.PICK_RELEASED_DATE_TIME), HOUR) / 24.0, 1) AS DELIVERY_LT_DAY
       , ROUND(TIMESTAMP_DIFF(PARSE_TIMESTAMP('%Y%m%d%H%M', T.PICK_RELEASED_DATE_TIME),
                               PARSE_TIMESTAMP('%Y%m%d%H%M', COALESCE(T.OBS_ORDER_DATE, T.ORDER_DATE)), HOUR) / 24.0, 1) AS ORDER_PICKRELEASE_LT_DAY
       , CASE WHEN COALESCE(T.UPDATED_DELIVERY_APPT_DATE_TIME, T.ORIGINAL_DELIVERY_APPT_DATE_TIME) IS NULL
                   OR T.ACTUAL_ARRIAVL_DATE IS NULL
              THEN NULL
              WHEN SUBSTR(T.ACTUAL_ARRIAVL_DATE,1,8) <= SUBSTR(COALESCE(T.UPDATED_DELIVERY_APPT_DATE_TIME, T.ORIGINAL_DELIVERY_APPT_DATE_TIME),1,8)
              THEN 'On-time/Early'
              ELSE 'Late'
         END                                      AS IRAD_RESULT
    FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_OBS_SO_LINE T, PARAM P
    LEFT JOIN `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST M
      ON T.MODEL_SUFFIX = M.MDL_SFFX_CD
   WHERE T.ORDER_STATUS = 'Completed'
     AND SUBSTR(T.IOD_CONFIRM_DATE,1,6) = P.base_ym
     AND (P.legal_entity = 'ALL'    OR T.SUBSIDIARY IN UNNEST(SPLIT(P.legal_entity, '|')))
     AND (P.division     = '[ALL]' OR M.DIV_NM     = P.division)
     AND (P.lmsp_name    = '[ALL]' OR T.LMSP_NAME  = P.lmsp_name)
   ORDER BY T.IOD_CONFIRM_DATE DESC
"""

QUERY_OBS_LMSP_LIST = """
-- 3PL(LMSP) 필터 옵션 목록
SELECT DISTINCT LMSP_NAME
  FROM `pjt-lge-oversea-sales-olap`.SCM_DEV.M_OBS_SO_LINE
 WHERE LMSP_NAME IS NOT NULL
   AND (@legal_entity = 'ALL' OR SUBSIDIARY IN UNNEST(SPLIT(@legal_entity, '|')))
 ORDER BY LMSP_NAME
"""
