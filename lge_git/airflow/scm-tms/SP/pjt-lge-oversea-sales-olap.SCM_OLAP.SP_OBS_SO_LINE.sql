BEGIN

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_M_OBS_SO_LINE', CURRENT_TIMESTAMP, 'START', 'OSO.LIW.OBS (Hourly)');

    CREATE OR REPLACE TABLE `pjt-lge-oversea-sales-olap`.SCM_OLAP.M_OBS_SO_LINE
    AS
    SELECT MAIN.*
    FROM ( SELECT *
           FROM   `pjt-lge-edl-ob`.OB_00030.V_L0LMDS_TB_LI_ORDERLIST_ONEVIEW_S_IF
           WHERE  1 = 1
             AND  ORDER_DATE  >= '20250101'
           QUALIFY ROW_NUMBER() OVER(PARTITION BY SHIPMENT_ID ORDER BY SYS_CREATE_DATE DESC ) = 1
         ) MAIN
    LEFT JOIN
           `pjt-lge-oversea-sales-olap`.PRD_OLAP.D_NPT_MDL_NEW_MST M2
       ON  MAIN.MODEL_SUFFIX  =  M2.MDL_SFFX_CD
    WHERE  1 = 1
    --   AND ORDER_STATUS = 'Completed'   -- 끝난 것 기준으로 계산
    ;

    INSERT INTO `pjt-lge-oversea-sales-olap`.PRD_OLAP.OSO_BATCH_LOG VALUES ('SP_M_OBS_SO_LINE', CURRENT_TIMESTAMP, 'END', 'OSO.LIW.OBS (Hourly)');

END