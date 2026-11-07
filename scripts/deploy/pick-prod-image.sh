#!/usr/bin/env bash
# CI 운영 배포의 올릴 이미지 정하기 단계.
# 이미지에 들어가는 파일이 이 커밋과 같은 개발 커밋의 이미지 중 가장 최근 커밋의 것을 고른다. 개발 CI가 확인하고 올린 이미지다.
# develop→main을 squash로 합치면 개발 커밋이 main의 조상이 아니므로 이력이 아니라 내용으로 고른다.
# 그런 이미지가 없으면 develop의 개발 배포가 아직 끝나지 않은 것이라 멈춘다. 수동 실행은 고른 운영 태그를 그대로 쓴다.
# 환경 변수: ECR_REPOSITORY, INPUT_TAG(수동 실행)
set -e

REPO="${ECR_REPOSITORY#*/}"
if [ "$GITHUB_EVENT_NAME" = workflow_dispatch ]; then
  if ! [[ "$INPUT_TAG" =~ ^prod-[0-9a-f]{12}$ ]]; then
    echo "::error::태그는 prod-<커밋 12자리>다: $INPUT_TAG"
    exit 1
  fi
  DIGEST=$(aws ecr describe-images --repository-name "$REPO" --image-ids imageTag="$INPUT_TAG" \
    --query 'imageDetails[0].imageDigest' --output text)
  echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
  echo "수동 되돌리기: $INPUT_TAG ($DIGEST)" | tee -a "$GITHUB_STEP_SUMMARY"
  exit 0
fi
INPUTS=(server src/local_pipeline.py src/rules 'requirements-*.txt' Dockerfile model.sha256 .dockerignore scripts/build-image.sh)
# shellcheck disable=SC2016 # 백틱은 JMESPath 문자열이다
IMAGES=$(aws ecr describe-images --repository-name "$REPO" \
  --query 'imageDetails[?imageTags].[imageDigest,join(` `,imageTags)]' --output text)
BEST="" DIGEST="" BEST_TIME=""
while IFS=$'\t' read -r D TAGS; do
  for T in $TAGS; do
    [[ "$T" =~ ^[0-9a-f]{12}$ ]] || continue
    git rev-parse -q --verify "$T^{commit}" >/dev/null || continue
    git diff --quiet "$T" "$GITHUB_SHA" -- "${INPUTS[@]}" || continue
    TIME=$(git log -1 --format=%ct "$T")
    if [ -z "$BEST_TIME" ] || [ "$TIME" -gt "$BEST_TIME" ]; then
      BEST="$T" DIGEST="$D" BEST_TIME="$TIME"
    fi
  done
done <<< "$IMAGES"
if [ -z "$BEST" ]; then
  echo "::error::이 커밋과 이미지 내용이 같은 개발 이미지가 없다. develop의 개발 배포가 끝난 뒤 main에 합친다"
  exit 1
fi
echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
echo "올릴 이미지: 개발 커밋 $BEST ($DIGEST)" | tee -a "$GITHUB_STEP_SUMMARY"
