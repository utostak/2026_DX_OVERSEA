BEGIN
    DECLARE BASE_DATE  DATE;
    SET     BASE_DATE  =  ( SELECT DATE_SUB(CURRENT_DATE('Asia/Seoul'), INTERVAL 1 DAY) );

    /************************
     --- DELETE -------------
    *************************/
    DELETE FROM `pjt-lge-oversea-sales-olap`.SCM_OLAP.TB_GTM_ORDER_OLAP_S_IF_OS
    WHERE  P_PTT  >=  BASE_DATE
      AND  DATE(ETL_LOAD_TS, 'Asia/Seoul')  >=  BASE_DATE
    ;

    /************************
     --- INSERT -------------
    *************************/
    INSERT INTO `pjt-lge-oversea-sales-olap`.SCM_OLAP.TB_GTM_ORDER_OLAP_S_IF_OS
    WITH W_GTM_ORDER_OLAP AS
    (
      SELECT *
      FROM   `pjt-lge-edl-ob`.OB_00030.V_L0TMS__TB_GTM_ORDER_OLAP_S_IF_OS
      WHERE  P_PTT  >=  BASE_DATE
        AND  DATE(ETL_LOAD_TS, 'Asia/Seoul')  >=  BASE_DATE
      QUALIFY ROW_NUMBER() OVER (PARTITION BY SOURCE_HEADER_ID, SOURCE_LINE_ID, SHIPMENTNUMBER ORDER BY CREATE_DATE DESC) = 1
    )
    SELECT T1.*
         , T2.SUBSDR_NAME
         , T2.REGION_NAME
         , T2.DISPLAY_NAME
         , CURRENT_DATETIME('Asia/Seoul')  AS INPUT_DT
    FROM
           W_GTM_ORDER_OLAP                                    AS T1
    JOIN   `pjt-lge-oversea-sales-olap`.SCM_OLAP.D_SUBSDR_MST  AS T2
      ON   T1.SUBSIDIARY_CODE  =  T2.SUBSDR_NAME
    WHERE  1 = 1
    ;

END