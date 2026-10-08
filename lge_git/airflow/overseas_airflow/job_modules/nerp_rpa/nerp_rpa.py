"""Airflow NERP Web Request 운영 Job.

SO Closed=N, SO Closed=Y 월별, IO, CIV를 순차 추출하고 SCM_OLAP 운영 테이블에 적재한다.
각 WebGUI 세션은 web_extract.py에서 CANCEL2로 종료 및 검증된다.
XLSX는 시스템 임시 폴더에 생성하며 BQ 적재 후 자동 삭제된다.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR_ZIP = BASE_DIR / "vendor.zip"
if VENDOR_ZIP.exists():
    sys.path.insert(0, str(VENDOR_ZIP))
sys.path.insert(0, str(BASE_DIR))

import load_to_bq
import web_extract
import web_login

CHAINS_DIR = BASE_DIR / "chains"
START_DATE_CLOSED_Y = dt.date(2025, 11, 1)
DATASET = "SCM_OLAP"
TABLES = {
    "so": "M_NERP_SALES_ORDER_INQUIRY",
    "io": "M_NERP_INVOICED_ORDER_INQUIRY",
    "civ": "M_NERP_CURRENT_INVENTORY",
}
CONST_COLS = {
    "civ": {
        "SUBSDR_CD": "EACM",
        "SUBSDR_NM": "LGEPH",
    }
}


def add_months(value, months):
    index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(index, 12)
    return dt.date(year, month_zero + 1, 1)


def month_intervals(start_date, end_date):
    intervals = []
    current = start_date
    while current <= end_date:
        next_month = add_months(current, 1)
        finish = min(next_month - dt.timedelta(days=1), end_date)
        intervals.append((current, finish))
        current = finish + dt.timedelta(days=1)
    return intervals


def sap_date(value):
    return value.strftime("%Y.%m.%d")


def replace_content(node, suffix, value):
    changed = 0
    if isinstance(node, dict):
        post_name = node.get("post")
        if (
            isinstance(post_name, str)
            and post_name.endswith(suffix)
            and "content" in node
        ):
            node["content"] = value
            changed += 1
        for child in node.values():
            changed += replace_content(child, suffix, value)
    elif isinstance(node, list):
        for child in node:
            changed += replace_content(child, suffix, value)
    return changed


def build_so_chain(source_steps, closed, start_date=None, end_date=None):
    steps = copy.deepcopy(source_steps)
    counts = {
        "closed": 0,
        "low": 0,
        "high": 0,
        "high_inserted": 0,
    }
    parsed = []

    for step in steps:
        raw = step.get("post", "")
        if not raw or not raw.lstrip().startswith("["):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        counts["closed"] += replace_content(
            payload,
            "/usr/cmbP_CLOSE",
            closed,
        )
        if start_date is not None:
            counts["low"] += replace_content(
                payload,
                "/usr/ctxtS_AUDATE-LOW",
                sap_date(start_date),
            )
        if end_date is not None:
            counts["high"] += replace_content(
                payload,
                "/usr/ctxtS_AUDATE-HIGH",
                sap_date(end_date),
            )
        parsed.append((step, payload))

    if end_date is not None and counts["high"] == 0:
        for _, payload in parsed:
            execute_index = next(
                (
                    index
                    for index, item in enumerate(payload)
                    if isinstance(item, dict)
                    and isinstance(item.get("post"), str)
                    and "/tbar[1]/btn[8]" in item["post"]
                ),
                None,
            )
            if execute_index is None:
                continue

            payload[execute_index:execute_index] = [
                {
                    "content": sap_date(end_date),
                    "post": "value/wnd[0]/usr/ctxtS_AUDATE-HIGH",
                },
                {
                    "post": "action/304/wnd[0]/usr/ctxtS_AUDATE-HIGH",
                    "content": "position=10",
                    "logic": "ignore",
                },
                {
                    "post": "focus/wnd[0]/usr/ctxtS_AUDATE-HIGH",
                    "logic": "ignore",
                },
            ]
            counts["high"] = 1
            counts["high_inserted"] = 1
            break

    for step, payload in parsed:
        step["post"] = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    required = ["closed"]
    if start_date is not None:
        required.append("low")
    if end_date is not None:
        required.append("high")

    missing = [name for name in required if counts[name] == 0]
    if missing:
        raise RuntimeError(
            "SO 체인 조건 반영 실패: " + ", ".join(missing)
        )
    return steps, counts


def extract_steps(session, key, steps):
    original_chains = web_extract.CHAINS
    with tempfile.TemporaryDirectory(prefix="nerp_airflow_chain_") as temp_dir:
        temporary_chains = Path(temp_dir)
        (temporary_chains / f"chain_full_{key}.json").write_text(
            json.dumps(steps, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        try:
            web_extract.CHAINS = temporary_chains
            return web_extract.extract(session, key)
        finally:
            web_extract.CHAINS = original_chains


def process_task(
    session,
    key,
    name,
    file_label,
    steps,
    batch_dt,
    chain_counts=None,
):
    started = time.perf_counter()
    print(f"\n===== {name} =====")
    if chain_counts is not None:
        print(f"[체인 치환] {chain_counts}")

    extract_started = time.perf_counter()
    data = extract_steps(session, key, steps)
    extract_seconds = time.perf_counter() - extract_started

    if data is None:
        print(f"[NO DATA] {name}")
        total_seconds = time.perf_counter() - started

        return {
            "name": name,
            "rows": 0,
            "extract": extract_seconds,
            "bq": 0.0,
            "total": total_seconds,
            "no_data": True,
        }
    

    # XLSX는 시스템 임시 폴더에만 생성한다.
    # BQ 적재 성공, 실패, 예외 여부와 관계없이 with 종료 시 자동 삭제된다.
    with tempfile.TemporaryDirectory(prefix=f"nerp_{key}_xlsx_") as temp_dir:
        xlsx_path = Path(temp_dir) / f"web_{file_label}.xlsx"
        xlsx_path.write_bytes(data)
        print(
            f"[임시 XLSX] {xlsx_path.name} "
            f"/ {xlsx_path.stat().st_size:,}B"
        )

        load_started = time.perf_counter()
        rows = load_to_bq.load(
            xlsx_path,
            if_exists="append",
            table=TABLES[key],
            dataset=DATASET,
            typed=True,
            batch_dt=batch_dt,
            const_cols=CONST_COLS.get(key),
        )
        load_seconds = time.perf_counter() - load_started

    print(f"[임시 XLSX 정리] {file_label} 자동 삭제 완료")
    total_seconds = time.perf_counter() - started
    print(
        f"[완료] {name}: {rows:,}행 "
        f"/ 추출+종료={extract_seconds:.1f}초 "
        f"/ BQ={load_seconds:.1f}초 "
        f"/ 전체={total_seconds:.1f}초"
    )
    return {
        "name": name,
        "rows": rows,
        "extract": extract_seconds,
        "bq": load_seconds,
        "total": total_seconds,
    }


def main(params=None, context=None):
    del params, context

    for key in ("so", "io", "civ"):
        chain_path = CHAINS_DIR / f"chain_full_{key}.json"
        if not chain_path.exists():
            raise FileNotFoundError(f"체인 파일 없음: {chain_path}")

    source_so = json.loads(
        (CHAINS_DIR / "chain_full_so.json").read_text(encoding="utf-8")
    )
    source_io = json.loads(
        (CHAINS_DIR / "chain_full_io.json").read_text(encoding="utf-8")
    )
    source_civ = json.loads(
        (CHAINS_DIR / "chain_full_civ.json").read_text(encoding="utf-8")
    )

    now = dt.datetime.now()
    batch_dt = now.replace(
        minute=(now.minute // 15) * 15,
        second=0,
        microsecond=0,
    )
    batch_started = time.perf_counter()
    successes = []
    failures = []
    session = web_login.login()

    try:
        try:
            steps, counts = build_so_chain(source_so, "N")
            successes.append(
                process_task(
                    session,
                    "so",
                    "SO Closed=N",
                    "so_closed_n",
                    steps,
                    batch_dt,
                    counts,
                )
            )
        except Exception as exc:
            failures.append(
                f"SO Closed=N: {type(exc).__name__}: {exc}"
            )
            print(f"[실패] {failures[-1]}")

        for start_date, end_date in month_intervals(
            START_DATE_CLOSED_Y,
            dt.date.today(),
        ):
            name = f"SO Closed=Y {start_date}~{end_date}"
            label = (
                f"so_closed_y_{start_date:%Y%m%d}_{end_date:%Y%m%d}"
            )
            try:
                steps, counts = build_so_chain(
                    source_so,
                    "Y",
                    start_date,
                    end_date,
                )
                successes.append(
                    process_task(
                        session,
                        "so",
                        name,
                        label,
                        steps,
                        batch_dt,
                        counts,
                    )
                )
            except Exception as exc:
                failures.append(
                    f"{name}: {type(exc).__name__}: {exc}"
                )
                print(f"[실패] {failures[-1]}")

        for key, name, steps in (
            ("io", "IO", source_io),
            ("civ", "CIV", source_civ),
        ):
            try:
                successes.append(
                    process_task(
                        session,
                        key,
                        name,
                        key,
                        steps,
                        batch_dt,
                    )
                )
            except Exception as exc:
                failures.append(
                    f"{name}: {type(exc).__name__}: {exc}"
                )
                print(f"[실패] {failures[-1]}")
    finally:
        session.close()
        print("[정리] requests.Session.close() 완료")

    total_seconds = time.perf_counter() - batch_started
    total_rows = sum(item["rows"] for item in successes)

    print("\n========== NERP Airflow 결과 ==========")
    for item in successes:
        if item.get("no_data"):
            print(
                f"- {item['name']}: NO DATA "
                f"/ 전체={item['total']:.1f}초"
            )
        else:
            print(
                f"- {item['name']}: {item['rows']:,}행 "
                f"/ 전체={item['total']:.1f}초"
            )
    print(
        f"성공={len(successes)} / 실패={len(failures)} "
        f"/ 총 행수={total_rows:,}"
    )
    print(
        f"전체={total_seconds:.1f}초 "
        f"({total_seconds / 60:.2f}분)"
    )

    if failures:
        raise RuntimeError(
            "NERP Airflow 작업 실패 | " + " | ".join(failures)
        )

    return {
        "success": len(successes),
        "rows": total_rows,
        "seconds": round(total_seconds, 1),
    }


def run(
    params: dict = None,
    sql_text: str = "",
    context: dict = None,
):
    del sql_text
    result = main(params=params, context=context)
    return f"NERP RPA 처리 완료: {result}"


if __name__ == "__main__":
    main()
