"""
jobs/utils/bigquery.py — BigQuery Client (독립 실행용)

인증 파일(GOOGLE_APPLICATION_CREDENTIALS)은 jobs 폴더 기준 상대경로로 해석됩니다.
예) .env.prd 에 GOOGLE_APPLICATION_CREDENTIALS=./svcac-....json 로 지정 후
    해당 json 파일을 jobs 폴더에 함께 두면 됩니다.
"""
import os
from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd

from utils.config import getenv


class BigQueryClient:
    """BigQuery Client Singleton"""

    _instance = None
    _client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BigQueryClient, cls).__new__(cls)
        return cls._instance

    def get_client(self):
        """Get BigQuery client"""
        if self._client is None:
            self._client = self._initialize_client()
        return self._client

    def _initialize_client(self):
        """Initialize BigQuery client"""
        # 1. Try credentials file from environment variable or relative path
        credentials_path = getenv('GOOGLE_APPLICATION_CREDENTIALS', './svcac-if-gmc-birpt.pjt-lge-oversea-sales-olap.json')

        # Convert relative path to absolute path (jobs 폴더 기준)
        if not os.path.isabs(credentials_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            credentials_path = os.path.join(project_root, credentials_path)

        if os.path.exists(credentials_path):
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
                return bigquery.Client(credentials=credentials)
            except Exception as e:
                print(f"Failed to initialize BigQuery client with credentials file: {str(e)}")
        else:
            print(f"Credentials file not found: {credentials_path}")

        # 2. Try default credentials (gcloud auth)
        try:
            return bigquery.Client()
        except Exception as e:
            print(f"BigQuery authentication failed: {str(e)}")
            return None


def get_bigquery_client():
    """Get cached BigQuery client"""
    bq = BigQueryClient()
    return bq.get_client()


def run_query(query: str, params: dict = None):
    """
    Execute BigQuery query

    Args:
        query: SQL query string
        params: Query parameters dictionary

    Returns:
        pandas.DataFrame or None
    """
    client = get_bigquery_client()
    if client is None:
        print("BigQuery client is not initialized")
        return None

    try:
        # Configure query parameters
        job_config = bigquery.QueryJobConfig()
        if params:
            query_parameters = []
            for key, value in params.items():
                if isinstance(value, (list, tuple)):
                    # 배열 파라미터 (IN UNNEST(@key) 용)
                    sample = value[0] if len(value) else ''
                    if isinstance(sample, bool):
                        elem_type = "BOOL"
                    elif isinstance(sample, int):
                        elem_type = "INT64"
                    elif isinstance(sample, float):
                        elem_type = "FLOAT64"
                    else:
                        elem_type = "STRING"
                        value = [str(v) for v in value]
                    query_parameters.append(
                        bigquery.ArrayQueryParameter(key, elem_type, list(value))
                    )
                    continue
                if isinstance(value, str):
                    param_type = "STRING"
                elif isinstance(value, int):
                    param_type = "INT64"
                elif isinstance(value, float):
                    param_type = "FLOAT64"
                else:
                    param_type = "STRING"
                    value = str(value)

                query_parameters.append(
                    bigquery.ScalarQueryParameter(key, param_type, value)
                )
            job_config.query_parameters = query_parameters

        # Execute query
        df = client.query(query, job_config=job_config).to_dataframe()
        return df

    except Exception as e:
        # 쿼리 실패는 상위(run)로 전파하여 잡을 실패 처리한다.
        # (None을 반환하면 run()이 '데이터 없음'으로 오인해 정상 종료됨)
        print(f"Query execution error: {str(e)}")
        print(f"Query: {query}")
        raise


def test_connection():
    """Test BigQuery connection"""
    client = get_bigquery_client()
    if client is None:
        return False

    try:
        query = "SELECT 1 as test"
        result = client.query(query).to_dataframe()
        return len(result) == 1
    except Exception as e:
        print(f"Connection test failed: {str(e)}")
        return False
