"""
Power Automate (Teams 웹후크) 호출 프로그램

Power Automate 의 "Teams 웹후크 요청이 수신된 경우" 트리거로 생성된
HTTP URL 로 POST 요청을 보내 그룹 채팅에 메시지를 전송합니다.
"""

import json
import sys

import requests


def build_groupchat(group_chat_id: str, message: str) -> dict:
    """그룹 채팅에 메시지를 보내는 JSON 파라미터 형식.

    Power Automate 흐름에서 triggerBody()?['GroupChatId'], triggerBody()?['Message']
    로 값을 참조하도록 구성한 경우 사용합니다.
    """
    return {
        "GroupChatId": group_chat_id,
        "Message": message,
    }


# 기본 웹후크 URL / 그룹 채팅 ID (환경에 맞게 수정)
DEFAULT_WEBHOOK_URL = (
    "https://default5069cde4642a45c08094d0c2dec10b.e3.environment.api.powerplatform.com:443"
    "/powerautomate/automations/direct/cu/00/workflows/81388b12d5f042b297e02c28ce3f692e"
    "/triggers/manual/paths/invoke?api-version=1"
    "&sp=%2Ftriggers%2Fmanual%2Frun"
    "&sv=1.0"
    "&sig=GPy1cX8bl-aEAjVQnfs-4pqhpWcM37dnJAi7goLK2Us"
)
# 그룹 채팅 ID는 확인방법
# 팀즈 그룹채팅방에서 1) 우측 상단 ... 메뉴에서 링크복사후 2) 복사된 링크에서
# thread.v2 앞의 19:~@thread.v2 부분을 복사하면 됩니다.
DEFAULT_GROUP_CHAT_ID = "19:731b0bb6e942458286860c8d453d3289@thread.v2"


def send_group_chat_message(
    message: str,
    group_chat_id: str = DEFAULT_GROUP_CHAT_ID,
    url: str = DEFAULT_WEBHOOK_URL,
    timeout: int = 30,
) -> bool:
    """그룹 채팅에 메시지를 전송한다.

    Args:
        message: 전송할 메시지 텍스트.
        group_chat_id: 대상 그룹 채팅 ID (기본값 사용 가능).
        url: Power Automate 웹후크 URL (기본값 사용 가능).
        timeout: 요청 타임아웃(초).

    Returns:
        전송 성공 여부(True/False).
    """
    if not url:
        print("[오류] 웹후크 URL 이 없습니다.")
        return False

    payload = build_groupchat(group_chat_id, message)

    print("[요청] mode=groupchat")
    print(f"[요청] url ={url[:80]}...")
    print("[요청] payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        print(f"[실패] 요청 중 예외 발생: {e}")
        return False

    print("-" * 60)
    print(f"[응답] status_code = {resp.status_code}")
    print(f"[응답] headers     = {dict(resp.headers)}")
    body = resp.text.strip()
    print(f"[응답] body        = {body if body else '(빈 응답 - 정상적으로 트리거된 경우 흔함)'}")

    if resp.status_code in (200, 202):
        print("[성공] 웹후크 호출이 정상적으로 접수되었습니다.")
        return True

    print("[경고] 예상치 못한 상태 코드입니다. URL/권한/페이로드 형식을 확인하세요.")
    return False


def main() -> int: 
    ok = send_group_chat_message(
        message="Power Automate 그룹 채팅 테스트 메시지입니다."
    )
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())

    
    
    
    