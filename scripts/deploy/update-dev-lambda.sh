#!/usr/bin/env bash
# CI 개발 배포의 개발 Lambda 이미지 교체 단계.
# 개발 Lambda는 이 CI가 올린 첫 이미지로 만든다(URECA-Cking/Cking-Infra#127). 그 전에는 건너뛴다.
# 배포된 커밋이 이 커밋의 조상이면 교체하고, 이 커밋이 더 오래됐으면(지난 실행의 재시도) 건너뛴다.
# 둘 다 아니면 이력이 갈라진 것이라 멈춘다. 배포된 이미지에 커밋 태그가 여럿이면(내용이 같은 이미지) 모두 본다.
# 환경 변수: ECR_REPOSITORY, FUNCTION_NAME, DIGEST
set -e

echo "이미지: $ECR_REPOSITORY:${GITHUB_SHA::12} ($DIGEST)" | tee -a "$GITHUB_STEP_SUMMARY"
if ! CURRENT=$(aws lambda get-function --function-name "$FUNCTION_NAME" \
    --query Code.ResolvedImageUri --output text 2>"$RUNNER_TEMP/lambda.err"); then
  if grep -q ResourceNotFoundException "$RUNNER_TEMP/lambda.err"; then
    echo "개발 Lambda가 아직 없어 이미지 교체를 건너뛴다" | tee -a "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
  cat "$RUNNER_TEMP/lambda.err"
  exit 1
fi
DEPLOYED=$(aws ecr describe-images --repository-name "${ECR_REPOSITORY#*/}" --image-ids imageDigest="${CURRENT#*@}" \
  --query 'imageDetails[0].imageTags' --output text | tr '\t' '\n' | grep -xE '[0-9a-f]{12}' || true)
NEWER=""
while read -r T; do
  if [ -z "$T" ] || ! git rev-parse -q --verify "$T^{commit}" >/dev/null; then
    echo "::error::배포된 이미지 $CURRENT 의 커밋을 확인할 수 없다"
    exit 1
  fi
  if git merge-base --is-ancestor "$T" "$GITHUB_SHA"; then
    continue
  elif git merge-base --is-ancestor "$GITHUB_SHA" "$T"; then
    NEWER="$NEWER $T"
  else
    echo "::error::배포된 커밋 $T 과 이 커밋의 이력이 갈라졌다"
    exit 1
  fi
done <<< "$DEPLOYED"
if [ -n "$NEWER" ]; then
  echo "::warning::더 새 커밋$NEWER 이 배포되어 있어 이미지 교체를 건너뛴다"
  echo "더 새 커밋$NEWER 이 배포되어 있어 이미지 교체를 건너뛴다" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi
aws lambda update-function-code --function-name "$FUNCTION_NAME" \
  --image-uri "$ECR_REPOSITORY@$DIGEST" --query LastUpdateStatus --output text
aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
echo "개발 Lambda 이미지 교체: ${DEPLOYED//$'\n'/ } -> ${GITHUB_SHA::12} ($DIGEST)" | tee -a "$GITHUB_STEP_SUMMARY"
