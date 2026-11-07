#!/usr/bin/env bash
# CI 개발 배포의 ECR 푸시 단계. 확인한 이미지(filter:check)를 커밋 태그로 올리고 digest를 출력한다.
# 환경 변수: ECR_REPOSITORY
set -e

TAG="${GITHUB_SHA::12}"
docker tag filter:check "$ECR_REPOSITORY:$TAG"
docker push "$ECR_REPOSITORY:$TAG"
DIGEST=$(aws ecr describe-images --repository-name "${ECR_REPOSITORY#*/}" --image-ids imageTag="$TAG" \
  --query 'imageDetails[0].imageDigest' --output text)
echo "digest=$DIGEST" >> "$GITHUB_OUTPUT"
