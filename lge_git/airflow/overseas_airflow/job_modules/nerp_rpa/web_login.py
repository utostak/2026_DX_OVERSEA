"""NERP SSO 로그인. Selenium 없이 requests.Session을 반환한다."""
import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests
import urllib3

urllib3.disable_warnings()

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "ep_settings.json"
if not SETTINGS_PATH.exists():
    raise FileNotFoundError(f"EP 설정 파일 없음: {SETTINGS_PATH}")

SETTINGS = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
LOGIN_URL = SETTINGS["URL"]
SSO_BASE = "https://" + LOGIN_URL.split("/")[2]
_LOGIN_INFO = SETTINGS["Login Info"]
UID = _LOGIN_INFO["ID"]
PW = _LOGIN_INFO["PW"]
OTP = _LOGIN_INFO.get("OTP", "")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TARGET_FCC = "/portalRedirect.jsp?target=http%3A%2F%2Fep.lge.com%2Findex.html%3Flang%3Dkr"
TARGET_OTP = "http://ep.lge.com/index.html"
NERP_FLP = "https://nerp.lge.com/sap/bc/ui2/flp"


def _parse_form(html, action_keyword):
    for match in re.finditer(r"<form[^>]*>.*?</form>", html, re.I | re.S):
        block = match.group(0)
        action_match = re.search(r"action=[\"']([^\"']+)[\"']", block, re.I)
        action = action_match.group(1) if action_match else ""
        if action_keyword.lower() not in action.lower():
            continue
        fields = {}
        for input_match in re.finditer(r"<input[^>]+>", block, re.I):
            name_match = re.search(r"name=[\"']([^\"']+)[\"']", input_match.group(0), re.I)
            value_match = re.search(r"value=[\"']([^\"']*)[\"']", input_match.group(0), re.I | re.S)
            if name_match:
                fields[name_match.group(1)] = unescape(value_match.group(1)) if value_match else ""
        return action, fields
    return None, None


def _follow_saml(session, response, max_hops=8, log=print):
    for hop in range(max_hops):
        if "SAP_SESSIONID_S4P_100" in session.cookies:
            return response
        block = None
        for match in re.finditer(r"<form[^>]*>.*?</form>", response.text, re.I | re.S):
            if re.search(
                r'name=["\'](SAMLRequest|SAMLResponse|RelayState|SMSAML|RelayURL)["\']',
                match.group(0), re.I,
            ):
                block = match.group(0)
                break
        if not block:
            return response
        action_match = re.search(r"action=[\"']([^\"']*)[\"']", block, re.I)
        action = urljoin(response.url, unescape(action_match.group(1)) if action_match else response.url)
        fields = {}
        for input_match in re.finditer(r"<input[^>]+>", block, re.I):
            name_match = re.search(r'name=["\']([^"\']+)', input_match.group(0))
            value_match = re.search(r'value=["\']([^"\']*)', input_match.group(0), re.S)
            if name_match:
                fields[name_match.group(1)] = unescape(value_match.group(1)) if value_match else ""
        log(f"    SAML hop{hop} -> {action[:50]}")
        response = session.post(action, data=fields, verify=False, timeout=30)
    return response


def login(verbose=True):
    log = print if verbose else (lambda *args, **kwargs: None)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    try:
        log("[로그인 1] GET eplogin.jsp")
        session.get(LOGIN_URL, verify=False, timeout=20).raise_for_status()
        log("[로그인 2] userOtpCheck.jsp")
        session.post(
            f"{SSO_BASE}/check/userOtpCheck.jsp", data={"userId": UID}, verify=False, timeout=20
        ).raise_for_status()
        log("[로그인 3] ssoOtpAuth.jsp")
        response = session.post(
            f"{SSO_BASE}/ssoOtpAuth.jsp",
            data={
                "TARGET": TARGET_OTP, "SMAUTHREASON": "0", "OTPYN": "Y", "OTPCHECK": "M",
                "USER": UID, "LDAPPASSWORD": PW, "OTPPASSWORD": OTP,
            },
            headers={"Referer": LOGIN_URL, "Content-Type": "application/x-www-form-urlencoded"},
            verify=False, timeout=20,
        )
        response.raise_for_status()
        action, fields = _parse_form(response.text, "login.fcc")
        if not fields or not fields.get("PASSWORD"):
            raise RuntimeError("ssoOtpAuth 응답에서 login.fcc 폼을 찾지 못했습니다.")
        log("[로그인 4] login.fcc")
        fcc_url = action if action.startswith("http") else SSO_BASE + action
        body = (
            f"TARGET={TARGET_FCC}&SMAUTHREASON={fields.get('SMAUTHREASON', '0')}"
            f"&PASSWORD={quote_plus(fields['PASSWORD'])}&OTPYN={fields.get('OTPYN', 'Y')}"
            f"&USER={fields.get('USER', UID)}&RANDOMNUMBER={quote_plus(fields.get('RANDOMNUMBER', ''))}"
            f"&FIDOFLAG={fields.get('FIDOFLAG', 'OTP')}"
        )
        session.post(
            fcc_url, data=body,
            headers={"Referer": f"{SSO_BASE}/ssoOtpAuth.jsp", "Content-Type": "application/x-www-form-urlencoded"},
            verify=False, timeout=20,
        ).raise_for_status()
        if "SMSESSION" not in session.cookies:
            raise RuntimeError("SMSESSION 미발급")
        log("[로그인 5] NERP 진입")
        response = session.get(NERP_FLP, verify=False, timeout=30)
        _follow_saml(session, response, log=log)
        if "SAP_SESSIONID_S4P_100" not in session.cookies:
            raise RuntimeError("SAP_SESSIONID 미발급")
        log("[로그인 완료] SAP_SESSIONID 획득 (브라우저 0)")
        return session
    except Exception:
        session.close()
        raise
