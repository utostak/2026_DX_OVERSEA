# TMS Dashboard - 실행 가이드

## 🚀 빠른 시작

### 1. 환경 설정

```powershell
# Python 가상환경 생성
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 2. BigQuery 인증 설정

**방법 A: Streamlit Secrets (권장)**

`.streamlit/secrets.toml` 파일을 생성하고 GCP 서비스 계정 정보 입력:

```toml
[gcp_service_account]
type = "service_account"
project_id = "pjt-lge-edl-ob"
private_key_id = "YOUR_KEY_ID"
private_key = "YOUR_PRIVATE_KEY"
client_email = "YOUR_SERVICE_ACCOUNT@PROJECT.iam.gserviceaccount.com"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CERT_URL"
```

**방법 B: 환경 변수**

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account-key.json"
```

자세한 내용은 `BIGQUERY_AUTH_GUIDE.md` 참조.

### 3. 대시보드 실행

```powershell
streamlit run app.py
```

브라우저에서 자동으로 `http://localhost:8501` 열림.

## 📁 프로젝트 구조

```
scm-tms/
├── app.py                          # 메인 애플리케이션
├── requirements.txt                # Python 의존성
├── config/
│   └── bigquery.py                 # BigQuery 연결 설정
├── queries/
│   └── bigquery_queries.py         # SQL 쿼리 모음
├── .streamlit/
│   └── secrets.toml                # Streamlit Secrets (Git 제외)
├── BIGQUERY_AUTH_GUIDE.md          # BigQuery 인증 가이드
├── RUNNING_GUIDE.md                # 이 파일
└── README.md                       # 프로젝트 소개
```

## 🎯 주요 기능

### 페이지 구성

1. **종합 대시보드**: 전체 KPI 및 주요 지표
2. **Shipment 분석**: 출하 추이, Zone별/창고별 분석
3. **Load 운영**: Load 현황, 운송사별 분석, Shipment 연결
4. **비용 분석**: 운임 변경, Spot Rate 추이
5. **네트워크 분석**: Zone별 운송 네트워크
6. **모델·물량**: 모델별 TOP 분석, 일별 Mix
7. **출고실적**: 창고별 실적, 리드타임 분석

### 전역 필터 (사이드바)

- **기간 설정**: 시작일 ~ 종료일
- **법인**: ALL, LGECL, LGECI, LGEPL, LGEUK
- **운송사**: ALL, DHL, Fedex, Pantos, 기타

## 🔌 BigQuery 연결 테스트

대시보드 사이드바에서 "🔌 BigQuery 연결 테스트" 버튼 클릭.

또는 Python에서 직접 테스트:

```python
from config.bigquery import test_connection

if test_connection():
    print("✅ 연결 성공!")
```

## 📊 데이터 쿼리 실행

```python
from config.bigquery import run_query
from queries.bigquery_queries import QUERY_SHIPMENT_DAILY_TREND

params = {
    'start_date': '2026-01-01',
    'end_date': '2026-04-17',
    'legal_entity': 'LGECL'
}

df = run_query(QUERY_SHIPMENT_DAILY_TREND, params)
print(df.head())
```

## 🛠️ 개발 가이드

### 새로운 쿼리 추가

1. `queries/bigquery_queries.py`에 쿼리 정의:

```python
QUERY_NEW_ANALYSIS = f"""
SELECT ...
FROM `{PROJECT_ID}.{DATASET_ID}.V_L0TMS__TABLE_NAME_OS`
WHERE ...
"""
```

2. `app.py`에서 쿼리 사용:

```python
from queries.bigquery_queries import QUERY_NEW_ANALYSIS
from config.bigquery import run_query

df = run_query(QUERY_NEW_ANALYSIS, params)
```

### 새로운 페이지 추가

1. `app.py`에 페이지 렌더링 함수 추가:

```python
def render_new_page(filters):
    st.markdown('<h1 class="main-header">새 페이지</h1>', unsafe_allow_html=True)
    # 페이지 내용
```

2. `main()` 함수의 `option_menu`에 메뉴 추가:

```python
options=["종합", "Shipment", ..., "새 메뉴"],
icons=["house", "box-seam", ..., "new-icon"],
```

3. 페이지 라우팅 추가:

```python
elif selected == "새 메뉴":
    render_new_page(filters)
```

## 🐛 문제 해결

### 1. BigQuery 인증 실패

- `.streamlit/secrets.toml` 파일 확인
- 서비스 계정 권한 확인 (BigQuery Data Viewer, BigQuery Job User)
- 환경 변수 `GOOGLE_APPLICATION_CREDENTIALS` 경로 확인

### 2. 모듈 import 오류

```powershell
pip install -r requirements.txt --upgrade
```

### 3. Streamlit 실행 오류

```powershell
# 캐시 삭제
streamlit cache clear

# 강제 재실행
streamlit run app.py --server.headless true
```

## 📦 배포

### Docker 배포 (선택사항)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

빌드 및 실행:

```powershell
docker build -t tms-dashboard .
docker run -p 8501:8501 tms-dashboard
```

## 📚 추가 문서

- **BigQuery 인증**: `BIGQUERY_AUTH_GUIDE.md`
- **개발 가이드**: `dashboard_development_guide.md`
- **테이블 정보**: `table_columns.csv`, `table.csv`
- **SQL 스키마**: `schema_DDL.sql`

## 💡 팁

1. **성능 최적화**: BigQuery 쿼리 결과는 자동 캐싱 (기본 10분)
2. **필터 활용**: 날짜 범위를 좁혀서 쿼리 속도 향상
3. **데이터 새로고침**: 브라우저에서 `R` 키 또는 `Ctrl+R`

## 📞 지원

문제 발생 시:
1. `BIGQUERY_AUTH_GUIDE.md` 확인
2. BigQuery 콘솔에서 직접 쿼리 테스트
3. Streamlit 로그 확인 (`터미널 출력`)
