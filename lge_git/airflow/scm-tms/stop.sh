#!/bin/bash
# Dashboard Flask Application - Linux Stop Script (Gunicorn)

PID_FILE="liw_prd.pid"

echo "Stopping LIW (Gunicorn)..."

ps aux | grep liw_prd | grep -v grep | awk '{print $2}' | xargs -r kill -9