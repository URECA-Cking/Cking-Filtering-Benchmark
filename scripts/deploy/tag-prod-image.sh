#!/usr/bin/env bash
# CI 운영 배포의 운영 태그 붙이기 단계.
# 태그는 덮어쓸 수 없어, 같은 커밋을 다시 실행하면 이미 붙은 태그가 같은 이미지인지만 본다.
# 매니페스트는 받은 그대로 넣는다. 파일로 쓰면 끝에 줄바꿈이 붙어 digest가 달라지고, --image-digest로 ECR이 다르면 거부한다.
# 환경 변수: ECR_REPOSITORY, DIGEST
set -e

REPO="${ECR_REPOSITORY#*/}"
TAG="prod-${GITHUB_SHA::12}"
if EXISTING=$(aws ecr describe-images --repository-name "$REPO" --image-ids imageTag="$TAG" \
    --query 'imageDetails[0].imageDigest' --output text 2>/dev/null); then
  [ "$EXISTING" = "$DIGEST" ] || { echo "::error::$TAG 가 다른 이미지($EXISTING)에 붙어 있다"; exit 1; }
  exit 0
fi
read -r MEDIA < <(aws ecr batch-get-image --repository-name "$REPO" --image-ids imageDigest="$DIGEST" \
  --query 'images[0].imageManifestMediaType' --output text)
MANIFEST=$(aws ecr batch-get-image --repository-name "$REPO" --image-ids imageDigest="$DIGEST" \
  --query 'images[0].imageManifest' --output text)
aws ecr put-image --repository-name "$REPO" --image-tag "$TAG" --image-manifest "$MANIFEST" \
  --image-manifest-media-type "$MEDIA" --image-digest "$DIGEST" --query 'image.imageId.imageTag' --output text
