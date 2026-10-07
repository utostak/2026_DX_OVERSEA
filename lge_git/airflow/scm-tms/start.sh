#!/bin/bash
# Dashboard Flask Application - Linux Start Script (Gunicorn)
# 실행: bash start.sh  (sh 는 source / BASH_SOURCE 미지원으로 사용 불가)

PID_FILE="liw_prd.pid"
LOG_DIR="logs"

# ── 환경 선택 (기본: production 고정)
export APP_ENV="prd"
echo "Starting LIW (Gunicorn) [$APP_ENV]..."

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "LIW is already running (PID: $(cat "$PID_FILE"))."
    exit 1
fi

# Activate virtual environment
. /home/oss_admin/.venv/bin/activate

# Set BigQuery credentials path
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export GOOGLE_APPLICATION_CREDENTIALS="$SCRIPT_DIR/.streamlit/svcac-if-gmc-birpt.pjt-lge-oversea-sales-olap.json"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Start Gunicorn in background
gunicorn -c gunicorn_config.py app:app \
    --pid "$PID_FILE" \
    --daemon

# PID 파일 생성 대기 (preload_app=True 로 앱 로딩 후 fork → PID 기록까지 수 초 소요)
_timeout=20
_elapsed=0
while [ ! -f "$PID_FILE" ] && [ "$_elapsed" -lt "$_timeout" ]; do
    sleep 1
    _elapsed=$((_elapsed + 1))
done

if [ -f "$PID_FILE" ]; then
    echo "LIW started (PID: $(cat "$PID_FILE")). Port: 9003"
else
    echo "⚠️  LIW started but PID file not found after ${_timeout}s. Check logs/gunicorn.log"
fi


