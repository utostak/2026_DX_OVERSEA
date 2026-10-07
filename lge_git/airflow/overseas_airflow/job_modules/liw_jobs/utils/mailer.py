"""
jobs/utils/mailer.py — SMTP 메일 발송 유틸리티

환경변수(.env.prd):
  SMTP_HOST        SMTP 서버 (예: smtp.office365.com)
  SMTP_PORT        포트 (기본 587)
  SMTP_USER        인증 계정
  SMTP_PASSWORD    인증 비밀번호
  SMTP_FROM        보내는 사람 주소 (없으면 SMTP_USER 사용)
  SMTP_USE_TLS     STARTTLS 사용 여부 (true/false, 기본 true)
  SMTP_USE_SSL     SSL 사용 여부 (true/false, 기본 false) — 465 포트용
"""
import os
import ssl
import base64
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr, formatdate

from utils.config import getenv

logger = logging.getLogger(__name__)


def _bool(v: str, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def smtp_configured() -> bool:
    """SMTP 발송이 가능한 최소 설정이 있는지 확인."""
    return bool(getenv('SMTP_HOST'))


def send_email(
    to_addrs,
    subject: str,
    html_body: str = None,
    text_body: str = None,
    attachments=None,       # [{'filename': str, 'content': bytes|base64str, 'is_base64': bool}]
    from_name: str = None,
    from_addr: str = None,  # From 헤더 주소 (로그인 사용자 이메일). 미지정 시 SMTP_FROM/SMTP_USER 사용
    cc_addrs=None,
    reply_to: str = None,   # Reply-To 헤더
    bcc_addrs=None,         # BCC 헤더 (수신자에게 비표시)
):
    """
    이메일 발송. 성공 시 True, 실패 시 예외 발생.

    to_addrs / cc_addrs : str 또는 list[str]
    attachments         : [{'filename', 'content'(bytes 또는 base64 str), 'is_base64'(bool),
                            'mime'(선택, 예: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}]
    """
    host = getenv('SMTP_HOST')
    if not host:
        raise RuntimeError('SMTP_HOST 가 설정되지 않았습니다. (.env 에 SMTP_* 설정 필요)')

    port          = getenv('SMTP_PORT', 587, cast=int)
    user          = getenv('SMTP_USER', '')
    password      = getenv('SMTP_PASSWORD', '')
    smtp_sender   = getenv('SMTP_FROM') or user   # SMTP 인증/envelope 발신 계정
    display_from  = from_addr or smtp_sender          # From: 헤더에 표시할 주소
    use_tls  = _bool(getenv('SMTP_USE_TLS'), True)
    use_ssl  = _bool(getenv('SMTP_USE_SSL'), False)

    if not smtp_sender:
        raise RuntimeError('SMTP_FROM 또는 SMTP_USER 가 필요합니다.')

    if isinstance(to_addrs, str):
        to_addrs = [a.strip() for a in to_addrs.replace(';', ',').split(',') if a.strip()]
    if isinstance(cc_addrs, str):
        cc_addrs = [a.strip() for a in cc_addrs.replace(';', ',').split(',') if a.strip()]
    if isinstance(bcc_addrs, str):
        bcc_addrs = [a.strip() for a in bcc_addrs.replace(';', ',').split(',') if a.strip()]
    cc_addrs  = cc_addrs  or []
    bcc_addrs = bcc_addrs or []

    if not to_addrs:
        raise RuntimeError('받는 사람(to_addrs)이 없습니다.')

    # ── 메시지 구성 ──────────────────────────────────────────────
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From']    = formataddr((from_name or 'LIW', display_from))
    msg['To']      = ', '.join(to_addrs)
    if cc_addrs:
        msg['Cc'] = ', '.join(cc_addrs)
    # BCC 는 헤더에 추가하지 않음 — envelope에만 포함
    if reply_to:
        msg['Reply-To'] = reply_to
    msg['Date']    = formatdate(localtime=True)

    # 본문 (alternative: text + html)
    alt = MIMEMultipart('alternative')
    if text_body:
        alt.attach(MIMEText(text_body, 'plain', 'utf-8'))
    if html_body:
        alt.attach(MIMEText(html_body, 'html', 'utf-8'))
    if not text_body and not html_body:
        alt.attach(MIMEText('', 'plain', 'utf-8'))
    msg.attach(alt)

    # 첨부파일
    for att in (attachments or []):
        content = att.get('content')
        if content is None:
            continue
        if att.get('is_base64'):
            # data URL(예: "data:...;base64,XXXX") 이면 콤마 뒤만 취함
            if isinstance(content, str) and ',' in content[:64] and content[:5] in ('data:', 'DATA:'):
                content = content.split(',', 1)[1]
            content = base64.b64decode(content)
        elif isinstance(content, str):
            content = content.encode('utf-8')

        filename = att.get('filename', 'attachment.bin')
        mime = att.get('mime', '')
        subtype = 'octet-stream'
        if mime.endswith('spreadsheetml.sheet') or filename.lower().endswith('.xlsx'):
            subtype = 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif filename.lower().endswith('.csv'):
            subtype = 'csv'

        part = MIMEApplication(content, _subtype=subtype)
        part.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(part)

    all_recipients = to_addrs + cc_addrs + bcc_addrs  # BCC는 envelope에만 포함, 헤더엔 없음

    # ── 발송 ─────────────────────────────────────────────────────
    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.ehlo()
            if user and password and server.has_extn('auth'):
                server.login(user, password)
            server.sendmail(smtp_sender, all_recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
            if user and password and server.has_extn('auth'):
                server.login(user, password)
            server.sendmail(smtp_sender, all_recipients, msg.as_string())

    logger.info(f"📧 메일 발송 완료 → {all_recipients} (from={display_from}, subject={subject!r})")
    return True
