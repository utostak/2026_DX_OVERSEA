#!/bin/bash
# Dashboard Flask Application - Linux Start Script (Development)
# 실행: bash start.dev.sh

PID_FILE="liw_dev.pid"
LOG_DIR="logs"

export APP_ENV="dev"
echo "Starting LIW (Development / Flask) [$APP_ENV]..."

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

# Run Flask dev server in background and save PID
python3 app.py --pid "$PID_FILE" >> "$LOG_DIR/app.log" 2>&1 &
echo $! > "$PID_FILE"
echo "LIW (dev) started (PID: $(cat "$PID_FILE")). Port: 9004"
