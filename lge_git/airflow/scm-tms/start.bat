@echo off
rem ── 개발 서버 시작 (.env.dev 로드 / FLASK_DEBUG=true / PORT 9004)
set APP_ENV=dev
py -3.11 app.py
pause