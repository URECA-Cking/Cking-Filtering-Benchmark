#!/usr/bin/env bash
# CI 운영 배포의 운영 Lambda 교체 순서 확인 단계.
# 개발과 같은 기준이다. 배포된 운영 커밋(prod- 태그)이 이 커밋의 조상이면 교체하고, 더 새로우면 건너뛰고, 갈라졌으면 멈춘다.
# 환경 변수: ECR_REPOSITORY, PROD_FUNCTION_NAME
set -e

if ! CURRENT=$(aws lambda get-function --function-name "$PROD_FUNCTION_NAME" \
    --query Code.ResolvedImageUri --output text 2>"$RUNNER_TEMP/lambda.err"); then
  if grep -q ResourceNotFoundException "$RUNNER_TEMP/lambda.err"; then
    echo "운영 Lambda가 아직 없어 건너뛴다" | tee -a "$GITHUB_STEP_SUMMARY"
    echo "skip=true" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  cat "$RUNNER_TEMP/lambda.err"
  exit 1
fi
echo "previous=${CURRENT#*@}" >> "$GITHUB_OUTPUT"
[ "$GITHUB_EVENT_NAME" = workflow_dispatch ] && exit 0
if ! TAGS=$(aws ecr describe-images --repository-name "${ECR_REPOSITORY#*/}" --image-ids imageDigest="${CURRENT#*@}" \
    --query 'imageDetails[0].imageTags' --output text); then
  echo "::error::배포된 운영 이미지 $CURRENT 의 태그를 조회하지 못했다"
  exit 1
fi
DEPLOYED=$(printf '%s\n' "$TAGS" | tr '\t' '\n' | sed -n 's/^prod-\([0-9a-f]\{12\}\)$/\1/p')
NEWER=""
while read -r T; do
  [ -n "$T" ] || continue
  if ! git rev-parse -q --verify "$T^{commit}" >/dev/null; then
    echo "::error::배포된 운영 이미지 $CURRENT 의 커밋을 확인할 수 없다"
    exit 1
  fi
  if git merge-base --is-ancestor "$T" "$GITHUB_SHA"; then
    continue
  elif git merge-base --is-ancestor "$GITHUB_SHA" "$T"; then
    NEWER="$NEWER $T"
  else
    echo "::error::배포된 운영 커밋 $T 과 이 커밋의 이력이 갈라졌다"
    exit 1
  fi
done <<< "$DEPLOYED"
if [ -n "$NEWER" ]; then
  echo "::warning::더 새 커밋$NEWER 이 운영에 배포되어 있어 건너뛴다"
  echo "더 새 커밋$NEWER 이 운영에 배포되어 있어 건너뛴다" >> "$GITHUB_STEP_SUMMARY"
  echo "skip=true" >> "$GITHUB_OUTPUT"
fi
