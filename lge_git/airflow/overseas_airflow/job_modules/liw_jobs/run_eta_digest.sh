#!/bin/bash
# jobs/run_eta_digest.sh
# ─────────────────────────────────────────────────────────────
# 해상배송 ETA 변경 다이제스트 메일 발송 (cron 용 래퍼)
# 매일 아침 09:00 (Asia/Seoul) 실행 대상.

set -e

# jobs 폴더 (이 스크립트가 있는 디렉토리)
JOB_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$JOB_DIR"

# 운영 환경 (.env.prd 로드)
export APP_ENV="prd"

# 가상환경 활성화 (환경에 맞게 경로 수정)
# . /home/oss_admin/.venv/bin/activate

mkdir -p "$JOB_DIR/logs"

# 실행 (jobs 폴더 안에서 직접 실행)
python eta_digest_email.py >> "$JOB_DIR/logs/eta_digest.log" 2>&1
