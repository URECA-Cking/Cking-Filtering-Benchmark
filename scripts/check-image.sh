#!/usr/bin/env bash
# 필터 이미지를 띄워 확인한다: 기동, /health, /moderate(통과·차단·422), 읽기 전용 파일 시스템(Lambda와 같은 조건).
# 사용법: scripts/check-image.sh <이미지>
set -euo pipefail

IMAGE="${1:?사용법: scripts/check-image.sh <이미지>}"
OUT=$(mktemp)
trap 'docker rm -f filter-check filter-check-ro >/dev/null 2>&1 || true; rm -f "$OUT"' EXIT

start() {
  local name=$1 port=$2
  shift 2
  docker run -d --name "$name" -p "127.0.0.1:$port:8000" "$@" "$IMAGE" >/dev/null
  for _ in $(seq 1 90); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$port/health" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "기동 실패: $name"
  docker logs --tail 30 "$name"
  return 1
}

moderate() {
  curl -sS -o "$OUT" -w '%{http_code}' -H 'Content-Type: application/json' -d "$2" "http://127.0.0.1:$1/moderate"
}

expect() {
  if [ "$2" != "$3" ]; then
    echo "실패: $1 (기대 $3, 실제 $2)"
    cat "$OUT"
    exit 1
  fi
  echo "통과: $1"
}

start filter-check 18000
expect "정상 댓글 상태" "$(moderate 18000 '{"commentId":1,"content":"오늘 방송 정말 재밌었어요 다음에도 기대할게요"}')" 200
expect "정상 댓글 판정" "$(jq -r .action "$OUT")" PASS
expect "전화번호 댓글 상태" "$(moderate 18000 '{"commentId":2,"content":"연락주세요 010-1234-5678"}')" 200
expect "전화번호 댓글 판정" "$(jq -r .action "$OUT")" BLOCK
expect "전화번호 사유" "$(jq -r '.reasons | index("privacy:phone") != null' "$OUT")" true
expect "빈 댓글" "$(moderate 18000 '{"commentId":3,"content":""}')" 422
expect "commentId 없는 요청" "$(moderate 18000 '{"content":"원문표시"}')" 422
expect "422 응답에 원문 없음" "$(grep -c 원문표시 "$OUT" || true)" 0

start filter-check-ro 18001 --read-only --tmpfs /tmp
expect "읽기 전용 정상 댓글 상태" "$(moderate 18001 '{"commentId":4,"content":"오늘 방송 정말 재밌었어요 다음에도 기대할게요"}')" 200
expect "읽기 전용 정상 댓글 판정" "$(jq -r .action "$OUT")" PASS
