BEGIN
    DECLARE MAX_DATE     DATETIME;
    SET     MAX_DATE  =  ( SELECT MAX(P_DATETIME) AS MAX_DATE  FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_NERP_INVOICED_ORDER_INQUIRY );

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_INVOICE', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.RPA (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_INVOICE
    AS
        /*
      ─────────────────────────────────────────────────────────────────────────────────────────────────────
       작성일자      작성자           작성내용
      ─────────────────────────────────────────────────────────────────────────────────────────────────────
       2026.07.23  haehyun.baek  `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE 에서 추출하면 Invoice No 없음
                                  - Invoice 기준으로 분할 될수 있음
                                 `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZSSDA0226 에서 추출 해야함
       2026.08.07                `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11 테이블로 MAIN 변경
       2026.09.14  hjun.lim      `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXARF_INVOICE_LINES_ALL 에서 GERP쪽 Invoice정보 가져옴
      ─────────────────────────────────────────────────────────────────────────────────────────────────────
    */
        SELECT
               CURRENT_DATE()                               AS P_PTT
             , PARSE_DATETIME('%Y%m%d %H%M%S', A.LOGSTAMP)  AS LOGSTAMP
             , CONCAT(A.LOGSTAMP, '000')                    AS LOGKEY                --  임의로 생성
             , A.DIV_CD                                     AS DIV_CD                --  Division Code
             , A.DIV_NM                                     AS DIV_NM                --  Division Name
             , A.AFFILIATE_CODE                             AS AFFILIATE_CODE        --  Company Code to Be Billed(법인)
             , A.SUBSDR_NAME                                AS SUBSDR_NAME           --  Company Name
             , A.ORDER_CATEGORY                             AS ORDER_CATEGORY        --  Order Category
             , A.ORDER_TYPE_NAME                            AS ORDER_TYPE_NAME       --  Order Category Name
             , A.BILL_TO_CUSTOMER_CODE                      AS BILLTO_CODE           --  Sold-To Party
             , A.BILL_TO_CUSTOMER_NAME                      AS BILLTO_NAME           --  Sold-To Party Name
             , A.SHIP_TO_CUSTOMER_CODE                      AS SHIPTO_CODE           --  Ship-To Party
             , A.SHIP_TO_CUSTOMER_NAME                      AS SHIPTO_NAME           --  Ship-To Party Name
             , A.SALES_ORDER_NO                             AS SALES_ORDER_NO        --  Sales Document
             , A.SALES_ORDER_LINE_NO                        AS SALES_ORDER_LINE_NO   --  Sales Document Item
             , CAST(NULL AS STRING)                         AS SALES_FG              --  Sales Flag (ZSSDA0226에는 있는 컬럼인데 ZSSDA0226에는 없음
             , A.SALES_DATE                                 AS SALES_DATE            --  Billing Date
             , A.ORDER_QTY                                  AS ORDER_QTY             --  Target Quantity in Sales Units
             , A.SALES_QTY                                  AS SALES_QTY             --  Billing Quantity
             , A.CURRENCY_CODE                              AS CURRENCY_CODE         --  SD Document Currency
             , A.ORDER_AMOUNT                               AS ORDER_AMOUNT          --  Target Amount in Sales Units (Exclude Tax)
             , CASE WHEN A.ORDER_TYPE    IN  ('ZRCB', 'ZRSB', 'ZRSC', 'ZRSD', 'ZRSM', 'ZRSX') THEN 0  --Invoice 조회시 Subscribe는 Default가 제외
                    WHEN IC.IN_CATEGORY  =   'Adjust' THEN 0
                    ELSE A.SALES_AMOUNT
               END                                          AS SALES_AMOUNT          --  Billing Quantity
             , A.UNIT_SELLING_PRICE                         AS UNIT_SELLING_PRICE    --  Selling Price
             , A.UNIT_LIST_PRICE                            AS UNIT_LIST_PRICE       --  List Price
             , A.INVOICE_NO                                 AS INVOICE_NO            --  Invoice No
             , A.PRDT_GRP_CD                                AS PRDT_GRP_CD
             , BZ.BILLTO_BIZ_NAME
             , BZ.TEAM_NAME
             , 'NERP'                                       AS SOURCE_NM
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T11            AS A
          LEFT OUTER JOIN
                 `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST  AS BZ
                 ON  A.SUBSDR_NAME            =  BZ.SUBSDR_NAME
                AND  A.BILL_TO_CUSTOMER_CODE  =  BZ.BILLTO_CODE
                AND  A.PRDT_GRP_CD            =  BZ.PRODUCT_GROUP_CODE
        LEFT OUTER JOIN
               ( /* Invoice Category */
                 SELECT KFIELD01
                      , CFIELD01  AS IN_CATEGORY
                 FROM   `pjt-lge-edl-ob`.OB_00030.V_L0NEDW_ZPCMA0060
                 WHERE  CODEGRP   LIKE  '%ZSD_INV_CATEGORY%'
                 QUALIFY ROW_NUMBER() OVER (PARTITION BY CODEGRP, KFIELD01 ORDER BY SDATE DESC, EDATE DESC, ETL_LOAD_TS DESC) = 1
               )                                                             AS IC
           ON  A.ORDER_TYPE    =   IC.KFIELD01
          AND  IC.IN_CATEGORY  IN  ('Sales', 'Return', 'Adjust')
        WHERE  1 = 1
          AND  COALESCE(A.INVOICE_NO, '')  <>  ''
          AND  A.MODEL_CATEGORY            <>  'B'
          AND  A.USER_ITEM_TYPE            <>  'W'
          AND  A.SUBSDR_NAME               <>  'LGEPH'
        UNION ALL
        SELECT
               P_PTT
             , CAST(LOGSTAMP AS DATETIME)   AS LOGSTAMP
             , CAST(NULL AS STRING)         AS LOGKEY
             , T1.DIV_CD                --  Division Code
             , T1.DIV_NM                --  Division Name
             , T1.AFFILIATE_CODE        --  Company Code to Be Billed
             , T1.SUBSDR_NAME           --  Company Name
             , T1.ORDER_CATEGORY        --  Order Category
             , T1.ORDER_TYPE_NAME       --  Order Category Name
             , T1.BILLTO_CODE           --  Sold-To Party
             , T1.BILLTO_NAME           --  Sold-To Party Name
             , T1.SHIPTO_CODE           --  Ship-To Party
             , T1.SHIPTO_NAME           --  Ship-To Party Name
             , T1.SALES_ORDER_NO        --  Sales Document
             , T1.SALES_ORDER_LINE_NO   --  Sales Document Item
             , T1.SALES_FG              --  Sales Flag (ZSSDS0226에 V=)
             , T1.SALES_DATE            --  Billing Date
             , T1.ORDER_QTY             --  Target Quantity in Sales Units
             , T1.SALES_QTY             --  Billing Quantity
             , T1.CURRENCY_CODE         --  SD Document Currency
             , T1.ORDER_AMOUNT          --  Target Amount in Sales Units (Exclude Tax)
             , T1.SALES_AMOUNT          --  Billing Quantity
             , T1.UNIT_SELLING_PRICE    --  Selling Price
             , T1.UNIT_LIST_PRICE       --  List Price
             , T1.INVOICE_NO            --  Invoice No
             , T1.PRDT_GRP_CD
             , T1.BILLTO_BIZ_NAME
             , T1.TEAM_NAME
             , 'NERP'                       AS SOURCE_NM
        FROM   `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_RPA_GET_SO_LINE_INVOICE  AS T1
        WHERE  1 = 1
        UNION ALL
        SELECT
             CURRENT_DATE()                                   AS P_PTT               -- NERP branch와 동일 패턴으로 통일
           , CAST(NULL AS DATETIME)                           AS LOGSTAMP            -- SAP IDoc 타임스탬프, GERP엔 없음
           , CAST(NULL AS STRING)                             AS LOGKEY              -- 〃
           , DM.DIV_CD                                        AS DIV_CD              -- D_NPT_MDL_NEW_MST에서 채움
           , A.DIV_NM                                         AS DIV_NM
           , A.AFFILIATE_CODE                                 AS AFFILIATE_CODE
           , A.SUBSDR_NAME                                    AS SUBSDR_NAME
           , A.ORDER_CATEGORY_CODE                            AS ORDER_CATEGORY      -- NERP는 CATEGORY명, GERP는 CODE밖에 없어서 code로 대체
           , A.ORDER_TYPE_NAME                                AS ORDER_TYPE_NAME
           , A.BILL_TO_CUSTOMER_CODE                          AS BILLTO_CODE
           , A.BILL_TO_CUSTOMER_NAME                          AS BILLTO_NAME
           , A.SHIP_TO_CUSTOMER_CODE                          AS SHIPTO_CODE
           , A.SHIP_TO_CUSTOMER_NAME                          AS SHIPTO_NAME
           , A.SALES_ORDER_NO                                 AS SALES_ORDER_NO
           , A.SALES_ORDER_LINE_NO                            AS SALES_ORDER_LINE_NO
           , CAST(NULL AS STRING)                             AS SALES_FG             -- NERP 전용 플래그, GERP 없음
           , A.SALES_DATE                                     AS SALES_DATE
           , A.ORDER_QTY                                      AS ORDER_QTY
           , B.PICKING_QTY                                    AS SALES_QTY            -- 실청구(출고) 수량
           , A.CURRENCY_CODE                                  AS CURRENCY_CODE
           , A.ORDER_AMOUNT                                   AS ORDER_AMOUNT
           , CASE WHEN A.ORDER_TYPE_NAME LIKE 'ACCRUAL_ADJUST%' THEN 0                -- NERP의 Subscribe/Adjust 제외 로직과 동일 취지
                  ELSE B.NET_AMOUNT
             END                                              AS SALES_AMOUNT         -- Target Amount in Sales Units (Exclude Tax)
           , A.UNIT_SELLING_PRICE                             AS UNIT_SELLING_PRICE
           , A.UNIT_LIST_PRICE                                AS UNIT_LIST_PRICE
           , B.INVOICE_NO                                     AS INVOICE_NO
           , A.PRDT_GRP_CD                                    AS PRDT_GRP_CD
           , BZ.BILLTO_BIZ_NAME
           , BZ.TEAM_NAME
           , 'GERP'                                           AS SOURCE_NM
        FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_SO_LINE_T01                 AS A
        LEFT OUTER JOIN
             `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST            AS DM
          ON  A.MODEL_CODE = DM.MDL_SFFX_CD
        LEFT OUTER JOIN
             `pjt-lge-oversea-sales-olap`.SCM_OLAP.REF_D_BILLTO_BIZ_MST         AS BZ
          ON  A.SUBSDR_NAME            = BZ.SUBSDR_NAME
         AND  A.BILL_TO_CUSTOMER_CODE  = BZ.BILLTO_CODE
         AND  A.PRDT_GRP_CD            = BZ.PRODUCT_GROUP_CODE
        LEFT JOIN
             (
               SELECT
                     SALES_ORDER_NO
                   , ORDER_LINE_NO
                   , INVOICE_NO
                   , PICKING_QTY
                   , NET_AMOUNT
                   , CREATION_DATE
               FROM `pjt-lge-edl-ob`.OB_00030.V_L0GERP_XXARF_INVOICE_LINES_ALL
               WHERE TRX_TYPE_NAME = 'INV'
                 AND P_PTT >= '2025-01-01'
               QUALIFY ROW_NUMBER() OVER (
                         PARTITION BY SALES_ORDER_NO, ORDER_LINE_NO
                         ORDER BY CREATION_DATE DESC
                       ) = 1
             )                                                                  AS B
          ON  A.SALES_ORDER_NO                = B.SALES_ORDER_NO
         AND  CAST(A.ORDER_LINE_ID AS STRING) = B.ORDER_LINE_NO
       WHERE  1 = 1
    ;

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_SO_LINE_INVOICE', CURRENT_TIMESTAMP, 'END', 'OSO.LIW.RPA (Hourly)');

END