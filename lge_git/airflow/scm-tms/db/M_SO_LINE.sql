 
    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T 
    AS
    WITH T_P_PTT AS (SELECT max(P_PTT) AS P_PTT FROM `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S)
    , T_P_SEQ AS (SELECT max(P_SEQ) AS P_SEQ FROM `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T WHERE P_PTT = (SELECT P_PTT FROM T_P_PTT))
    , T_LIST AS (
         SELECT *
           FROM `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T1
          WHERE P_SEQ = 'Closed' 
            AND LINE_STATUS_CODE = 'CLOSED'
            --AND AFFILIATE_CODE = 'EEPL'
         UNION ALL
         SELECT *
           FROM `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T1
          WHERE P_PTT = (SELECT P_PTT FROM  T_P_PTT )
            AND P_SEQ = (SELECT P_SEQ FROM T_P_SEQ)
            --AND AFFILIATE_CODE = 'EEPL'
    )
    , T_AFFILIATE_CODE AS (
      SELECT DISTINCT 
             SUBSDR_SHRT_NAME AS SUBSDR_NAME
           , SUBSDR_CD        AS AFFILIATE_CODE
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L1SALE_TMSALE_NERP_NDGS_SUBSDR_M
    )
    SELECT P_PTT
         , P_SEQ
         , T1.AFFILIATE_CODE
         , T2.SUBSDR_NAME
         , ACCOUNTING_UNIT_CODE
         , HQ_ACCOUNTING_UNIT_CODE
         , DOMAIN_CODE
         , PARENT_CHANNEL_MEANING
         , SALES_CHANNEL_NAME
         , CUSTOMER_CODE
         , MDMS_CUSTOMER_CODE
         , CUSTOMER_NAME
         , BILL_TO_CUSTOMER_CODE
         , BILL_TO_CUSTOMER_NAME
         , SHIP_TO_CUSTOMER_CODE
         , SHIP_TO_CUSTOMER_NAME
         , PROJECT_CODE
         , SHIP_TO_STATE_CODE
         , SHIP_TO_CITY_NAME
         , SHIP_TO_POSTAL_CODE
         , MODEL_CODE
         , MODE_DESC
         , MODEL_CATEGORY
         , PRODUCT_LEVEL1_CODE
         , PRODUCT_LEVEL2_CODE
         , PRODUCT_LEVEL3_CODE
         , PRODUCT_LEVEL4_CODE
         , ORDER_CATEGORY_CODE
         , ORDER_TYPE_NAME
         , LINE_CATEGORY_CODE
         , SALES_ORDER_NO
         , ORDER_HEADER_ID
         , SALES_ORDER_LINE_NO
         , ORDER_LINE_ID
         , CUST_PO_NO
         , PICK_NO
         , ORDER_STATUS_CODE
         , LINE_STATUS_CODE
         , LINE_TYPE_NAME
         , LINE_STATUS_CODE2
         , OPEN_FLAG
         , INVENTORY_RESERVED
         , WAREHOUSE_CODE
         , SUBINVENTORY_CODE
         , PICK_RELEASE_YN
         , HOLD_FLAG
         , ORDER_HOLD_ID 
         , RELEASE_DATE
         , BACK_ORDER_HOLD
         , CREDIT_HOLD
         , OVERDUE_HOLD
         , CUSTOMER_HOLD
         , PAYTERM_TERM_HOLD
         , FP_HOLD
         , MINIMUM_HOLD
         , FUTURE_HOLD
         , RESERVE_HOLD
         , MANUAL_HOLD
         , AUTO_PENDING_HOLD
         , SA_HOLD
         , FORM_HOLD
         , BANK_COLLATERAL_HOLD
         , INSURANCE_HOLD
         , ETC_HOLD
         , UNIT_SELLING_PRICE
         , UNIT_LIST_PRICE
         , CURRENCY_CODE
         , CUST_PO_DATE
         , ORDERED_DATE
         , BOOKED_DATE
         , REQUEST_ARRIVAL_FROM_DATE
         , REQUEST_ARRIVAL_TO_DATE
         , CUSTOMER_RAD
         , REQUEST_SHIPPING_DATE
         , PICK_RELEASE_DATE
         , APPOINTMENT_FROM_DATE
         , APPOINTMENT_TO_DATE
         , PROMISED_ARRIVAL_DATE
         , PROMISED_SHIP_DATE
         , PICKING_DATE
         , ACTUAL_SHIPMENT_DATE
         , SALES_DATE
         , SALESPERSON_NAME
         , SHIPPING_METHOD_CODE
         , SHIPPING_REMARK_INFO
         , STATUS
         , CONVERSION_RATE
         , USER_CONVERSION_TYPE_CODE
         , INVOICE_REMARK
         , CREATION_DATE
         , ORDER_QTY
         , CANCEL_QTY
         , ORDER_AMOUNT
         , PICK_RELEASE_QTY
         , AP_ORDER_AMOUNT 
         , IL_BRANCH
         , TAX_AMOUNT
         , CHARGE_AMOUNT
         , IL_MODEL_CATEGORY
         , PRODUCT_VALUE
         , ITEM_TYPE
         , INIT_PROMISED_ARRIVAL_DATE
      FROM T_LIST  T1
      JOIN T_AFFILIATE_CODE T2
        ON T1.AFFILIATE_CODE = T2.AFFILIATE_CODE
    ;


    
    
    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE 
    PARTITION BY ORDERED_DATE
    CLUSTER BY SUBSDR_NAME  
    OPTIONS (
      require_partition_filter = FALSE
    )
    AS 
    SELECT M1.* 
            , CASE WHEN PROGRESS_STATUS = 'SHIPPED'          THEN DATE_DIFF( P_PTT , DATE(M1.WMS_SHIPPED_DATE), DAY)         ELSE DATE_DIFF( DATE(SALES_DATE) , DATE(M1.WMS_SHIPPED_DATE), DAY) END      AS SHIPPED_IN_DAYS
            , CASE WHEN PROGRESS_STATUS = 'SHIPPING_CONFIRM' THEN DATE_DIFF( P_PTT , DATE(M1.WMS_SHIPPING_CONFIRM_DATE),DAY) ELSE DATE_DIFF( DATE(M1.WMS_SHIPPED_DATE) , DATE(M1.WMS_SHIPPING_CONFIRM_DATE),DAY) END      AS SHIPPING_CONFIRM_IN_DAYS
            , CASE WHEN PROGRESS_STATUS = 'WH_RELEASE'       THEN DATE_DIFF( P_PTT , DATE(M1.TMS_WH_RELEASE_DATE) , DAY)     ELSE DATE_DIFF( DATE(M1.WMS_SHIPPING_CONFIRM_DATE) , DATE(M1.TMS_WH_RELEASE_DATE) , DAY) END      AS WH_RELEASE_IN_DAYS
            , CASE WHEN PROGRESS_STATUS = 'LOAD_CREATION'    THEN DATE_DIFF( P_PTT , DATE(M1.TMS_LOAD_CREATION_DATE)  , DAY) ELSE DATE_DIFF( DATE(M1.TMS_WH_RELEASE_DATE) , DATE(M1.TMS_LOAD_CREATION_DATE), DAY) END      AS LOAD_CREATION_IN_DAYS 
            , CASE WHEN PROGRESS_STATUS = 'PICK_RELEASE'     THEN DATE_DIFF( P_PTT , DATE(M1.TMS_PICK_RELEASE_DATE)  , DAY) ELSE DATE_DIFF( DATE(M1.TMS_LOAD_CREATION_DATE) , DATE(M1.TMS_PICK_RELEASE_DATE), DAY) END      AS PICK_RELEASE_IN_DAYS 
            , CASE WHEN PROGRESS_STATUS = 'BOOKED'           THEN DATE_DIFF( P_PTT , DATE(M1.BOOKED_DATE), DAY)              ELSE DATE_DIFF( DATE(M1.TMS_PICK_RELEASE_DATE) , DATE(M1.BOOKED_DATE), DAY) END      AS BOOKED_IN_DAYS
            , CASE WHEN PROGRESS_STATUS = 'ENTERED'          THEN DATE_DIFF( P_PTT , DATE(M1.ORDERED_DATE), DAY)             ELSE DATE_DIFF( DATE(BOOKED_DATE) , DATE(M1.ORDERED_DATE), DAY)              END      AS ENTERED_IN_DAYS
            , CASE WHEN PROGRESS_STATUS = 'HOLD'             THEN DATE_DIFF( P_PTT , DATE(M1.HOLD_DATE), DAY)                ELSE HOLD_DAYS END      AS HOLD_IN_DAYS 
      FROM (
        SELECT T1.P_PTT
             , T1.P_SEQ
             , T1.AFFILIATE_CODE
             , T1.SUBSDR_NAME
             , T1.ACCOUNTING_UNIT_CODE
             , T1.HQ_ACCOUNTING_UNIT_CODE
             , T1.DOMAIN_CODE
             , T1.PARENT_CHANNEL_MEANING
             , T1.SALES_CHANNEL_NAME
             , T1.CUSTOMER_CODE
             , T1.MDMS_CUSTOMER_CODE
             , T1.CUSTOMER_NAME
             , T1.BILL_TO_CUSTOMER_CODE
             , T1.BILL_TO_CUSTOMER_NAME
             , T1.SHIP_TO_CUSTOMER_CODE
             , T1.SHIP_TO_CUSTOMER_NAME
             , T1.PROJECT_CODE
             , T1.SHIP_TO_STATE_CODE
             , T1.SHIP_TO_CITY_NAME
             , T1.SHIP_TO_POSTAL_CODE
             , T1.MODEL_CODE
             , T1.MODE_DESC
             , T1.MODEL_CATEGORY
             , T1.PRODUCT_LEVEL1_CODE
             , T1.PRODUCT_LEVEL2_CODE
             , T1.PRODUCT_LEVEL3_CODE
             , T1.PRODUCT_LEVEL4_CODE
             , T1.ORDER_CATEGORY_CODE
             , T1.ORDER_TYPE_NAME
             , T1.LINE_CATEGORY_CODE
             , T1.SALES_ORDER_NO
             , T1.ORDER_HEADER_ID
             , T1.SALES_ORDER_LINE_NO
             , T1.ORDER_LINE_ID
             , T1.CUST_PO_NO
             , T1.PICK_NO
             , T1.ORDER_STATUS_CODE
             , T1.LINE_STATUS_CODE
             , T1.LINE_TYPE_NAME
             , T1.LINE_STATUS_CODE2
             , T1.OPEN_FLAG
             , T1.INVENTORY_RESERVED
             , T1.WAREHOUSE_CODE
             , T1.SUBINVENTORY_CODE
             , T1.PICK_RELEASE_YN
             , T1.HOLD_FLAG
             , T1.ORDER_HOLD_ID 
             , T1.RELEASE_DATE
             , T1.BACK_ORDER_HOLD
             , T1.CREDIT_HOLD
             , T1.OVERDUE_HOLD
             , T1.CUSTOMER_HOLD
             , T1.PAYTERM_TERM_HOLD
             , T1.FP_HOLD
             , T1.MINIMUM_HOLD
             , T1.FUTURE_HOLD
             , T1.RESERVE_HOLD
             , T1.MANUAL_HOLD
             , T1.AUTO_PENDING_HOLD
             , T1.SA_HOLD
             , T1.FORM_HOLD
             , T1.BANK_COLLATERAL_HOLD
             , T1.INSURANCE_HOLD
             , T1.ETC_HOLD
             , T1.UNIT_SELLING_PRICE
             , T1.UNIT_LIST_PRICE
             , T1.CURRENCY_CODE
             , T1.CUST_PO_DATE
             , T1.ORDERED_DATE
             , T1.BOOKED_DATE
             , T1.REQUEST_ARRIVAL_FROM_DATE
             , T1.REQUEST_ARRIVAL_TO_DATE
             , T1.CUSTOMER_RAD
             , T1.REQUEST_SHIPPING_DATE
             , T1.PICK_RELEASE_DATE
             , T1.APPOINTMENT_FROM_DATE
             , T1.APPOINTMENT_TO_DATE
             , T1.PROMISED_ARRIVAL_DATE
             , T1.PROMISED_SHIP_DATE
             , T1.PICKING_DATE
             , T1.ACTUAL_SHIPMENT_DATE
             , T1.SALES_DATE
             , T1.SALESPERSON_NAME
             , T1.SHIPPING_METHOD_CODE
             , T1.SHIPPING_REMARK_INFO
             , T1.STATUS
             , T1.CONVERSION_RATE
             , T1.USER_CONVERSION_TYPE_CODE
             , T1.INVOICE_REMARK
             , T1.CREATION_DATE
             , T1.ORDER_QTY
             , T1.CANCEL_QTY
             , T1.ORDER_AMOUNT
             , T1.PICK_RELEASE_QTY
             , T1.AP_ORDER_AMOUNT 
             , T1.IL_BRANCH
             , T1.TAX_AMOUNT
             , T1.CHARGE_AMOUNT
             , T1.IL_MODEL_CATEGORY
             , T1.PRODUCT_VALUE
             , T1.ITEM_TYPE
             , T1.INIT_PROMISED_ARRIVAL_DATE
             , T2.RELEASED_FLAG AS HOLD_RELEASED_FLAG
             , T2.HOLD_DATE
             , T2.RELEASE_DATE AS HOLD_RELEASE_DATE
             , T2.HOLD_NAME
             , T2.HOLD_REASON_CODE
             , CASE WHEN T2.RELEASED_FLAG = 'N' THEN T2.HOLD_DAYS + DATE_DIFF(T1.P_PTT, DATE(T2.HOLD_DATE), DAY) ELSE T2.HOLD_DAYS END  AS HOLD_DAYS
             , T3.PICK_RELEASE_DATE       AS TMS_PICK_RELEASE_DATE
             , T3.LOAD_CREATION_DATE      AS TMS_LOAD_CREATION_DATE
             , T3.TENDER_DATE             AS TMS_TENDER_DATE
             , T3.WH_RELEASE_DATE         AS TMS_WH_RELEASE_DATE
             , T3.SHIPPING_CONFIRM_DATE   AS WMS_SHIPPING_CONFIRM_DATE
             , T3.SHIPPED_DATE            AS WMS_SHIPPED_DATE
             , T3.APPOINTMENT_TO_DATE     AS TMS_APPOINTMENT_TO_DATE
             , T3.RAD_DATE                AS TMS_RAD_DATE 
             , CASE WHEN  T1.LINE_STATUS_CODE IN ('CANCELLED') THEN 'CANCELLED'
                  WHEN  T1.LINE_STATUS_CODE IN ('CLOSED') THEN 'CLOSED'
                  WHEN  T1.SALES_DATE IS NOT NULL THEN 'CLOSED'
                  WHEN  T3.SHIPPED_DATE IS NOT NULL THEN 'SHIPPED'
                  WHEN  T3.SHIPPING_CONFIRM_DATE IS NOT NULL THEN 'SHIPPING_CONFIRM'
                  WHEN  T3.WH_RELEASE_DATE IS NOT NULL THEN 'WH_RELEASE' 
                  WHEN  T3.LOAD_CREATION_DATE IS NOT NULL THEN 'LOAD_CREATION'
                  WHEN  T3.PICK_RELEASE_DATE IS NOT NULL THEN 'PICK_RELEASE'
                  WHEN  T1.HOLD_FLAG = 'Y' THEN 'HOLD'
                  WHEN  T1.BOOKED_DATE IS NOT NULL THEN 'BOOKED'
                  WHEN  T1.ORDERED_DATE IS NOT NULL THEN 'ENTERED'
              END  AS PROGRESS_STATUS 
          FROM  `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T T1
          LEFT JOIN (
            SELECT 
                  ORDER_HEADER_ID
                , ORDER_LINE_ID
                , MAX(CASE WHEN RN = 1 THEN RELEASED_FLAG END)    AS RELEASED_FLAG
                , MAX(CASE WHEN RN = 1 THEN HOLD_DATE END)        AS HOLD_DATE
                , MAX(CASE WHEN RN = 1 THEN RELEASE_DATE END)     AS RELEASE_DATE
                , MAX(CASE WHEN RN = 1 THEN HOLD_REASON_CODE END) AS HOLD_REASON_CODE
                , MAX(CASE WHEN RN = 1 THEN HOLD_NAME END)        AS HOLD_NAME 
                , SUM(HOLD_DAYS) AS HOLD_DAYS
              FROM (
                    SELECT  
                          L.*
                        , ROW_NUMBER() OVER(PARTITION BY L.ORDER_HEADER_ID,L.ORDER_LINE_ID ORDER BY L.HOLD_DATE DESC) AS RN
                      FROM (
                           SELECT HOLD_LEVEL
                                , ORDER_HEADER_ID
                                , ORDER_LINE_ID
                                , RELEASED_FLAG
                                , RELEASE_DATE
                                , HOLD_DATE
                                , HOLD_REASON_CODE
                                , HOLD_NAME 
                                , DATE_DIFF(DATE(T1.RELEASE_DATE), DATE(T1.HOLD_DATE), DAY) AS HOLD_DAYS
                             FROM `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V T1
                            WHERE HOLD_LEVEL = 'LINE'
                              AND ORDER_HEADER_ID IN (SELECT ORDER_HEADER_ID FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T)
                            UNION ALL
                           SELECT T1.HOLD_LEVEL
                                , T1.ORDER_HEADER_ID
                                , T2.ORDER_LINE_ID
                                , T1.RELEASED_FLAG
                                , T1.RELEASE_DATE
                                , T1.HOLD_DATE
                                , T1.HOLD_REASON_CODE
                                , T1.HOLD_NAME
                                , DATE_DIFF(DATE(T1.RELEASE_DATE), DATE(T1.HOLD_DATE), DAY) AS HOLD_DAYS
                             FROM `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V T1
                             JOIN `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T T2
                               ON T1.ORDER_HEADER_ID = T2.ORDER_HEADER_ID
                            WHERE HOLD_LEVEL = 'HEADER'
                        ) L
               )
             GROUP BY 
                  ORDER_HEADER_ID
                , ORDER_LINE_ID
             ) T2
            ON T1.ORDER_HEADER_ID = T2.ORDER_HEADER_ID
           AND T1.ORDER_LINE_ID   = T2.ORDER_LINE_ID
        LEFT JOIN (
            SELECT
                  GL.SOURCE_HEADER_ID AS ORDER_HEADER_ID,
                  GL.SOURCE_LINE_ID   AS ORDER_LINE_ID,
                  DATE(MAX(S.PICK_RELEASE_DATE))                                       AS PICK_RELEASE_DATE,
                  DATE(MAX(GL.LOAD_CREATION_DATE))                                     AS LOAD_CREATION_DATE,
                  -- ── [4] Tender 응답 마감일  
                  DATE(MAX(TDR.TDR_RSPS_BY_DTT))                                       AS TENDER_DATE, 
                  -- ── [7] 창고 릴리즈일 (WH Release))  
                  DATE(MAX(GL.RELEASE_TO_WH_DATE))                                     AS WH_RELEASE_DATE,
                  -- ── [8] 실제 출고일 (Ship Confirm))  
                  DATE(MAX(GL.SHIPPING_DATE))                                          AS SHIPPING_CONFIRM_DATE,
                  -- ── [9] 출고 완료일 (LD_LEG_T.SHPD_DTT)  
                  DATE(MAX(L.SHPD_DTT))                                                AS SHIPPED_DATE,
                  -- ── [10] RAD (요청 도착일)  
                  DATE(MAX(S.ORI_DELY_TO))                                             AS RAD_DATE,
                  DATE(MAX(GL.APPOINTMENT_TO_DATE))                                     AS APPOINTMENT_TO_DATE
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
             AND FX.BASE_YYMM   = FORMAT_DATE('%Y%m', DATE(S.SALES_ORDER_DATE))
            GROUP BY
                  GL.SOURCE_HEADER_ID,
                  GL.SOURCE_LINE_ID
              ) T3 
            ON T1.ORDER_HEADER_ID = T3.ORDER_HEADER_ID
           AND T1.ORDER_LINE_ID   = T3.ORDER_LINE_ID
     ) M1
      