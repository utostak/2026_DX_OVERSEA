"""
Power Automate (Teams 웹후크) 호출 테스트 프로그램

Power Automate 의 "Teams 웹후크 요청이 수신된 경우" 트리거로 생성된
HTTP URL 로 POST 요청을 보내 흐름이 정상 동작하는지 테스트합니다.

사용법:
    1) 환경변수 또는 --url 인자로 웹후크 URL 지정
       - PowerShell:  $env:PA_WEBHOOK_URL="https://default....../..."
       - 또는:        python test_powerautomate_webhook.py --url "https://..."

    2) 실행 예시:
       python test_powerautomate_webhook.py                       # 기본 텍스트 카드
       python test_powerautomate_webhook.py --text "테스트 메시지"
       python test_powerautomate_webhook.py --mode adaptive       # Adaptive Card
       python test_powerautomate_webhook.py --mode raw            # 단순 JSON(Body/Attachments)
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests


def build_messagecard(text: str, title: str) -> dict:
    """Teams MessageCard(레거시) 형식 - Attachments 없이 Body(text) 위주."""
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": title,
        "title": title,
        "text": text,
    }


def build_adaptive_card(text: str, title: str) -> dict:
    """Teams Adaptive Card 형식 - Attachments 배열에 카드가 담김."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": title,
                        },
                        {
                            "type": "TextBlock",
                            "text": text,
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "spacing": "Small",
                            "isSubtle": True,
                            "text": f"전송시각: {datetime.now():%Y-%m-%d %H:%M:%S}",
                        },
                    ],
                },
            }
        ],
    }


def build_simple(text: str, title: str) -> dict:
    """가장 단순한 형식 - text 필드만 전송.

    Power Automate 흐름에서 Body 변수를 triggerBody()?['text'] 로 설정한 경우 사용.
    Adaptive Card 의 TextBlock text 에 @{variables('Body')} 로 그대로 넣으면 됩니다.
    """
    return {
        "text": text,
    }


def build_raw(text: str, title: str) -> dict:
    """흐름에서 Body / Attachments 변수를 직접 참조하는 경우의 단순 JSON."""
    return {
        "title": title,
        "body": text,
        "attachments": [],
        "timestamp": datetime.now().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Power Automate Teams 웹후크 호출 테스트")
    parser.add_argument(
        "--url",
        default="https://default5069cde4642a45c08094d0c2dec10b.e3.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/20/workflows/fe21f70dc36b414cb6aba1c3971ba5fe/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=t1nZBj0uUdpy2azbSCiUbHohLjd7VCrevVqMjeNVvpc",
        help="웹후크 HTTP URL (미지정 시 환경변수 PA_WEBHOOK_URL 사용)",
    )
    parser.add_argument("--text", default="Power Automate 웹후크 테스트 메시지입니다.", help="본문 텍스트")
    parser.add_argument("--title", default="SCM-TMS 웹후크 테스트", help="제목")
    parser.add_argument(
        "--mode",
        choices=["simple", "messagecard", "adaptive", "raw"],
        default="simple",
        help="전송 페이로드 형식 (기본 simple: {\"text\": \"...\"})",
    )
    parser.add_argument("--timeout", type=int, default=30, help="요청 타임아웃(초)")
    args = parser.parse_args()

    if not args.url:
        print("[오류] 웹후크 URL 이 없습니다. --url 인자 또는 환경변수 PA_WEBHOOK_URL 을 설정하세요.")
        return 1

    builders = {
        "simple": build_simple,
        "messagecard": build_messagecard,
        "adaptive": build_adaptive_card,
        "raw": build_raw,
    }
    payload = builders[args.mode](args.text, args.title)

    print(f"[요청] mode={args.mode}")
    print(f"[요청] url ={args.url[:80]}...")
    print("[요청] payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        resp = requests.post(
            args.url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=args.timeout,
        )
    except requests.RequestException as e:
        print(f"[실패] 요청 중 예외 발생: {e}")
        return 2

    print("-" * 60)
    print(f"[응답] status_code = {resp.status_code}")
    print(f"[응답] headers     = {dict(resp.headers)}")
    body = resp.text.strip()
    print(f"[응답] body        = {body if body else '(빈 응답 - 정상적으로 트리거된 경우 흔함)'}")

    # Power Automate 트리거는 보통 202 Accepted 또는 200 을 반환
    if resp.status_code in (200, 202):
        print("[성공] 웹후크 호출이 정상적으로 접수되었습니다.")
        return 0

    print("[경고] 예상치 못한 상태 코드입니다. URL/권한/페이로드 형식을 확인하세요.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
