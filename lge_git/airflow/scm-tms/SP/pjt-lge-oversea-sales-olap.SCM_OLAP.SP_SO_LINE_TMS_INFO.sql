BEGIN
    
    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_TMS_INFO', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.TMS (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO
    AS
    -- ① 오더 기준 Shipment 매핑
    WITH W_TMS_DATA_GERP AS
    (
      SELECT T1.LEGAL_ENTITY_NAME
           , T1.SHIPMENTNUMBER
           , CAST(T2.SOURCE_HEADER_ID AS STRING)            AS SOURCE_HEADER_ID
           , CAST(T2.SOURCE_LINE_ID   AS STRING)            AS SOURCE_LINE_ID
           , CAST(T2.SOURCE_HEADER_NO AS STRING)            AS SOURCE_HEADER_NO
           , LTRIM(CAST(T2.SOURCE_LINE_NO AS STRING), '0')  AS SOURCE_LINE_NO
           , T1.PICK_RELEASE_DATE
           , T1.ORI_DELY_TO                                 AS RAD_DATE
           , T1.GERP_SHIPTO_CODE
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TB_GTM_SHIPMENT_TMS_S_IF_OS  AS T1
      LEFT OUTER JOIN
             `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TB_GTM_ORDERS_GERP_R_IF_OS   AS T2
         ON  T2.MOVE_ORDER_LINE_ID  =  T1.MOVE_ORDER_LINE_ID
        AND  T2.LEGAL_ENTITY_NAME   =  T1.LEGAL_ENTITY_NAME
        AND  T2.TMS_PRCS_FLAG       =  'Y'
      WHERE  1 = 1
        AND  T2.P_PTT  >=  '2025-01-01'
    )
    , W_TMS_DATA_NERP AS
    ( 
      SELECT *
      FROM (
             SELECT T1.SUBSIDIARY_CODE                                   AS LEGAL_ENTITY_NAME
                  , T1.SHIPMENTNUMBER
                  , SOURCE_HEADER_ID                                     AS SOURCE_HEADER_ID
                  , SOURCE_LINE_ID                                       AS SOURCE_LINE_ID
                  , SOURCE_HEADER_NO                                     AS SALES_ORDER_NO
                  , LPAD(SPLIT(SOURCE_LINE_NO, '.')[OFFSET(0)], 6, '0')  AS SALES_ORDER_LINE_NO
                  , T1.PICK_ORDER_NO                                     AS PICK_ORDER_NO
                  , T1.PICK_RELEASE_DATE 
                  , T1.RAD_DATE 
                  , T1.LOAD_CREATION_DATE
                  , T2.NERP_OPEN_YMD
                  , ROW_NUMBER() OVER(PARTITION BY SHIPMENTNUMBER ORDER BY ETL_LOAD_TS DESC,INTERFACE_ID DESC) AS RN
             FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.TB_GTM_ORDER_OLAP_S_IF_OS  AS T1
             JOIN   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST               AS T2
                ON  T1.SUBSIDIARY_CODE  =   T2.SUBSDR_NM
             WHERE  1 = 1
           )
      WHERE  RN  =  1 
    )
   -- ② Load 정보 (LD_LEG_DETL_T → LD_LEG_T)
    , W_LOAD_INFO AS
    (
      SELECT T1.SHPM_NUM
           , T2.LD_LEG_ID
           , T2.CRTD_DTT          AS LOAD_CREATION_DATE
           , T2.CARR_CD
           , T2.SRVC_CD
           , T2.EQMT_TYP
           , T2.TRCTR_NUM
           , T2.TRLR_NUM
           , T2.SHPD_DTT          AS SHIPPED_DATE  -- 예정 출발일
           , T1.FRM_SHPG_LOC_CD
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__LD_LEG_DETL_T_OS  AS T1
      LEFT OUTER JOIN
             `pjt-lge-edl-ob`.OB_00030.V_L0TMS__LD_LEG_T_OS       AS T2
         ON  T2.LD_LEG_ID  =  T1.LD_LEG_ID
      WHERE  T1.SEQ_NUM  =  100
    )
    -- ③ TB_GTM_LOAD (WH Release, Ship Confirm)
    , W_GTM_LOAD_INFO AS
    (
      SELECT SHIPMENTNUMBER
           , LD_LEG_ID
           , LOAD_ID
           , SOURCE_HEADER_ID
           , SOURCE_LINE_ID
           , RELEASE_TO_WH_DATE
           , SHIPPING_DATE           AS SHIPPING_CONFIRM_DATE
           , LOAD_CREATION_DATE
           , APPOINTMENT_FROM_DATE
           , APPOINTMENT_TO_DATE
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TB_GTM_LOAD_OS
    )
    -- ④ Tender 최신 1건
    , W_TENDER_INFO AS
    (
      SELECT LD_LEG_ID
           , MAX(TDR_RSPS_BY_DTT)   AS TENDER_DATE
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TDR_REQ_T_OS
      GROUP BY LD_LEG_ID
    ) 
    -- ⑤ IOD / POD 완료일자
    , W_IOD_INFO AS
    (
      SELECT SHIPMENTNUMBER
           , LD_LEG_ID
           , IOD_DATE                   AS IOD_DATE          -- 실제 수령일 
           , IOD_INPUT_DATE             AS IOD_INPUT_DATE    -- IOD 시스템 입력일
           , IOD_CONFIRM_DATE           AS IOD_CONFIRM_DATE  -- IOD 최종 확정일
           , IOD_CONFIRM_FLAG           AS IOD_CONFIRM_FLAG  -- Y/N
           , POD_INPUT_DATE             AS POD_INPUT_DATE    -- POD 업로드일
           , POD_DATE                   AS POD_DATE          -- POD 서명/수령일
           , POD_COLLECT_DATE           AS POD_COLLECT_DATE  -- POD 수거일
           , CASE WHEN IOD_INPUT_DATE IS NULL AND POD_INPUT_DATE IS NULL     THEN 'Multi Pending'
                  WHEN IOD_INPUT_DATE IS NULL AND POD_INPUT_DATE IS NOT NULL THEN 'IOD Pending'
                  WHEN IOD_INPUT_DATE IS NOT NULL AND POD_FILE_NAME IS NULL  THEN 'POD Pending'
                  ELSE 'Closed'
             END                        AS IOD_STATUS
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TB_GTM_IOD_OS
    )
    , W_EUTMS_MAX_DATA_GET AS
    (
      SELECT *
      FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_EUTMS_ORDER_HIST_GERP
      WHERE  1 = 1
      QUALIFY ROW_NUMBER() OVER(PARTITION BY SHIPMENT_NO ORDER BY INPUT_DT DESC,TRANSFER_DATE DESC) = 1
    )
    , W_UNION_DATA_SET AS
    (
      SELECT 'OTMS'                       AS TMS_TYPE
           , 'GERP'                       AS DATA_TYPE
           , T1.LEGAL_ENTITY_NAME
           , T1.SOURCE_HEADER_ID          -- NERP : NULL
           , T1.SOURCE_LINE_ID            -- NERP : NULL
           , T1.SOURCE_HEADER_NO          AS SALES_ORDER_NO
           , T1.SOURCE_LINE_NO            AS SALES_ORDER_LINE_NO
           , T1.GERP_SHIPTO_CODE
           , CAST(NULL AS STRING)         AS PICK_ORDER_NO
             -- ── 날짜
           , T1.RAD_DATE                  AS RAD_DATE
           , T2.APPOINTMENT_FROM_DATE     AS APPOINTMENT_FROM_DATE
           , T2.APPOINTMENT_TO_DATE       AS APPOINTMENT_TO_DATE
             -- ── Load
           , T2.LD_LEG_ID
           , T1.SHIPMENTNUMBER
           , T1.PICK_RELEASE_DATE         AS PICK_RELEASE_DATE
           , T2.RELEASE_TO_WH_DATE        AS WH_RELEASE_DATE
           , T6.LOAD_CREATION_DATE        AS LOAD_CREATION_DATE
           , T4.TENDER_DATE               AS TENDER_DATE
           , T2.SHIPPING_CONFIRM_DATE     AS SHIPPING_CONFIRM_DATE
           , T3.SHIPPED_DATE              AS SHIPPED_DATE
           , T5.IOD_DATE                  AS IOD_DATE
           , T5.POD_DATE                  AS POD_DATE
             -- ── 운송사
           , T3.CARR_CD
           , T3.SRVC_CD
           , T3.EQMT_TYP
           , T3.TRCTR_NUM
           , T3.TRLR_NUM
           , CAST(NULL AS STRING)         AS MDL_SHIPTO_MIX_CD
      FROM   W_TMS_DATA_GERP    AS T1
      LEFT OUTER JOIN
             W_GTM_LOAD_INFO    AS T2
         ON  T2.SHIPMENTNUMBER  =  T1.SHIPMENTNUMBER
      LEFT OUTER JOIN
             W_LOAD_INFO        AS T3
         ON  T3.SHPM_NUM        =  T1.SHIPMENTNUMBER
      LEFT OUTER JOIN
             W_TENDER_INFO      AS T4
         ON  T4.LD_LEG_ID       =  T3.LD_LEG_ID 
      LEFT OUTER JOIN
             W_IOD_INFO         AS T5
         ON  T2.LD_LEG_ID       =  T5.LD_LEG_ID 
        AND  T2.SHIPMENTNUMBER  =  T5.SHIPMENTNUMBER
      LEFT OUTER JOIN
             W_TMS_DATA_NERP    AS T6
         ON  T1.SHIPMENTNUMBER    =   T6.SHIPMENTNUMBER
        AND  T6.SOURCE_HEADER_ID  IS  NOT NULL           --(GERP란 의미)
      WHERE  1 = 1
      UNION ALL
      SELECT 'OTMS'                       AS TMS_TYPE
           , 'NERP'                       AS DATA_TYPE
           , T1.LEGAL_ENTITY_NAME
           , CAST(NULL AS STRING)         AS SOURCE_HEADER_ID          -- NERP : NULL
           , CAST(NULL AS STRING)         AS SOURCE_LINE_ID            -- NERP : NULL
           , T1.SALES_ORDER_NO
           , T1.SALES_ORDER_LINE_NO
           , CAST(NULL AS STRING)         AS GERP_SHIPTO_CODE
           , T1.PICK_ORDER_NO
             -- ── 날짜
           , T1.RAD_DATE                  AS RAD_DATE
           , T2.APPOINTMENT_FROM_DATE     AS APPOINTMENT_FROM_DATE
           , T2.APPOINTMENT_TO_DATE       AS APPOINTMENT_TO_DATE
             -- ── Load
           , T2.LD_LEG_ID
           , T1.SHIPMENTNUMBER
           , T1.PICK_RELEASE_DATE         AS PICK_RELEASE_DATE
           , T2.RELEASE_TO_WH_DATE        AS WH_RELEASE_DATE
           , T1.LOAD_CREATION_DATE        AS LOAD_CREATION_DATE
           , T4.TENDER_DATE               AS TENDER_DATE
           , T2.SHIPPING_CONFIRM_DATE     AS SHIPPING_CONFIRM_DATE
           , T3.SHIPPED_DATE              AS SHIPPED_DATE
           , T5.IOD_DATE                  AS IOD_DATE
           , T5.POD_DATE                  AS POD_DATE
             -- ── 운송사
           , T3.CARR_CD
           , T3.SRVC_CD
           , T3.EQMT_TYP
           , T3.TRCTR_NUM
           , T3.TRLR_NUM
           , CAST(NULL AS STRING)         AS MDL_SHIPTO_MIX_CD
      FROM   W_TMS_DATA_NERP    AS T1
      LEFT OUTER JOIN
             W_GTM_LOAD_INFO    AS T2
         ON  T2.SHIPMENTNUMBER  =  T1.SHIPMENTNUMBER
      LEFT OUTER JOIN
             W_LOAD_INFO        AS T3
         ON  T3.SHPM_NUM        =  T1.SHIPMENTNUMBER
      LEFT OUTER JOIN
             W_TENDER_INFO      AS T4
         ON  T4.LD_LEG_ID       =  T3.LD_LEG_ID 
      LEFT OUTER JOIN
             W_IOD_INFO         AS T5
         ON  T2.LD_LEG_ID       =  T5.LD_LEG_ID 
        AND  T2.SHIPMENTNUMBER  =  T5.SHIPMENTNUMBER
      WHERE  1 = 1
        AND  T1.SOURCE_HEADER_ID  IS  NULL   --(NERP는 NULL)
        AND  T1.NERP_OPEN_YMD     <=  FORMAT_DATE('%Y%m%d', CURRENT_DATE('Asia/Seoul'))
      UNION ALL
      -- EU-TMS Add --
      SELECT 'EUTMS'                                  AS TMS_TYPE
           , 'GERP'                                   AS DATA_TYPE
           , T2.SUBSDR_NM                             AS LEGAL_ENTITY_NAME
           , CAST(NULL AS STRING)                     AS SOURCE_HEADER_ID
           , CAST(NULL AS STRING)                     AS SOURCE_LINE_ID
           , T1.ORDER_NO                              AS SALES_ORDER_NO
           , CAST(NULL AS STRING)                     AS SALES_ORDER_LINE_NO
           , T1.SHIP_TO_CODE                          AS GERP_SHIPTO_CODE
           , T1.PICK_ORDER_NO                         AS PICK_ORDER_NO
           , CAST(NULL AS DATETIME)                   AS RAD_DATE
           , CAST(NULL AS DATETIME)                   AS APPOINTMENT_FROM_DATE
           , CAST(NULL AS DATETIME)                   AS APPOINTMENT_TO_DATE
           , CAST(NULL AS NUMERIC)                    AS LD_LEG_ID
           , T1.SHIPMENT_NO                           AS SHIPMENTNUMBER
           , CAST(T1.PICK_RELEASED_DATE AS DATETIME)  AS PICK_RELEASE_DATE
           , CAST(T1.RELEASE_TO_WH_DATE AS DATETIME)  AS WH_RELEASE_DATE
           , CAST(T1.LOAD_CREATE_DATE   AS DATETIME)  AS LOAD_CREATION_DATE
           , CAST(T1.TENDER_ACCEPT_DATE AS DATETIME)  AS TENDER_DATE
           , CAST(T1.SHIP_CONFIRM_DATE  AS DATETIME)  AS SHIPPING_CONFIRM_DATE
           , CAST(T1.PICK_REQUEST_DATE  AS DATETIME)  AS SHIPPED_DATE
           , CAST(T1.IOD_INPUT_DATE     AS DATETIME)  AS IOD_DATE
           , CAST(NULL AS DATETIME)                   AS POD_DATE
           , CAST(NULL AS STRING)                     AS CARR_CD
           , CAST(NULL AS STRING)                     AS SRVC_CD
           , CAST(NULL AS STRING)                     AS EQMT_TYP
           , CAST(NULL AS STRING)                     AS TRCTR_NUM
           , CAST(NULL AS STRING)                     AS TRLR_NUM
           , COALESCE(MODEL_SUFFIX, ' ') || '_' || COALESCE(SHIP_TO_CODE, ' ')  AS MDL_SHIPTO_MIX_CD
      FROM   W_EUTMS_MAX_DATA_GET                                AS T1
      LEFT OUTER JOIN
             `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST  AS T2
         ON  T2.SUBSDR_CD  =  T1.AFFILIATE
      WHERE  1 = 1
      UNION ALL
      SELECT 'OBS'                      AS TMS_TYPE
           , 'ALL'                      AS DATA_TYPE
           , T1.SUBSIDIARY              AS LEGAL_ENTITY_NAME
             /*-- LGEAK,LGEAP,LGEBN,LGECB,LGECK,LGECL,LGEDG,LGEEG,LGEFS,LGEIL,LGEIN,LGEIS,LGEMS,LGEPL,LGEPS,LGESA,LGESJ,LGESP,LGESW,LGETH,LGETK,LGETT,LGEUK,LGEVH --*/
           , CAST(NULL AS STRING)       AS SOURCE_HEADER_ID
           , CAST(NULL AS STRING)       AS SOURCE_LINE_ID
           , T1.GERP_ORDER_NO           AS SALES_ORDER_NO
           , CASE WHEN T2.NERP_OPEN_YMD IS NULL                            THEN LTRIM(CAST(T1.GERP_ORDER_LINE_NO AS STRING), '0')  --NERP
                  WHEN T2.NERP_OPEN_YMD >= FORMAT_DATE('%Y%m%d', T1.P_PTT) THEN LTRIM(CAST(T1.GERP_ORDER_LINE_NO AS STRING), '0')  --NERP
                  ELSE LPAD(CAST(T1.GERP_ORDER_LINE_NO AS STRING), 6, '0')
             END                        AS SALES_ORDER_LINE_NO
           , CAST(NULL AS STRING)       AS GERP_SHIPTO_CODE
           , T1.GERP_PICK_NO            AS PICK_ORDER_NO
           , CAST(NULL AS DATETIME)     AS RAD_DATE
           , CAST(NULL AS DATETIME)     AS APPOINTMENT_FROM_DATE
           , CAST(NULL AS DATETIME)     AS APPOINTMENT_TO_DATE
           , CAST(NULL AS NUMERIC)      AS LD_LEG_ID
           , T1.SHIPMENT_ID             AS SHIPMENTNUMBER
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.PICK_RELEASED_DATE_TIME || '00')  AS PICK_RELEASE_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.WH_RELEASE_DATE || '00')          AS WH_RELEASE_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.LOAD_CREATE_DATE || '00')         AS LOAD_CREATION_DATE
           , CAST(NULL AS DATETIME)                                               AS TENDER_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.SHIP_CONFIRM_DATE_TIME || '00')   AS SHIPPING_CONFIRM_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.SHIP_CONFIRM_DATE_TIME || '00')   AS SHIPPED_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.IOD_INPUT_DATE || '00')           AS IOD_DATE
           , PARSE_DATETIME('%Y%m%d %H%M%S', T1.POD_INPUT_DATE || '00')           AS POD_DATE
           , CAST(NULL AS STRING)       AS CARR_CD
           , CAST(NULL AS STRING)       AS SRVC_CD
           , CAST(NULL AS STRING)       AS EQMT_TYP
           , CAST(NULL AS STRING)       AS TRCTR_NUM
           , CAST(NULL AS STRING)       AS TRLR_NUM
           , T1.MODEL_SUFFIX            AS MDL_SHIPTO_MIX_CD
      FROM
             `pjt-lge-edl-ob`.OB_00030.V_L0LMDS_TB_LI_ORDERLIST_ONEVIEW_S_IF  AS T1
      JOIN   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST               AS T2
         ON  T2.SUBSDR_NM    =  T1.SUBSIDIARY
        AND  T2.DATA_AGG_YN  =  'Y'
      WHERE  1 = 1
        AND  T1.ORDER_DATE  >= '20250101'
      QUALIFY ROW_NUMBER() OVER(PARTITION BY T1.SHIPMENT_ID ORDER BY SYS_CREATE_DATE DESC ) = 1
    )
    SELECT LEGAL_ENTITY_NAME
         , TMS_TYPE
         , DATA_TYPE
         , SOURCE_HEADER_ID
         , SOURCE_LINE_ID
         , SALES_ORDER_NO
         , SALES_ORDER_LINE_NO
         , MDL_SHIPTO_MIX_CD
         , MAX(PICK_RELEASE_DATE)       AS PICK_RELEASE_DATE
         , MAX(WH_RELEASE_DATE)         AS WH_RELEASE_DATE
         , MAX(LOAD_CREATION_DATE)      AS LOAD_CREATION_DATE
         , MAX(SHIPPING_CONFIRM_DATE)   AS SHIPPING_CONFIRM_DATE
         , MAX(SHIPPED_DATE)            AS SHIPPED_DATE
         , MAX(IOD_DATE)                AS IOD_DATE
         , MAX(POD_DATE)                AS POD_DATE
         , MAX(TENDER_DATE)             AS TENDER_DATE
         , MIN(APPOINTMENT_FROM_DATE)   AS APPOINTMENT_FROM_DATE
         , MAX(APPOINTMENT_TO_DATE)     AS APPOINTMENT_TO_DATE
         , MAX(RAD_DATE)                AS RAD_DATE
    FROM (
           SELECT
                  LEGAL_ENTITY_NAME
                , TMS_TYPE
                , DATA_TYPE
                , CAST(SOURCE_HEADER_ID AS NUMERIC)   AS SOURCE_HEADER_ID
                , CAST(SOURCE_LINE_ID AS NUMERIC)     AS SOURCE_LINE_ID
                , SALES_ORDER_NO
                , SALES_ORDER_LINE_NO
                , LD_LEG_ID
                , SHIPMENTNUMBER
                , MDL_SHIPTO_MIX_CD
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(PICK_RELEASE_DATE)     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN PICK_RELEASE_DATE     END  AS PICK_RELEASE_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) = 
                            COUNT(WH_RELEASE_DATE)       OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN WH_RELEASE_DATE       END AS WH_RELEASE_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(LOAD_CREATION_DATE)    OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN LOAD_CREATION_DATE    END AS LOAD_CREATION_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(TENDER_DATE)           OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN TENDER_DATE           END AS TENDER_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(SHIPPING_CONFIRM_DATE) OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN SHIPPING_CONFIRM_DATE END AS SHIPPING_CONFIRM_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(SHIPPED_DATE)          OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN SHIPPED_DATE          END AS SHIPPED_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(IOD_DATE)              OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN IOD_DATE              END AS IOD_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(POD_DATE)              OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN POD_DATE              END AS POD_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(APPOINTMENT_FROM_DATE) OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN APPOINTMENT_FROM_DATE END AS APPOINTMENT_FROM_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(APPOINTMENT_TO_DATE)   OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN APPOINTMENT_TO_DATE   END AS APPOINTMENT_TO_DATE
                , CASE WHEN COUNT(1)                     OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) =
                            COUNT(RAD_DATE)              OVER(PARTITION BY SHIPMENTNUMBER, TMS_TYPE, DATA_TYPE) THEN RAD_DATE              END AS RAD_DATE
                , COUNT(1) OVER(PARTITION BY SHIPMENTNUMBER)  AS SHIPMENTNUMBER_CNT
           FROM   W_UNION_DATA_SET
           WHERE  1 = 1
         )
    GROUP  BY 1,2,3,4,5,6,7,8
    ;

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_TMS_INFO', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.TMS (Hourly)');

END