"""
LIW LGEPH Teams 알림 발송 모듈

Power Automate의 "Teams 웹후크 요청이 수신된 경우" 트리거로
HTTP POST 요청을 보내 Teams 그룹 채팅에 메시지를 전송합니다.

실제 메시지 전송 대상 그룹 채팅과 발신 계정은
Power Automate 워크플로의 Teams 액션 설정을 따릅니다.
"""

import logging

import requests


logger = logging.getLogger(__name__)


# LGEPH LIW 알림용 Power Automate 웹후크 URL
# Power Automate에서 복사한 URL의 "&amp;"는 반드시 "&"로 변경해야 합니다.
DEFAULT_WEBHOOK_URL = (
    "https://default5069cde4642a45c08094d0c2dec10b.e3.environment.api.powerplatform.com:443"
    "/powerautomate/automations/direct/cu/25/workflows/44c8843825494fe2b89d3958cd7e476f"
    "/triggers/manual/paths/invoke?api-version=1"
    "&sp=%2Ftriggers%2Fmanual%2Frun"
    "&sv=1.0"
    "&sig=gPxSJ-Rt6Nh4OhdzG_uTrxotubEVOR86O586u58xawQ"
)


def send_liw_lgeph_message(
    message: str,
    url: str = DEFAULT_WEBHOOK_URL,
    timeout: int = 30,
) -> bool:
    """
    LIW LGEPH Teams 알림을 전송합니다.

    Args:
        message: Teams에 표시할 메시지.
        url: Power Automate 웹후크 URL.
        timeout: HTTP 요청 제한 시간(초).

    Returns:
        웹후크 요청 성공 여부.
    """
    if not url:
        logger.error("[LIW LGEPH Teams] 웹후크 URL이 없습니다.")
        return False

    if not message:
        logger.error("[LIW LGEPH Teams] 전송할 메시지가 없습니다.")
        return False

    payload = {
        "Message": message,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

        if response.status_code in (200, 202):
            logger.info(
                "[LIW LGEPH Teams] 웹후크 호출 성공: status=%s",
                response.status_code,
            )
            return True

        logger.warning(
            "[LIW LGEPH Teams] 웹후크 호출 실패: status=%s, body=%s",
            response.status_code,
            response.text,
        )
        return False

    except requests.RequestException as error:
        logger.warning(
            "[LIW LGEPH Teams] 웹후크 요청 중 오류 발생: %s",
            error,
            exc_info=True,
        )
        return False