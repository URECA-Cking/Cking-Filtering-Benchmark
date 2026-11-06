#!/usr/bin/env bash
# CI 운영 배포의 실패 시 이전 이미지로 되돌리기 단계.
# 진행 중인 교체가 있으면 다시 교체할 수 없어 끝나기를 먼저 기다린다.
# 환경 변수: ECR_REPOSITORY, PROD_FUNCTION_NAME, PREVIOUS
set -e

aws lambda wait function-updated-v2 --function-name "$PROD_FUNCTION_NAME" || true
STATE=$(aws lambda get-function --function-name "$PROD_FUNCTION_NAME" \
  --query '[Configuration.LastUpdateStatus,Code.ResolvedImageUri]' --output text)
read -r STATUS IMAGE <<< "$STATE"
if [ "$STATUS" = InProgress ]; then
  echo "::error::이미지 교체가 아직 진행 중이라 되돌리지 못했다. 끝난 뒤 이전 이미지($PREVIOUS)로 되돌린다"
  exit 1
fi
if [ "$STATUS" = Successful ] && [ "${IMAGE#*@}" = "$PREVIOUS" ]; then
  echo "::error::이미지 교체가 적용되지 않아 이전 이미지($PREVIOUS) 그대로다"
  exit 0
fi
aws lambda update-function-code --function-name "$PROD_FUNCTION_NAME" \
  --image-uri "$ECR_REPOSITORY@$PREVIOUS" --query LastUpdateStatus --output text
aws lambda wait function-updated-v2 --function-name "$PROD_FUNCTION_NAME"
echo "::error::교체 또는 확인에 실패해 이전 이미지($PREVIOUS)로 되돌렸다"
