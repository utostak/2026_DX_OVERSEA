BEGIN

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_T01', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.T01 (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01
    AS
    WITH T_P_PTT AS
    (
      SELECT MAX(P_PTT) AS P_PTT
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S
    )
    , T_P_SEQ AS
    (
      SELECT MAX(P_SEQ) AS P_SEQ 
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T
      WHERE  P_PTT  =  ( SELECT P_PTT FROM T_P_PTT )
    )
    , T_LIST AS
    (
      SELECT *
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T1
      WHERE  P_SEQ             =  'Closed' 
        AND  LINE_STATUS_CODE  =  'CLOSED'
      UNION ALL
      SELECT *
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__SO_LINE_DW_S T1
      WHERE  P_PTT  =  ( SELECT P_PTT FROM T_P_PTT )
        AND  P_SEQ  =  ( SELECT P_SEQ FROM T_P_SEQ )
        --AND  AFFILIATE_CODE = 'EEPL'
    )
    SELECT T1.P_PTT
         , P_SEQ
         , T1.AFFILIATE_CODE
         , T2.SUBSDR_NM                            AS SUBSDR_NAME
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
         , M.DIV_NM
         , M.CMPNY_CD
         , M.CMPNY_NM
         , MODE_DESC                               AS MODEL_DESC
         , MODEL_CATEGORY
         , PRODUCT_LEVEL1_CODE
         , PRODUCT_LEVEL2_CODE
         , PRODUCT_LEVEL3_CODE
         , PRODUCT_LEVEL4_CODE 
         , ORDER_CATEGORY_CODE
         , ORDER_TYPE_NAME
         , LINE_CATEGORY_CODE
         , SALES_ORDER_NO
         , T1.ORDER_HEADER_ID
         , SALES_ORDER_LINE_NO
         , T1.ORDER_LINE_ID
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
         , T1.RELEASE_DATE 
         , CASE WHEN T1.HOLD_FLAG = 'Y' THEN  
                     CASE WHEN T1.CREDIT_HOLD  = 'Y'    THEN 'Finance Hold'
                          WHEN T1.OVERDUE_HOLD = 'Y'    THEN 'Finance Hold'
                          WHEN T1.FUTURE_HOLD  = 'Y'    THEN 'Future' 
                          WHEN T1.BACK_ORDER_HOLD = 'N' THEN 'Etc'  
                          WHEN T1.BACK_ORDER_HOLD = 'Y' THEN 'Back Order'   
                     END
           END                                     AS HOLD_TYPE
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
         , COALESCE(REQUEST_ARRIVAL_TO_DATE, REQUEST_ARRIVAL_FROM_DATE)  AS RAD_DATE
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
         , CR.USD_CONVERSION_RATE                  AS  CONVERSION_RATE 
         , INVOICE_REMARK
         , CREATION_DATE
         , ORDER_QTY
         , CANCEL_QTY
         , ORDER_AMOUNT 
         , ORDER_AMOUNT * CR.USD_CONVERSION_RATE   AS USD_ORDER_AMOUNT 
         , PICK_RELEASE_QTY
         , IL_BRANCH
         , TAX_AMOUNT
         , CHARGE_AMOUNT
         , IL_MODEL_CATEGORY
         , PRODUCT_VALUE
         , ITEM_TYPE
         , INIT_PROMISED_ARRIVAL_DATE
         , T3.RELEASED_FLAG                              AS HOLD_RELEASED_FLAG
         , T3.HOLD_DATE
         , T3.RELEASE_DATE                               AS HOLD_RELEASE_DATE
         , T3.HOLD_REASON_CODE
         , T3.HOLD_NAME
         , T3.HOLD_DAYS
         , T6.PRODUCT_GROUP_CODE                         AS PRDT_GRP_CD
         , T6.PRODUCT_CATEGORY_CODE                      AS PRDT_CAT_CD
           /* 2026-08-13 : T7 - Direct Shipment 반영 */   
         , T7.BL_ID                                      AS BL_ID
         , T7.HOUSE_BL_NO                                AS HOUSE_BL_NO
         , CASE WHEN T7.CONTAINER_NO IS NOT NULL THEN T7.CONTAINER_NO
                WHEN PO.PO_CONTAINER_NO IS NOT NULL THEN PO.PO_CONTAINER_NO
                WHEN T1.ORDER_TYPE_NAME LIKE 'DIRECT%' THEN '_'
                ELSE NULL
            END                                          AS CONTAINER_NO   -- DIRECT 상태인데 아직 NO가 나오지 않은경우 _ 처리 (화면에서 DIRECT 구분을 위함)
         , T7.SO_SA_MAPPING_FLAG                         AS SO_SA_MAPPING_FLAG
    FROM   T_LIST                                                           AS T1
    JOIN   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST               AS T2
       ON  T1.AFFILIATE_CODE  =  T2.SUBSDR_CD
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_USD_CONVERSION_RATE_MST  AS CR
       ON  T1.CURRENCY_CODE  =  CR.FROM_CURRENCY_CODE
      AND  T1.ORDERED_DATE   =  CR.P_PTT
    LEFT OUTER JOIN
           `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST          AS M
       ON  T1.MODEL_CODE = M.MDL_SFFX_CD
    LEFT OUTER JOIN
         (
           SELECT ORDER_HEADER_ID
                , ORDER_LINE_ID
                , MAX(CASE WHEN RN = 1 THEN RELEASED_FLAG END)    AS RELEASED_FLAG
                , MAX(CASE WHEN RN = 1 THEN HOLD_DATE END)        AS HOLD_DATE
                , MAX(CASE WHEN RN = 1 THEN RELEASE_DATE END)     AS RELEASE_DATE
                , MAX(CASE WHEN RN = 1 THEN HOLD_REASON_CODE END) AS HOLD_REASON_CODE
                , MAX(CASE WHEN RN = 1 THEN HOLD_NAME END)        AS HOLD_NAME
                , SUM(HOLD_DAYS) AS HOLD_DAYS
           FROM (
                  SELECT L.*
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
                              , DATE_DIFF(DATE(RELEASE_DATE), DATE(HOLD_DATE), DAY) AS HOLD_DAYS
                         FROM   `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V
                         WHERE  1 = 1
                           AND  HOLD_LEVEL       =   'LINE'
                           AND  ORDER_HEADER_ID  IN  ( SELECT ORDER_HEADER_ID FROM T_LIST )
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
                         FROM   `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_ORDER_HOLDS_HISTORY_V  AS T1
                         JOIN   T_LIST                                                           AS T2
                            ON  T1.ORDER_HEADER_ID  =  T2.ORDER_HEADER_ID
                         WHERE  HOLD_LEVEL  =  'HEADER'
                       ) L
                )
           GROUP  BY 1, 2
        )                                                                   AS T3
       ON  T1.ORDER_HEADER_ID = T3.ORDER_HEADER_ID
      AND  T1.ORDER_LINE_ID   = T3.ORDER_LINE_ID
     LEFT OUTER JOIN
            `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_PRODUCT_MST        AS T6
       ON  1 = 1
      AND  T6.SUBSDR_NAME   =  T2.SUBSDR_NM
      AND  T6.PRODUCT_CODE  =  T1.PRODUCT_LEVEL4_CODE
	  /* 2026-08-13 : T7 - Direct Shipment 반영 */   
     LEFT OUTER JOIN
         (
           SELECT X1.ORG_ID
			          , X1.ORDER_HEADER_ID        AS  ORDER_HEADER_ID
			          , X1.ORDER_LINE_ID          AS  ORDER_LINE_ID  
			          , CAST(X1.BL_ID AS STRING)  AS  BL_ID 
			          , CAST(NULL     AS STRING)  AS  HOUSE_BL_NO         /* 나중에 찾아 넣어야 할듯 */
			          , X1.CONTAINER_NO           AS  CONTAINER_NO   
			          , 'Y'                       AS  SO_SA_MAPPING_FLAG
					 FROM (
					        SELECT *
					        FROM   `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXOMDS_SO_SA_MAPPING
					        WHERE  1 = 1 
					        QUALIFY ROW_NUMBER() OVER (PARTITION BY ORG_ID, ORDER_HEADER_ID, ORDER_LINE_ID ORDER BY LAST_UPDATE_DATE DESC) = 1
					      ) AS X1
				   WHERE  X1.STATUS_CODE  !=  'CANCELLED'
         )                                                                  AS T7
       ON  T1.ORDER_HEADER_ID  =  T7.ORDER_HEADER_ID
      AND  T1.ORDER_LINE_ID    =  T7.ORDER_LINE_ID
     LEFT OUTER JOIN                                       -- 신규 추가 (직배송 PO 컨테이너 fallback)
          (
            SELECT P.TO_SUBSDR_CD,
                   CAST(CAST(P.DIRECT_SALES_ORDER_NO AS INT64) AS STRING) AS SO_NO,
                   P.DIRECT_LINE_NO AS SO_LINE_NO,
                   STRING_AGG(DISTINCT P.CNTR_NO, ', ') AS PO_CONTAINER_NO
              FROM `pjt-lge-edl-ob`.OB_00030.V_L1SCM__TRSCM__VD_PO_TRACKING_L P
             WHERE P.CNTR_NO IS NOT NULL
               AND P.DIRECT_SALES_ORDER_NO IS NOT NULL
             GROUP BY 1, 2, 3
          ) AS PO
        ON T1.AFFILIATE_CODE = PO.TO_SUBSDR_CD
       AND T1.SALES_ORDER_NO = PO.SO_NO
       AND T1.SALES_ORDER_LINE_NO = PO.SO_LINE_NO
       AND T1.ORDER_TYPE_NAME LIKE 'DIRECT%'              -- 직배송 등록 오더만 매칭
     WHERE  1 = 1
       AND  T1.ORDERED_DATE  >=  '2025-01-01'
       AND (
             (T1.LINE_STATUS_CODE != 'CLOSED' AND COALESCE(T2.NERP_OPEN_YMD,'99991231') >= FORMAT_DATE('%Y%m%d',CURRENT_DATE()))
        OR   (T1.LINE_STATUS_CODE =  'CLOSED')
           )
    ;

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_T01', CURRENT_TIMESTAMP, 'END', 'OSO.LIW.T01 (Hourly)');

END