"""NERP Web Request 추출 모듈.

캡처한 chains/chain_full_<key>.json을 requests로 재생하여 XLSX bytes를 반환한다.
각 부팅으로 생성된 SAP WebGUI 세션은 성공/실패 여부와 관계없이
sap-sessioncmd=CANCEL2로 종료하고, 동일 token/moin 재호출이 거부되는지 검증한다.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from types import TracebackType

CHAINS = Path(__file__).resolve().parent / "chains"
NERP_HOST = "https://nerp.lge.com"


class WebGuiCloseError(RuntimeError):
    """SAP WebGUI 서버 세션 종료 또는 종료 검증 실패."""


def _find_boot(steps):
    for step in steps:
        if step.get("method") == "POST" and "~service=3200" in step.get("url", ""):
            return step
    raise RuntimeError("체인에 부팅 요청(~service=3200)이 없습니다.")


def _find_old_token(steps):
    for step in steps:
        match = re.search(r"sap\(cz1[^)]+\)", step.get("url", ""))
        if match:
            return match.group(0)
    raise RuntimeError("체인에서 기존 sap(cz1...) 토큰을 찾지 못했습니다.")


def _find_old_moin(steps):
    for step in steps:
        moin = step.get("headers", {}).get("moin")
        if moin:
            return moin
    raise RuntimeError("체인에서 기존 moin을 찾지 못했습니다.")


def _batch_url(token: str, session_command: str | None = None) -> str:
    url = (
        f"{NERP_HOST}/{token}/bc/gui/sap/its/webgui/batch/json"
        "?~RG_WEBGUI=X&sap-statistics=true"
    )
    if session_command:
        url += f"&sap-sessioncmd={session_command}"
    return url


def _batch_headers(moin: str, referer: str) -> dict[str, str]:
    return {
        "Accept": "multipart/mixed",
        "Content-Type": "application/json;charset=UTF-8",
        "moin": moin,
        "sap-cancel-on-close": "true",
        "Referer": referer,
    }


def _probe_closed_session(sess, token: str, moin: str, referer: str) -> dict:
    """CANCEL2 후 동일 세션이 무효화됐는지 확인한다."""
    payload = [
        {"post": "okcode/ses[0]", "content": "%_KEEPALIVE"},
        {"get": "state/ur"},
    ]
    try:
        response = sess.post(
            _batch_url(token),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=_batch_headers(moin, referer),
            verify=False,
            timeout=30,
        )
        text = response.text
        lower = text.lower()
        closed_markers = (
            "session timed out",
            "icmenosession",
            "no session",
            "session not found",
            "session terminated",
            "session has been closed",
        )
        live_markers = ("<delta-update>", "arrsystemparams", "dynpro", "t-code")
        closed = response.status_code >= 400 or any(marker in lower for marker in closed_markers)
        live = response.status_code == 200 and any(marker in lower for marker in live_markers)
        return {
            "status": response.status_code,
            "bytes": len(response.content),
            "closed": closed,
            "live": live,
            "preview": text[:160].replace("\r", " ").replace("\n", " "),
        }
    except Exception as exc:
        return {
            "status": None,
            "bytes": 0,
            "closed": True,
            "live": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def cancel_webgui_session(
    sess,
    token: str,
    moin: str,
    referer: str,
    verbose: bool = True,
    verify_closed: bool = True,
) -> dict:
    """CANCEL2로 SAP WebGUI 세션을 종료하고 선택적으로 무효화를 검증한다."""
    log = print if verbose else (lambda *args, **kwargs: None)
    payload = [
        {"post": "vkey/0/ses[0]"},
        {"get": "state/ur"},
    ]

    try:
        response = sess.post(
            _batch_url(token, session_command="CANCEL2"),
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=_batch_headers(moin, referer),
            verify=False,
            timeout=30,
        )
        response.raise_for_status()
    except Exception as exc:
        raise WebGuiCloseError(
            f"CANCEL2 요청 실패: {type(exc).__name__}: {exc}"
        ) from exc

    result = {
        "cancel_status": response.status_code,
        "cancel_bytes": len(response.content),
        "verified": False,
        "probe": None,
    }
    log(
        f"[WebGUI 종료] CANCEL2 HTTP {response.status_code} "
        f"/ 응답={len(response.content):,}B"
    )

    if not verify_closed:
        return result

    time.sleep(0.5)
    probe = _probe_closed_session(sess, token, moin, referer)
    result["probe"] = probe
    result["verified"] = bool(probe.get("closed") and not probe.get("live"))

    if not result["verified"]:
        raise WebGuiCloseError(
            "CANCEL2 후 동일 token/moin 세션이 계속 유효합니다: "
            f"{probe}"
        )

    log(
        f"[WebGUI 종료 검증] 동일 세션 HTTP {probe.get('status')} "
        f"/ 종료 확인"
    )
    return result


def extract(sess, key, verbose=True):
    """인증 Session과 so|io|civ 키를 받아 리포트 XLSX bytes를 반환한다."""
    log = print if verbose else (lambda *args, **kwargs: None)
    chain_path = CHAINS / f"chain_full_{key}.json"
    if not chain_path.exists():
        raise FileNotFoundError(f"체인 파일이 없습니다: {chain_path}")

    steps = json.loads(chain_path.read_text(encoding="utf-8"))
    boot = _find_boot(steps)
    old_token = _find_old_token(steps)
    old_moin = _find_old_moin(steps)

    new_token = None
    new_moin = None
    referer = boot["url"]
    result = None
    primary_error: BaseException | None = None
    primary_traceback: TracebackType | None = None

    try:
        log(f"[추출:{key}] 부팅")
        response = sess.post(
            boot["url"],
            data=boot.get("post", ""),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False,
            timeout=40,
        )
        response.raise_for_status()

        token_match = re.search(r"sap\(cz1[^)\"'\s]+\)", response.text)
        moin_match = re.search(
            r"moin['\"]?\s*[:=]\s*['\"]?([0-9A-Fa-f]{12,})", response.text
        )
        if not token_match or not moin_match:
            raise RuntimeError("부팅 응답에서 새 token/moin을 찾지 못했습니다.")

        new_token = token_match.group(0)
        new_moin = moin_match.group(1)

        def substitute(value):
            if not value:
                return value
            return value.replace(old_token, new_token).replace(old_moin, new_moin)

        chunks = []
        boot_index = steps.index(boot)

        for step in steps[boot_index + 1 :]:
            url = substitute(step.get("url", ""))
            post = substitute(step.get("post", ""))

            if url.endswith(".js") or ("/data/" in url and url.endswith("~get")):
                continue

            if "/state/ur" in url:
                replay_response = sess.post(
                    url,
                    data=post,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "moin": new_moin,
                        "Referer": referer,
                    },
                    verify=False,
                    timeout=40,
                )
            elif "batch/json" in url:
                replay_response = sess.post(
                    url,
                    data=post.encode("utf-8"),
                    headers=_batch_headers(new_moin, referer),
                    verify=False,
                    timeout=90,
                )
            else:
                continue

            replay_response.raise_for_status()

            pattern = r"webgui/(\d+)/data/([0-9A-Fa-f]+)~[^)]*?Append:'(\w+)'"
            for match in re.finditer(pattern, replay_response.text):
                resource_id, download_moin, _append = match.groups()
                download_url = (
                    f"{NERP_HOST}/{new_token}/bc/gui/sap/its/webgui/"
                    f"{resource_id}/data/{download_moin}~get"
                )
                file_response = sess.post(
                    download_url,
                    data=b"",
                    headers={"moin": new_moin, "Referer": referer},
                    verify=False,
                    timeout=180,
                )
                file_response.raise_for_status()
                chunks.append(file_response.content)
                log(f"    파일 조각 {len(chunks)}: +{len(file_response.content):,}B")

        if not chunks:
            if verbose:
                print("[정보] 조회 결과가 없어 XLSX가 생성되지 않았습니다.")
            return None

        result = b"".join(chunks)
        log(f"[추출:{key}] 완료 -> {len(result):,}B ({len(chunks)}조각)")

    except BaseException as exc:
        primary_error = exc
        primary_traceback = sys.exc_info()[2]

    close_error = None
    if new_token and new_moin:
        try:
            cancel_webgui_session(
                sess,
                token=new_token,
                moin=new_moin,
                referer=referer,
                verbose=verbose,
                verify_closed=True,
            )
        except WebGuiCloseError as exc:
            close_error = exc
            log(f"[WebGUI 종료 실패] {exc}")

    if primary_error is not None:
        if close_error is not None:
            raise RuntimeError(
                f"추출 실패: {primary_error}; 추가로 WebGUI 종료 실패: {close_error}"
            ) from primary_error
        raise primary_error.with_traceback(primary_traceback)

    if close_error is not None:
        raise close_error

    return result
