#!/usr/bin/env bash
# 필터 이미지를 Lambda와 같은 조건(읽기 전용 파일 시스템, 쓰기는 /tmp만, root가 아닌 사용자)으로 띄워 확인한다:
# 기동, /health, /moderate(통과·차단·422).
# 사용법: scripts/check-image.sh <이미지>
set -euo pipefail

IMAGE="${1:?사용법: scripts/check-image.sh <이미지>}"
OUT=$(mktemp)
trap 'docker rm -f filter-check >/dev/null 2>&1 || true; rm -f "$OUT"' EXIT

docker run -d --name filter-check -p 127.0.0.1:18000:8000 --read-only --tmpfs /tmp --user 65534:65534 "$IMAGE" >/dev/null
for i in $(seq 1 90); do
  if curl -fsS --max-time 5 -o /dev/null http://127.0.0.1:18000/health 2>/dev/null; then
    break
  fi
  if [ "$i" -eq 90 ]; then
    echo "기동 실패"
    docker logs --tail 30 filter-check
    exit 1
  fi
  sleep 1
done

moderate() {
  curl -sS --max-time 30 -o "$OUT" -w '%{http_code}' -H 'Content-Type: application/json' -d "$1" http://127.0.0.1:18000/moderate
}

expect() {
  if [ "$2" != "$3" ]; then
    echo "실패: $1 (기대 $3, 실제 $2)"
    cat "$OUT"
    exit 1
  fi
  echo "통과: $1"
}

expect "정상 댓글 상태" "$(moderate '{"commentId":1,"content":"오늘 방송 정말 재밌었어요 다음에도 기대할게요"}')" 200
expect "정상 댓글 판정" "$(jq -r .action "$OUT")" PASS
expect "전화번호 댓글 상태" "$(moderate '{"commentId":2,"content":"연락주세요 010-1234-5678"}')" 200
expect "전화번호 댓글 판정" "$(jq -r .action "$OUT")" BLOCK
expect "전화번호 사유" "$(jq -r '.reasons | index("privacy:phone") != null' "$OUT")" true
expect "빈 댓글" "$(moderate '{"commentId":3,"content":""}')" 422
expect "commentId 없는 요청" "$(moderate '{"content":"원문표시"}')" 422
expect "422 응답에 원문 없음" "$(grep -c 원문표시 "$OUT" || true)" 0
