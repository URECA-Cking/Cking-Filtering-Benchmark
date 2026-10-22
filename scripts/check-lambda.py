#!/usr/bin/env python3
"""배포한 Lambda를 함수 URL로 IAM 서명(SigV4)을 붙여 불러, 통과·차단 판정을 확인한다.

사용법: scripts/check-lambda.py <함수 URL>
자격 증명은 실행 환경(환경 변수, GitHub Actions의 역할)에서 읽는다. 새 이미지의 첫 호출은 콜드 스타트라
요청마다 실행 상한(120초)보다 조금 길게 기다린다.
"""
import json
import sys
import urllib.error
import urllib.request

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

REGION = "ap-northeast-2"
CASES = [
    ("정상 댓글", {"commentId": 1, "content": "오늘 방송 정말 재밌었어요 다음에도 기대할게요"}, "PASS"),
    ("전화번호 댓글", {"commentId": 2, "content": "연락주세요 010-1234-5678"}, "BLOCK"),
]


def moderate(url, body, credentials):
    data = json.dumps(body, ensure_ascii=False).encode()
    signed = AWSRequest(method="POST", url=url, data=data, headers={"Content-Type": "application/json"})
    SigV4Auth(credentials, "lambda", REGION).add_auth(signed)
    request = urllib.request.Request(url, data=data, headers=dict(signed.headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            return response.status, json.loads(response.read()).get("action")
    except urllib.error.HTTPError as error:
        return error.code, None


def main():
    if len(sys.argv) != 2:
        sys.exit("사용법: scripts/check-lambda.py <함수 URL>")
    url = sys.argv[1].rstrip("/") + "/moderate"
    credentials = Session().get_credentials()
    if credentials is None:
        sys.exit("자격 증명이 없다")
    credentials = credentials.get_frozen_credentials()
    failed = False
    for name, body, want in CASES:
        status, action = moderate(url, body, credentials)
        ok = status == 200 and action == want
        failed |= not ok
        print(f"{'통과' if ok else '실패'}: {name} 상태 {status}, 판정 {action} (기대 {want})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
