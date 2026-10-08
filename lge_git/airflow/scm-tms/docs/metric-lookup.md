# 화면 내 지표별 소스테이블 정리

> 화면 카드/그리드 하나하나가 정확히 어느 테이블·어느 계산식에서 나오는지 정리. **다른 문서 안 열어봐도 되게 필요한 내용은 다 인라인으로 적어둠.**
> **테이블명 표기 규칙**: 각 섹션에서 처음 나올 때만 `프로젝트.데이터셋.테이블명` 풀네임(복붙용), 그 이후는 테이블명만 짧게(예: `M_SO_LINE`). 전부 별다른 표기 없으면 `pjt-lge-oversea-sales-olap.SCM_OLAP` 소속.

---

## Active Orders 화면 — 실제 화면 순서(위→아래)

```
1. Delivery Stage  (IOD 차트: Actual / Safe / Achievable / Unachievable / Target)
2. Shipping Stage  (카드 5개: Pick Released / Load Creation / W/H Release / Ship Confirm / Shipped)
3. Order Stage     (카드 3개: Booked / Hold / Hold Released)
   └ Hold Detail   (Order Stage 바로 아래, 접이식)
4. Inbound Stage (Back Order)  (From Stock 등 6개 티어)
5. 맨 밑 Raw 그리드 + IOD 탭
```

### 1. Delivery Stage — IOD 차트 (Actual / Safe / Achievable / Unachievable / Target)

⚠️ 이 5개는 독립 카드가 아니라 **"Delivery Stage" 아래 누적 막대그래프 하나**를 이루는 구성요소입니다. Safe/Achievable/Unachievable은 **아래 2번·3번 카드들의 값을 그대로 합산**한 것 — 즉 이 차트가 2번+3번의 요약본입니다.

| 구성요소 | 계산 |
|---|---|
| **Actual**(초록, Invoiced) | 당월 `SALES_DATE` 기준 `M_SO_LINE.SALES_AMOUNT * 환율`(GERP) + `M_SO_LINE_INVOICE_NERP.SALES_AMOUNT * 환율`(NERP) 합산 |
| **Target**(파란 선) | `REF_D_SALES_TARGET_MST.TARGET_AMOUNT` (해당 법인·월), 월말 환율로 환산. **입력이 안 되어 있으면 0** — 배치 문제 아니라 마스터데이터 미입력 여부부터 확인 |
| **Safe**(노랑) | 2번 Shipping Stage 카드 5개의 achievable_amt 합 |
| **Achievable**(주황) | 3번 Order Stage 카드 3개의 achievable_amt 합 |
| **Unachievable**(빨강) | 2번+3번 카드들의 unachievable_amt 합 |

**"Achievable이 이상하다" = "3번 Order Stage 카드들의 도착예정 판정이 이상하다"는 뜻** → 3번 섹션 확인.

---

### 2. Shipping Stage — 카드 5개 (Pick Released / Load Creation / W/H Release / Ship Confirm / Shipped)

- **원본 테이블**: `pjt-lge-oversea-sales-olap.SCM_OLAP.M_SO_LINE` — 이 표의 모든 컬럼(`APPOINTMENT_TO_DATE`, `TMS_APPOINTMENT_TO_DATE`, `EST_ARRIVAL_DATE`, `PROGESS_STATUS`, `SALES_AMOUNT` 등)은 **전부 이 한 테이블(`M_SO_LINE`) 안에 있는 컬럼입니다.**
- **계산식**:
  ```
  base_achievable_date = COALESCE(APPOINTMENT_TO_DATE, TMS_APPOINTMENT_TO_DATE, EST_ARRIVAL_DATE)
  Safe(=achievable_amt)   = SUM(SALES_AMOUNT) WHERE base_achievable_date <= 당월 말일(D-1 기준)
  Unsafe(=unachievable_amt) = SUM(SALES_AMOUNT) WHERE base_achievable_date IS NULL 또는 당월 초과
  SALES_AMOUNT = COALESCE(ACTIVE_AMOUNT * 환율, USD_ORDER_AMOUNT)
  ```
- **카드 하나(예: Shipped)에 잡히는 대상**: `M_SO_LINE.PROGESS_STATUS = 'SHIPPED'`인 라인들. (`OPEN_FLAG='Y'`, `PROGESS_STATUS NOT IN ('ENTERED','CLOSED')`)

**Safe/Unsafe 값이 이상할 때 원인 3가지(전부 `M_SO_LINE` 컬럼 값 자체의 문제)**:

1. **`APPOINTMENT_TO_DATE`/`TMS_APPOINTMENT_TO_DATE`/`EST_ARRIVAL_DATE` 3개 다 NULL** → 무조건 Unsafe로 빠짐.
2. **`EST_ARRIVAL_DATE`가 이상함**: 이 값은 배치가 채워넣는 "예상 도착일"인데, 계산 방식이 **"이 법인·거래처의 과거 완료건들이 평균 며칠 걸렸는지" 벤치마크값 + 오늘 날짜**입니다. 이 평균값 자체가 `D_SO_REM_DAYS`라는 별도 테이블(법인+거래처별 과거 완료건 평균 소요일 통계)에 미리 계산되어 있고, `M_SO_LINE`을 만드는 배치가 그 값을 가져다 씀. → 평균이 이상하면 그 법인의 과거 데이터 자체가 적거나 튀는 값(예: 옛날에 한 번 엄청 오래 걸린 주문)이 평균을 왜곡했을 가능성.
3. **`TMS_APPOINTMENT_TO_DATE`가 안 채워짐**: 이 컬럼은 TMS(물류실행 시스템)에서 오는 값인데, **"같은 배송(트럭/컨테이너)에 실린 다른 라인 중 하나라도 날짜가 비어있으면, 그 배송 전체를 통째로 NULL 처리"**하는 방어로직이 있습니다. 즉 내 라인은 멀쩡해도 같이 실린 다른 라인 데이터가 안 들어와서 내 것까지 NULL이 될 수 있음.
4. **애초에 그 라인이 이 카드(예: Shipped)에 안 잡힘**: `PROGESS_STATUS` 자체가 잘못 판정된 경우. GERP 법인은 "TMS 쪽 배송완료일 우선, 없으면 자체(ERP) 출고일로 대체" 순서로 판정하고, NERP(SAP) 법인은 **TMS 안 보고 ERP(SAP) 쪽 날짜로만 판정**합니다 — 그래서 NERP 법인은 TMS 쪽 배송 데이터가 아무리 이상해도 Shipped 판정 자체엔 영향 없음(반대로 ERP 쪽 날짜가 이상하면 바로 영향받음).

---

### 3. Order Stage — 카드 3개 (Booked / Hold / Hold Released)

- 2번(Shipping Stage)과 **완전히 같은 테이블(`M_SO_LINE`)·같은 계산식**을 씁니다. 대상 상태만 `PROGESS_STATUS IN ('BOOKED','HOLD','PICK_READY')`로 바뀌고, 카드 라벨이 Safe/Unsafe 대신 **Achievable/Unachievable**로 표시될 뿐 로직은 동일합니다.
- **이상할 때 확인할 것도 2번과 완전히 동일**(위 1~4번 그대로 적용).

#### Hold Detail (Order Stage 바로 아래, 접이식) — AR / Back Order / Future / Etc

- **원본 테이블**: `M_SO_LINE` — `BACK_ORDER_HOLD`, `AR_HOLD`(=`CREDIT_HOLD` 또는 `OVERDUE_HOLD`가 Y), `FUTURE_HOLD`, `ETC_HOLD` 플래그별 집계. 필터: `HOLD_FLAG='Y'` AND `PROGESS_STATUS='HOLD'`
- **홀드 종류 판정 우선순위** (이 순서대로 하나만 걸림):
  ```
  1순위: CREDIT_HOLD='Y' 또는 OVERDUE_HOLD='Y'  → AR(Finance Hold)
  2순위: FUTURE_HOLD='Y'                         → Future
  3순위: BACK_ORDER_HOLD='Y'                     → Back Order
  4순위: 그 외 HOLD_FLAG='Y'인 나머지            → Etc
  ```
- **값이 이상할 때**: 어떤 라인이 "Etc"로 잘못 잡힌다면, 위 순서상 CREDIT/OVERDUE/FUTURE/BACK_ORDER 플래그가 전부 'N'인데 `HOLD_FLAG`만 'Y'인 경우 — 그 4개 플래그 자체를 `M_SO_LINE`에서 직접 조회해서 확인.

---

### 4. Inbound Stage (Back Order) — From Stock / POD→FDEST / POL→POD / Ship Out / On Factory / PO Required

- **원본 테이블**: `pjt-lge-oversea-sales-olap.SCM_OLAP.M_SO_LINE_BACK` (`M_SO_LINE`과는 **다른 테이블**입니다 — 백오더 전용으로 별도 배치가 만듦)
- **계산 방식 — 모델 단위 워터폴**: 그 법인·모델의 백오더 총수량(`MBACK`)에서, 공급처를 가까운 순서대로 하나씩 빼가면서 각 티어 수량을 정함:
  ```
  From Stock  = LEAST(MBACK, 재고수량)
  POD→FDEST   = LEAST(GREATEST(MBACK - 재고수량, 0), POD→FDEST 단계 PO수량)
  POL→POD     = LEAST(GREATEST(MBACK - 재고수량 - POD→FDEST수량, 0), POL→POD 단계 PO수량)
  Ship Out    = (같은 방식으로 순서대로 차감)
  On Factory  = (같은 방식으로 순서대로 차감)
  PO Required = 위 5개를 다 빼고 남은 나머지 (= 아직 공급처가 없는 부족분)
  ```
- **From Stock의 "재고수량" 원본**: `M_CURINV_SNAPSHOT_S` 테이블의 `AVAILABLE_QTY`. (필리핀 법인만 예외 — `SUBINVENTORY_CODE='5000'`인 재고만 가용재고로 인정, 다른 법인은 전체 인정)
- **PO단계별("POD→FDEST"~"On Factory") 수량 원본**: `M_PO_TRACKING` 테이블의 `PO_STATUS`별 `QTY` 합계 (`PO_STATUS` 판정 방식은 아래 Active PO 섹션과 동일)

**From Stock 값이 안 맞을 때**: `M_CURINV_SNAPSHOT_S`에서 그 법인+모델의 `AVAILABLE_QTY`를 직접 조회해서 대조. 필리핀이면 `SUBINVENTORY_CODE='5000'` 조건도 같이 걸어서 확인.
**PO단계 티어 값이 안 맞을 때**: 아래 Active PO 섹션의 "POL→POD 카드" 확인 순서와 동일한 원인(F Dest Arrival 오버라이드 등)일 수 있음.

### 5. 맨 밑 Raw 그리드 / IOD 탭

- **Raw 그리드**(전체 라인 리스트): **설명을 따로 안 넣은 게 맞습니다** — 이건 계산된 지표가 아니라 `M_SO_LINE`을 필터 조건 그대로 SELECT * 해서 보여주는 화면입니다. 컬럼 하나하나가 전부 `M_SO_LINE`의 원본 컬럼이라, 특정 값이 이상하면 그냥 그 컬럼명으로 `M_SO_LINE`을 직접 조회하면 됩니다(예: `WAREHOUSE_CODE`가 이상하면 `M_SO_LINE`에서 `WAREHOUSE_CODE` 그대로 확인).
- **IOD 탭**(인보이스/송장): GERP 법인은 `INVOICE_NO`가 항상 NULL(원천에 그 컬럼 자체가 없음 — 버그 아니고 미해결 조사건). NERP 법인은 별도 테이블 `M_SO_LINE_INVOICE_NERP.INVOICE_NO`에서 옴.

---

## Active PO 화면

### 파이프라인 단계 카드 (On Factory / Factory Ship Out / Intransit(POL~POD) / Intransit(POD~FDEST))

- **원본 테이블**: `pjt-lge-oversea-sales-olap.SCM_OLAP.M_PO_TRACKING`
- **계산식**: `TRIM(PO_STATUS)`로 그룹핑, 카드별 `line_cnt`(건수)/`bl_cnt`(BL수)/`invoice_cnt`(인보이스수)/`total_qty`(=`SUM(QTY)`). `PO_STATUS`가 `'Cancelled'` 또는 `'F Dest Arrival'`(완료도착)이면 이 카드들에서 아예 제외.
- **리드타임 벤치마크**(`avg_po_factory_lt` 등): 화면 쿼리가 `PO_STATUS='F Dest Arrival'`인 완료건만 골라 그 자리에서 즉석으로 평균 계산.

**"POL→POD 카드 값이 안 맞아요" 확인 순서**:
1. `M_PO_TRACKING`에서 `TRIM(PO_STATUS) = 'Intransit (POL~POD)'`인 행만 직접 조회해서 화면 값과 일치하는지 먼저 대조.
2. 일치하면 → **`PO_STATUS`가 왜 그 값인지가 진짜 원인**. `M_PO_TRACKING`을 만드는 배치는 원본 `PO_STATUS`를 그대로 쓰다가, **실제 도착일(`FDEST_ATA_DATE`)이 확인되면 무조건 `PO_STATUS`를 `'F Dest Arrival'`로 덮어씁니다.**
   - 실제로는 아직 안 왔는데 도착으로 잘못 덮어써진 경우 → 이미 "F Dest Arrival"로 카드에서 사라진 것 → PO_TRACKING 원본의 `FDEST_ATA_DATE`가 왜 채워졌는지 확인
   - 실제로는 도착했는데 계속 "POL→POD"에 남아있는 경우 → `FDEST_ATA_DATE`가 안 채워진 것. 이 값은 PANTOS(해상운송 컨테이너 추적) 데이터와 `법인+BL번호+컨테이너번호`로 매칭해서 채워지는데, 이 3개 키가 안 맞으면 도착해도 안 잡힘.
3. BigQuery 직접조회 값과 화면 값 자체가 다르면 → 화면 필터(법인/Division) 문제이거나 배치 최신성 문제 → 화면의 "데이터 최신시각" 표시로 배치가 언제 마지막으로 돌았는지 확인.

### Raw 그리드 — ETA 변경 표시(`CHANGE_YN`/`DFF_DAYS`)

- **원본 테이블**: `M_PO_TRACKING` + `pjt-lge-oversea-sales-olap.SCM_OLAP.M_SEA_SHIPMENT_INFO`(최신 파티션만)
- **`M_SEA_SHIPMENT_INFO`란**: 아직 도착 안 한 해상 컨테이너만 매일 다시 뽑아서, **어제 스냅샷과 오늘 스냅샷의 도착예정일(FDEST_ETA_DATE)을 비교**해 "바뀌었는지(`CHANGE_YN`)"/"며칠 밀렸는지(`DFF_DAYS`)"를 계산해두는 별도 테이블. **7일 지나면 그 날짜 데이터는 자동삭제**되므로 일주일 넘은 변경이력은 조회 불가.

**ETA 변경 표시가 안 맞을 때**: `M_SEA_SHIPMENT_INFO`에서 해당 컨테이너의 어제/오늘 값을 직접 대조.

---

## Inventory 화면

### 상단 카드 4개 (Snapshot Date / Models / Onhand Qty / Available Qty)

- **원본 테이블**: `pjt-lge-oversea-sales-olap.SCM_OLAP.M_CURINV_SNAPSHOT_S`
- **계산식**: Snapshot Date=`ANY_VALUE(P_PTT)`, Models=`COUNT(DISTINCT MODEL_CODE)`, Onhand Qty=`SUM(ONHAND_QTY)`, Available Qty=`SUM(AVAILABLE_QTY)`

**값이 이상할 때**:
- 이 테이블은 GERP 법인 재고와 NERP 법인 재고를 하나로 합쳐서 만드는데, **법인마다 GERP 소스를 볼지 NERP 소스를 볼지는 그 법인의 "NERP 전환일" 기준으로 스위칭**합니다. 전환일 근처 법인이면 과거 이 스위칭 로직에 중복집계 버그가 있었던 적이 있음(현재는 수정됨, 재발 여부 의심).
- 재고 데이터가 법인마다 매일 안 들어올 수 있어서, **"최근 1주일 내 가장 최신 스냅샷"만 채택**하는 로직임 — 화면의 "데이터 최신시각"을 그 법인 기준으로 확인해서 며칠 지난 데이터인지부터 체크.

---

## 아직 이 표에 없는 지표

- Flow/IOD 상세 리포트 모달(팀×거래처별) 세부 컬럼
- Container 상세 모달
- Order(legacy)/Master Data/Issues 등 다른 화면 전체

필요할 때마다 같은 형식(원본테이블 → 계산식 → "이상할 때 확인할 것", 다른 문서 참조 없이 여기서 끝나게)으로 추가.
