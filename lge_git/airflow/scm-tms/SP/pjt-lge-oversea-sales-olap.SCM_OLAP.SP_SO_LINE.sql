BEGIN

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_NEW', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.SO_LINE (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE
    PARTITION BY ORDERED_DATE
    CLUSTER   BY SUBSDR_NAME
    OPTIONS  (require_partition_filter = FALSE)
    AS
    WITH W_OTMS_ADD_DATA AS
      (
        SELECT T1.*
             , CAST(T2.PICK_RELEASE_DATE AS DATETIME)  AS TMS_PICK_RELEASE_DATE
             , T2.WH_RELEASE_DATE                      AS TMS_WH_RELEASE_DATE
             , T2.LOAD_CREATION_DATE                   AS TMS_LOAD_CREATION_DATE
             , T2.TENDER_DATE                          AS TMS_TENDER_DATE
             , T2.SHIPPING_CONFIRM_DATE                AS WMS_SHIPPING_CONFIRM_DATE
             , T2.SHIPPED_DATE                         AS WMS_SHIPPED_DATE
             , T2.IOD_DATE                             AS TMS_IOD_DATE
             , T2.POD_DATE                             AS TMS_POD_DATE
             , T2.RAD_DATE                             AS TMS_RAD_DATE 
             , T2.APPOINTMENT_FROM_DATE                AS TMS_APPOINTMENT_FROM_DATE
             , T2.APPOINTMENT_TO_DATE                  AS TMS_APPOINTMENT_TO_DATE
             , T2.TMS_TYPE                             AS TMS_TYPE
             , T2.LEGAL_ENTITY_NAME                    AS LEGAL_ENTITY_NAME
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01       AS T1
        JOIN
               `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO  AS T2
           ON  1 = 1
          AND  T1.HOLD_FLAG  =   'N'
          AND  T2.DATA_TYPE  IN  ('GERP', 'ALL')
          AND  T2.TMS_TYPE   =   'OTMS'
          AND  T2.SOURCE_HEADER_ID  =  T1.ORDER_HEADER_ID
          AND  T2.SOURCE_LINE_ID    =  T1.ORDER_LINE_ID
      )
    , W_OBS_ADD_DATA AS
      (
        SELECT T1.*
             , CAST(T2.PICK_RELEASE_DATE AS DATETIME)  AS TMS_PICK_RELEASE_DATE
             , T2.WH_RELEASE_DATE                      AS TMS_WH_RELEASE_DATE
             , T2.LOAD_CREATION_DATE                   AS TMS_LOAD_CREATION_DATE
             , T2.TENDER_DATE                          AS TMS_TENDER_DATE
             , T2.SHIPPING_CONFIRM_DATE                AS WMS_SHIPPING_CONFIRM_DATE
             , T2.SHIPPED_DATE                         AS WMS_SHIPPED_DATE
             , T2.IOD_DATE                             AS TMS_IOD_DATE
             , T2.POD_DATE                             AS TMS_POD_DATE
             , T2.RAD_DATE                             AS TMS_RAD_DATE 
             , T2.APPOINTMENT_FROM_DATE                AS TMS_APPOINTMENT_FROM_DATE
             , T2.APPOINTMENT_TO_DATE                  AS TMS_APPOINTMENT_TO_DATE
             , T2.TMS_TYPE                             AS TMS_TYPE
             , T2.LEGAL_ENTITY_NAME                    AS LEGAL_ENTITY_NAME
        FROM ( SELECT *
               FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01
               QUALIFY ROW_NUMBER() OVER (PARTITION BY SUBSDR_NAME, SALES_ORDER_NO, SPLIT(SALES_ORDER_LINE_NO, ".")[offset(0)] ORDER BY SALES_ORDER_LINE_NO) = 1
             )                                                            AS T1
        JOIN
               `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO   AS T2
           ON  1 = 1
          AND  T1.HOLD_FLAG  =   'N'
          AND  T2.DATA_TYPE  IN  ('GERP', 'ALL')
          AND  T2.TMS_TYPE   =   'OBS'
          AND  T2.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
          AND  T2.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
          AND  T2.SALES_ORDER_LINE_NO  =  SPLIT(T1.SALES_ORDER_LINE_NO, ".")[offset(0)]
          AND  T2.MDL_SHIPTO_MIX_CD    =  T1.MODEL_CODE
        WHERE  1 = 1
          AND  NOT EXISTS ( SELECT '1'
                            FROM   W_OTMS_ADD_DATA                       AS T3
                            WHERE  1 = 1
                              AND  T3.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
                              AND  T3.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
                          )
      )
    , W_EUTMS_ADD_DATA AS
      (
        SELECT T1.*
             , CAST(T2.PICK_RELEASE_DATE AS DATETIME)  AS TMS_PICK_RELEASE_DATE
             , T2.WH_RELEASE_DATE                      AS TMS_WH_RELEASE_DATE
             , T2.LOAD_CREATION_DATE                   AS TMS_LOAD_CREATION_DATE
             , T2.TENDER_DATE                          AS TMS_TENDER_DATE
             , T2.SHIPPING_CONFIRM_DATE                AS WMS_SHIPPING_CONFIRM_DATE
             , T2.SHIPPED_DATE                         AS WMS_SHIPPED_DATE
             , T2.IOD_DATE                             AS TMS_IOD_DATE
             , T2.POD_DATE                             AS TMS_POD_DATE
             , T2.RAD_DATE                             AS TMS_RAD_DATE 
             , T2.APPOINTMENT_FROM_DATE                AS TMS_APPOINTMENT_FROM_DATE
             , T2.APPOINTMENT_TO_DATE                  AS TMS_APPOINTMENT_TO_DATE
             , T2.TMS_TYPE                             AS TMS_TYPE
             , T2.LEGAL_ENTITY_NAME                    AS LEGAL_ENTITY_NAME
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01       AS T1
        JOIN
               `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO  AS T2
           ON  1 = 1
          AND  T1.HOLD_FLAG  =   'N'
          AND  T2.DATA_TYPE  IN  ('GERP', 'ALL')
          AND  T2.TMS_TYPE   =   'EUTMS'
          AND  T2.SALES_ORDER_NO     =  T1.SALES_ORDER_NO
          AND  T2.LEGAL_ENTITY_NAME  =  T1.SUBSDR_NAME
          AND  T2.MDL_SHIPTO_MIX_CD  =  T1.MODEL_CODE || '_' || SUBSTR(T1.SUBSDR_NAME, 4, 2) || T1.SHIP_TO_CUSTOMER_CODE
        WHERE  1 = 1
          AND  NOT EXISTS ( SELECT '1'
                            FROM   W_OTMS_ADD_DATA                       AS T3
                            WHERE  1 = 1
                              AND  T3.ORDER_HEADER_ID    =  T1.ORDER_HEADER_ID
                              AND  T3.ORDER_LINE_ID      =  T1.ORDER_LINE_ID
                              AND  T3.LEGAL_ENTITY_NAME  =  T1.SUBSDR_NAME
                          )
          AND  NOT EXISTS ( SELECT '1'
                            FROM   W_OBS_ADD_DATA                        AS T4
                            WHERE  1 = 1
                              AND  T4.ORDER_HEADER_ID     =  T1.ORDER_HEADER_ID
                              AND  T4.ORDER_LINE_ID       =  T1.ORDER_LINE_ID
                              AND  T4.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
                              AND  T4.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
                              AND  T4.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO
                          )
      )
    , W_NOT_EXIST_TMS_DATA AS
      (
        SELECT T1.*
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01  AS T1
        WHERE  1 = 1
          AND  NOT EXISTS ( SELECT 'OK'
                            FROM (
                                   SELECT *
                                   FROM   W_OTMS_ADD_DATA
                                   UNION  ALL
                                   SELECT *
                                   FROM   W_OBS_ADD_DATA
                                   UNION  ALL
                                   SELECT *
                                   FROM   W_EUTMS_ADD_DATA
                                 )                                  AS T2
                            WHERE  1 = 1
                              AND  T2.ORDER_HEADER_ID      =  T1.ORDER_HEADER_ID
                              AND  T2.ORDER_LINE_ID        =  T1.ORDER_LINE_ID
                              AND  T2.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
                              AND  T2.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO 
                              AND  T2.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
                          )
      )
    , W_MAIN_DATA_SET AS
      (
        SELECT *
        FROM (
               SELECT *
               FROM   W_OTMS_ADD_DATA
               UNION  ALL
               SELECT *
               FROM   W_OBS_ADD_DATA
               UNION  ALL
               SELECT *
               FROM   W_EUTMS_ADD_DATA
               UNION  ALL
               SELECT *
                    , CAST(NULL AS DATETIME)  AS TMS_PICK_RELEASE_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_WH_RELEASE_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_LOAD_CREATION_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_TENDER_DATE
                    , CAST(NULL AS DATETIME)  AS WMS_SHIPPING_CONFIRM_DATE
                    , CAST(NULL AS DATETIME)  AS WMS_SHIPPED_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_IOD_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_POD_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_RAD_DATE 
                    , CAST(NULL AS DATETIME)  AS TMS_APPOINTMENT_FROM_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_APPOINTMENT_TO_DATE
                    , CAST(NULL AS STRING)    AS TMS_TYPE
                    , CAST(NULL AS STRING)    AS LEGAL_ENTITY_NAME
               FROM   W_NOT_EXIST_TMS_DATA
             )
      )
    , W_SALES_ORDER_DATA AS
      (
        SELECT T1.P_PTT
             , T1.ORDER_HEADER_ID
             , T1.ORDER_LINE_ID
             , T1.SALES_ORDER_NO
             , T1.SALES_ORDER_LINE_NO
             , T1.LINE_STATUS_CODE
                /*
             , CASE WHEN T1.LINE_STATUS_CODE IN ('CANCELLED')             THEN 'CANCELLED'
                    WHEN T1.LINE_STATUS_CODE IN ('CLOSED')                THEN 'CLOSED'
                    WHEN T1.SALES_DATE                IS NOT NULL         THEN 'CLOSED'
                    WHEN T1.HOLD_QTY       > 0                            THEN 'HOLD'
                    WHEN T1.TMS_IOD_DATE              IS NOT NULL         THEN 'IOD'
                    WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_RELE_QTY  > 0  THEN 'PICK_RELEASE, SHIPPED'
                    WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_READY_QTY > 0  THEN 'PICK_READY, SHIPPED'
                    WHEN T1.PICK_RELE_QTY  > 0 AND T1.PICK_READY_QTY > 0  THEN 'PICK_READY, PICK_RELEASE'
                    WHEN T1.SHIPPED_QTY    > 0                            THEN 'SHIPPED'
                    WHEN T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL         THEN 'SHIPPING_CONFIRM'
                    WHEN T1.TMS_WH_RELEASE_DATE       IS NOT NULL         THEN 'WH_RELEASE'
                    WHEN T1.TMS_LOAD_CREATION_DATE    IS NOT NULL         THEN 'LOAD_CREATION'
                    WHEN T1.PICK_RELE_QTY  > 0                            THEN 'PICK_RELEASE'
                    WHEN T1.PICK_READY_QTY > 0                            THEN 'PICK_READY'
                    WHEN T1.OPEN_QTY       > 0                            THEN 'BOOKED'
                    WHEN T1.ORDERED_DATE              IS NOT NULL         THEN 'ENTERED'  -- NERP는 존재치 않음
                    ELSE 'ERROR'
               END                                      AS PROGRESS_STATUS
               */
             , CASE WHEN  T1.LINE_STATUS_CODE  IN  ('CANCELLED')   THEN 'CANCELLED'
                    WHEN  T1.LINE_STATUS_CODE  IN  ('CLOSED')      THEN 'CLOSED'
                    WHEN  T1.SALES_DATE                IS NOT NULL THEN 'CLOSED'
                    WHEN  T1.HOLD_FLAG = 'Y'                       THEN 'HOLD'
                    WHEN  T1.TMS_IOD_DATE              IS NOT NULL THEN 'IOD'
                    WHEN  T1.WMS_SHIPPED_DATE          IS NOT NULL THEN 'SHIPPED'
                    WHEN  T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL THEN 'SHIPPING_CONFIRM'
                    WHEN  T1.TMS_WH_RELEASE_DATE       IS NOT NULL THEN 'WH_RELEASE' 
                    WHEN  T1.TMS_LOAD_CREATION_DATE    IS NOT NULL THEN 'LOAD_CREATION'
                    WHEN  T1.PICK_RELEASE_DATE         IS NOT NULL THEN 'PICK_RELEASE'
                    WHEN  T1.TMS_PICK_RELEASE_DATE     IS NOT NULL THEN 'PICK_RELEASE'
                    WHEN  T1.HOLD_RELEASE_DATE         IS NOT NULL THEN 'PICK_READY'
                    WHEN  T1.BOOKED_DATE               IS NOT NULL THEN 'BOOKED'
                    WHEN  T1.ORDERED_DATE              IS NOT NULL THEN 'ENTERED'
               END                                     AS PROGRESS_STATUS
             , T1.P_SEQ
             , T1.OPEN_FLAG
             , T1.AFFILIATE_CODE
             , T1.SUBSDR_NAME
             , T1.DOMAIN_CODE
             , T1.BILL_TO_CUSTOMER_CODE
             , T1.BILL_TO_CUSTOMER_NAME
             , T1.SHIP_TO_CUSTOMER_CODE
             , T1.SHIP_TO_CUSTOMER_NAME
             , T1.PROJECT_CODE
             , T1.MODEL_CODE
             , T1.DIV_NM
             , T1.MODEL_DESC
             , T1.MODEL_CATEGORY
             , T1.ORDER_TYPE_NAME
             , T1.LINE_CATEGORY_CODE
             , T1.HOLD_FLAG
             , CASE WHEN COUNT(1) OVER (PARTITION BY T1.SALES_ORDER_NO) <> COUNT(CASE WHEN T1.HOLD_FLAG = 'Y' THEN 1 END) OVER (PARTITION BY T1.SALES_ORDER_NO)
                     AND COUNT(CASE WHEN T1.HOLD_FLAG = 'Y' THEN 1 END) OVER (PARTITION BY T1.SALES_ORDER_NO) <> 0
               THEN 'Y' END                            AS PARTIAL_HOLD_FLAG
             , T1.HOLD_TYPE
             , IF(T1.HOLD_FLAG = 'Y' AND T1.CREDIT_HOLD = 'Y' AND T1.OVERDUE_HOLD = 'Y' AND T1.CUSTOMER_HOLD = 'Y' AND T1.PAYTERM_TERM_HOLD = 'Y', 'Y', 'N')  AS AR_HOLD
             , T1.FUTURE_HOLD
             , T1.ORDER_HOLD_ID
             , T1.BACK_ORDER_HOLD
             , T1.CREDIT_HOLD
             , T1.OVERDUE_HOLD
             , T1.CUSTOMER_HOLD
             , T1.PAYTERM_TERM_HOLD
             , T1.FP_HOLD
             , T1.MINIMUM_HOLD
             , T1.RESERVE_HOLD
             , T1.MANUAL_HOLD
             , T1.AUTO_PENDING_HOLD
             , T1.ETC_HOLD
             , T1.UNIT_SELLING_PRICE
             , T1.UNIT_LIST_PRICE
             , T1.CURRENCY_CODE
             , T1.ORDERED_DATE
             , T1.BOOKED_DATE
             , T1.CUSTOMER_RAD
             , T1.REQUEST_SHIPPING_DATE
             , T1.PICK_RELEASE_DATE
             , T1.APPOINTMENT_FROM_DATE
             , T1.APPOINTMENT_TO_DATE
             , T1.PROMISED_ARRIVAL_DATE
             , T1.SALES_DATE
             , T1.CONVERSION_RATE 
             , T1.CREATION_DATE
             , T1.ORDER_QTY
             , T1.CANCEL_QTY
             , T1.ORDER_AMOUNT
             , T1.USD_ORDER_AMOUNT
             , T1.RAD_DATE
             , T1.INIT_PROMISED_ARRIVAL_DATE
             , T1.HOLD_RELEASED_FLAG
             , T1.HOLD_DATE
             , T1.HOLD_RELEASE_DATE
             , T1.HOLD_NAME
             , CASE WHEN T1.HOLD_RELEASED_FLAG = 'N' THEN T1.HOLD_DAYS + DATE_DIFF(T1.P_PTT, DATE(T1.HOLD_DATE), DAY)
                    ELSE T1.HOLD_DAYS
               END                                     AS HOLD_DAYS
             , T1.TMS_PICK_RELEASE_DATE
             , T1.TMS_WH_RELEASE_DATE
             , T1.TMS_LOAD_CREATION_DATE
             , T1.TMS_TENDER_DATE
             , T1.WMS_SHIPPING_CONFIRM_DATE
             , T1.WMS_SHIPPED_DATE
             , CAST(NULL AS DATETIME)                  AS SHIPPING_DATE
             , T1.TMS_IOD_DATE
             , T1.TMS_POD_DATE
             , T1.TMS_RAD_DATE 
             , T1.TMS_APPOINTMENT_FROM_DATE
             , T1.TMS_APPOINTMENT_TO_DATE
             , T1.PRDT_GRP_CD
             , T1.PRDT_CAT_CD
             , T1.TMS_TYPE                             AS TMS_TYPE
             , T1.CUST_PO_NO
             , IF(T1.SALES_DATE IS NULL, 0, T1.ORDER_QTY)      AS SALES_QTY
             , IF(T1.SALES_DATE IS NULL, 0, T1.ORDER_AMOUNT)   AS SALES_AMOUNT
             , T1.WAREHOUSE_CODE
               /*-- GERP SO-SA Mapping Direct Shipment 반영 --*/
             , T1.BL_ID
             , T1.HOUSE_BL_NO
             , T1.CONTAINER_NO
             , T1.SO_SA_MAPPING_FLAG
               /*-- Not Use --
             , T1.HOLD_REASON_CODE
             , T1.RELEASE_DATE
             , T1.CUST_PO_DATE
             , T1.ACCOUNTING_UNIT_CODE
             , T1.HQ_ACCOUNTING_UNIT_CODE
             , T1.PARENT_CHANNEL_MEANING
             , T1.SALES_CHANNEL_NAME
             , T1.CUSTOMER_CODE
             , T1.MDMS_CUSTOMER_CODE
             , T1.CUSTOMER_NAME
             , T1.SHIP_TO_STATE_CODE
             , T1.SHIP_TO_CITY_NAME
             , T1.SHIP_TO_POSTAL_CODE
             , T1.PRODUCT_LEVEL1_CODE
             , T1.PRODUCT_LEVEL2_CODE
             , T1.PRODUCT_LEVEL3_CODE
             , T1.PRODUCT_LEVEL4_CODE
             , T1.ORDER_CATEGORY_CODE
             , T1.ORDER_HEADER_ID
             , T1.ORDER_LINE_ID
             , T1.ORDER_STATUS_CODE
             , T1.LINE_TYPE_NAME
             , T1.LINE_STATUS_CODE2
             , T1.PICK_NO
             , T1.INVENTORY_RESERVED
             , T1.SUBINVENTORY_CODE
             , T1.PICK_RELEASE_YN
             , T1.SA_HOLD
             , T1.FORM_HOLD
             , T1.BANK_COLLATERAL_HOLD
             , T1.INSURANCE_HOLD
             , T1.REQUEST_ARRIVAL_FROM_DATE
             , T1.REQUEST_ARRIVAL_TO_DATE
             , T1.PROMISED_SHIP_DATE
             , T1.PICKING_DATE
             , T1.ACTUAL_SHIPMENT_DATE
             , T1.SALESPERSON_NAME
             , T1.SHIPPING_METHOD_CODE
             , T1.SHIPPING_REMARK_INFO
             , T1.STATUS
             , T1.INVOICE_REMARK
             , T1.PICK_RELEASE_QTY
             , T1.IL_BRANCH
             , T1.TAX_AMOUNT
             , T1.CHARGE_AMOUNT
             , T1.IL_MODEL_CATEGORY
             , T1.PRODUCT_VALUE
             , T1.ITEM_TYPE
             --*/
        FROM   W_MAIN_DATA_SET  AS T1
        WHERE  1 = 1
      )
    , W_IN_DAYS_GET AS
      (
        SELECT M1.ORDER_HEADER_ID
             , M1.ORDER_LINE_ID
             , IF(PROGRESS_STATUS = 'ENTERED'         , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.ORDERED_DATE), DAY), 0)                AS ENTERED_IN_DAYS
             , IF(PROGRESS_STATUS = 'BOOKED'          , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.BOOKED_DATE), DAY), 0)                 AS BOOKED_IN_DAYS
             , IF(PROGRESS_STATUS = 'HOLD'            , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.HOLD_DATE), DAY), 0)                   AS HOLD_IN_DAYS 
             , IF(PROGRESS_STATUS = 'PICK_READY'      , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(COALESCE(M1.HOLD_RELEASE_DATE, M1.BOOKED_DATE)), DAY), 0)  AS PICK_READY_IN_DAYS 
             , IF(PROGRESS_STATUS = 'PICK_RELEASE'    , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_PICK_RELEASE_DATE), DAY), 0)       AS PICK_RELEASE_IN_DAYS
             , IF(PROGRESS_STATUS = 'LOAD_CREATION'   , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_LOAD_CREATION_DATE), DAY), 0)      AS LOAD_CREATION_IN_DAYS 
             , IF(PROGRESS_STATUS = 'WH_RELEASE'      , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_WH_RELEASE_DATE), DAY), 0)         AS WH_RELEASE_IN_DAYS
             , IF(PROGRESS_STATUS = 'SHIPPING_CONFIRM', DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DAY), 0)   AS SHIPPING_CONFIRM_IN_DAYS
             , IF(PROGRESS_STATUS = 'SHIPPED'         , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.WMS_SHIPPED_DATE), DAY), 0)            AS SHIPPED_IN_DAYS
             , IF(PROGRESS_STATUS = 'IOD'             , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_IOD_DATE), DAY), 0)                AS IOD_IN_DAYS
               /*
             , IF(PROGRESS_STATUS = 'ENTERED'         , DATE_DIFF(DATE(M1.BOOKED_DATE),               DATE(M1.ORDERED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'BOOKED'          , DATE_DIFF(DATE(M1.HOLD_RELEASE_DATE),         DATE(M1.BOOKED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'HOLD'            , HOLD_DAYS)
             , IF(PROGRESS_STATUS = 'PICK_READY'      , DATE_DIFF(DATE(M1.TMS_PICK_RELEASE_DATE),     DATE(M1.HOLD_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'PICK_RELEASE'    , DATE_DIFF(DATE(M1.TMS_LOAD_CREATION_DATE),    DATE(M1.TMS_PICK_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'LOAD_CREATION'   , DATE_DIFF(DATE(M1.TMS_WH_RELEASE_DATE),       DATE(M1.TMS_LOAD_CREATION_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'WH_RELEASE'      , DATE_DIFF(DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DATE(M1.TMS_WH_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'SHIPPING_CONFIRM', DATE_DIFF(DATE(M1.WMS_SHIPPED_DATE),          DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'SHIPPED'         , DATE_DIFF(DATE(TMS_IOD_DATE),                 DATE(M1.WMS_SHIPPED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'IOD'             , DATE_DIFF(DATE(SALES_DATE),                   DATE(M1.TMS_IOD_DATE), DAY), 0)
               */
        FROM   W_SALES_ORDER_DATA  AS M1
      )
    SELECT T1.P_PTT
         , T1.ORDER_HEADER_ID
         , T1.ORDER_LINE_ID
         , T1.SALES_ORDER_NO
         , T1.SALES_ORDER_LINE_NO
         , T1.LINE_STATUS_CODE
         , T1.PROGRESS_STATUS
         , T1.P_SEQ
         , T1.OPEN_FLAG
         , T1.AFFILIATE_CODE
         , T1.SUBSDR_NAME
         , T1.DOMAIN_CODE
         , T1.BILL_TO_CUSTOMER_CODE
         , T1.BILL_TO_CUSTOMER_NAME
         , T1.SHIP_TO_CUSTOMER_CODE
         , T1.SHIP_TO_CUSTOMER_NAME
         , T1.PROJECT_CODE
         , T1.MODEL_CODE
         , T1.DIV_NM
         , T1.MODEL_DESC
         , T1.MODEL_CATEGORY
         , T1.ORDER_TYPE_NAME
         , T1.LINE_CATEGORY_CODE
         , T1.HOLD_FLAG
         , T1.PARTIAL_HOLD_FLAG
         , T1.HOLD_TYPE
         , T1.AR_HOLD
         , T1.FUTURE_HOLD
         , T1.ORDER_HOLD_ID
         , T1.BACK_ORDER_HOLD
         , T1.CREDIT_HOLD
         , T1.OVERDUE_HOLD
         , T1.CUSTOMER_HOLD
         , T1.PAYTERM_TERM_HOLD
         , T1.FP_HOLD
         , T1.MINIMUM_HOLD
         , T1.RESERVE_HOLD
         , T1.MANUAL_HOLD
         , T1.AUTO_PENDING_HOLD
         , T1.ETC_HOLD
         , T1.UNIT_SELLING_PRICE
         , T1.UNIT_LIST_PRICE
         , T1.CURRENCY_CODE
         , T1.ORDERED_DATE
         , T1.BOOKED_DATE
         , T1.CUSTOMER_RAD
         , T1.REQUEST_SHIPPING_DATE
         , T1.PICK_RELEASE_DATE
         , T1.APPOINTMENT_FROM_DATE
         , T1.APPOINTMENT_TO_DATE
         , T1.PROMISED_ARRIVAL_DATE
         , T1.SALES_DATE
         , T1.CONVERSION_RATE 
         , T1.CREATION_DATE
         , T1.ORDER_QTY
         , T1.CANCEL_QTY
         , T1.ORDER_AMOUNT
         , T1.USD_ORDER_AMOUNT
         , T1.RAD_DATE
         , T1.INIT_PROMISED_ARRIVAL_DATE
         , T1.HOLD_RELEASED_FLAG
         , T1.HOLD_DATE
         , T1.HOLD_RELEASE_DATE
         , T1.HOLD_NAME
         , T1.HOLD_DAYS
         , T1.TMS_PICK_RELEASE_DATE
         , T1.TMS_WH_RELEASE_DATE
         , T1.TMS_LOAD_CREATION_DATE
         , T1.TMS_TENDER_DATE
         , T1.WMS_SHIPPING_CONFIRM_DATE
         , T1.WMS_SHIPPED_DATE
         , T1.SHIPPING_DATE
         , T1.TMS_IOD_DATE
         , T1.TMS_POD_DATE
         , T1.TMS_RAD_DATE 
         , T1.TMS_APPOINTMENT_FROM_DATE
         , T1.TMS_APPOINTMENT_TO_DATE
         , T2.ENTERED_IN_DAYS
         , T2.BOOKED_IN_DAYS
         , T2.HOLD_IN_DAYS
         , T2.PICK_READY_IN_DAYS
         , T2.PICK_RELEASE_IN_DAYS
         , T2.LOAD_CREATION_IN_DAYS
         , T2.WH_RELEASE_IN_DAYS
         , T2.SHIPPING_CONFIRM_IN_DAYS
         , T2.SHIPPED_IN_DAYS
         , T2.IOD_IN_DAYS
		       -- 현재 PROGRESS_STATUS 기준 잔여 평균 소요일 합산 → 도착 예정일 추정
		     , DATE_ADD(CURRENT_DATE('Asia/Seoul'),
		                INTERVAL CAST(
		                              ROUND(
		                                    CASE T1.PROGRESS_STATUS
		                                         WHEN 'ENTERED'          THEN COALESCE(T3.REM_ENTERED_DAYS,          T4.REM_ENTERED_DAYS)
		                                         WHEN 'BOOKED'           THEN COALESCE(T3.REM_BOOKED_DAYS,           T4.REM_BOOKED_DAYS)
		                                         WHEN 'HOLD'             THEN COALESCE(T3.REM_HOLD_DAYS,             T4.REM_HOLD_DAYS)
		                                         WHEN 'PICK_RELEASE'     THEN COALESCE(T3.REM_PICK_RELEASE_DAYS,     T4.REM_PICK_RELEASE_DAYS)
		                                         WHEN 'PICK_READY'       THEN COALESCE(T3.REM_PICK_READY_DAYS,       T4.REM_PICK_READY_DAYS)
		                                         WHEN 'LOAD_CREATION'    THEN COALESCE(T3.REM_LOAD_CREATION_DAYS,    T4.REM_LOAD_CREATION_DAYS)
		                                         WHEN 'WH_RELEASE'       THEN COALESCE(T3.REM_WH_RELEASE_DAYS,       T4.REM_WH_RELEASE_DAYS)
		                                         WHEN 'SHIPPING_CONFIRM' THEN COALESCE(T3.REM_SHIPPING_CONFIRM_DAYS, T4.REM_SHIPPING_CONFIRM_DAYS)
		                                         WHEN 'SHIPPED'          THEN COALESCE(T3.REM_SHIPPED_DAYS,          T4.REM_SHIPPED_DAYS)
		                                         ELSE NULL
		                                    END)   AS INT64
		                ) DAY)                                                      AS EST_ARRIVAL_DATE 
         , T1.ORDER_QTY                                                         AS ACTIVE_QTY
         , T1.ORDER_AMOUNT                                                      AS ACTIVE_AMOUNT
         , CAST(T1.SALES_QTY    AS NUMERIC)                                     AS SALES_QTY
         , CAST(T1.SALES_AMOUNT AS NUMERIC)                                     AS SALES_AMOUNT
         , IF(T1.PROGRESS_STATUS IN ('ENTERED', 'BOOKED'), T1.ORDER_QTY, 0)     AS OPEN_QTY
         , IF(T1.PROGRESS_STATUS IN ('ENTERED', 'BOOKED'), T1.ORDER_AMOUNT, 0)  AS OPEN_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'PICK_READY',       T1.ORDER_QTY, 0)         AS PICK_READY_QTY
         , IF(T1.PROGRESS_STATUS = 'PICK_READY',       T1.ORDER_AMOUNT, 0)      AS PICK_READY_AMOUNT
         , CAST(NULL AS NUMERIC)                                                AS ORI_PICK_RELE_QTY
         , CAST(NULL AS NUMERIC)                                                AS ORI_PICK_RELE_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'PICK_RELEASE',     T1.ORDER_QTY, 0)         AS PICK_RELE_QTY
         , IF(T1.PROGRESS_STATUS = 'PICK_RELEASE',     T1.ORDER_AMOUNT, 0)      AS PICK_RELE_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'SHIPPING_CONFIRM', T1.ORDER_QTY, 0)         AS SHIP_CONFIRM_QTY
         , IF(T1.PROGRESS_STATUS = 'SHIPPING_CONFIRM', T1.ORDER_AMOUNT, 0)      AS SHIP_CONFIRM_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'WH_RELEASE',       T1.ORDER_QTY, 0)         AS WH_RELE_QTY
         , IF(T1.PROGRESS_STATUS = 'WH_RELEASE',       T1.ORDER_AMOUNT, 0)      AS WH_RELE_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'LOAD_CREATION',    T1.ORDER_QTY, 0)         AS LOAD_CREATE_QTY
         , IF(T1.PROGRESS_STATUS = 'LOAD_CREATION',    T1.ORDER_AMOUNT, 0)      AS LOAD_CREATE_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'SHIPPED',          T1.ORDER_QTY, 0)         AS SHIPPED_QTY
         , IF(T1.PROGRESS_STATUS = 'SHIPPED',          T1.ORDER_AMOUNT, 0)      AS SHIPPED_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'HOLD',             T1.ORDER_QTY, 0)         AS HOLD_QTY
         , IF(T1.PROGRESS_STATUS = 'HOLD',             T1.ORDER_AMOUNT, 0)      AS HOLD_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.AR_HOLD = 'Y',         T1.ORDER_QTY, 0)     AS AR_HOLD_QTY
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.AR_HOLD = 'Y',         T1.ORDER_AMOUNT, 0)  AS AR_HOLD_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.BACK_ORDER_HOLD = 'Y', T1.ORDER_QTY, 0)     AS BACK_HOLD_QTY
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.BACK_ORDER_HOLD = 'Y', T1.ORDER_AMOUNT, 0)  AS BACK_HOLD_AMOUNT
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.FUTURE_HOLD = 'Y',     T1.ORDER_QTY, 0)     AS FUTURE_HOLD_QTY
         , IF(T1.PROGRESS_STATUS = 'HOLD' AND T1.FUTURE_HOLD = 'Y',     T1.ORDER_AMOUNT, 0)  AS FUTURE_HOLD_AMOUNT
         , 'GERP'                                       AS SOURCE
         , T1.PRDT_GRP_CD
         , T1.PRDT_CAT_CD
         , IF(T1.CONTAINER_NO IS NOT NULL, 'DIRECT', T1.TMS_TYPE)  AS TR_SYS_TYPE
         , FORMAT_DATE('%Y%m%d', T1.P_PTT) || '000000'             AS LOGSTAMP
         , T5.BILLTO_BIZ_NAME
         , T5.TEAM_NAME
         , T1.CUST_PO_NO
         , T1.WAREHOUSE_CODE
           /* SO-SA Mapping Direct Shipment 반영 */
         , T1.BL_ID
         , T1.HOUSE_BL_NO
         , T1.CONTAINER_NO
         , T1.SO_SA_MAPPING_FLAG
    FROM
           W_SALES_ORDER_DATA                                          AS T1
    JOIN   W_IN_DAYS_GET                                               AS T2
       ON  T1.ORDER_HEADER_ID  =  T2.ORDER_HEADER_ID
      AND  T1.ORDER_LINE_ID    =  T2.ORDER_LINE_ID
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SO_REM_DAYS         AS T3
		   ON  T1.SUBSDR_NAME = T3.SUBSDR_NAME  
		  AND  T1.SHIP_TO_CUSTOMER_CODE  =  T3.SHIP_TO_CUSTOMER_CODE
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SO_REM_DAYS         AS T4
       ON  T1.SUBSDR_NAME            =  T4.SUBSDR_NAME  
      AND  T4.SHIP_TO_CUSTOMER_CODE  =  '[ALL]'
    LEFT OUTER JOIN 
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST  AS T5
       ON  T1.SUBSDR_NAME            =  T5.SUBSDR_NAME
      AND  T1.BILL_TO_CUSTOMER_CODE  =  T5.BILLTO_CODE
      AND  T1.PRDT_GRP_CD            =  T5.PRODUCT_GROUP_CODE
    ;

    /*-----------------------------------------------------------------------
      --[*][] NERP AREA [][*]--
    -------------------------------------------------------------------------*/
    INSERT INTO  `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE
    (
        P_PTT
      , ORDER_HEADER_ID
      , ORDER_LINE_ID
      , SALES_ORDER_NO
      , SALES_ORDER_LINE_NO
      , LINE_STATUS_CODE
      , PROGRESS_STATUS
      , P_SEQ
      , OPEN_FLAG
      , AFFILIATE_CODE
      , SUBSDR_NAME
      , DOMAIN_CODE
      , BILL_TO_CUSTOMER_CODE
      , BILL_TO_CUSTOMER_NAME
      , SHIP_TO_CUSTOMER_CODE
      , SHIP_TO_CUSTOMER_NAME
      , PROJECT_CODE
      , MODEL_CODE
      , DIV_NM
      , MODEL_DESC
      , MODEL_CATEGORY
      , ORDER_TYPE_NAME
      , LINE_CATEGORY_CODE
      , HOLD_FLAG
      , PARTIAL_HOLD_FLAG
      , HOLD_TYPE
      , AR_HOLD
      , FUTURE_HOLD
      , BACK_ORDER_HOLD
      , CREDIT_HOLD
      , OVERDUE_HOLD
      , CUSTOMER_HOLD
      , PAYTERM_TERM_HOLD
      , FP_HOLD
      , MINIMUM_HOLD
      , RESERVE_HOLD
      , MANUAL_HOLD
      , AUTO_PENDING_HOLD
      , ETC_HOLD
      , UNIT_SELLING_PRICE
      , UNIT_LIST_PRICE
      , CURRENCY_CODE
      , ORDERED_DATE
      , BOOKED_DATE
      , CUSTOMER_RAD
      , REQUEST_SHIPPING_DATE
      , PICK_RELEASE_DATE
      , APPOINTMENT_FROM_DATE
      , APPOINTMENT_TO_DATE
      , PROMISED_ARRIVAL_DATE
      , SALES_DATE
      , CONVERSION_RATE
      , CREATION_DATE
      , ORDER_QTY
      , CANCEL_QTY
      , ORDER_AMOUNT
        --, PICK_RELEASE_QTY   --DELETE
      , USD_ORDER_AMOUNT
      , RAD_DATE
      , INIT_PROMISED_ARRIVAL_DATE
      , HOLD_RELEASED_FLAG
      , HOLD_DATE
      , HOLD_RELEASE_DATE
      , HOLD_NAME
      , HOLD_DAYS
      , TMS_PICK_RELEASE_DATE
      , TMS_WH_RELEASE_DATE
      , TMS_LOAD_CREATION_DATE
      , TMS_TENDER_DATE
      , WMS_SHIPPING_CONFIRM_DATE
      , WMS_SHIPPED_DATE
      , SHIPPING_DATE
      , TMS_IOD_DATE
      , TMS_POD_DATE
      , TMS_RAD_DATE
      , TMS_APPOINTMENT_FROM_DATE
      , TMS_APPOINTMENT_TO_DATE
      , ENTERED_IN_DAYS
      , BOOKED_IN_DAYS
      , HOLD_IN_DAYS
      , PICK_READY_IN_DAYS
      , PICK_RELEASE_IN_DAYS
      , LOAD_CREATION_IN_DAYS
      , WH_RELEASE_IN_DAYS
      , SHIPPING_CONFIRM_IN_DAYS
      , SHIPPED_IN_DAYS
      , IOD_IN_DAYS
      , EST_ARRIVAL_DATE
      , ACTIVE_QTY
      , ACTIVE_AMOUNT
      , SALES_QTY
      , SALES_AMOUNT
      , OPEN_QTY
      , OPEN_AMOUNT
      , PICK_READY_QTY
      , PICK_READY_AMOUNT
      , ORI_PICK_RELE_QTY
      , ORI_PICK_RELE_AMOUNT
      , PICK_RELE_QTY
      , PICK_RELE_AMOUNT
      , SHIP_CONFIRM_QTY
      , SHIP_CONFIRM_AMOUNT
      , WH_RELE_QTY
      , WH_RELE_AMOUNT
      , LOAD_CREATE_QTY
      , LOAD_CREATE_AMOUNT
      , SHIPPED_QTY
      , SHIPPED_AMOUNT
      , HOLD_QTY
      , HOLD_AMOUNT
      , AR_HOLD_QTY
      , AR_HOLD_AMOUNT
      , BACK_HOLD_QTY
      , BACK_HOLD_AMOUNT
      , FUTURE_HOLD_QTY
      , FUTURE_HOLD_AMOUNT
      , SOURCE
      , PRDT_GRP_CD
      , PRDT_CAT_CD
      , TR_SYS_TYPE
      , LOGSTAMP
      , BILLTO_BIZ_NAME
      , TEAM_NAME
      , WAREHOUSE_CODE
        /* NERP SO-SA Mapping Direct Shipment 반영 */
      , BL_ID
      , HOUSE_BL_NO
      , CONTAINER_NO
      , SO_SA_MAPPING_FLAG
    )
    WITH W_OTMS_ADD_DATA AS
      (
        SELECT T1.*
             , CAST(T2.PICK_RELEASE_DATE AS DATETIME)  AS TMS_PICK_RELEASE_DATE
             , T2.WH_RELEASE_DATE                      AS TMS_WH_RELEASE_DATE
             , T2.LOAD_CREATION_DATE                   AS TMS_LOAD_CREATION_DATE
             , T2.TENDER_DATE                          AS TMS_TENDER_DATE
             , T2.SHIPPING_CONFIRM_DATE                AS WMS_SHIPPING_CONFIRM_DATE
             , T2.SHIPPED_DATE                         AS WMS_SHIPPED_DATE
             , T2.IOD_DATE                             AS TMS_IOD_DATE
             , T2.POD_DATE                             AS TMS_POD_DATE
             , T2.RAD_DATE                             AS TMS_RAD_DATE 
             , T2.APPOINTMENT_FROM_DATE                AS TMS_APPOINTMENT_FROM_DATE
             , T2.APPOINTMENT_TO_DATE                  AS TMS_APPOINTMENT_TO_DATE
             , T2.TMS_TYPE                             AS TMS_TYPE
             , T2.LEGAL_ENTITY_NAME                    AS LEGAL_ENTITY_NAME
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11       AS T1
        JOIN
               `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO  AS T2
           ON  1 = 1
          AND  T1.HOLD_FLAG  =   'N'
          AND  T2.DATA_TYPE  IN  ('NERP', 'ALL')
          AND  T2.TMS_TYPE   =   'OTMS'
          AND  T2.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
          AND  T2.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO
      )
    , W_OBS_ADD_DATA AS
      (
        SELECT T1.*
             , CAST(T2.PICK_RELEASE_DATE AS DATETIME)  AS TMS_PICK_RELEASE_DATE
             , T2.WH_RELEASE_DATE                      AS TMS_WH_RELEASE_DATE
             , T2.LOAD_CREATION_DATE                   AS TMS_LOAD_CREATION_DATE
             , T2.TENDER_DATE                          AS TMS_TENDER_DATE
             , T2.SHIPPING_CONFIRM_DATE                AS WMS_SHIPPING_CONFIRM_DATE
             , T2.SHIPPED_DATE                         AS WMS_SHIPPED_DATE
             , T2.IOD_DATE                             AS TMS_IOD_DATE
             , T2.POD_DATE                             AS TMS_POD_DATE
             , T2.RAD_DATE                             AS TMS_RAD_DATE 
             , T2.APPOINTMENT_FROM_DATE                AS TMS_APPOINTMENT_FROM_DATE
             , T2.APPOINTMENT_TO_DATE                  AS TMS_APPOINTMENT_TO_DATE
             , T2.TMS_TYPE                             AS TMS_TYPE
             , T2.LEGAL_ENTITY_NAME                    AS LEGAL_ENTITY_NAME
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11       AS T1
        JOIN
               `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_TMS_INFO  AS T2
           ON  1 = 1
          AND  T1.HOLD_FLAG  =   'N'
          AND  T2.DATA_TYPE  IN  ('NERP', 'ALL')
          AND  T2.TMS_TYPE   =   'OBS'
          AND  T2.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
          AND  T2.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO  
          AND  T2.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
        WHERE  1 = 1
          AND  NOT EXISTS ( SELECT '1'
                            FROM   W_OTMS_ADD_DATA                       AS T3
                            WHERE  1 = 1
                              AND  T3.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
                              AND  T3.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO  
                              AND  T3.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
                          )
      )
    , W_NOT_EXIST_TMS_DATA AS
      (
        SELECT T1.*
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11  AS T1
        WHERE  1 = 1
          AND  NOT EXISTS ( SELECT 'OK'
                            FROM (
                                   SELECT *
                                   FROM   W_OTMS_ADD_DATA
                                   UNION  ALL
                                   SELECT *
                                   FROM   W_OBS_ADD_DATA
                                 )                                  AS T2
                            WHERE  1 = 1
                              AND  T2.SALES_ORDER_NO       =  T1.SALES_ORDER_NO
                              AND  T2.SALES_ORDER_LINE_NO  =  T1.SALES_ORDER_LINE_NO  
                              AND  T2.LEGAL_ENTITY_NAME    =  T1.SUBSDR_NAME
                          )
      )
    , W_MAIN_DATA_SET AS
      (
        SELECT *
        FROM (
               SELECT *
               FROM   W_OTMS_ADD_DATA
               UNION  ALL
               SELECT *
               FROM   W_OBS_ADD_DATA
               UNION  ALL
               SELECT *
                    , CAST(NULL AS DATETIME)  AS TMS_PICK_RELEASE_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_WH_RELEASE_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_LOAD_CREATION_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_TENDER_DATE
                    , CAST(NULL AS DATETIME)  AS WMS_SHIPPING_CONFIRM_DATE
                    , CAST(NULL AS DATETIME)  AS WMS_SHIPPED_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_IOD_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_POD_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_RAD_DATE 
                    , CAST(NULL AS DATETIME)  AS TMS_APPOINTMENT_FROM_DATE
                    , CAST(NULL AS DATETIME)  AS TMS_APPOINTMENT_TO_DATE
                    , CAST(NULL AS STRING)    AS TMS_TYPE
                    , CAST(NULL AS STRING)    AS LEGAL_ENTITY_NAME
               FROM   W_NOT_EXIST_TMS_DATA
             )
      )
    , W_SALES_ORDER_DATA AS
      (
         SELECT T1.P_PTT
              , T1.SALES_ORDER_NO
              , T1.SALES_ORDER_LINE_NO
              , T1.LINE_STATUS_CODE
              , CASE WHEN T1.LINE_STATUS_CODE IN ('CANCELLED')                                                          THEN 'CANCELLED'
                     WHEN T1.LINE_STATUS_CODE IN ('CLOSED')                                                             THEN 'CLOSED'
                     WHEN T1.SALES_DATE       IS NOT NULL                                                               THEN 'CLOSED'
                     WHEN T1.HOLD_QTY       > 0                                                                         THEN 'HOLD'
                     WHEN T1.PICK_RELE_QTY  > 0 AND T1.TMS_IOD_DATE   IS  NOT NULL                                      THEN 'IOD'
                     WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_RELE_QTY  > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL  THEN 'SHIPPING_CONFIRM, SHIPPED'
                     WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_RELE_QTY  > 0 AND T1.TMS_WH_RELEASE_DATE       IS NOT NULL  THEN 'WH_RELEASE, SHIPPED'
                     WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_RELE_QTY  > 0 AND T1.TMS_LOAD_CREATION_DATE    IS NOT NULL  THEN 'LOAD_CREATION, SHIPPED'
                     WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_RELE_QTY  > 0                                               THEN 'PICK_RELEASE, SHIPPED'
                     WHEN T1.SHIPPED_QTY    > 0 AND T1.PICK_READY_QTY > 0                                               THEN 'PICK_READY, SHIPPED'
                     WHEN T1.SHIPPED_QTY    > 0                                                                         THEN 'SHIPPED'
                     WHEN T1.PICK_RELE_QTY  > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL                            THEN 'SHIPPING_CONFIRM'
                     WHEN T1.PICK_RELE_QTY  > 0 AND T1.TMS_WH_RELEASE_DATE       IS NOT NULL                            THEN 'WH_RELEASE'
                     WHEN T1.PICK_RELE_QTY  > 0 AND T1.TMS_LOAD_CREATION_DATE    IS NOT NULL                            THEN 'LOAD_CREATION'
                     WHEN T1.PICK_RELE_QTY  > 0 AND T1.PICK_READY_QTY > 0                                               THEN 'PICK_READY, PICK_RELEASE'
                     WHEN T1.PICK_RELE_QTY  > 0                                                                         THEN 'PICK_RELEASE'
                     WHEN T1.PICK_READY_QTY > 0                                                                         THEN 'PICK_READY'
                     WHEN T1.OPEN_QTY       > 0                                                                         THEN 'BOOKED'
                     WHEN T1.ORDERED_DATE              IS NOT NULL                                                      THEN 'ENTERED'  -- NERP는 존재치 않음
                     ELSE 'ERROR'
                END                                            AS PROGRESS_STATUS
              , T1.P_SEQ
              , T1.AFFILIATE_CODE
              , T1.SUBSDR_NAME
              , T1.DOMAIN_CODE
              , T1.BILL_TO_CUSTOMER_CODE
              , T1.BILL_TO_CUSTOMER_NAME
              , T1.SHIP_TO_CUSTOMER_CODE
              , T1.SHIP_TO_CUSTOMER_NAME
              , T1.PROJECT_CODE
              , T1.MODEL_CODE
              , T1.DIV_NM
              , T1.MODEL_DESC
              , T1.MODEL_CATEGORY
              , T1.ORDER_TYPE_NAME
              , T1.LINE_CATEGORY_CODE
              , T1.HOLD_FLAG
              , CASE WHEN COUNT(1) OVER (PARTITION BY T1.SALES_ORDER_NO) <> COUNT(CASE WHEN T1.HOLD_FLAG = 'Y' THEN 1 END) OVER (PARTITION BY T1.SALES_ORDER_NO)
                      AND COUNT(CASE WHEN T1.HOLD_FLAG = 'Y' THEN 1 END) OVER (PARTITION BY T1.SALES_ORDER_NO) <> 0  THEN  'Y' 
                END                                            AS PARTIAL_HOLD_FLAG
              , T1.HOLD_TYPE
              , T1.AR_HOLD
              , T1.FUTURE_HOLD
              , T1.BACK_HOLD                                   AS BACK_ORDER_HOLD
              , T1.CREDIT_HOLD
              , T1.OVERDUE_HOLD
              , T1.CUSTOMER_HOLD
              , T1.PAYTERM_TERM_HOLD
              , T1.FP_HOLD
              , T1.MINIMUM_HOLD
              , T1.RESERVE_HOLD
              , T1.MANUAL_HOLD
              , T1.AUTO_PENDING_HOLD
              , T1.ETC_HOLD
              , T1.UNIT_SELLING_PRICE
              , T1.UNIT_LIST_PRICE
              , T1.CURRENCY_CODE
              , T1.ORDERED_DATE
              , T1.BOOKED_DATE
              , T1.CUSTOMER_RAD
              , T1.REQUEST_SHIPPING_DATE
              , T1.PICK_RELEASE_DATE
              , T1.APPOINTMENT_FROM_DATE
              , T1.APPOINTMENT_TO_DATE
              , T1.PROMISED_ARRIVAL_DATE
              , T1.SALES_DATE 
              , T1.CONVERSION_RATE 
              , T1.CREATION_DATE
              , T1.ORDER_QTY
              , T1.CANCEL_QTY
              , T1.ORDER_AMOUNT
                --, T1.PICK_RELEASE_QTY  --DELETE
              , CAST(T1.USD_ORDER_AMOUNT AS NUMERIC)           AS USD_ORDER_AMOUNT
              , T1.OPEN_FLAG
              , T1.RAD_DATE
              , T1.INIT_PROMISED_ARRIVAL_DATE
              , T1.HOLD_RELEASED_FLAG
              , T1.HOLD_DATE
              , T1.HOLD_RELEASE_DATE
              , T1.HOLD_NAME
              , CASE WHEN T1.HOLD_RELEASED_FLAG = 'N' THEN T1.HOLD_DAYS + DATE_DIFF(T1.P_PTT, DATE(T1.HOLD_DATE), DAY)
                     ELSE T1.HOLD_DAYS
                END                                            AS HOLD_DAYS
              , T1.TMS_PICK_RELEASE_DATE
              , T1.TMS_WH_RELEASE_DATE
              , T1.TMS_LOAD_CREATION_DATE
              , T1.TMS_TENDER_DATE
              , T1.WMS_SHIPPING_CONFIRM_DATE
              , T1.WMS_SHIPPED_DATE
              , T1.SHIPPING_DATE
              , T1.TMS_IOD_DATE
              , T1.TMS_POD_DATE
              , T1.TMS_RAD_DATE 
              , T1.TMS_APPOINTMENT_FROM_DATE
              , T1.TMS_APPOINTMENT_TO_DATE
              , IF(T1.SALES_DATE IS NULL, 0, T1.ORDER_QTY)     AS SALES_QTY
              , IF(T1.SALES_DATE IS NULL, 0, T1.ORDER_AMOUNT)  AS SALES_AMOUNT
              , T1.SHIPPED_QTY    + T1.PICK_RELE_QTY    + T1.PICK_READY_QTY    + T1.HOLD_QTY    + T1.OPEN_QTY     AS ACTIVE_QTY
              , T1.SHIPPED_AMOUNT + T1.PICK_RELE_AMOUNT + T1.PICK_READY_AMOUNT + T1.HOLD_AMOUNT + T1.OPEN_AMOUNT  AS ACTIVE_AMOUNT
              , T1.OPEN_QTY
              , T1.OPEN_AMOUNT
              , T1.PICK_READY_QTY
              , T1.PICK_READY_AMOUNT
              , T1.PICK_RELE_QTY
              , T1.PICK_RELE_AMOUNT
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL THEN T1.PICK_RELE_QTY
                     ELSE 0
                END                                            AS SHIP_CONFIRM_QTY
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NOT NULL THEN T1.PICK_RELE_AMOUNT
                     ELSE 0
                END                                            AS SHIP_CONFIRM_AMOUNT
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NULL AND T1.TMS_WH_RELEASE_DATE IS NOT NULL THEN T1.PICK_RELE_QTY
                     ELSE 0
                END                                            AS WH_RELE_QTY
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NULL AND T1.TMS_WH_RELEASE_DATE IS NOT NULL THEN T1.PICK_RELE_AMOUNT
                     ELSE 0
                END                                            AS WH_RELE_AMOUNT
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NULL AND T1.TMS_WH_RELEASE_DATE IS NULL AND T1.TMS_LOAD_CREATION_DATE IS NOT NULL THEN T1.PICK_RELE_QTY
                     ELSE 0
                END                                            AS LOAD_CREATE_QTY
              , CASE WHEN T1.PICK_RELE_QTY > 0 AND T1.WMS_SHIPPING_CONFIRM_DATE IS NULL AND T1.TMS_WH_RELEASE_DATE IS NULL AND T1.TMS_LOAD_CREATION_DATE IS NOT NULL THEN T1.PICK_RELE_AMOUNT
                     ELSE 0
                END                                            AS LOAD_CREATE_AMOUNT
              , T1.SHIPPED_QTY
              , T1.SHIPPED_AMOUNT
              , T1.HOLD_QTY
              , T1.HOLD_AMOUNT
              , T1.AR_HOLD_QTY
              , T1.AR_HOLD_AMOUNT
              , T1.BACK_HOLD_QTY
              , T1.BACK_HOLD_AMOUNT
              , T1.FUTURE_HOLD_QTY
              , T1.FUTURE_HOLD_AMOUNT
              , T1.PRDT_GRP_CD
              , T1.PRDT_CAT_CD
              , T1.TMS_TYPE
              , T1.LOGSTAMP
              , T1.WAREHOUSE_CODE
                /* SO-SA Mapping Direct Shipment 반영 */
              , T1.BL_ID
              , T1.HOUSE_BL_NO
              , T1.CONTAINER_NO
              , T1.SO_SA_MAPPING_FLAG
         FROM   W_MAIN_DATA_SET       AS T1
         WHERE  1 = 1
      )
    , W_IN_DAYS_GET AS
      (
        SELECT M1.SALES_ORDER_NO
             , M1.SALES_ORDER_LINE_NO
             , IF(PROGRESS_STATUS = 'ENTERED'         , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.ORDERED_DATE), DAY), 0)                AS ENTERED_IN_DAYS
             , IF(PROGRESS_STATUS = 'BOOKED'          , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.BOOKED_DATE), DAY), 0)                 AS BOOKED_IN_DAYS
             , IF(PROGRESS_STATUS = 'HOLD'            , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.HOLD_DATE), DAY), 0)                   AS HOLD_IN_DAYS 
             , IF(PROGRESS_STATUS = 'PICK_READY'      , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(COALESCE(M1.HOLD_RELEASE_DATE, M1.BOOKED_DATE)), DAY), 0)  AS PICK_READY_IN_DAYS 
             , IF(PROGRESS_STATUS = 'PICK_RELEASE'    , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_PICK_RELEASE_DATE), DAY), 0)       AS PICK_RELEASE_IN_DAYS
             , IF(PROGRESS_STATUS = 'LOAD_CREATION'   , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_LOAD_CREATION_DATE), DAY), 0)      AS LOAD_CREATION_IN_DAYS 
             , IF(PROGRESS_STATUS = 'WH_RELEASE'      , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_WH_RELEASE_DATE), DAY), 0)         AS WH_RELEASE_IN_DAYS
             , IF(PROGRESS_STATUS = 'SHIPPING_CONFIRM', DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DAY), 0)   AS SHIPPING_CONFIRM_IN_DAYS
             , IF(PROGRESS_STATUS = 'SHIPPED'         , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.WMS_SHIPPED_DATE), DAY), 0)            AS SHIPPED_IN_DAYS
             , IF(PROGRESS_STATUS = 'IOD'             , DATE_DIFF(CURRENT_DATE('Asia/Seoul'), DATE(M1.TMS_IOD_DATE), DAY), 0)                AS IOD_IN_DAYS
               /*
             , IF(PROGRESS_STATUS = 'ENTERED'         , DATE_DIFF(DATE(M1.BOOKED_DATE),               DATE(M1.ORDERED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'BOOKED'          , DATE_DIFF(DATE(M1.HOLD_RELEASE_DATE),         DATE(M1.BOOKED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'HOLD'            , HOLD_DAYS)
             , IF(PROGRESS_STATUS = 'PICK_READY'      , DATE_DIFF(DATE(M1.TMS_PICK_RELEASE_DATE),     DATE(M1.HOLD_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'PICK_RELEASE'    , DATE_DIFF(DATE(M1.TMS_LOAD_CREATION_DATE),    DATE(M1.TMS_PICK_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'LOAD_CREATION'   , DATE_DIFF(DATE(M1.TMS_WH_RELEASE_DATE),       DATE(M1.TMS_LOAD_CREATION_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'WH_RELEASE'      , DATE_DIFF(DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DATE(M1.TMS_WH_RELEASE_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'SHIPPING_CONFIRM', DATE_DIFF(DATE(M1.WMS_SHIPPED_DATE),          DATE(M1.WMS_SHIPPING_CONFIRM_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'SHIPPED'         , DATE_DIFF(DATE(TMS_IOD_DATE),                 DATE(M1.WMS_SHIPPED_DATE), DAY), 0)
             , IF(PROGRESS_STATUS = 'IOD'             , DATE_DIFF(DATE(SALES_DATE),                   DATE(M1.TMS_IOD_DATE), DAY), 0)
               */
        FROM   W_SALES_ORDER_DATA  AS M1
      )
    SELECT T1.P_PTT
         , CAST(NULL AS NUMERIC)     AS ORDER_HEADER_ID
         , CAST(NULL AS NUMERIC)     AS ORDER_LINE_ID
         , T1.SALES_ORDER_NO
         , T1.SALES_ORDER_LINE_NO
         , T1.LINE_STATUS_CODE
         , T1.PROGRESS_STATUS
         , T1.P_SEQ
         , T1.OPEN_FLAG
         , T1.AFFILIATE_CODE
         , T1.SUBSDR_NAME
         , T1.DOMAIN_CODE
         , T1.BILL_TO_CUSTOMER_CODE
         , T1.BILL_TO_CUSTOMER_NAME
         , T1.SHIP_TO_CUSTOMER_CODE
         , T1.SHIP_TO_CUSTOMER_NAME
         , T1.PROJECT_CODE
         , T1.MODEL_CODE
         , T1.DIV_NM
         , T1.MODEL_DESC
         , T1.MODEL_CATEGORY
         , T1.ORDER_TYPE_NAME
         , T1.LINE_CATEGORY_CODE
         , T1.HOLD_FLAG
         , T1.PARTIAL_HOLD_FLAG
         , T1.HOLD_TYPE
         , T1.AR_HOLD
         , T1.FUTURE_HOLD
         , T1.BACK_ORDER_HOLD
         , T1.CREDIT_HOLD
         , T1.OVERDUE_HOLD
         , T1.CUSTOMER_HOLD
         , T1.PAYTERM_TERM_HOLD
         , T1.FP_HOLD
         , T1.MINIMUM_HOLD
         , T1.RESERVE_HOLD
         , T1.MANUAL_HOLD
         , T1.AUTO_PENDING_HOLD
         , T1.ETC_HOLD
         , T1.UNIT_SELLING_PRICE
         , T1.UNIT_LIST_PRICE
         , T1.CURRENCY_CODE
         , T1.ORDERED_DATE
         , T1.BOOKED_DATE
         , T1.CUSTOMER_RAD
         , T1.REQUEST_SHIPPING_DATE
         , T1.PICK_RELEASE_DATE
         , T1.APPOINTMENT_FROM_DATE
         , T1.APPOINTMENT_TO_DATE
         , T1.PROMISED_ARRIVAL_DATE
         , T1.SALES_DATE
         , T1.CONVERSION_RATE
         , T1.CREATION_DATE
         , T1.ORDER_QTY
         , T1.CANCEL_QTY
         , T1.ORDER_AMOUNT
           --, PICK_RELEASE_QTY
         , T1.USD_ORDER_AMOUNT
         , T1.RAD_DATE
         , T1.INIT_PROMISED_ARRIVAL_DATE
         , T1.HOLD_RELEASED_FLAG
         , T1.HOLD_DATE
         , T1.HOLD_RELEASE_DATE
         , T1.HOLD_NAME
         , T1.HOLD_DAYS
         , T1.TMS_PICK_RELEASE_DATE
         , T1.TMS_WH_RELEASE_DATE
         , T1.TMS_LOAD_CREATION_DATE
         , T1.TMS_TENDER_DATE
         , T1.WMS_SHIPPING_CONFIRM_DATE
         , T1.WMS_SHIPPED_DATE
         , T1.SHIPPING_DATE
         , T1.TMS_IOD_DATE
         , T1.TMS_POD_DATE
         , T1.TMS_RAD_DATE
         , T1.TMS_APPOINTMENT_FROM_DATE
         , T1.TMS_APPOINTMENT_TO_DATE
         , T9.ENTERED_IN_DAYS
         , T9.BOOKED_IN_DAYS
         , T9.HOLD_IN_DAYS
         , T9.PICK_READY_IN_DAYS
         , T9.PICK_RELEASE_IN_DAYS
         , T9.LOAD_CREATION_IN_DAYS
         , T9.WH_RELEASE_IN_DAYS
         , T9.SHIPPING_CONFIRM_IN_DAYS
         , T9.SHIPPED_IN_DAYS
         , T9.IOD_IN_DAYS
     	     -- 현재 PROGRESS_STATUS 기준 잔여 평균 소요일 합산 → 도착 예정일 추정
         , DATE_ADD(CURRENT_DATE('Asia/Seoul'),
                    INTERVAL CAST(
                                  ROUND(
                                        CASE T1.PROGRESS_STATUS
                                             WHEN 'ENTERED'          THEN COALESCE(T3.REM_ENTERED_DAYS,          T4.REM_ENTERED_DAYS)
                                             WHEN 'BOOKED'           THEN COALESCE(T3.REM_BOOKED_DAYS,           T4.REM_BOOKED_DAYS)
                                             WHEN 'HOLD'             THEN COALESCE(T3.REM_HOLD_DAYS,             T4.REM_HOLD_DAYS)
                                             WHEN 'PICK_RELEASE'     THEN COALESCE(T3.REM_PICK_RELEASE_DAYS,     T4.REM_PICK_RELEASE_DAYS)
                                             WHEN 'PICK_READY'       THEN COALESCE(T3.REM_PICK_READY_DAYS,       T4.REM_PICK_READY_DAYS)
                                             WHEN 'LOAD_CREATION'    THEN COALESCE(T3.REM_LOAD_CREATION_DAYS,    T4.REM_LOAD_CREATION_DAYS)
                                             WHEN 'WH_RELEASE'       THEN COALESCE(T3.REM_WH_RELEASE_DAYS,       T4.REM_WH_RELEASE_DAYS)
                                             WHEN 'SHIPPING_CONFIRM' THEN COALESCE(T3.REM_SHIPPING_CONFIRM_DAYS, T4.REM_SHIPPING_CONFIRM_DAYS)
                                             WHEN 'SHIPPED'          THEN COALESCE(T3.REM_SHIPPED_DAYS,          T4.REM_SHIPPED_DAYS)
                                             ELSE NULL
                                        END) AS INT64
                    ) DAY)                   AS EST_ARRIVAL_DATE
         , T1.ACTIVE_QTY
         , T1.ACTIVE_AMOUNT
         , CAST(T1.SALES_QTY    AS NUMERIC)  AS SALES_QTY
         , CAST(T1.SALES_AMOUNT AS NUMERIC)  AS SALES_AMOUNT
         , T1.OPEN_QTY
         , T1.OPEN_AMOUNT
         , T1.PICK_READY_QTY
         , T1.PICK_READY_AMOUNT
         , T1.PICK_RELE_QTY                  AS ORI_PICK_RELE_QTY
         , T1.PICK_RELE_AMOUNT               AS ORI_PICK_RELE_AMOUNT
         , IF(T1.SHIP_CONFIRM_QTY + T1.WH_RELE_QTY + T1.LOAD_CREATE_QTY = 0, T1.PICK_RELE_QTY, 0)     AS PICK_RELE_QTY
         , IF(T1.SHIP_CONFIRM_QTY + T1.WH_RELE_QTY + T1.LOAD_CREATE_QTY = 0, T1.PICK_RELE_AMOUNT, 0)  AS PICK_RELE_AMOUNT
         , T1.SHIP_CONFIRM_QTY
         , T1.SHIP_CONFIRM_AMOUNT
         , T1.WH_RELE_QTY
         , T1.WH_RELE_AMOUNT
         , T1.LOAD_CREATE_QTY
         , T1.LOAD_CREATE_AMOUNT
         , T1.SHIPPED_QTY
         , T1.SHIPPED_AMOUNT
         , T1.HOLD_QTY
         , T1.HOLD_AMOUNT
         , T1.AR_HOLD_QTY
         , T1.AR_HOLD_AMOUNT
         , T1.BACK_HOLD_QTY
         , T1.BACK_HOLD_AMOUNT
         , T1.FUTURE_HOLD_QTY
         , T1.FUTURE_HOLD_AMOUNT
         , 'NERP'                            AS SOURCE
         , T1.PRDT_GRP_CD
         , T1.PRDT_CAT_CD
         , IF(T1.CONTAINER_NO IS NOT NULL, 'DIRECT', T1.TMS_TYPE)  AS TR_SYS_TYPE
         , T1.LOGSTAMP
         , T2.BILLTO_BIZ_NAME
         , T2.TEAM_NAME
         , T1.WAREHOUSE_CODE
         , T1.BL_ID
         , T1.HOUSE_BL_NO
         , T1.CONTAINER_NO
         , T1.SO_SA_MAPPING_FLAG
    FROM   W_SALES_ORDER_DATA                                          AS T1
    JOIN   W_IN_DAYS_GET                                               AS T9
       ON  T1.SALES_ORDER_NO       =  T9.SALES_ORDER_NO
      AND  T1.SALES_ORDER_LINE_NO  =  T9.SALES_ORDER_LINE_NO
    LEFT OUTER JOIN 
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST  AS T2
       ON  T1.SUBSDR_NAME            =  T2.SUBSDR_NAME
      AND  T1.BILL_TO_CUSTOMER_CODE  =  T2.BILLTO_CODE
      AND  T1.PRDT_GRP_CD            =  T2.PRODUCT_GROUP_CODE
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SO_REM_DAYS         AS T3
       ON  T1.SUBSDR_NAME            =  T3.SUBSDR_NAME
      AND  T1.SHIP_TO_CUSTOMER_CODE  =  T3.SHIP_TO_CUSTOMER_CODE
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SO_REM_DAYS         AS T4
       ON  T1.SUBSDR_NAME            =  T4.SUBSDR_NAME
      AND  T4.SHIP_TO_CUSTOMER_CODE  =  '[ALL]'
    ;

    /*------------------------------------------------------------------------------------------------------------------
    SELECT * FROM (
    SELECT SALES_ORDER_NO
         , SALES_ORDER_LINE_NO
         , CASE WHEN REMN_PICK_RELE_QTY > 0 AND SHIPPED_QTY > 0 AND PICK_RELE_QTY > 0 THEN 'PICK_RELEASE, SHIPPED'
                WHEN SHIPPED_QTY   > 0 AND HOLD_RELE_QTY > 0                          THEN 'HOLD RELEASE, SHIPPED'
                WHEN PICK_RELE_QTY > 0 AND HOLD_RELE_QTY > 0                          THEN 'HOLD RELEASE, PICK_RELEASE'
                WHEN SHIPPED_QTY   > 0 THEN 'SHIPPED'
                WHEN PICK_RELE_QTY > 0 THEN 'PICK_RELEASE'
                WHEN HOLD_RELE_QTY > 0 THEN 'HOLD RELEASE'
                WHEN HOLD_QTY      > 0 THEN 'HOLD'
                WHEN REMN_OPEN_QTY > 0 THEN 'BOOKED'
           END  STATUS
    FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_NEW_T11
    WHERE  1 = 1
    --  AND  SALES_ORDER_NO IN ('1123403246', '1120085206')
    )
    WHERE  1 = 1
      AND  LENGTH(STATUS) - LENGTH(REPLACE(STATUS, ',', '')) >= 1 
    ;
    --------------------------------------------------------------------------------------------------------------------*/

END