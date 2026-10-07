        select * from(
 select inner_temp.*, rownum as devonindex from  ( 
            SELECT 
                TOT.LD_LEG_ID,
                TOT.FRST_SHPG_LOC_NAME,
                TOT.FRST_SHPG_LOC_CD,
                TOT.LAST_SHPG_LOC_NAME,
                TOT.LAST_SHPG_LOC_CD,
                TOT.LAST_CTY_NAME,
                TOT.LOAD_TYPE,
                TOT.CARR_NAME,
                TOT.SRVC_CD,
                TOT.EQMT_TYP,
                TOT.TRCTR_NUM,
                TOT.TRLR_NUM,
                TOT.SEAL_NUM,
                TOT.DRVR,
                TOT.TRCTR_LIC_NUM AS DRIVER_PHONE_NUMBER,
                TOT.MASTER_LOAD_ID,
                TOT.MERGE_FLAG,
                TOT.TOT_VOL,
                TOT.TOT_QTY,
                TOT.STUFFING_RATIO,
                TOT.MODEL_MIX,
                TOT.NUM_OF_SHIPTO,
                TOT.SHIPPING_CBM,
                TOT.SHIPPING_QTY,
                TOT.LOAD_VALUE,
                TOT.LOAD_STATUS,
                TO_CHAR(TOT.TENDER_RESPONSE_DATE,'YYYY-MM-DD HH24:MI:SS') AS TENDER_RESPONSE_DATE,        
                TO_CHAR(TOT.CRTD_DTT,'YYYY-MM-DD HH24:MI:SS') AS CRTD_DTT,
                TO_CHAR((SELECT MIN((SELECT /*+index_desc(B TB_GTM_BOOKINGHISTORY_IX04)*/
                            APPOINTMENT_DATE
                             FROM TB_GTM_BOOKINGHISTORY B
                            WHERE B.SHPM_NUM = LEGD.SHPM_NUM
                              AND B.REG_DATE <= SYSDATE + 1
                              AND NVL(B.SEQ_NUM, 100) = TOT.SHIPMENT_LEG -- Hub ���� ���� �߰� 20150507 �̵���
                              AND ROWNUM = 1)) AS APT_DATE
                  FROM TMSPROD.LD_LEG_DETL_T LEGD
                 WHERE LEGD.LD_LEG_ID = TOT.LD_LEG_ID)-DECODE(TOT.DISTANCE_USE_FLAG,'Y',TOT.DISTANCE_LEAD_TIME,TOT.LEAD_TIME ),'YYYY-MM-DD HH24:MI:SS') AS SUGGESTED_SHIP_OUT_DATE,
                DECODE(TOT.DISTANCE_USE_FLAG,'Y',TOT.DISTANCE_LEAD_TIME,TOT.LEAD_TIME ) AS LEAD_TIME, --ETA ���� ����
            --TOT.LEAD_TIME, --ETA ���� ����
            --TOT.DISTANCE_LEAD_TIME,--ETA ���� ����
                TO_CHAR((SELECT MIN((SELECT /*+index_desc(B TB_GTM_BOOKINGHISTORY_IX04)*/
                            APPOINTMENT_DATE
                             FROM TB_GTM_BOOKINGHISTORY B
                            WHERE B.SHPM_NUM = LEGD.SHPM_NUM
                              AND B.REG_DATE <= SYSDATE + 1
                              AND NVL(B.SEQ_NUM, 100) = TOT.SHIPMENT_LEG -- Hub ���� ���� �߰� 20150507 �̵���
                              AND ROWNUM = 1)) AS APT_DATE
                  FROM TMSPROD.LD_LEG_DETL_T LEGD
                 WHERE LEGD.LD_LEG_ID = TOT.LD_LEG_ID),'YYYY-MM-DD HH24:MI:SS') AS APPOINTMENT_DATE,
                TOT.REQUEST_FLAG,
                TOT.APPROVAL_FLAG,
                
                TOT.CHANGE_TARIFF_ID,
                TOT.CHANGE_CARRIER_TYPE,
                TOT.CHANGE_SERVICE_TYPE,
                TOT.CHANGE_VEHICLE_TYPE,
                TOT.CHANGE_FREIGHT_COST,
                TOT.CHANGE_REASON,
                TOT.CHANGE_REQUEST_ID,
                --TOT.CHANGE_USER_ID,
                TOT.FREIGHT_COST,
                TOT.TARIFF_ID,
                TOT.DIV_CD,
                TOT.CARR_CD,
                TOT.MODEL_GROSS_CBM,
                TOT.LOAD_STATUS_ID,
                TOT.WMSTYPE,
                TOT.SPOT_RATE_FLAG,
                TOT.LOAD_CREATE_BY AS LOAD_CREATE_BY,
                TOT.LDPNT1_LOC,
                TOT.DELIVERY_NOTE_USE_FLAG,
                TOT.DELIVERY_NOTE_AUTO_POPUP_FLAG,
                TO_CHAR(TOT.CFMD_DTT,'YYYY-MM-DD HH24:MI:SS') AS CFMD_DTT,
                TOT.ORGANIZATION_CODE,
                TOT.ORI_EVIDENCE_FILE_NAME,
                TOT.CHANGE_REASON_CATEGORY,
                TOT.WH_RELEASE_BY,
                TOT.SHIP_CONFIRM_BY,
                TOT.RATE_CHANGE_BY,
                TOT.SPOT_RATE,
                (select GERP_SHIPTO_CODE from (SELECT SHIP.GERP_SHIPTO_CODE,STOPT.LD_LEG_ID
              FROM TMSPROD.STOP_T           STOPT
                  ,TMSPROD.LD_LEG_DETL_T    LEGD
                  ,TB_GTM_SHIPMENT_TMS_S_IF SHIP
             WHERE STOPT.LD_LEG_ID = LEGD.LD_LEG_ID
               AND LEGD.DROP_STOP_ID=STOPT.STOP_ID 
               AND LEGD.SHPM_NUM = SHIP.SHIPMENTNUMBER
          ORDER BY STOPT.SEQ_NUM DESC) s where ROWNUM = 1 and s.ld_leg_id=TOT.LD_LEG_ID) as GERP_SHIPTO_CODE,
          TOT.LOAD_REMARK,
          TOT.TOTAL_WEIGHT,
          TOT.NUM_OF_ORIGIN,
          TOT.REQUEST_DELIVERY_DATE,
            SCHEDULED_ARRIVAL_DATE,
            SCHEDULED_DEPARTURE_DATE,
          DECODE(TOT.DISTANCE_USE_FLAG,'Y',TOT.DISTANCE_ETA,TOT.ETA ) AS ETA --ETA ���� ����
           --TOT.ETA,--ETA ���� ����
           --TOT.DISTANCE_ETA,--ETA ���� ����
              --TOT.DISTANCE_USE_FLAG --ETA ���� ����
              ,TOT.ZONE
              ,TOT.ZONE_NAME
              ,TOT.SHRT_DESC
              ,TOT.WMS_STATUS
              ,TOT.AUTO_SHIP_CONFIRM_YN
              ,TOT.WMS_STATUS_CODE
              ,TOT.TOUR_NO
              ,TOT.RESPONSE_ARRIVAL_LG_WH
              ,TOT.LOAD_GROUP_ID
              ,TOT.LOAD_GROUP_ID_TH
              ,TOT.REF_BOOK_NO
              ,(SELECT MAX(LOAD_GROUP_USE_YN) FROM TB_GTM_DCCONFIG WHERE DC_CD = TOT.FRST_SHPG_LOC_CD) AS LOAD_GROUP_USE_YN
              ,DECODE((SELECT COUNT(*) FROM TB_GTM_LOAD_PRT WHERE LD_LEG_ID = TOT.LD_LEG_ID), 0, 'N', 'Y') AS DELIVERY_NOTE_PRINT_FLAG
              ,COUNT(LD_LEG_ID) OVER () TOT_CNT
              ,(SELECT DECODE(COUNT(1), 0, 'N', 'Y')
                  FROM TB_GTM_CODEMAPPING_MST A,
                       TB_GTM_DCCONFIG        B
                 WHERE A.LEGAL_ENTITY_NAME = B.LEGAL_ENTITY_NAME
                   AND B.DC_CD = TOT.FRST_SHPG_LOC_CD
                   AND A.CD_TYPE = 'DELIVERY_NOTE_RESTRICT_FLAG'
                   AND A.USE_YN = 'Y'
                   AND A.CD = 'Y') AS DELIVERY_NOTE_RESTRICT_FLAG
               ,TOT.INVO_AVAIL_FLAG
               --,NVL(TOT.RFRC_NUM6,CEIL(TOT.TOT_VOL /(SELECT MAX(A.CD_NM2) FROM TB_GTM_CODEMAPPING_MST A WHERE A.LEGAL_ENTITY_NAME = TOT.LEGAL_ENTITY_NAME AND A.USE_YN = 'Y' AND A.CD_TYPE = 'PALLET_TYPE' AND A.CD = 'STD_PALLET'))) AS PALLET_QTY
               ,CASE WHEN (SELECT DC.RATE_BY_PLT_USE_YN
                             FROM TB_GTM_DCCONFIG DC
                            WHERE DC.DC_CD = TOT.FRST_SHPG_LOC_CD
                              AND DC.LEGAL_ENTITY_NAME = TOT.LEGAL_ENTITY_NAME
                              AND DC.GERP_ORG_CODE = TOT.ORGANIZATION_CODE
                              AND DC.USE_YN = 'Y') = 'Y'
                     THEN (SELECT SUM(C.DECLAREDVALUE)
                             FROM TB_GTM_LOAD L
                                 ,TB_GTM_CONTAINER_TMS_S_IF C
                            WHERE L.SHIPMENTNUMBER = C.SHIPMENTNUMBER
                              AND L.CANCEL_FLAG = 'N'
                              AND L.LD_LEG_ID = TOT.LD_LEG_ID)
                     ELSE NVL(TO_NUMBER(TOT.RFRC_NUM6), CEIL(TOT.TOT_VOL / (SELECT MAX(A.CD_NM2)
                                                                        FROM TB_GTM_CODEMAPPING_MST A
                                                                       WHERE A.LEGAL_ENTITY_NAME = TOT.LEGAL_ENTITY_NAME
                                                                         AND A.USE_YN = 'Y'
                                                                         AND A.CD_TYPE = 'PALLET_TYPE'
                                                                         AND A.CD = 'STD_PALLET')))
                END AS PALLET_QTY -- plt_yn = y �̸� container �� declearvalue 20150604 �̵���
               
               ,TOT.SHIPMENT_LEG -- Hub ���� �÷� �߰� 20150507 �̵���
               ,TOT.HUB -- Hub ���� �÷� �߰� 20150507 �̵���
               ,TOT.HUB_LOAD_ID -- Hub ���� �÷� �߰� 20150507 �̵���
               ,TO_HUB_CODE
               ,TOT.GLN_CODE -- LGEAG ���� �÷� �߰� 20150611 �̵���
               ,TOT.BEX_NO -- LGEAG ���� �÷� �߰� 20150611 �̵���
               ,TOT.REMITO_STATUS -- LGEAR ���� �÷� �߰� 20170502 ���ۿ� 
               ,TOT.EDI_FAIL_MESSAGE -- LGEAR ���� �÷� �߰� 20170502 ���ۿ� 
               ,CASE WHEN TOT.HUB IS NULL
                     THEN (SELECT MAX(SHIPD.SHIP_TO_SHORT_NAME)
                             FROM TB_GTM_SHIPMENT_DETAIL SHIPD
                            WHERE SHIPD.SHIPMENTNUMBER IN (SELECT LLDT.SHPM_NUM
                                                             FROM TMSPROD.LD_LEG_DETL_T LLDT
                                                            WHERE LLDT.LD_LEG_ID = TOT.LD_LEG_ID
                                                              AND LLDT.SEQ_NUM = TOT.SHIPMENT_LEG))
                     ELSE TOT.HUB
                END AS SHIP_TO_SHORT_NAME -- LGEDG ���� �÷� �߰� 20150611 �̵���
                ,DECODE((SELECT COUNT(*) FROM TB_GTM_CODEMAPPING_MST A WHERE A.CD_TYPE = 'DELIVERY_NOTE_PRT_RSTC' AND A.CD = LAST_SHPG_LOC_CD AND REPLACE(A.LEGAL_ENTITY_NAME,'LGE','LG') = TOT.DIV_CD),0,'Y','N') AS SHIP_TO_INVO_DOC_PRT_RSTC
                ,NVL(PDF_CREATE_FLAG,'N') AS  PDF_CREATE_FLAG --PDF �������� �߰�(Q20190403_09737) 20190513 ������
                ,(SELECT CASE WHEN COUNT(1) > 0 THEN 'NOT CLOSED' ELSE 'ALL CLOSED' END
        FROM TMSPROD.LD_LEG_DETL_T LT,TB_GTM_SHIPMENT_TMS_S_IF TMS,TB_GTM_CONTAINER_TMS_S_IF CON
        WHERE LT.SHPM_NUM = TMS.SHIPMENTNUMBER
        AND LT.SHPM_NUM = CON.SHIPMENTNUMBER
        AND CON.MODEL_GRADE = 'GS-XDOCK'
        AND TMS.XDOCK_STATUS NOT IN ('CLOSED','CANCELED')
        AND LT.LD_LEG_ID = TOT.LD_LEG_ID) AS XDOCK_CHECK -- C20200810_83090 FS XDOCK ���� �߰����� �߰�
        ,(SELECT COUNT(1) 
        FROM TMSPROD.LD_LEG_DETL_T LT,TB_GTM_SHIPMENT_TMS_S_IF TMS,TB_GTM_CONTAINER_TMS_S_IF CON
        WHERE LT.SHPM_NUM = TMS.SHIPMENTNUMBER
        AND LT.SHPM_NUM = CON.SHIPMENTNUMBER
        AND CON.MODEL_GRADE = 'GS-XDOCK'
        AND TMS.XDOCK_STATUS NOT IN ('CLOSED','CANCELED')
        AND LT.LD_LEG_ID = TOT.LD_LEG_ID) AS XDOCK_NOTCLOSED_CNT -- C20200810_83090 FS XDOCK ���� �߰����� �߰�
        ,(SELECT MAX(A.CD)   --C20200904_97370
                  FROM TB_GTM_CODEMAPPING_MST A,
                       TB_GTM_DCCONFIG        B
                 WHERE A.LEGAL_ENTITY_NAME = B.LEGAL_ENTITY_NAME
                   AND B.DC_CD = TOT.FRST_SHPG_LOC_CD
                   AND A.CD_TYPE = 'XDOCKBLOCK'
                   AND A.USE_YN = 'Y') AS X_DOCK_BLOCK -- C20200810_83090 FS XDOCK ���� �߰����� �߰�
              ,TOT.LC_BY AS LC_BY     -- PJ2024A029 ADD 20250929
              ,TOT.AR_BY AS AR_BY     -- PJ2024A029
              ,TOT.AC_BY AS AC_BY     -- PJ2024A029
              ,TOT.TA_BY AS TA_BY     -- PJ2024A029
              ,TOT.WR_BY AS WR_BY   -- PJ2024A029
              ,TOT.SC_BY AS SC_BY     -- RITM2628561
            FROM
            (
           SELECT /* + LEADING(LOAD) */
                  A.LD_LEG_ID,
                  A.FRST_SHPG_LOC_NAME,
                  A.FRST_SHPG_LOC_CD,
                  A.LAST_SHPG_LOC_NAME,
                  A.LAST_SHPG_LOC_CD,
                  A.LAST_CTY_NAME,
                  DECODE(A.LD_SRC_ENU,1,'Optimizer','Manual') AS LOAD_TYPE,
                  CARR.NAME AS CARR_NAME,
                  A.SRVC_CD,
                  A.EQMT_TYP,
                  A.TRCTR_NUM,
                  A.TRLR_NUM,
                  A.SEAL_NUM,
                  A.DRVR,
                  A.TRCTR_LIC_NUM,
                  A.RFRC_NUM2 AS MASTER_LOAD_ID,
                  NVL2(A.RFRC_NUM2,'Y','N') AS MERGE_FLAG,
--   T               SUM(CNTR.QUANTITY * ROUND(CNTR.VOLUME, 4)) AS TOT_VOL,
                  SUM(LOAD.PICK_QTY* ROUND((SELECT MAX(GC.VOLUME) FROM TB_GTM_CONTAINER_TMS_S_IF GC WHERE GC.SHIPMENTNUMBER = LOAD.SHIPMENTNUMBER), 3)) AS TOT_VOL,-- *******************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
--  T                SUM(CNTR.QUANTITY) AS TOT_QTY,
                  SUM(LOAD.PICK_QTY) AS TOT_QTY,-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
--  T                DECODE(NVL(MAX(RSTC.MAX_VOL),0),0,0,ROUND(SUM(CNTR.QUANTITY * ROUND(CNTR.VOLUME, 4))/MAX(RSTC.MAX_VOL) * 100 ,2)) AS STUFFING_RATIO,
                  DECODE(NVL(MAX(RSTC.MAX_VOL),0),0,0,ROUND(SUM(LOAD.PICK_QTY* ROUND(MODL.MODEL_GROSS_CBM, 4))/MAX(RSTC.MAX_VOL) * 100 ,2)) AS STUFFING_RATIO, -- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************                 
                  
                  DECODE(COUNT(DISTINCT(MODL.PRODUCT_LEVEL4_CODE)),1,'N','Y') AS MODEL_MIX,
                  (SELECT COUNT(*) FROM TMSPROD.STOP_T STP WHERE STP.LD_LEG_ID = A.LD_LEG_ID AND STP.SHPM_PICK = 0  ) AS NUM_OF_SHIPTO,
--      T            CASE WHEN MAX(A.CUR_OPTLSTAT_ID) >= 335 THEN SUM(LOAD.DELIVERY_QTY * ROUND(CNTR.VOLUME, 4)) ELSE 0 END  AS SHIPPING_CBM,
                  CASE WHEN MAX(A.CUR_OPTLSTAT_ID) >= 335 THEN SUM(LOAD.DELIVERY_QTY * ROUND(MODL.MODEL_GROSS_CBM, 3)) ELSE 0 END  AS SHIPPING_CBM,-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                  CASE WHEN MAX(A.CUR_OPTLSTAT_ID) >= 335 THEN SUM(LOAD.DELIVERY_QTY) ELSE 0 END  AS SHIPPING_QTY,
--      T            TRUNC(SUM(NVL(SHIP.TAX_EXCLUSIVE_PRICE,0)*CNTR.RES_QUANTITY),2) AS LOAD_VALUE,
                    TRUNC(SUM(NVL(SHIP.TAX_EXCLUSIVE_PRICE,0)*LOAD.DELIVERY_QTY),2) AS LOAD_VALUE,-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                  STAT.STAT_SHRT_DESC AS LOAD_STATUS,
                  MAX(TDR.TDR_RSPS_BY_DTT) AS TENDER_RESPONSE_DATE,
                  MAX((SELECT FC_GTM_GET_DATE_SYSTOLOC(A.FRST_SHPG_LOC_CD,A.CRTD_DTT) FROM DUAL)) AS CRTD_DTT,
                  FC_GTM_GET_PLAN_LEADTIME(A.FRST_SHPG_LOC_CD,A.LAST_SHPG_LOC_CD) AS LEAD_TIME,--ETA ���� ����
                ROUND(MAX(A.END_DTT) - MAX(A.STRD_DTT),2) AS DISTANCE_LEAD_TIME,--ETA ���� ����
                  --MIN(APT.APT_DATE) AS APPOINTMENT_DATE,
                  NVL((SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.REQUEST_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE = 'LC' AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ),'N') AS REQUEST_FLAG,
                  NVL((SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.APPROVAL_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE = 'LC' AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ),'N') AS APPROVAL_FLAG,
                  
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_TARIFF_ID FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_TARIFF_ID,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_CARRIER_CODE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_CARRIER_TYPE,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_SERVICE_CODE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_SERVICE_TYPE,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_VEHICLE_TYPE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_VEHICLE_TYPE,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_FREIGHT_COST FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_FREIGHT_COST,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_REASON FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REASON,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.REQUEST_ID FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REQUEST_ID,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.LAST_UPDATE_BY FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS RATE_CHANGE_BY,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.ORI_EVIDENCE_FILE_NAME FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS ORI_EVIDENCE_FILE_NAME,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_REASON_CATEGORY FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REASON_CATEGORY,
                  MAX(A.CHGD_AMT_DLR) AS FREIGHT_COST,
                  A.TFF_ID AS TARIFF_ID,
                  A.DIV_CD,
                  CARR.CARR_CD,
--          T        MAX(ROUND(CNTR.VOLUME, 4)) AS MODEL_GROSS_CBM,
                  MAX(ROUND(MODL.MODEL_GROSS_CBM, 4)) AS MODEL_GROSS_CBM,-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                  A.CUR_OPTLSTAT_ID AS LOAD_STATUS_ID,
                  (SELECT MAX(DC.WMS_SYS_TYPE) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS WMSTYPE,
                  (SELECT MAX(DC.DELIVERY_NOTE_USE_FLAG) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS DELIVERY_NOTE_USE_FLAG,
                  (SELECT MAX(DC.DELIVERY_NOTE_AUTO_POPUP_FLAG) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS DELIVERY_NOTE_AUTO_POPUP_FLAG,
                  (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.SPOT_RATE_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS SPOT_RATE_FLAG,
                  DECODE(A.LD_SRC_ENU,1,MAX(A.CRTD_USR_CD),(SELECT CREATE_BY FROM TB_GTM_LOAD_HISTORY WHERE LD_LEG_ID=A.LD_LEG_ID AND TYPE = 'MLC'))  AS LOAD_CREATE_BY,
                  MAX(NVL(RSTC.MAX_VOL,0)) AS LDPNT1_LOC,
--   T               MIN((SELECT FC_GTM_GET_DATE_SYSTOLOC(A.FRST_SHPG_LOC_CD,LEGD.CFMD_DTT) FROM DUAL)) AS CFMD_DTT,
                  MIN(LOAD.SHIPPING_DATE) AS CFMD_DTT, -- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                  DECODE(SHIP.LEGAL_ENTITY_NAME,'LGEUK',SHIP.SHIPFROMLOCATIONCODE,'LGEPH',SHIP.SHIPFROMLOCATIONCODE,SHIP.ORGANIZATION_CODE) AS ORGANIZATION_CODE,
                  MAX(LOAD.CREATION_USER_ID) AS WH_RELEASE_BY,
                  CASE WHEN A.CUR_OPTLSTAT_ID >= 335 THEN MAX(LOAD.LAST_UPDATE_USER_ID) ELSE '' END AS SHIP_CONFIRM_BY,
                  CASE A.SPOT_RATE_YN WHEN 'F' THEN 'N' WHEN 'T' THEN 'Y' ELSE '' END AS SPOT_RATE,
                  A.RFRC_NUM3 LOAD_REMARK,
--          T        SUM(CNTR.QUANTITY * ROUND(MODL.GROSS_WEIGHT, 4)) AS TOTAL_WEIGHT,
                  SUM(LOAD.PICK_QTY * ROUND(MODL.GROSS_WEIGHT, 4)) AS TOTAL_WEIGHT,-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                  (SELECT COUNT(*) FROM TMSPROD.STOP_T STP WHERE STP.LD_LEG_ID = A.LD_LEG_ID AND STP.SHPM_DROP = 0  ) AS NUM_OF_ORIGIN,
                  A.TRLR_LIC_NUM AS REQUEST_DELIVERY_DATE,
                MAX(TO_CHAR(A.END_DTT,'YYYY-MM-DD HH24:MI:SS')) AS SCHEDULED_ARRIVAL_DATE,
                MAX(TO_CHAR(A.STRD_DTT,'YYYY-MM-DD HH24:MI:SS')) AS SCHEDULED_DEPARTURE_DATE,
/*         T         MAX(CASE WHEN A.CUR_OPTLSTAT_ID IN (335, 345) THEN TO_CHAR(FC_GTM_GET_DATE_SYSTOLOC(LEGD.FRM_SHPG_LOC_CD, LEGD.CFMD_DTT) + FC_GTM_GET_PLAN_LEADTIME(A.FRST_SHPG_LOC_CD,A.LAST_SHPG_LOC_CD), 'YYYY-MM-DD HH24:MI:SS')
                     WHEN A.CUR_OPTLSTAT_ID IN (300, 305, 310, 315, 320, 325) THEN TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')
                     ELSE NULL END) AS ETA,--ETA ���� ����*/
                MAX(CASE WHEN A.CUR_OPTLSTAT_ID IN (335, 345) THEN TO_CHAR(LOAD.SHIPPING_DATE + FC_GTM_GET_PLAN_LEADTIME(A.FRST_SHPG_LOC_CD,A.LAST_SHPG_LOC_CD), 'YYYY-MM-DD HH24:MI:SS')
                     WHEN A.CUR_OPTLSTAT_ID IN (300, 305, 310, 315, 320, 325) THEN TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')
                     ELSE NULL END) AS ETA,  -- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
/*        T        MAX(CASE WHEN A.CUR_OPTLSTAT_ID IN (335, 345) THEN TO_CHAR(FC_GTM_GET_DATE_SYSTOLOC(LEGD.FRM_SHPG_LOC_CD, LEGD.CFMD_DTT) + ROUND(A.END_DTT - A.STRD_DTT, 1), 'YYYY-MM-DD HH24:MI:SS')
                     WHEN A.CUR_OPTLSTAT_ID IN (300, 305, 310, 315, 320, 325) THEN TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')
                     ELSE NULL END) AS DISTANCE_ETA,--ETA ���� ����*/
                MAX(CASE WHEN A.CUR_OPTLSTAT_ID IN (335, 345) THEN TO_CHAR(LOAD.SHIPPING_DATE + ROUND(A.END_DTT - A.STRD_DTT, 1), 'YYYY-MM-DD HH24:MI:SS')
                     WHEN A.CUR_OPTLSTAT_ID IN (300, 305, 310, 315, 320, 325) THEN TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')
                     ELSE NULL END) AS DISTANCE_ETA,       -- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************                  
                     LT.DISTANCE_USE_FLAG -- ETA ���� ����
                  
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,SHIP.ZONE_CODE,NULL)) AS ZONE
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,
                      (SELECT ZN_DESC FROM TMSPROD.ZN_T ZN WHERE ZN.ZN_CD = SHIP.ZONE_CODE AND ROWNUM = 1)                      
                    ,NULL)) AS ZONE_NAME
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,
                    (SELECT SHRT_DESC FROM TMSPROD.ZN_T ZN WHERE ZN.ZN_CD = SHIP.ZONE_CODE AND ROWNUM = 1)      
                    ,NULL)) AS SHRT_DESC
             ,max((select CD_NM from tb_gtm_code_mst where cd_type = 'WMS_STATUS' AND CD = LOAD.LOAD_STATUS)) AS  WMS_STATUS
             ,max((SELECT  MAX(auto_ship_confirm_yn) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD)) AS  auto_ship_confirm_yn 
             ,MAX(LOAD.LOAD_STATUS) as WMS_STATUS_CODE
               ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ H.TOUR_NO        
             FROM   TMS_IF.TB_GTM_TENDER_HISTORY H 
            WHERE H.LD_LEG_ID =  A.LD_LEG_ID
          AND ROWNUM = 1) AS TOUR_NO  
        ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ TO_CHAR(H.RESPONSE_ARRIVAL_LG_WH,'YYYY-MM-DD HH24:MI:SS')
             FROM   TMS_IF.TB_GTM_TENDER_HISTORY H 
            WHERE H.LD_LEG_ID =  A.LD_LEG_ID 
          AND ROWNUM = 1) AS RESPONSE_ARRIVAL_LG_WH  
               ,A.RFRC_NUM4 AS LOAD_GROUP_ID
               ,A.RFRC_NUM4 AS LOAD_GROUP_ID_TH
               ,A.RFRC_NUM5 AS REF_BOOK_NO
               ,DECODE(SUM(DECODE(DECODE(LOAD.DELIVERY_QTY,0,NULL,LOAD.INVO_NO), NULL, 0, 1)), A.NUM_SHPM, 'Y', 'N') AS INVO_AVAIL_FLAG
               ,A.RFRC_NUM6
               ,SHIP.LEGAL_ENTITY_NAME
               ,MAX(LEGD.SEQ_NUM) AS SHIPMENT_LEG -- Hub ���� �÷� �߰� 20150507 �̵���
               ,MAX((SELECT /*+INDEX_DESC(H PK_HUB)*/
                     H.NAME
                 FROM TMSPROD.HUB_T H
                WHERE H.SHPG_LOC_CD = LEGD.TO_SHPG_LOC_CD)) AS HUB -- Hub ���� �÷� �߰� 20150507 �̵���
        ,MAX(CASE
               WHEN LEGD.SEQ_NUM > 100 THEN
                (SELECT /*+INDEX_DESC(LDT FKLLD_SHPM)*/
                        LDT.LD_LEG_ID
                   FROM TMSPROD.LD_LEG_DETL_T LDT
                  WHERE LDT.SHPM_ID = LEGD.SHPM_ID
                    AND LDT.SEQ_NUM = LEGD.SEQ_NUM - 100)
             ELSE
              NULL
         END) AS HUB_LOAD_ID -- Hub ���� �÷� �߰� 20150507 �̵���
         ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ H.CARRIER_TERMINAL_CODE2        
                 FROM   TMS_IF.TB_GTM_TENDER_HISTORY H 
                WHERE H.LD_LEG_ID =  A.LD_LEG_ID
                  AND ROWNUM = 1) AS TO_HUB_CODE
                 ,MAX(LOAD.GLN_CODE) AS GLN_CODE -- LGEAG ���� �÷� �߰� 20150611 �̵���
             ,MAX(LOAD.BEX_NO) AS BEX_NO -- LGEAG ���� �÷� �߰� 20150611 �̵���
             ,NVL(MAX(LOAD.ATTRIBUTE3),'Not Send') AS REMITO_STATUS -- LGEAR ���� �÷� �߰� 20170502 ���ۿ�
             ,MAX(LOAD.ATTRIBUTE4) AS EDI_FAIL_MESSAGE -- LGEAR ���� �÷� �߰� 20170413 �̼���
             ,MAX(LOAD.ATTRIBUTE30) AS PDF_CREATE_FLAG --PDF �������� �߰�(Q20190403_09737) 20190513 ������
         
         /*
         ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'LC', null),'YYYY-MM-DD HH24:MI:SS')    AS LC_BY -- PJ2024A029 ADD 20250929
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'AR', null),'YYYY-MM-DD HH24:MI:SS')    AS AR_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'AC', null),'YYYY-MM-DD HH24:MI:SS')    AS AC_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'TA', null),'YYYY-MM-DD HH24:MI:SS')    AS TA_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'WR', null),'YYYY-MM-DD HH24:MI:SS')    AS WR_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'SC', null),'YYYY-MM-DD HH24:MI:SS')    AS SC_BY -- PJ2024A029
                 */
       
       /*Due Date RITM2628561*/
       ,(SELECT TO_CHAR(MIN(DUE.LOAD_CREATE_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS LC_BY
       ,(SELECT TO_CHAR(MIN(DUE.APPOINTMENT_REQUEST_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS AR_BY
       ,(SELECT TO_CHAR(MIN(DUE.APPOINTMENT_CONFIRM_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS AC_BY
       ,(SELECT TO_CHAR(MIN(DUE.TENDER_RESPONSE_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS TA_BY
       ,(SELECT TO_CHAR(MIN(DUE.RELEASE_TO_WH_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS WR_BY
       ,(SELECT TO_CHAR(MIN(DUE.SHIP_CONFIRM_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS SC_BY
                FROM TMSPROD.LD_LEG_T A,
                  TMSPROD.STOP_T C,
                  TMSPROD.LD_LEG_DETL_T LEGD, -- Hub ���� �ּ����� 20150507 �̵���
                  TB_GTM_LOAD LOAD,
                  TB_GTM_SHIPMENT_TMS_S_IF SHIP,
--       T        TB_GTM_CONTAINER_TMS_S_IF CNTR,
                  VI_GTM_MODEL MODL,
                  TMSPROD.CARR_T CARR,
                  TMSPROD.STAT_T STAT,
                  TMSPROD.TDR_REQ_T TDR,
                  
                TMSPROD.TFF_SRVC_EQMT_T EQMT,
                TMSPROD.RSTC_T RSTC,
              TB_GTM_SERVICE_LEADTIME LT  -- ETA ���� ����
                WHERE A.LD_LEG_ID = C.LD_LEG_ID
                 AND C.SEQ_NUM = 1
                 AND A.LD_LEG_ID = LOAD.LD_LEG_ID
                 AND LOAD.LD_LEG_ID = LEGD.LD_LEG_ID -- Hub ���� �ּ����� 20150507 �̵���
                 AND LOAD.SHIPMENTNUMBER = LEGD.SHPM_NUM -- Hub ���� �ּ����� 20150507 �̵���
                 AND SHIP.SHIPMENTNUMBER = LEGD.SHPM_NUM -- Hub ���� �ּ����� 20150507 �̵���
                 AND LOAD.SHIPMENTNUMBER = SHIP.SHIPMENTNUMBER   -- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
--  T                 AND LEGD.SEQ_NUM = '100'
--  T                 AND SHIP.SHIPMENTNUMBER = CNTR.SHIPMENTNUMBER
--  T                 AND CNTR.AFFILIATE_CODE = MODL.AFFILIATE_CODE(+)
--  T                 AND CNTR.CONTAINERTYPECODE = MODL.MODEL_CODE(+)
                 AND LOAD.AFFILIATE_CODE = MODL.AFFILIATE_CODE(+)-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                 AND LOAD.ITEM_CODE = MODL.MODEL_CODE(+)-- ************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************
                 AND A.CARR_CD = CARR.CARR_CD(+)
                 AND A.CUR_OPTLSTAT_ID = STAT.STAT_ID
                 AND A.TDR_REQ_ID = TDR.TDR_REQ_ID(+)
                 
                 AND A.TFF_ID = EQMT.TFF_ID(+)
               AND A.SRVC_CD = EQMT.SRVC_CD(+)
               AND A.EQMT_TYP = EQMT.EQMT_TYP_CD(+)
               AND EQMT.RSTC_ID = RSTC.RSTC_ID(+)
               AND A.DIV_CD = LT.DIV_CD(+) -- ETA ���� ����
              AND A.SRVC_CD = LT.SERVICE_CODE(+) -- ETA ���� ����
                 AND A.CUR_OPTLSTAT_ID >= 325
                    AND LOAD.FRM_SHPG_LOC_CD IN ( 'N2U' ) 
                    AND LOAD.LOAD_CREATION_DATE BETWEEN TO_DATE('20260402','YYYYMMDD') AND TO_DATE('20260409','YYYYMMDD')+0.99999 
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    AND LOAD.LEGAL_ENTITY_NAME IN ('LGECL') 
                    
                    AND LOAD.FRM_SHPG_LOC_CD IN ( 'N2U' ) 
                    
                    
                    
                    AND LEGD.SEQ_NUM IN ( 100 ) 
                     
   
         GROUP BY
                A.LD_LEG_ID,
                A.FRST_SHPG_LOC_NAME,
                A.FRST_SHPG_LOC_CD,
                A.LAST_SHPG_LOC_NAME,
                A.LAST_SHPG_LOC_CD,
                A.LAST_CTY_NAME,
                A.LD_SRC_ENU,
                CARR.NAME,
                A.SRVC_CD,
                A.EQMT_TYP,
                A.TRCTR_NUM,
                A.TRLR_NUM,
                A.SEAL_NUM,
                A.DRVR,
                A.TRCTR_LIC_NUM,
                STAT.STAT_SHRT_DESC,
                A.TFF_ID,
                A.DIV_CD,
                CARR.CARR_CD,
                A.CUR_OPTLSTAT_ID,
                A.RFRC_NUM2,
                DECODE(SHIP.LEGAL_ENTITY_NAME,'LGEUK',SHIP.SHIPFROMLOCATIONCODE,'LGEPH',SHIP.SHIPFROMLOCATIONCODE,SHIP.ORGANIZATION_CODE),
                A.SPOT_RATE_YN,
                A.RFRC_NUM3,
                A.TRLR_LIC_NUM,
                LT.DISTANCE_USE_FLAG,
                A.RFRC_NUM4,
        A.RFRC_NUM5, 
        A.NUM_SHPM,
        A.RFRC_NUM6,
               SHIP.LEGAL_ENTITY_NAME
                
UNION ALL
 
 SELECT   /*+ LEADING(A)*/
                    A.LD_LEG_ID,
                    A.FRST_SHPG_LOC_NAME,
                    A.FRST_SHPG_LOC_CD,
                    A.LAST_SHPG_LOC_NAME,
                    A.LAST_SHPG_LOC_CD,
                    A.LAST_CTY_NAME,
                    DECODE(A.LD_SRC_ENU,1,'Optimizer','Manual') AS LOAD_TYPE,
                    CARR.NAME AS CARR_NAME,
                    A.SRVC_CD,
                    A.EQMT_TYP,
                    A.TRCTR_NUM,
                    A.TRLR_NUM,
                    A.SEAL_NUM,
                    A.DRVR,
                    A.TRCTR_LIC_NUM,
                    A.RFRC_NUM2 AS MASTER_LOAD_ID,
                    NVL2(A.RFRC_NUM2,'Y','N') AS MERGE_FLAG,
                    SUM(CNTR.QUANTITY * ROUND(CNTR.VOLUME, 3)) AS TOT_VOL,
                    SUM(CNTR.QUANTITY) AS TOT_QTY,
                    DECODE(NVL(MAX(RSTC.MAX_VOL),0),0,0,ROUND(SUM(CNTR.QUANTITY * ROUND(CNTR.VOLUME, 4))/MAX(RSTC.MAX_VOL) * 100 ,2)) AS STUFFING_RATIO,
                    
                    DECODE(COUNT(DISTINCT(MODL.PRODUCT_LEVEL4_CODE)),1,'N','Y') AS MODEL_MIX,
                    (SELECT COUNT(*) FROM TMSPROD.STOP_T STP WHERE STP.LD_LEG_ID = A.LD_LEG_ID AND STP.SHPM_PICK = 0  ) AS NUM_OF_SHIPTO,
                    CASE WHEN MAX(A.CUR_OPTLSTAT_ID) >= 335 THEN SUM(CNTR.RES_QUANTITY * ROUND(CNTR.VOLUME, 3)) ELSE 0 END  AS SHIPPING_CBM,
                    CASE WHEN MAX(A.CUR_OPTLSTAT_ID) >= 335 THEN SUM(CNTR.RES_QUANTITY) ELSE 0 END  AS SHIPPING_QTY,
                    TRUNC(SUM(NVL(SHIP.TAX_EXCLUSIVE_PRICE,0)*CNTR.RES_QUANTITY),2) AS LOAD_VALUE,
                    STAT.STAT_SHRT_DESC AS LOAD_STATUS,
                    MAX(TDR.TDR_RSPS_BY_DTT) AS TENDER_RESPONSE_DATE,
                    MAX((SELECT FC_GTM_GET_DATE_SYSTOLOC(A.FRST_SHPG_LOC_CD,A.CRTD_DTT)FROM DUAL)) AS CRTD_DTT,
                    FC_GTM_GET_PLAN_LEADTIME(A.FRST_SHPG_LOC_CD,A.LAST_SHPG_LOC_CD) AS LEAD_TIME,--ETA ���� ����
                ROUND(MAX(A.END_DTT) - MAX(A.STRD_DTT),2) AS DISTANCE_LEAD_TIME,--ETA ���� ����
                    --MIN(APT.APT_DATE) AS APPOINTMENT_DATE,
                    NVL((SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.REQUEST_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE = 'LC' AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ),'N') AS REQUEST_FLAG,
                    NVL((SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.APPROVAL_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE = 'LC' AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ),'N') AS APPROVAL_FLAG,
                    
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_TARIFF_ID FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_TARIFF_ID,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_CARRIER_CODE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_CARRIER_TYPE,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_SERVICE_CODE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_SERVICE_TYPE,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_VEHICLE_TYPE FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_VEHICLE_TYPE,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_FREIGHT_COST FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_FREIGHT_COST,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_REASON FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REASON,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.REQUEST_ID FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REQUEST_ID,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.LAST_UPDATE_BY FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS RATE_CHANGE_BY,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.ORI_EVIDENCE_FILE_NAME FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS ORI_EVIDENCE_FILE_NAME,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.CHANGE_REASON_CATEGORY FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS CHANGE_REASON_CATEGORY,
                         
                    MAX(A.CHGD_AMT_DLR) AS FREIGHT_COST,
                    A.TFF_ID AS TARIFF_ID,
                    A.DIV_CD,
                    CARR.CARR_CD,
                    MAX(ROUND(CNTR.VOLUME, 4)) AS MODEL_GROSS_CBM,
                    A.CUR_OPTLSTAT_ID AS LOAD_STATUS_ID,
                    (SELECT MAX(DC.WMS_SYS_TYPE) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS WMSTYPE,
                    (SELECT MAX(DC.DELIVERY_NOTE_USE_FLAG) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS DELIVERY_NOTE_USE_FLAG,
                    (SELECT MAX(DC.DELIVERY_NOTE_AUTO_POPUP_FLAG) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD) AS DELIVERY_NOTE_AUTO_POPUP_FLAG,
                    (SELECT /*+index_desc(REQ TB_GTM_LOADADJUST_REQ_IX03)*/ REQ.SPOT_RATE_FLAG FROM TB_GTM_LOADADJUST_REQUEST REQ WHERE REQ.LOAD_ID=A.LD_LEG_ID AND REQ.REQUEST_TYPE IN ('LC','LM') AND REQ.LAST_UPDATE_DATE < SYSDATE AND ROWNUM=1 ) AS SPOT_RATE_FLAG,
                    DECODE(A.LD_SRC_ENU,1,MAX(A.CRTD_USR_CD),(SELECT CREATE_BY FROM TB_GTM_LOAD_HISTORY WHERE LD_LEG_ID=A.LD_LEG_ID AND TYPE = 'MLC')) AS LOAD_CREATE_BY,
                    MAX(NVL(RSTC.MAX_VOL,0)) AS LDPNT1_LOC,
                    (SELECT FC_GTM_GET_DATE_SYSTOLOC(A.FRST_SHPG_LOC_CD,LEGD.CFMD_DTT) FROM DUAL) AS CFMD_DTT,
                    DECODE(SHIP.LEGAL_ENTITY_NAME,'LGEUK',SHIP.SHIPFROMLOCATIONCODE,'LGEPH',SHIP.SHIPFROMLOCATIONCODE,SHIP.ORGANIZATION_CODE) AS ORGANIZATION_CODE,
                    '' AS WH_RELEASE_BY,
                    '' AS SHIP_CONFIRM_BY,
                    CASE A.SPOT_RATE_YN WHEN 'F' THEN 'N' WHEN 'T' THEN 'Y' ELSE '' END AS SPOT_RATE,
                    A.RFRC_NUM3 LOAD_REMARK,
                  SUM(CNTR.QUANTITY * ROUND(MODL.GROSS_WEIGHT, 4)) AS TOTAL_WEIGHT,
                  (SELECT COUNT(*) FROM TMSPROD.STOP_T STP WHERE STP.LD_LEG_ID = A.LD_LEG_ID AND STP.SHPM_DROP = 0  ) AS NUM_OF_ORIGIN,
                  A.TRLR_LIC_NUM AS REQUEST_DELIVERY_DATE,
                MAX(TO_CHAR(A.END_DTT,'YYYY-MM-DD HH24:MI:SS')) AS SCHEDULED_ARRIVAL_DATE,
                MAX(TO_CHAR(A.STRD_DTT,'YYYY-MM-DD HH24:MI:SS')) AS SCHEDULED_DEPARTURE_DATE,
                  MAX(TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')) AS ETA,--ETA ���� ����
               MAX(TO_CHAR(A.END_DTT, 'YYYY-MM-DD HH24:MI:SS')) AS DISTANCE_ETA,--ETA ���� ����
                LT.DISTANCE_USE_FLAG --ETA ���� ����
                
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,SHIP.ZONE_CODE,NULL)) AS ZONE
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,
                      (SELECT ZN_DESC FROM TMSPROD.ZN_T ZN WHERE ZN.ZN_CD = SHIP.ZONE_CODE AND ROWNUM = 1)                      
                  ,NULL)) AS ZONE_NAME
                ,MAX(DECODE(A.LAST_SHPG_LOC_CD,SHIP.SHIPTOLOCATIONCODE,
                    (SELECT SHRT_DESC FROM TMSPROD.ZN_T ZN WHERE ZN.ZN_CD = SHIP.ZONE_CODE AND ROWNUM = 1)      
                    ,NULL)) AS SHRT_DESC
        ,'' AS  WMS_STATUS
        ,MAX((SELECT  MAX(auto_ship_confirm_yn) FROM TB_GTM_DCCONFIG DC WHERE DC.USE_YN = 'Y' AND DC.DC_CD = A.FRST_SHPG_LOC_CD)) AS  AUTO_SHIP_CONFIRM_YN
        ,NULL as WMS_STATUS_CODE
               ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ H.TOUR_NO        
             FROM   TMS_IF.TB_GTM_TENDER_HISTORY H 
            WHERE H.LD_LEG_ID =  A.LD_LEG_ID 
          AND ROWNUM = 1) AS TOUR_NO  
        ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ TO_CHAR(H.RESPONSE_ARRIVAL_LG_WH,'YYYY-MM-DD HH24:MI:SS')
             FROM   TMS_IF.TB_GTM_TENDER_HISTORY H 
            WHERE H.LD_LEG_ID =  A.LD_LEG_ID 
          AND ROWNUM = 1) AS RESPONSE_ARRIVAL_LG_WH                         
              ,A.RFRC_NUM4 AS LOAD_GROUP_ID
              ,A.RFRC_NUM4 AS LOAD_GROUP_ID_TH
          ,A.RFRC_NUM5 AS REF_BOOK_NO
          ,'N' AS INVO_AVAIL_FLAG
          ,A.RFRC_NUM6
               ,SHIP.LEGAL_ENTITY_NAME
               ,MAX(LEGD.SEQ_NUM) AS SHIPMENT_LEG -- Hub ���� �÷� �߰� 20150507 �̵���
               ,MAX((SELECT /*+INDEX_DESC(H PK_HUB)*/
                       H.NAME
                FROM TMSPROD.HUB_T H
               WHERE H.SHPG_LOC_CD = LEGD.TO_SHPG_LOC_CD)) AS HUB -- Hub ���� �÷� �߰� 20150507 �̵���
        ,MAX(CASE
               WHEN LEGD.SEQ_NUM > 100 THEN
                (SELECT /*+INDEX_DESC(LDT FKLLD_SHPM)*/
                        LDT.LD_LEG_ID
                   FROM TMSPROD.LD_LEG_DETL_T LDT
                  WHERE LDT.SHPM_ID = LEGD.SHPM_ID
                    AND LDT.SEQ_NUM = LEGD.SEQ_NUM - 100)
             ELSE
              NULL
         END) AS HUB_LOAD_ID -- Hub ���� �÷� �߰� 20150507 �̵���
         ,(SELECT /*+ INDEX_DESC(H TB_GTM_TENDER_HISTORY_PK01) */ H.CARRIER_TERMINAL_CODE2        
                 FROM TMS_IF.TB_GTM_TENDER_HISTORY H 
                WHERE H.LD_LEG_ID =  A.LD_LEG_ID
                  AND ROWNUM = 1) AS TO_HUB_CODE
             ,MAX((SELECT MAX(LOAD.GLN_CODE)
                  FROM TB_GTM_LOAD LOAD
                 WHERE LOAD.LD_LEG_ID = LEGD.LD_LEG_ID
                   AND LOAD.LD_LEG_SEQ_NO = LEGD.SEQ_NUM)) AS GLN_CODE -- LGEAG ���� �߰� 20150611 �̵���
          ,MAX((SELECT MAX(LOAD.BEX_NO) 
                 FROM TB_GTM_LOAD LOAD
                WHERE LOAD.LD_LEG_ID = LEGD.LD_LEG_ID
                  AND LOAD.LD_LEG_SEQ_NO = LEGD.SEQ_NUM)) AS BEX_NO -- LGEAG ���� �߰� 20150611 �̵���
         ,'Not Send' AS REMITO_STATUS   -- LGEAR ���� �߰� 20170502 ���ۿ�
         ,'' AS EDI_FAIL_MESSAGE -- LGEAR ���� �߰� 20170502 ���ۿ�
         ,'' AS PDF_CREATE_FLAG --PDF �������� �߰�(Q20190403_09737) 20190513 ������
               
               /*
               ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'LC', null),'YYYY-MM-DD HH24:MI:SS')    AS LC_BY -- PJ2024A029 ADD 20250929
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'AR', null),'YYYY-MM-DD HH24:MI:SS')    AS AR_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'AC', null),'YYYY-MM-DD HH24:MI:SS')    AS AC_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'TA', null),'YYYY-MM-DD HH24:MI:SS')    AS TA_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'WR', null),'YYYY-MM-DD HH24:MI:SS')    AS WR_BY -- PJ2024A029
                 ,TO_CHAR(PK_GTM_DATE.GET_DUE_DATE(MAX(LEGD.SHPM_NUM), 'SC', null),'YYYY-MM-DD HH24:MI:SS')    AS SC_BY -- PJ2024A029
                 */
       
       /*Due Date RITM2628561*/
       ,(SELECT TO_CHAR(MIN(DUE.LOAD_CREATE_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS LC_BY
       ,(SELECT TO_CHAR(MIN(DUE.APPOINTMENT_REQUEST_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS AR_BY
       ,(SELECT TO_CHAR(MIN(DUE.APPOINTMENT_CONFIRM_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS AC_BY
       ,(SELECT TO_CHAR(MIN(DUE.TENDER_RESPONSE_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS TA_BY
       ,(SELECT TO_CHAR(MIN(DUE.RELEASE_TO_WH_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS WR_BY
       ,(SELECT TO_CHAR(MIN(DUE.SHIP_CONFIRM_DUE),'YYYY-MM-DD HH24:MI:SS') FROM TB_GTM_DUE_DATE_CALC DUE WHERE 1=1 AND DUE.LOAD_ID = A.LD_LEG_ID)     AS SC_BY
                FROM TMSPROD.LD_LEG_T A,
                    TMSPROD.STOP_T C,
                    TMSPROD.LD_LEG_DETL_T LEGD,
                    TB_GTM_SHIPMENT_TMS_S_IF SHIP,
                    TB_GTM_CONTAINER_TMS_S_IF CNTR,
                    --TB_GTM_MODEL MODL,
                    VI_GTM_MODEL MODL,
                    TMSPROD.CARR_T CARR,
                    TMSPROD.STAT_T STAT,
                    TMSPROD.TDR_REQ_T TDR,
                    
                  TMSPROD.TFF_SRVC_EQMT_T EQMT,
                  TMSPROD.RSTC_T RSTC,
                  TB_GTM_SERVICE_LEADTIME LT  -- ETA ���� ����   
                WHERE A.LD_LEG_ID=C.LD_LEG_ID
                    AND C.SEQ_NUM=1
                    AND A.CUR_OPTLSTAT_ID =320
                    AND A.LD_LEG_ID=LEGD.LD_LEG_ID
                    AND LEGD.SHPM_NUM=SHIP.SHIPMENTNUMBER
                    --AND LEGD.SEQ_NUM='100' --Hub ���� �ּ�ó�� 20150507 �̵���
                    AND SHIP.SHIPMENTNUMBER = CNTR.SHIPMENTNUMBER
                    AND CNTR.AFFILIATE_CODE = MODL.AFFILIATE_CODE(+)
                    AND CNTR.CONTAINERTYPECODE = MODL.MODEL_CODE(+)
                    AND A.CARR_CD = CARR.CARR_CD(+)
                    AND A.CUR_OPTLSTAT_ID = STAT.STAT_ID
                    AND A.TDR_REQ_ID = TDR.TDR_REQ_ID(+)
                    
                    AND A.TFF_ID = EQMT.TFF_ID(+)
                  AND A.SRVC_CD = EQMT.SRVC_CD(+)
                  AND A.EQMT_TYP = EQMT.EQMT_TYP_CD(+)
                  AND EQMT.RSTC_ID = RSTC.RSTC_ID(+)
                  AND A.DIV_CD = LT.DIV_CD(+) -- ETA ���� ����
              AND A.SRVC_CD = LT.SERVICE_CODE(+) -- ETA ���� ����
                 
                    AND A.FRST_SHPG_LOC_CD IN ( 'N2U' ) 
                    AND TO_CHAR((SELECT FC_GTM_GET_DATE_SYSTOLOC(A.FRST_SHPG_LOC_CD,A.CRTD_DTT)FROM DUAL),'YYYYMMDD') BETWEEN '20260402' AND '20260409'            -- Load Create Date 
                    AND  A.CRTD_DTT BETWEEN TO_DATE('20260402','YYYYMMDD') -2  AND TO_DATE('20260409' ,'YYYYMMDD') + 2 
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    
                    AND SHIP.LEGAL_ENTITY_NAME IN ('LGECL') 
                    
                    AND A.FRST_SHPG_LOC_CD IN ( 'N2U' ) 
                    
                    
                    
                    AND LEGD.SEQ_NUM IN ( 100 ) 
                    
                GROUP BY
                    A.LD_LEG_ID,
                    A.FRST_SHPG_LOC_NAME,
                    A.FRST_SHPG_LOC_CD,
                    A.LAST_SHPG_LOC_NAME,
                    A.LAST_SHPG_LOC_CD,
                    A.LAST_CTY_NAME,
                    A.LD_SRC_ENU,
                    CARR.NAME,
                    A.SRVC_CD,
                    A.EQMT_TYP,
                    A.TRCTR_NUM,
                    A.TRLR_NUM,
                    A.SEAL_NUM,
                    A.DRVR,
                    A.TRCTR_LIC_NUM,
                    STAT.STAT_SHRT_DESC,
                    A.TFF_ID,
                    A.DIV_CD,
                    CARR.CARR_CD,
                    A.CUR_OPTLSTAT_ID,
                    A.RFRC_NUM2,
                    LEGD.CFMD_DTT,
                    DECODE(SHIP.LEGAL_ENTITY_NAME,'LGEUK',SHIP.SHIPFROMLOCATIONCODE,'LGEPH',SHIP.SHIPFROMLOCATIONCODE,SHIP.ORGANIZATION_CODE),  
                    A.SPOT_RATE_YN,
                    A.RFRC_NUM3,
                    A.TRLR_LIC_NUM,
               LT.DISTANCE_USE_FLAG,
                A.RFRC_NUM4,
        A.RFRC_NUM5,
        A.RFRC_NUM6,
               SHIP.LEGAL_ENTITY_NAME
                
            ) TOT
            WHERE 1= 1
             
             
             
            order by LD_LEG_ID DESC) inner_temp where rownum <= ('0'+1) * '100'
) where devonindex between  '1' and '1'+99 
