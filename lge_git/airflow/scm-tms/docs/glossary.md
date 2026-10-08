# 용어집 (Glossary) — 전체 배치 공통

> 현업과 얘기하다 모르는 단어 나오면 여기서 바로 찾기용. `docs/batch.SO/`, `docs/batch.0800/` 등 배치그룹별 문서에서 공통으로 참조.
> "확인됨"=코드/실측 검증, "업계표준"=일반 물류용어, "미확인"=아직 못 찾음.

## 채널/오더 종류

| 용어 | 의미 |
|---|---|
| OBS | 온라인 브랜드 샵 — 개인 고객에게 직접 파는 B2C 채널 |
| SO | Sales Order — B2C 고객에게 판매하는 오더 |
| PO | Purchase Order — 판매법인이 생산공장에 구매요청하는 오더(부품 등). SO와 반대방향 |

## 시스템/ERP

| 용어 | 의미 |
|---|---|
| GERP | Oracle EBS 기반 레거시 오더관리 시스템. 대다수 법인이 사용. **"HOLD"** 용어 사용 |
| NERP | SAP 기반 신규 오더관리 시스템. 일부 법인만 전환 완료. **"BLOCK"** 용어 사용 |
| TMS | Transportation Management System — 물류 운송 실행 시스템 |
| GSCP | Global Supply Chain Planning (본 앱 데이터흐름 직접 참조는 미확인) |
| PANTOS | LG 계열 물류사로 추정 — 해상운송 컨테이너 추적 데이터(`V_L0NEDW_ZSLEI1021`)의 원천 (FTV 약어는 미확인) |

**GERP="Hold" vs NERP="Block" — 확인됨.** SAP 원천뷰(`L1_SCM_.TRSCM__NERP_SO_LINE_DW_S_DO`)엔 원본 컬럼명 자체가 `Back_Order_Block`, `Credit_Block`, `Block_Flag`. Oracle 쪽은 `HOLD_FLAG`, `CREDIT_HOLD`. LIW가 임의로 붙인 이름이 아니라 **벤더(Oracle vs SAP) 자체 용어 차이**.

## 오더 상태(주문 프로세스) — 확인됨

```
ENTERED → BOOKED → (HOLD) → PICK_READY → PICK_RELEASE → LOAD_CREATION → WH_RELEASE → SHIPPING_CONFIRM → SHIPPED → IOD → CLOSED
```

- **BOOKED**: 오더가 확정되어 "진짜 SALES ORDER"가 되는 시점. 이전(ENTERED)은 초안.
- **NERP는 ENTERED가 없음 — 실측 확인.** `M_SO_LINE`에서 `SOURCE='NERP'`인 행 중 `PROGESS_STATUS='ENTERED'`는 0건(GERP는 56,146건). SAP은 오더가 인터페이스될 때 이미 확정 상태로만 넘어옴.
- **HOLD RELEASE**: 홀드가 풀려서 "보낼 준비 완료(PICK_READY)"가 됨.
- **PICK RELEASE**: 창고에 "이 오더 꺼내라" 지시가 내려가는 것. 오더(라인) 단위. 이 시점에 Oracle Move Order가 생성되고 TMS가 이걸 받아서 SHIPMENT로 연결(=TMS로 오더를 넘기는 행동).
- **LOAD CREATION**: 트럭 배송 경로(Load)를 짜는 단계. ("배차/Tender"는 별도 상태값이 아니라 LOAD_CREATION의 보조/대체값)
- **TENDER DATE**: 배송을 위해 차량을 호출(요청)한 날짜.
- **WH RELEASE(창고 릴리즈)**: 창고에서 실제로 물건을 꺼내는 단계.
- **SHIPPING CONFIRM / SHIPPED**: 출고 확정 / 출고 완료.
- **IOD**: (추정) Image of Delivery — 배송완료 증빙사진, 온라인 등록.
- **POD(증빙)**: IOD 종이를 실물로 보관해두는 단계. ⚠️ **POD(항구, Port of Discharge)와 이름만 같은 별개 개념** — 문맥으로 구분.
- 이후 **인보이스 발행**(GERP/NERP 방식이 다름 — `docs/batch.SO/01-batch-jobs.md` 6번 항목 참고).

## HOLD 종류

| 종류 | 의미 |
|---|---|
| AR Hold (Finance Hold) | 고객이 아직 안 낸 돈(미수금)이 있어서 걸리는 홀드. `CREDIT_HOLD`/`OVERDUE_HOLD` |
| Back Order Hold | 재고 없음 — `BACK_ORDER_HOLD` |
| Future Hold | 미래 예정 오더 |
| Etc Hold | 위 3개 외 나머지 홀드 |
| SA_HOLD/FORM_HOLD/BANK_COLLATERAL_HOLD/INSURANCE_HOLD | 존재는 하나 `HOLD_TYPE` 산정에는 안 들어감. 정확한 의미는 미확인(추정만 가능) |

**필리핀(LGEPH) 연초 일괄 BACKHOLD — 코드로 확인 불가, 업무관행으로 추정.** ETL 어디에도 `AFFILIATE_CODE='LGEPH'`로 강제 BACKHOLD 처리하는 로직 없음. 필리핀 법인이 실제로 연초에 주문을 몰아 받는 방식으로 운영해서 결과적으로 그렇게 보이는 것으로 추정(확인 안 됨).

## 물류 실무 (업계표준)

| 용어 | 의미 |
|---|---|
| B/L | Bill of Lading (선하증권) |
| POL | Port Of Loading (출발항) |
| POD(항구) | Port Of Discharge (도착항) — 위 POD(증빙)와 다른 개념 |
| CY | Container Yard (컨테이너 야적장) |
| RAD | Request Arrival Date — 고객요청 도착일 |
| Stuffing Date | 컨테이너에 화물을 적입(포장)하는 날짜 |
| ATD / ATA | Actual Time of Departure/Arrival — **실제** 출발/도착시각 |
| ETD / ETA | Estimated Time of Departure/Arrival — **예정** 출발/도착시각 |
| CC (Customs Clearance) | 통관 |
| CC Requested/Declared/Completed | 통관 요청됨 / 신고됨(수입신고) / 완료됨 — 순서대로 진행 |
| CY Arrival / CY Departure | 컨테이너 야적장 도착 / 출발 |
| F Dest (Final Destination) | 최종 목적지(실제 도착지, 보통 법인 창고) |

## PO(인바운드) 진행 단계

```
On factory Processing → Factory Ship Out → Intransit (POL~POD) → Intransit (POD~FDEST) → F Dest Arrival
```
세부 통관상태(더 정밀한 워터폴):
```
PO_STATUS(원본) → CY Arrival → Customs Requested → Customs Declared → Customs Cleared → CY Departure → Final Destination
```

**리드타임 벤치마크 — SO와 PO 배치가 같은 설계 패턴을 공유함.** `docs/batch.SO`의 `D_SO_REM_DAYS`(`EST_ARRIVAL_DATE`)와 `docs/batch.0800`의 `M_PO_TRACKING`(`EST_FDEST_ARRIVAL_DATE`) 둘 다 **"과거 완료건의 평균 소요일수를 계산해서 현재 단계에 더해 도착예정일을 추정"**하는 동일한 방식. SO는 법인+거래처 단위, PO는 출발지+도착지+법인 단위로 벤치마크를 뽑는다는 차이만 있음.

## ID/NO 체계 — 헷갈리지 말 것 (실측 확인)

| 컬럼 | 정체 | 예시 |
|---|---|---|
| `ORDER_HEADER_ID` | 오더 헤더의 Oracle 내부 대리키. **오더번호 아님** | `1952057041` |
| `ORDER_LINE_ID` | 오더 라인의 Oracle 내부 대리키. 시스템 전역 일련번호(오더 전용 아님, 번호에 구멍 생김) | `3010650268` |
| `SALES_ORDER_NO` | 사람이 보는 진짜 오더번호 | `1003789349` |
| `SALES_ORDER_LINE_NO` | 사람이 보는 라인번호, GERP는 `N.M` 점표기 | `1.1`, `2.1` |
| `SOURCE_HEADER_ID`/`SOURCE_LINE_ID` (TMS쪽) | `ORDER_HEADER_ID`/`ORDER_LINE_ID`와 완전히 같은 값 (TMS 입장에서 "원천시스템 ID"란 뜻으로 개명한 것뿐) | — |

`SALES_ORDER_LINE_NO`의 `.M`이 정확히 "배송분할번호"인지는 근거컬럼 접근 불가로 **미확인** (Oracle 통상관례상 그럴 가능성은 높음).

## NERP(SAP) 수량 컬럼 — 워터폴 계산

SAP는 GERP처럼 상태값 하나가 아니라 **누적수량**을 단계별로 갖고 있어서 빼서 계산해야 함.

| 원본 누적수량 | 의미 |
|---|---|
| `ORDER_QTY` | 주문수량 (`ZREQ_QTY`) |
| `LE_QTY` | 피킹확정수량 (`ZSDDELQTY`) |
| `SHIP_QTY` | 출고수량 (`ZSHSPQTY`) |
| `POD_QTY` | 도착(수령확인)수량 (`ZPODQTY`) |

| 계산되는 값 | 계산식 | 의미 |
|---|---|---|
| `PICK_QTY` | `LE_QTY - SHIP_QTY` | 피킹확정 됐지만 아직 출고 안 한 양 |
| `DELY_QTY` | `SHIP_QTY - POD_QTY` | 출고는 했는데 아직 도착확인 안 된 양(운송중, 세부위치는 이 컬럼만으론 모름) |
| `OPEN_QTY` | (조건부) `ORDER_QTY - (LE_QTY-SHIP_QTY)` | 아직 피킹도 안 시작한 나머지 |

GERP는 이 계산이 없고 `ACTIVE_QTY = ORDER_QTY` 단순 대입.

## DIM 구분 — 미확인

| 용어 | 상태 |
|---|---|
| AU | **미확인** — 의미 확인되면 채워넣기 |
