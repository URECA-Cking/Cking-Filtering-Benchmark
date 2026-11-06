#!/usr/bin/env bash
# CI 개발 배포의 이미지 준비 단계.
# 태그는 커밋이고 덮어쓸 수 없다. 같은 커밋을 다시 실행하면 새로 빌드하지 않고 올려 둔 이미지를 받아 확인한다.
# 모델 경로는 src/local_pipeline.py의 MODEL_DIR에서 읽고, 모델은 개발 배포 버킷에서 받는다.
# 환경 변수: ECR_REPOSITORY
set -e

TAG="${GITHUB_SHA::12}"
aws ecr get-login-password | docker login --username AWS --password-stdin "${ECR_REPOSITORY%%/*}"
if DIGEST=$(aws ecr describe-images --repository-name "${ECR_REPOSITORY#*/}" --image-ids imageTag="$TAG" \
    --query 'imageDetails[0].imageDigest' --output text 2>"$RUNNER_TEMP/ecr.err"); then
  docker pull "$ECR_REPOSITORY@$DIGEST"
  docker tag "$ECR_REPOSITORY@$DIGEST" filter:check
  echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
elif grep -q ImageNotFoundException "$RUNNER_TEMP/ecr.err"; then
  scripts/build-image.sh filter:check
else
  cat "$RUNNER_TEMP/ecr.err"
  exit 1
fi
