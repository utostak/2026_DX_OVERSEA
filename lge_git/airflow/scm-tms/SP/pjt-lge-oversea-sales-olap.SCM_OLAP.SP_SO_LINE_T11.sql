BEGIN

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_T11', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.T11 (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11
    PARTITION BY ORDERED_DATE
    CLUSTER   BY SUBSDR_NAME
    AS
    WITH W_ZSSDA0226 AS
    (
      SELECT a.*
           , s.SUBSDR_NM
           , IF(a.DOC_TYPE  IN  ('ZCR', 'ZCRN', 'ZDR', 'ZOR', 'ZRE'), 'Y', 'N')  AS GROSS_SALES_ONLY
           , CASE WHEN a.ZITMSTSTX  =   'Completed' AND
                       a.BILL_DATE  IS  NOT NULL    AND
                       a.DOC_TYPE   IN  ('YDDC', 'YRIC', 'YRID', 'ZCR', 'ZDR', 'ZOR', 'ZORE', 'ZORL', 'ZRE') THEN 'Y'
                  ELSE 'N'
             END                                                                 AS INVOICED_YN
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDA0226        a
      JOIN   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST  s
         ON  a.COMP_CODE    =   s.SUBSDR_CD
        AND  s.DATA_AGG_YN  =   'Y'
        AND  a.DOC_DATE     >=  DATE_SUB(CURRENT_DATE, INTERVAL 1 YEAR)
      WHERE  a.SALESORG  LIKE  '%00'
        AND  a.ZDELEFG    <>   'D'
        AND  a.COMP_CODE  <>   'EACM'
      QUALIFY ROW_NUMBER() OVER(PARTITION BY a.COMP_CODE, a.DOC_NUMBER, a.S_ORD_ITEM ORDER BY a.ZLOGSTMP DESC) = 1
    )
    , W_MODEL_MST AS
    (
      SELECT MDL_SFFX_CD              AS MDL_SFFX_CD
           , ANY_VALUE(DIV_NM)        AS DIV_NM
           , ANY_VALUE(CMPNY_CD)      AS CMPNY_CD
           , ANY_VALUE(CMPNY_NM)      AS CMPNY_NM
           , ANY_VALUE(MDL_DESC)      AS MDL_DESC
           , ANY_VALUE(PROD_LVL4_CD)  AS PROD_LVL4_CD
      FROM   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST
      GROUP BY 1
    )
    , W_SOLDTO_NAME_GET AS
    (
      SELECT KUNNR                   AS SOLDTO_CD
           , ANY_VALUE(NAME_LOCAL)   AS SOLDTO_NM
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0MDM3_V_EDL_MDMS_BP_CUST_MST_SND_INF
      GROUP BY 1
    )
    , W_SHIPTO_NAME_GET AS
    (
      SELECT BUKRS
           , KUNNR                        AS SHIPTO_CD
           , ANY_VALUE(ZZ_SHORT_NAME_EN)  AS SHIPTO_NM
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0MDM3_MDMS_BP_SHIP_TO_PARTY_RCV_INF
      GROUP  BY 1,2
    )
    , W_DATA_SOURCE_GET AS
    (
      SELECT T1.SUBSDR_NM
           , T1.DOC_NUMBER    -- Sales Order No / VBELN
           , T1.S_ORD_ITEM    -- Sales Order Line No / POSNR
           , T1.DOC_TYPE      -- Order Type Cd / AUART
           , T2.DOC_TYPE_NM                         AS DOC_TYPE_NM
           , T1.ZPRCTR        -- Division Cd
           , T1.MATERIAL      -- Model Sffx Cd / MATNR
           , T1.ZMLCGC        -- Model Category
           , T1.ZORGONO
           , T1.ZPRDDITM
           , T1.PRODH4        --
           , T1.ZDOMAINCD     -- Domain Code
           , T1.SOLD_TO       --
           , T1.ZCUS_NM       -- Soldto Cust Name
           , T1.SHIP_TO       --
           , T3.SHIPTO_NM                           AS SHIPTO_NM
           , T1.WBS_ELEMT     -- Project Cd
           , T1.COMP_CODE     -- Affiliate Cd
           , T1.ZBUS_AREA     -- AU Cd
           , T1.ZLCURK        -- Currency Cd
           , T1.ZITMSTSCD     --
           , T1.ZITMSTSTX     -- Status / ITEM_STATUS_TX
           , T1.ZHOLD_FG      -- ETC Hold Flag
           , T1.ZBOH_FG       -- Back Hold Flag
           , T1.ZCRH_FG       -- Credit Hold
           , T1.ZOVH_FG       -- Overdue Hold
           , T1.ZCUH_FG       -- Customer Hold
           , T1.ZPYH_FG       -- Payment Term Hold
           , T1.ZDISPTH       -- Dispute Hold
           , T1.ZCRHE_FG      --
           , T1.ZOVHE_FG      --
           , T1.ZCUHE_FG      --
           , T1.ZPYHE_FG      --
           , T1.ZFH_FG        -- Future Hold / ZZ1_LIFSK_02_SDI
           , T1.ZREH_FG       -- Reserve Hold / ZZ1_LIFSK_03_SDI
           , T1.ZFPH_FG       -- FP Hold / ZZ1_LIFSK_11_SDI
           , T1.ZMIH_FG       -- Minimum Hold / ZZ1_LIFSK_10_SDI
           , T1.ZAPH_FG       -- Auto Pending Hold / ZZ1_LIFSK_13_SDI
           , T1.ZMAH_FG       -- Manual Hold / ZZ1_LIFSK_14_SDI
           , T1.DEL_BLOCK     --
           , T1.DOC_DATE      -- Ordered Date
           , T1.ZBOOKEDDT     -- Booked Date
           , T1.ZSOCREDAT     -- Creation Date
           , T1.ZC_RAD_DT     -- Customer Request Delivery Date / Request Delivery Date
           , T1.REQ_DATE      -- Request Delivery Date / EDATU
           , T1.ZRSH_DT       -- Request Shipping Date / ZZ1_REQ_SHIP_DATE_SDI (7.21, KDK)
           , T1.ZDELIVDT      -- Pick Release Date / DELI_DATE
           , T1.ZAPP_DT_F     -- Appointment From Date
           , T1.ZAPP_DT       -- Appointment To Date
           , T1.ZIPAD_DT      -- Init Promised Arrival Date
           , T1.ZPAD_DT       -- Promised Arrival Date
           , T1.BILL_DATE     -- Sales Date
           , T1.BILL_NUM      -- Sales Qty
           , T1.ZSHIPNGDT     -- Shipping Date
           , T1.GROSS_SALES_ONLY
           , T1.INVOICED_YN
             --(26.07.24 KDK, 'A0226'은 이미 음수처리가 되어있음), IF(T1.IMODOCCAT IN ('H','K'), -1, 1)   AS SGN              -- 반품(H)/환불(K) - 음수처리
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZREQ_QTY  AS FLOAT64), 0)  AS ORDER_QTY        -- 주문수량
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZSDDELQTY AS FLOAT64), 0)  AS LE_QTY           -- 납품(출고요청)수량
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZSHSPQTY  AS FLOAT64), 0)  AS SHIP_QTY         -- 출고수량
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZPODQTY   AS FLOAT64), 0)  AS POD_QTY          -- 고객입고수량
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZBKORDQTY AS FLOAT64), 0)  AS BACKORDER_QTY
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZSCNL_QTY AS FLOAT64), 0)  AS CANCEL_QTY
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.CONF_QTY  AS FLOAT64), 0)  AS CONF_QTY
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZOREXTAMT AS FLOAT64), 0)  AS ORDER_AMOUNT     -- 공급가(excl tax)
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZORUSAMT  AS FLOAT64), 0)  AS USD_ORDER_AMOUNT
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZUSD_RATE AS FLOAT64), 0)  AS CONVERSION_RATE
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZUNIAMT   AS FLOAT64), 0)  AS UNIT_SELL
           , IF(T1.GROSS_SALES_ONLY = 'Y', CAST(T1.ZS_LI_PRC AS FLOAT64), 0)  AS UNIT_LIST
           , IF(T1.INVOICED_YN = 'Y', CAST(T1.ZBILL_QTY AS FLOAT64), 0)       AS BILLING_QTY
           , IF(T1.INVOICED_YN = 'Y', CAST(T1.ZBILLAMT  AS FLOAT64), 0)       AS BILLING_AMOUNT
           , IF(T1.GROSS_SALES_ONLY = 'Y', SAFE_DIVIDE(CAST(T1.ZOREXTAMT AS FLOAT64), CAST(T1.ZREQ_QTY AS FLOAT64)), 0)  AS UNIT_PRICE
           , IF(T1.ZITMSTSTX IN ('Open', 'Fully Shipped', 'Partially Shipped'), 'Open', 'Closed')  AS P_SEQ
           , IF(T1.ZHOLD_FG = 'N' AND COALESCE(T1.ZBOH_FG,'N') = 'N', 'N', 'Y')                    AS BLOCK_FLAG
           , IF(COALESCE(CAST(T1.CONF_QTY AS FLOAT64), 0) > 0, 'Y', 'N')                           AS READY_TO_PICK
           , T1.ZLOGSTMP                            AS LOGSTAMP
           , T4.DIV_NM                              AS DIV_NM
           , T4.CMPNY_CD                            AS CMPNY_CD
           , T4.CMPNY_NM                            AS CMPNY_NM
           , T4.MDL_DESC                            AS MDL_DESC
           , T5.PRODUCT_GROUP_CODE                  AS PRDT_GRP_CD
           , T5.PRODUCT_CATEGORY_CODE               AS PRDT_CAT_CD
           , T1.ZXREF1_HD                           AS INVOICE_NO
           , T1.IMODOCCAT                           AS ORDER_CATEGORY
           , T1.ZPRDUNIT                            AS USER_ITEM_TYPE
           , T1.PLANT                               AS WAREHOUSE_CODE
      FROM   W_ZSSDA0226        AS T1
      LEFT OUTER JOIN
           (
             SELECT KFIELD01             AS DOC_TYPE
                  , ANY_VALUE(CFIELD02)  AS DOC_TYPE_NM
             FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZPCMA0060
             WHERE  CODEGRP  =  'ZSD_ORDER_SALES_FG'
             GROUP  BY 1
           )                    AS T2
         ON  1 = 1
        AND  T2.DOC_TYPE  =  T1.DOC_TYPE
      LEFT OUTER JOIN
             W_SHIPTO_NAME_GET  AS T3
         ON  1 = 1
        AND  T3.SHIPTO_CD  =  T1.SHIP_TO
        AND  T3.BUKRS      =  T1.COMP_CODE
      LEFT OUTER JOIN
             W_MODEL_MST        AS T4
         ON  1 = 1
        AND  T4.MDL_SFFX_CD  =  T1.MATERIAL
      LEFT OUTER JOIN
             `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_PRODUCT_MST  AS T5
         ON  1 = 1
        AND  T5.SUBSDR_NAME   =  T1.SUBSDR_NM
        AND  T5.PRODUCT_CODE  =  T4.PROD_LVL4_CD
    )
    , W_STATUS_QTY_GET AS
    (
      SELECT *
           , CASE WHEN P_SEQ = 'Open' AND GROSS_SALES_ONLY = 'Y' AND BLOCK_FLAG = 'N'
                       THEN ROUND(GREATEST(SHIP_QTY - POD_QTY, 0), 3)
                  ELSE 0
             END       AS DELY_QTY
           , CASE WHEN P_SEQ = 'Open' AND GROSS_SALES_ONLY = 'Y' AND BLOCK_FLAG = 'N'
                       THEN ROUND(GREATEST(LE_QTY - SHIP_QTY, 0), 3)
                  ELSE 0
             END       AS PICK_QTY
           , CASE WHEN P_SEQ = 'Open' AND GROSS_SALES_ONLY = 'Y' AND ZITMSTSTX = 'Open'
                       AND READY_TO_PICK = 'Y' AND COALESCE(ZBOH_FG, 'N') = 'N' AND ZCRH_FG = 'N' AND BLOCK_FLAG = 'N'
                       THEN ROUND(GREATEST(ORDER_QTY - GREATEST(LE_QTY - SHIP_QTY, 0), 0), 3)
                  ELSE 0
             END       AS OPEN_QTY
           , CASE WHEN P_SEQ = 'Open' AND GROSS_SALES_ONLY = 'Y' AND ZITMSTSTX = 'Open'
                       AND READY_TO_PICK = 'N' AND COALESCE(ZBOH_FG, 'N') = 'Y' AND ZCRH_FG = 'N'
                       THEN ROUND(ORDER_QTY, 3)
                  ELSE 0
             END       AS BACK_ORDER_QTY
           , CASE WHEN P_SEQ = 'Open' AND GROSS_SALES_ONLY = 'Y' AND (ZCRH_FG = 'Y' OR ZOVH_FG = 'Y' OR ZDISPTH = 'Y' OR ZCUH_FG = 'Y' OR ZPYH_FG = 'Y') THEN ROUND(ORDER_QTY, 3)
                  ELSE 0
             END       AS AR_HOLD_QTY
      FROM   W_DATA_SOURCE_GET
    )
    , W_HOLD_HISTORY AS
    (
      SELECT VBELN
           , POSNR
           , MIN(RELEASED_FLAG)  AS RELEASED_FLAG
           , MIN(HOLD_DT)        AS HOLD_DT
           , MAX(RELEASE_DT)     AS RELEASE_DT
           , MAX(IF(RELEASED_FLAG = 'N', BLOCK_NAME, NULL))  AS BLOCK_NAME
           , SUM(HOLD_DAYS)      AS HOLD_DAYS
      FROM (
             SELECT VBELN
                  , POSNR
                  , CASE WHEN VALUE_NEW IN ('A','C') THEN 'Y'
                         ELSE 'N'
                    END                     AS RELEASED_FLAG
                  , DATETIME(ERDAT, ERZET)  AS HOLD_DT
                  , DATETIME(UDATE, UTIME)  AS RELEASE_DT
                  , REPTEXT                 AS BLOCK_NAME
                  , DATE_DIFF(DATE(ERDAT), DATE(UDATE), DAY)  AS HOLD_DAYS
             FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDI1002
             QUALIFY ROW_NUMBER() OVER(PARTITION BY VBELN, POSNR, FNAME ORDER BY DATETIME(UDATE, UTIME) DESC) = 1
           )
      GROUP BY VBELN, POSNR
    )
    , W_ZSSDI1018 AS
    (
      SELECT z.VBELN
           , z.POSNR
           , z.AUART
           , TRIM(SPLIT(z.AUART, ":")[offset(0)])  AS DOC_TYPE
           , SPLIT(z.AUART, ":")[offset(1)]        AS DOC_TYPE_NM
           , z.KUNAG
           , z.SOLDTONM
           , z.MATNR
           , z.FKDAT
           , z.FKLMG
           , z.SALESAMTEXC
           , z.WAERK
           , s.SUBSDR_NM
           , z.GIDATE
           , T4.DIV_NM                             AS DIV_NM
           , T4.CMPNY_CD                           AS CMPNY_CD
           , T4.CMPNY_NM                           AS CMPNY_NM
           , T4.MDL_DESC                           AS MDL_DESC
           , T5.PRODUCT_CATEGORY_CODE              AS PRDT_CAT_CD
           , T5.PRODUCT_GROUP_CODE                 AS PRDT_GRP_CD
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDI1018        AS z
      JOIN   `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_SUBSDR_MST  AS s
         ON  z.BUKRS        =  s.SUBSDR_CD
        AND  s.DATA_AGG_YN  =  'Y'
      LEFT OUTER JOIN
             W_MODEL_MST        AS T4
         ON  1 = 1
        AND  T4.MDL_SFFX_CD  =  z.MATNR
      LEFT OUTER JOIN
             `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_PRODUCT_MST  AS T5
         ON  1 = 1
        AND  T5.SUBSDR_NAME   =  s.SUBSDR_NM
        AND  T5.PRODUCT_CODE  =  T4.PROD_LVL4_CD
      WHERE  z.VKORG  LIKE  '%00'
        AND  STARTS_WITH(z.AUART, 'YDDC')
        -- (전체 Read) AND  z.FKDAT  >=  DATE '2026-01-01'
      QUALIFY ROW_NUMBER() OVER (PARTITION BY z.BUKRS, z.VBELN, z.POSNR ORDER BY z.ZLOADTMP0 DESC) = 1
    )
    , W_ZSLES0201 AS
    ( /* 2026-08-18 : NERP Direct Shipment 반영 */
      SELECT  X1.BUKRS                      AS  BUKRS
           ,  X1.VBELN                      AS  VBELN
           ,  X1.POSNR                      AS  POSNR
           ,  X1.BL_ID                      AS  BL_ID
           ,  X1.HOUSE_BL_NO                AS  HOUSE_BL_NO
           ,  X1.CONTAINER_NO               AS  CONTAINER_NO
           ,  X1.MATNR                      AS  MATNR
           ,  X1.KWMENG                     AS  KWMENG
           ,  X1.ALLOCATION_QTY             AS  ALLOCATION_QTY
           ,  X1.ZSAQTY                     AS  ZSAQTY            /* Container_no 기준의 KWMENG 합 */
           ,  X1.ZSA_CANCEL_FLAG            AS  ZSA_CANCEL_FLAG
           ,  X1.ZSA_MAPPING_NO             AS  ZSA_MAPPING_NO
           , 'Y'                            AS  SO_SA_MAPPING_FLAG
      FROM (
             SELECT *
             FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSLES0201
             QUALIFY ROW_NUMBER() OVER (PARTITION BY BUKRS, VBELN, POSNR ORDER BY ZTPNUM DESC) = 1
           )  AS X1
      WHERE  1 = 1
        AND  X1.ZSA_CANCEL_FLAG  !=  'Y'
    )
    SELECT DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)       AS P_PTT
         , B.P_SEQ                                        AS P_SEQ
         , B.COMP_CODE                                    AS AFFILIATE_CODE
         , B.SUBSDR_NM                                    AS SUBSDR_NAME
         , B.DOC_NUMBER                                   AS SALES_ORDER_NO
         , B.S_ORD_ITEM                                   AS SALES_ORDER_LINE_NO
         , IF(COALESCE(B.ZORGONO, '') NOT IN ('', '0'), B.ZPRDDITM, NULL)  AS ITEM
         , B.DOC_TYPE || ':' || B.DOC_TYPE_NM             AS LINE_CATEGORY_CODE
         , B.WBS_ELEMT                                    AS PROJECT_CODE
         , B.DOC_TYPE                                     AS ORDER_TYPE
         , B.DOC_TYPE_NM                                  AS ORDER_TYPE_NAME
         , B.ZITMSTSTX                                    AS LINE_STATUS_CODE
         , CAST(B.ORDER_QTY AS NUMERIC)                   AS ORDER_QTY
         , CAST(B.LE_QTY AS NUMERIC)                      AS PICK_RELEASE_QTY
         , CAST(B.CANCEL_QTY AS NUMERIC)                  AS CANCEL_QTY
         , B.ZLCURK                                       AS CURRENCY_CODE
         , CAST(B.UNIT_SELL AS NUMERIC)                   AS UNIT_SELLING_PRICE
         , CAST(B.UNIT_LIST AS NUMERIC)                   AS UNIT_LIST_PRICE
         , CAST(ROUND(B.ORDER_AMOUNT, 2) AS NUMERIC)      AS ORDER_AMOUNT
         , CAST(ROUND(B.USD_ORDER_AMOUNT, 2) AS NUMERIC)  AS USD_ORDER_AMOUNT
         , CAST(B.CONVERSION_RATE AS NUMERIC)             AS CONVERSION_RATE
         , B.ZDOMAINCD                                    AS DOMAIN_CODE
         , B.SOLD_TO                                      AS BILL_TO_CUSTOMER_CODE
         , COALESCE(S1.SOLDTO_NM, B.ZCUS_NM, '')          AS BILL_TO_CUSTOMER_NAME
         , B.SHIP_TO                                      AS SHIP_TO_CUSTOMER_CODE
         , B.SHIPTO_NM                                    AS SHIP_TO_CUSTOMER_NAME
         , B.MATERIAL                                     AS MODEL_CODE
         , B.ZMLCGC                                       AS MODEL_CATEGORY
         , B.ZPRCTR                                       AS DIV_CD
         , B.DIV_NM                                       AS DIV_NM
         , B.CMPNY_CD                                     AS CMPNY_CD
         , B.CMPNY_NM                                     AS CMPNY_NM
         , B.MDL_DESC                                     AS MODEL_DESC
         , B.PRDT_GRP_CD                                  AS PRDT_GRP_CD
         , B.PRDT_CAT_CD                                  AS PRDT_CAT_CD
         , CASE WHEN B.ZCRH_FG = 'Y' OR B.ZOVH_FG = 'Y' OR B.ZDISPTH = 'Y' OR B.ZCUH_FG = 'Y' OR B.ZPYH_FG = 'Y' THEN 'AR_HOLD'
                WHEN COALESCE(B.ZFH_FG,  'N') = 'Y' THEN 'FUTURE_HOLD'
                WHEN COALESCE(B.ZBOH_FG, 'N') = 'Y' THEN 'BACK_HOLD'
                WHEN B.ZMAH_FG = 'Y' OR B.ZFPH_FG = 'Y' OR B.ZMIH_FG = 'Y' OR B.ZREH_FG = 'Y' OR B.ZAPH_FG = 'Y' THEN 'ETC_HOLD'
           END                                            AS HOLD_TYPE
         , IF(B.ZCRH_FG = 'Y' OR B.ZOVH_FG = 'Y' OR B.ZDISPTH = 'Y' OR B.ZCUH_FG = 'Y' OR B.ZPYH_FG = 'Y', 'Y', 'N')  AS AR_HOLD
         , COALESCE(B.ZFH_FG, 'N')                        AS FUTURE_HOLD
         , COALESCE(B.ZBOH_FG, 'N')                       AS BACK_HOLD
         , B.ZCRH_FG                                      AS CREDIT_HOLD
         , B.ZOVH_FG                                      AS OVERDUE_HOLD
         , B.ZCUH_FG                                      AS CUSTOMER_HOLD
         , B.ZPYH_FG                                      AS PAYTERM_TERM_HOLD
         , B.ZFPH_FG                                      AS FP_HOLD
         , B.ZMIH_FG                                      AS MINIMUM_HOLD
         , B.ZREH_FG                                      AS RESERVE_HOLD
         , B.ZMAH_FG                                      AS MANUAL_HOLD
         , B.ZAPH_FG                                      AS AUTO_PENDING_HOLD
         , IF(B.ZMAH_FG = 'Y' OR B.ZFPH_FG = 'Y' OR B.ZMIH_FG = 'Y' OR B.ZREH_FG = 'Y' OR B.ZAPH_FG = 'Y', 'Y', 'N')  AS ETC_HOLD
         , B.DOC_DATE                                     AS ORDERED_DATE
         , B.ZC_RAD_DT                                    AS CUSTOMER_RAD
         , B.REQ_DATE                                     AS RAD_DATE
         , B.BLOCK_FLAG                                   AS HOLD_FLAG
         , CASE WHEN B.BLOCK_FLAG = 'Y' THEN 'N'
                WHEN B.BLOCK_FLAG = 'N' AND HH.RELEASED_FLAG IS NOT NULL THEN 'Y'
                ELSE 'N'
           END                                            AS HOLD_RELEASED_FLAG
         , HH.HOLD_DT AS HOLD_DATE
         , IF(B.BLOCK_FLAG='N', HH.RELEASE_DT, NULL)      AS HOLD_RELEASE_DATE
         , IF(B.BLOCK_FLAG='Y', HH.BLOCK_NAME, NULL)      AS HOLD_NAME
         , HH.HOLD_DAYS                                   AS HOLD_DAYS
         , B.ZRSH_DT                                      AS REQUEST_SHIPPING_DATE
         , B.ZDELIVDT                                     AS PICK_RELEASE_DATE
         , B.ZAPP_DT_F                                    AS APPOINTMENT_FROM_DATE
         , B.ZAPP_DT                                      AS APPOINTMENT_TO_DATE
         , B.ZIPAD_DT                                     AS INIT_PROMISED_ARRIVAL_DATE
         , B.ZPAD_DT                                      AS PROMISED_ARRIVAL_DATE
         , B.ZSHIPNGDT                                    AS SHIPPING_DATE
         , B.BILL_DATE                                    AS SALES_DATE
         , CAST(B.BILLING_QTY AS NUMERIC)                 AS SALES_QTY
         , CAST(ROUND(B.BILLING_AMOUNT, 2) AS NUMERIC)    AS SALES_AMOUNT
         , B.ZSOCREDAT                                    AS CREATION_DATE
         , B.ZBOOKEDDT                                    AS BOOKED_DATE
         , IF(B.P_SEQ = 'Closed', 'N', 'Y')               AS OPEN_FLAG
         , B.ZBUS_AREA                                    AS ACCOUNTING_UNIT_CODE
         , CAST(B.DELY_QTY AS NUMERIC)                                                                  AS SHIPPED_QTY
         , CAST(ROUND(B.DELY_QTY * B.UNIT_PRICE, 2) AS NUMERIC)                                         AS SHIPPED_AMOUNT
         , CAST(B.PICK_QTY AS NUMERIC)                                                                  AS PICK_RELE_QTY
         , CAST(ROUND(B.PICK_QTY * B.UNIT_PRICE, 2) AS NUMERIC)                                         AS PICK_RELE_AMOUNT
         , CAST(IF(HH.RELEASE_DT IS NOT NULL, B.OPEN_QTY, 0) AS NUMERIC)                                AS PICK_READY_QTY
         , CAST(IF(HH.RELEASE_DT IS NOT NULL, ROUND(B.OPEN_QTY * B.UNIT_PRICE, 2), 0) AS NUMERIC)       AS PICK_READY_AMOUNT
         , CAST(IF(HH.RELEASE_DT IS NULL, B.OPEN_QTY, 0) AS NUMERIC)                                    AS OPEN_QTY
         , CAST(IF(HH.RELEASE_DT IS NULL, ROUND(B.OPEN_QTY * B.UNIT_PRICE, 2), 0) AS NUMERIC)           AS OPEN_AMOUNT
         , CAST(IF(BLOCK_FLAG = 'Y', B.ORDER_QTY, 0) AS NUMERIC)                                        AS HOLD_QTY
         , CAST(ROUND(IF(BLOCK_FLAG = 'Y', B.ORDER_QTY * B.UNIT_PRICE, 0), 2) AS NUMERIC)               AS HOLD_AMOUNT
         , CAST(B.AR_HOLD_QTY AS NUMERIC)                                                               AS AR_HOLD_QTY
         , CAST(ROUND(B.AR_HOLD_QTY * B.UNIT_PRICE, 2) AS NUMERIC)                                      AS AR_HOLD_AMOUNT
         , CAST(B.BACK_ORDER_QTY AS NUMERIC)                                                            AS BACK_HOLD_QTY
         , CAST(ROUND(B.BACK_ORDER_QTY * B.UNIT_PRICE, 2) AS NUMERIC)                                   AS BACK_HOLD_AMOUNT
         , CAST(IF(COALESCE(B.ZFH_FG, 'N') = 'Y', B.ORDER_QTY, 0) AS NUMERIC)                           AS FUTURE_HOLD_QTY
         , CAST(ROUND(IF(COALESCE(B.ZFH_FG, 'N') = 'Y', B.ORDER_QTY * B.UNIT_PRICE, 0), 2) AS NUMERIC)  AS FUTURE_HOLD_AMOUNT
         , B.LOGSTAMP                                     AS LOGSTAMP
         , B.INVOICE_NO                                   AS INVOICE_NO
         , B.ORDER_CATEGORY                               AS ORDER_CATEGORY
         , B.USER_ITEM_TYPE                               AS USER_ITEM_TYPE
         , B.GROSS_SALES_ONLY                             AS GROSS_SALES_ONLY
         , B.INVOICED_YN                                  AS INVOICED_YN
         , CAST(NULL AS NUMERIC)                          AS UNIT_PRICE
         , CAST(NULL AS NUMERIC)                          AS ORD_VALID_QTY
         , B.READY_TO_PICK                                AS READY_TO_PICK
         , B.WAREHOUSE_CODE                               AS WAREHOUSE_CODE
           /* 2026-08-18 : NERP Direct Shpment 반영 */
         , DS.BL_ID                                       AS BL_ID
         , DS.HOUSE_BL_NO                                 AS HOUSE_BL_NO
         , DS.CONTAINER_NO                                AS CONTAINER_NO
         , DS.SO_SA_MAPPING_FLAG                          AS SO_SA_MAPPING_FLAG
    FROM   W_STATUS_QTY_GET    AS B
    LEFT OUTER JOIN
           W_SOLDTO_NAME_GET   AS S1
       ON  B.SOLD_TO  =  S1.SOLDTO_CD
    LEFT OUTER JOIN
           W_HOLD_HISTORY      AS HH
       ON  CAST(B.DOC_NUMBER AS STRING)      =  CAST(HH.VBELN AS STRING)
      AND  SAFE_CAST(B.S_ORD_ITEM AS INT64)  =  SAFE_CAST(HH.POSNR AS INT64)
    LEFT OUTER JOIN
           W_ZSLES0201         AS DS
       ON  CAST(B.DOC_NUMBER AS STRING)      =  CAST(DS.VBELN AS STRING)
      AND  SAFE_CAST(B.S_ORD_ITEM AS INT64)  =  SAFE_CAST(DS.POSNR AS INT64)
    UNION ALL
    SELECT DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)  AS P_PTT
         , 'Closed'                                  AS P_SEQ
         , CAST(NULL AS STRING)                      AS AFFILIATE_CODE
         , z.SUBSDR_NM                               AS SUBSDR_NAME
         , z.VBELN                                   AS SALES_ORDER_NO
         , z.POSNR                                   AS SALES_ORDER_LINE_NO
         , CAST(NULL AS STRING)                      AS ITEM
         , z.AUART                                   AS LINE_CATEGORY_CODE
         , CAST(NULL AS STRING)                      AS PROJECT_CODE
         , z.DOC_TYPE                                AS ORDER_TYPE
         , z.DOC_TYPE_NM                             AS ORDER_TYPE_NAME
         , 'Completed'                               AS LINE_STATUS_CODE
         , CAST(NULL AS NUMERIC)                     AS ORDER_QTY
         , CAST(NULL AS NUMERIC)                     AS PICK_RELEASE_QTY
         , CAST(NULL AS NUMERIC)                     AS CANCEL_QTY
         , z.WAERK                                   AS CURRENCY_CODE
         , CAST(NULL AS NUMERIC)                     AS UNIT_SELLING_PRICE
         , CAST(NULL AS NUMERIC)                     AS UNIT_LIST_PRICE
         , CAST(NULL AS NUMERIC)                     AS ORDER_AMOUNT
         , CAST(NULL AS NUMERIC)                     AS USD_ORDER_AMOUNT
         , CAST(NULL AS NUMERIC)                     AS CONVERSION_RATE
         , CAST(NULL AS STRING)                      AS DOMAIN_CODE
         , z.KUNAG                                   AS BILL_TO_CUSTOMER_CODE
         , COALESCE(s1.SOLDTO_NM, z.SOLDTONM, '')    AS BILL_TO_CUSTOMER_NAME
         , CAST(NULL AS STRING)                      AS SHIP_TO_CUSTOMER_CODE
         , CAST(NULL AS STRING)                      AS SHIP_TO_CUSTOMER_NAME
         , z.MATNR                                   AS MODEL_CODE
         , CAST(NULL AS STRING)                      AS MODEL_CATEGORY
         , CAST(NULL AS STRING)                      AS DIV_CD
         , z.DIV_NM                                  AS DIV_NM
         , z.CMPNY_CD                                AS CMPNY_CD
         , z.CMPNY_NM                                AS CMPNY_NM
         , z.MDL_DESC                                AS MODEL_DESC
         , z.PRDT_GRP_CD                             AS PRDT_GRP_CD
         , z.PRDT_CAT_CD                             AS PRDT_CAT_CD
         , CAST(NULL AS STRING)                      AS HOLD_TYPE
         , 'N'                                       AS AR_HOLD
         , 'N'                                       AS FUTURE_HOLD
         , 'N'                                       AS BACK_HOLD
         , 'N'                                       AS CREDIT_HOLD
         , 'N'                                       AS OVERDUE_HOLD
         , 'N'                                       AS CUSTOMER_HOLD
         , 'N'                                       AS PAYTERM_TERM_HOLD
         , 'N'                                       AS FP_HOLD
         , 'N'                                       AS MINIMUM_HOLD
         , 'N'                                       AS RESERVE_HOLD
         , 'N'                                       AS MANUAL_HOLD
         , 'N'                                       AS AUTO_PENDING_HOLD
         , 'N'                                       AS ETC_HOLD
         , z.FKDAT                                   AS ORDERED_DATE
         , CAST(NULL AS DATE)                        AS CUSTOMER_RAD
         , CAST(NULL AS DATE)                        AS RAD_DATE
         , 'N'                                       AS HOLD_FLAG
         , CAST(NULL AS STRING)                      AS HOLD_RELEASED_FLAG
         , CAST(NULL AS DATETIME)                    AS HOLD_DATE
         , CAST(NULL AS DATETIME)                    AS HOLD_RELEASE_DATE
         , CAST(NULL AS STRING)                      AS HOLD_NAME
         , CAST(NULL AS INT64)                       AS HOLD_DAYS
         , CAST(NULL AS DATE)                        AS REQUEST_SHIPPING_DATE
         , CAST(NULL AS DATE)                        AS PICK_RELEASE_DATE
         , CAST(NULL AS DATE)                        AS APPOINTMENT_FROM_DATE
         , CAST(NULL AS DATE)                        AS APPOINTMENT_TO_DATE
         , CAST(NULL AS DATE)                        AS INIT_PROMISED_ARRIVAL_DATE
         , CAST(NULL AS DATE)                        AS PROMISED_ARRIVAL_DATE
         , z.GIDATE                                  AS SHIPPING_DATE
         , z.FKDAT                                   AS SALES_DATE
         , CAST(z.FKLMG AS NUMERIC)                  AS SALES_QTY
         , CAST(ROUND(z.SALESAMTEXC,2) AS NUMERIC)   AS SALES_AMOUNT
         , CAST(NULL AS DATE)                        AS CREATION_DATE
         , CAST(NULL AS DATE)                        AS BOOKED_DATE
         , 'N'                                       AS OPEN_FLAG
         , CAST(NULL AS STRING)                      AS ACCOUNTING_UNIT_CODE
         , CAST(0 AS NUMERIC)                        AS SHIPPED_QTY
         , CAST(0 AS NUMERIC)                        AS SHIPPED_AMOUNT
         , CAST(0 AS NUMERIC)                        AS PICK_RELE_QTY
         , CAST(0 AS NUMERIC)                        AS PICK_RELE_AMOUNT
         , CAST(0 AS NUMERIC)                        AS PICK_READY_QTY
         , CAST(0 AS NUMERIC)                        AS PICK_READY_AMOUNT
         , CAST(0 AS NUMERIC)                        AS OPEN_QTY
         , CAST(0 AS NUMERIC)                        AS OPEN_AMOUNT
         , CAST(0 AS NUMERIC)                        AS HOLD_QTY
         , CAST(0 AS NUMERIC)                        AS HOLD_AMOUNT
         , CAST(0 AS NUMERIC)                        AS AR_HOLD_QTY
         , CAST(0 AS NUMERIC)                        AS AR_HOLD_AMOUNT
         , CAST(0 AS NUMERIC)                        AS BACK_HOLD_QTY
         , CAST(0 AS NUMERIC)                        AS BACK_HOLD_AMOUNT
         , CAST(0 AS NUMERIC)                        AS FUTURE_HOLD_QTY
         , CAST(0 AS NUMERIC)                        AS FUTURE_HOLD_AMOUNT
         , CAST(NULL AS STRING)                      AS LOGSTAMP
         , CAST(NULL AS STRING)                      AS INVOICE_NO
         , CAST(NULL AS STRING)                      AS ORDER_CATEGORY
         , CAST(NULL AS STRING)                      AS USER_ITEM_TYPE
         , CAST(NULL AS STRING)                      AS GROSS_SALES_ONLY
         , CAST(NULL AS STRING)                      AS INVOICED_YN
         , CAST(NULL AS NUMERIC)                     AS UNIT_PRICE
         , CAST(NULL AS NUMERIC)                     AS ORD_VALID_QTY
         , CAST(NULL AS STRING)                      AS READY_TO_PICK
         , CAST(NULL AS STRING)                      AS WAREHOUSE_CODE
           /* 2026-08-18 : NERP Direct Shpment 반영 */
         , CAST(NULL AS STRING)                      AS BL_ID
         , CAST(NULL AS STRING)                      AS HOUSE_BL_NO
         , CAST(NULL AS STRING)                      AS CONTAINER_NO
         , CAST(NULL AS STRING)                      AS SO_SA_MAPPING_FLAG
    FROM   W_ZSSDI1018        AS z
    LEFT OUTER JOIN
           W_SOLDTO_NAME_GET  AS s1
       ON  z.KUNAG  =  s1.SOLDTO_CD
    LEFT OUTER JOIN
           W_MODEL_MST        AS m
       ON  z.MATNR  =  m.MDL_SFFX_CD
    UNION ALL
    SELECT T1.P_PTT
         , T1.P_SEQ
         , T1.AFFILIATE_CODE
         , T1.SUBSDR_NAME
         , T1.SALES_ORDER_NO
         , T1.SALES_ORDER_LINE_NO
         , CAST(NULL AS STRING)       AS ITEM
         , T1.LINE_CATEGORY_CODE
         , T1.PROJECT_CODE
         , T1.ORDER_TYPE
         , T1.ORDER_TYPE_NAME
         , T1.LINE_STATUS_CODE
         , T1.ORDER_QTY
         , T1.PICK_RELE_QTY           AS PICK_RELEASE_QTY
         , T1.CANCEL_QTY
         , T1.CURRENCY_CODE
         , T1.SELL_PRICE              AS UNIT_SELLING_PRICE
         , T1.LIST_PRICE              AS UNIT_LIST_PRICE
         , T1.ORDER_AMOUNT
         , T1.USD_ORDER_AMOUNT
         , T1.CONVERSION_RATE
         , T1.DOMAIN_CODE
         , T1.BILL_TO_CUSTOMER_CODE
         , T1.BILL_TO_CUSTOMER_NAME
         , T1.SHIP_TO_CUSTOMER_CODE
         , T1.SHIP_TO_CUSTOMER_NAME
         , T1.MODEL_CODE
         , T1.MODEL_CATEGORY
         , T1.DIV_CD
         , T1.DIV_NM
         , T1.CMPNY_CD
         , T1.CMPNY_NM
         , T1.MODEL_DESC
         , T1.PRDT_GRP_CD
         , T1.PRDT_CAT_CD
         , T1.HOLD_TYPE
         , T1.AR_HOLD
         , T1.FUTURE_HOLD
         , T1.BACK_HOLD
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
         , T1.ORDERED_DATE
         , CAST(T1.CUSTOMER_RAD AS DATE)   AS CUSTOMER_RAD
         , T1.RAD_DATE
         , T1.HOLD_FLAG
         , T1.HOLD_RELEASED_FLAG
         , T1.HOLD_DATE
         , T1.HOLD_RELEASE_DATE
         , T1.HOLD_NAME
         , T1.HOLD_DAYS
         , CAST(T1.REQUEST_SHIPPING_DATE      AS DATE)  AS REQUEST_SHIPPING_DATE
         , CAST(T1.PICK_RELEASE_DATE          AS DATE)  AS PICK_RELEASE_DATE
         , CAST(T1.APPOINTMENT_FROM_DATE      AS DATE)  AS APPOINTMENT_FROM_DATE
         , CAST(T1.APPOINTMENT_TO_DATE        AS DATE)  AS APPOINTMENT_TO_DATE
         , CAST(T1.INIT_PROMISED_ARRIVAL_DATE AS DATE)  AS INIT_PROMISED_ARRIVAL_DATE
         , CAST(T1.PROMISED_ARRIVAL_DATE      AS DATE)  AS PROMISED_ARRIVAL_DATE
         , CAST(T1.SHIPPING_DATE              AS DATE)  AS SHIPPING_DATE
         , CAST(T1.SALES_DATE                 AS DATE)  AS SALES_DATE
         , CAST(NULL AS NUMERIC)           AS SALES_QTY
         , CAST(NULL AS NUMERIC)           AS SALES_AMOUNT
         , CAST(T1.CREATION_DATE AS DATE)  AS CREATION_DATE
         , CAST(T1.BOOKED_DATE   AS DATE)  AS BOOKED_DATE
         , T1.OPEN_FLAG
         , T1.ACCOUNTING_UNIT_CODE
         , T1.SHIPPED_QTY
         , T1.SHIPPED_AMOUNT
         , T1.REMN_PICK_RELE_QTY           AS PICK_RELE_QTY
         , T1.PICK_RELE_AMOUNT
         , T1.PICK_READY_QTY
         , T1.PICK_READY_AMOUNT
         , T1.REMN_READY_QTY               AS OPEN_QTY
         , T1.OPEN_AMOUNT
         , T1.HOLD_QTY
         , T1.HOLD_AMOUNT
         , T1.AR_HOLD_QTY
         , T1.AR_HOLD_AMOUNT
         , T1.BACK_HOLD_QTY
         , T1.BACK_HOLD_AMOUNT
         , T1.FUTURE_HOLD_QTY
         , T1.FUTURE_HOLD_AMOUNT
         , T1.LOGSTAMP
         , T1.INVOICE_NO
         , T1.ORDER_CATEGORY
         , T1.USER_ITEM_TYPE
         , T1.GROSS_SALES_ONLY
         , CAST(NULL AS STRING)            AS INVOICED_YN
         , T1.UNIT_PRICE
         , T1.ORD_VALID_QTY
         , T1.READY_TO_PICK
         , T1.WAREHOUSE_CODE
           /* 2026-08-18 : NERP Direct Shpment 반영 */
         , T2.BL_ID                        AS BL_ID
         , T2.HOUSE_BL_NO                  AS HOUSE_BL_NO
         , T2.CONTAINER_NO                 AS CONTAINER_NO
         , T2.SO_SA_MAPPING_FLAG           AS SO_SA_MAPPING_FLAG
    FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_RPA_GET_SO_LINE_T11  AS T1
    LEFT OUTER JOIN
           W_ZSLES0201                                                 AS T2
       ON  CAST(T1.SALES_ORDER_NO AS STRING)           =  CAST(T2.VBELN AS STRING)
      AND  SAFE_CAST(T1.SALES_ORDER_LINE_NO AS INT64)  =  SAFE_CAST(T2.POSNR AS INT64)
    WHERE  1 = 1
      AND  T1.SUBSDR_NAME  =  'LGEPH'
    ;

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_T11', CURRENT_TIMESTAMP, 'END', 'OSO.LIW.T11 (Hourly)');

END