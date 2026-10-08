"""NERP XLSX를 BigQuery 운영 테이블에 append 적재한다."""


from pathlib import Path
import sys
import datetime as dt
import re
import time

BASE_DIR = Path(__file__).resolve().parent
VENDOR_ZIP = BASE_DIR / "vendor.zip"

if VENDOR_ZIP.exists():
    sys.path.insert(0, str(VENDOR_ZIP))

import pandas as pd
from google.api_core.exceptions import NotFound
from google.cloud import bigquery
from google.oauth2 import service_account

KEY_PATH = BASE_DIR / "bq_credential.json"

BQ_PROJECT = "pjt-lge-oversea-sales-olap"
BQ_DATASET = "SCM_OLAP"
BQ_TABLE = "M_NERP_SALES_ORDER_INQUIRY"
DEFAULT_MODE = "append"
PARTITION_EXPIRE_DAYS = 7
INT_KEYS = ("qty", "quantity", "stock", "ordered", "receiving", "mapping", "control", "avail")
FLOAT_KEYS = ("price", "amount", "amt", "rate", "weight", "cbm", "cost", "rrp")
DATETIME_COLS = ("goods_issue_date",)


def classify_type(column):
    name = column.lower()
    if "date" in name:
        return "DATETIME" if name in DATETIME_COLS else "DATE"
    if any(key in name for key in FLOAT_KEYS):
        return "FLOAT64"
    if any(key in name for key in INT_KEYS):
        return "INT64"
    return "STRING"


def _cast_column(series, data_type):
    if data_type == "DATE":
        values = pd.to_datetime(series, errors="coerce")
        return values.dt.date.where(values.notna(), None)
    if data_type == "DATETIME":
        return pd.to_datetime(series, errors="coerce")
    if data_type == "INT64":
        values = pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
        return values.round().astype("Int64")
    if data_type == "FLOAT64":
        return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")
    return series.astype(str).where(pd.notnull(series), "")


def clean_col(name):
    value = re.sub(r"[^0-9A-Za-z_]", "_", str(name))
    value = re.sub(r"_+", "_", value).strip("_") or "col"
    return "_" + value if value[0].isdigit() else value


def clean_columns(columns):
    seen, output = {}, []
    for column in columns:
        cleaned = clean_col(column)
        if cleaned in seen:
            seen[cleaned] += 1
            cleaned = f"{cleaned}_{seen[cleaned]}"
        else:
            seen[cleaned] = 1
        output.append(cleaned)
    return output


def _floor15(value):
    return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)


def load(
    xlsx_path,
    if_exists=DEFAULT_MODE,
    table=BQ_TABLE,
    dataset=BQ_DATASET,
    typed=False,
    type_overrides=None,
    batch_dt=None,
    const_cols=None,
):
    if not KEY_PATH.exists():
        raise FileNotFoundError(f"BQ credential 없음: {KEY_PATH}")

    started = time.time()
    print("  [적재] 엑셀 읽는 중(openpyxl)...", flush=True)
    frame = pd.read_excel(xlsx_path, dtype=str, engine="openpyxl")
    print(f"  [적재] 엑셀 읽음 {frame.shape} ({time.time() - started:.0f}s)", flush=True)

    if len(frame.columns) > 0:
        first = frame.columns[0]
        blank = frame[first].isna() | frame[first].astype(str).str.strip().isin(["", "nan", "None"])
        count = int(blank.sum())
        if count:
            frame = frame[~blank].reset_index(drop=True)
            print(f"  [적재] 합계행 {count}개 제거 -> {frame.shape}", flush=True)

    frame.columns = clean_columns(frame.columns)
    data_columns = list(frame.columns)
    type_overrides = type_overrides or {}
    column_types = {}

    if typed:
        for column in data_columns:
            data_type = type_overrides.get(column) or classify_type(column)
            column_types[column] = data_type
            frame[column] = _cast_column(frame[column], data_type)
        counts = {}
        for data_type in column_types.values():
            counts[data_type] = counts.get(data_type, 0) + 1
        print(f"  [적재] 타입지정 적용: {counts}", flush=True)
    else:
        frame = frame.astype(str).where(pd.notnull(frame), "")
        column_types = {column: "STRING" for column in data_columns}

    const_cols = const_cols or {}
    if const_cols:
        const_frame = pd.DataFrame({name: [value] * len(frame) for name, value in const_cols.items()}, index=frame.index)
        frame = pd.concat([frame.copy(), const_frame], axis=1)
        print(f"  [적재] 상수컬럼 주입: {const_cols}", flush=True)
    else:
        frame = frame.copy()

    batch_dt = _floor15(dt.datetime.now()) if batch_dt is None else batch_dt.replace(second=0, microsecond=0)
    stamp_frame = pd.DataFrame(
        {
            "P_DATE": [batch_dt.date()] * len(frame),
            "P_DATETIME": [pd.Timestamp(batch_dt)] * len(frame),
            "ETL_LOAD_TS": [pd.Timestamp.now(tz="UTC")] * len(frame),
        }, index=frame.index,
    )
    frame = pd.concat([frame, stamp_frame], axis=1)

    schema = [bigquery.SchemaField(column, column_types[column]) for column in data_columns]
    schema += [bigquery.SchemaField(name, "STRING") for name in const_cols]
    schema += [
        bigquery.SchemaField("P_DATE", "DATE"),
        bigquery.SchemaField("P_DATETIME", "DATETIME"),
        bigquery.SchemaField("ETL_LOAD_TS", "TIMESTAMP"),
    ]

    credentials = service_account.Credentials.from_service_account_file(str(KEY_PATH))
    client = bigquery.Client(project=BQ_PROJECT, credentials=credentials)
    table_id = f"{BQ_PROJECT}.{dataset}.{table}"
    disposition = "WRITE_TRUNCATE" if if_exists == "replace" else "WRITE_APPEND"
    config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=disposition,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
    )

    create_table = False
    try:
        existing = client.get_table(table_id)
        names = [field.name for field in existing.schema]
        if "P_DATE" not in names or existing.time_partitioning is None:
            raise RuntimeError(
                f"운영 테이블이 P_DATE 파티션 구조가 아닙니다: {table_id}. 자동 삭제하지 않습니다."
            )
    except NotFound:
        create_table = True

    if create_table:
        config.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="P_DATE",
            expiration_ms=PARTITION_EXPIRE_DAYS * 24 * 60 * 60 * 1000,
        )
        print(f"  [적재] P_DATE 파티션 테이블 신규 생성, expire={PARTITION_EXPIRE_DAYS}일", flush=True)

    print(f"  [적재] BQ {disposition} -> {dataset}.{table} (P_DATE={batch_dt.date()})", flush=True)
    load_started = time.time()
    job = client.load_table_from_dataframe(frame, table_id, job_config=config)
    job.result()
    print(f"  [적재] BQ 완료 ({time.time() - load_started:.0f}s)", flush=True)
    return len(frame)
