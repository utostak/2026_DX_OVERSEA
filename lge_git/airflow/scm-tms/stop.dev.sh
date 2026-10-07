#!/bin/bash
# Dashboard Flask Application - Linux Stop Script (Gunicorn)

PID_FILE="liw_dev.pid"

echo "Stopping LIW (Gunicorn)..."

ps aux | grep liw_dev | grep -v grep | awk '{print $2}' | xargs -r kill -9