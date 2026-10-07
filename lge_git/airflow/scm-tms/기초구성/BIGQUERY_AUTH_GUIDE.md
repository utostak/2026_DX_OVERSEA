# TMS Dashboard - BigQuery 인증 설정 가이드

## 1. BigQuery 인증 방법

### 방법 1: Streamlit Secrets (권장)

1. `.streamlit/secrets.toml` 파일 생성:

```toml
# .streamlit/secrets.toml
[gcp_service_account]
type = "service_account"
project_id = "pjt-lge-edl-ob"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
client_email = "YOUR_SERVICE_ACCOUNT_EMAIL"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CERT_URL"
```

2. `.gitignore`에 추가:
```
.streamlit/secrets.toml
```

### 방법 2: 환경 변수

1. 서비스 계정 JSON 키 파일 다운로드
2. 환경 변수 설정:

**Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account-key.json"
```

**Windows (영구 설정):**
```powershell
[System.Environment]::SetEnvironmentVariable("GOOGLE_APPLICATION_CREDENTIALS", "C:\path\to\service-account-key.json", "User")
```

**Linux/Mac:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### 방법 3: gcloud CLI

```bash
gcloud auth application-default login
```

## 2. 필요한 BigQuery 권한

서비스 계정에 다음 IAM 역할 부여:
- `BigQuery Data Viewer` (bigquery.dataViewer)
- `BigQuery Job User` (bigquery.jobUser)

## 3. 테스트

```python
from config.bigquery import test_connection

if test_connection():
    print("✅ BigQuery 연결 성공!")
else:
    print("❌ BigQuery 연결 실패")
```

## 4. 환경 변수 설정 (.env 파일)

```env
# .env
GOOGLE_APPLICATION_CREDENTIALS=./credentials/service-account-key.json
PROJECT_ID=pjt-lge-edl-ob
DATASET_ID=OB_00030
```

`.env` 파일도 `.gitignore`에 추가하세요.
