"""
mail_util.py — 공통 메일 발송 유틸리티
──────────────────────────────────────────────────────────────────
.env(또는 환경변수)의 SMTP_* 설정을 읽어 smtplib으로 메일을 발송한다.

환경변수 (plugins/.env 또는 시스템 환경변수):
  SMTP_SERVER      SMTP 서버 호스트 (예: lgekrhqmh01.lge.com)
  SMTP_PORT        포트 (기본 25)
  SMTP_USER        인증 계정 (불필요하면 빈 값)
  SMTP_PASSWORD    인증 비밀번호 (불필요하면 빈 값)
  SMTP_FROM        발신자 이메일
  SMTP_DEFAULT_TO  기본 수신자 (쉼표 구분, job에 이메일 미설정 시 폴백)
──────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

_log = logging.getLogger(__name__)

# ── .env 자동 로드 ─────────────────────────────────────────────────
# DAG 파일(batches_dynamic.py)에서 import 하는 경우 이미 로드됐을 수 있으나,
# 독립적으로 import 해도 동작하도록 여기서도 로드 시도.
try:
    from dotenv import load_dotenv as _load_dotenv
    _here = Path(__file__).parent           # utils/
    _root = _here.parent                    # dags/ (Docker) or project root
    for _p in [
        _here / ".env",
        _root / ".env",
        _root / "plugins" / ".env",
        _root.parent / "plugins" / ".env",  # Docker: /opt/airflow/plugins/.env
    ]:
        if _p.exists():
            _load_dotenv(_p, override=False)
            break
except ImportError:
    pass

# ── SMTP 설정 (하위 호환용 모듈 레벨 상수 — import 시점 스냅샷) ──
# ⚠ 주의: 이 값은 모듈 최초 import 시 1회만 읽힘.
#   .env 미로드 상태에서 import 되면 빈 값이 된다.
#   send_email() 내부에서 _ensure_env_loaded() + os.environ.get()으로 재확인함.
SMTP_SERVER     = os.environ.get("SMTP_SERVER",     "")
SMTP_PORT       = int(os.environ.get("SMTP_PORT",   "25"))
SMTP_USER       = os.environ.get("SMTP_USER",       "")
SMTP_PASSWORD   = os.environ.get("SMTP_PASSWORD",   "")
SMTP_FROM       = os.environ.get("SMTP_FROM",       "")
SMTP_DEFAULT_TO = [e.strip() for e in os.environ.get("SMTP_DEFAULT_TO", "").split(",") if e.strip()]


def _ensure_env_loaded() -> None:
    """SMTP_SERVER가 설정되지 않은 경우 .env를 재탐색해 강제 로드한다.
    모듈 import 시점에 .env가 없었던 경우(Docker task 실행 컨텍스트 등)를 보완."""
    if os.environ.get("SMTP_SERVER"):
        return  # 이미 설정돼 있으면 불필요
    try:
        from dotenv import load_dotenv
        _h = Path(__file__).parent          # utils/
        _r = _h.parent                      # dags/
        for _p in [
            _h / ".env",
            _r / ".env",
            _r / "plugins" / ".env",
            _r.parent / "plugins" / ".env", # Docker: /opt/airflow/plugins/.env
        ]:
            if _p.exists():
                load_dotenv(_p, override=True)
                _log.info(f"[mail_util] .env 재로드 성공: {_p}")
                return
    except ImportError:
        pass
    _log.warning("[mail_util] .env 파일을 찾을 수 없습니다. 시스템 환경변수를 사용합니다.")


def send_email(
    to_addrs: list | str,
    subject: str,
    body: str,
    from_addr: str = None,
    cc_addrs: list | str = None,
    body_type: str = "html",
) -> None:
    """
    smtplib으로 메일을 발송한다.

    :param to_addrs:  수신자 (str 또는 list)
    :param subject:   제목
    :param body:      본문
    :param from_addr: 발신자 (생략 시 SMTP_FROM 환경변수 사용)
    :param cc_addrs:  참조 (str 또는 list, 없으면 None)
    :param body_type: 'html' 또는 'plain' (기본 'html')
    :raises RuntimeError: SMTP_SERVER 미설정 시
    :raises smtplib.SMTPException: 발송 실패 시
    """
    # 모듈 import 시 .env 미로드 가능성 대비: 매번 환경변수를 신선하게 읽는다.
    _ensure_env_loaded()
    smtp_server   = os.environ.get("SMTP_SERVER",   "")
    smtp_port     = int(os.environ.get("SMTP_PORT", "25"))
    smtp_user     = os.environ.get("SMTP_USER",     "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_server:
        raise RuntimeError("SMTP_SERVER가 설정되지 않았습니다. .env를 확인하세요.")

    from_addr = from_addr or os.environ.get("SMTP_FROM", "") or SMTP_FROM
    if not from_addr:
        raise RuntimeError("SMTP_FROM(발신자)이 설정되지 않았습니다. .env를 확인하세요.")

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    if cc_addrs is None:
        cc_addrs = []
    elif isinstance(cc_addrs, str):
        cc_addrs = [cc_addrs]

    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"]  = ", ".join(cc_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, body_type, "utf-8"))

    all_recipients = to_addrs + cc_addrs

    _log.info(f"[mail_util] 메일 발송 시도: server={smtp_server}:{smtp_port}, to={to_addrs}, subject={subject!r}")
    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.ehlo()
        # smtp.starttls()  # TLS 암호화 필요 시만 활성화
        if smtp_user and smtp_password:
            # 서버가 AUTH를 지원하지 않는 경우(내부 SMTP 서버 등) 로그만 남기고 계속 진행
            if smtp.has_extn("AUTH"):
                smtp.login(smtp_user, smtp_password)
            else:
                _log.debug("[mail_util] 서버가 AUTH를 지원하지 않아 login() 생략")
        smtp.sendmail(from_addr, all_recipients, msg.as_string())

    _log.info(f"[mail_util] 메일 발송 완료 → {all_recipients} / 제목: {subject}")
