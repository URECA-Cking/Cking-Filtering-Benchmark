#!/usr/bin/env bash
# 필터 이미지를 빌드한다. 모델 경로는 src/local_pipeline.py의 MODEL_DIR 한 곳에서만 정하고 여기서 읽는다.
# 모델 파일은 model/<모델 이름>/에 모은다. 로컬 학습 결과(MODEL_DIR)가 있으면 그것을, 없으면 개발 배포 버킷의
# filter/models/<모델 이름>/best/를 쓴다. 모델 이름은 MODEL_DIR의 상위 폴더 이름이다.
# 사용법: scripts/build-image.sh <이미지 태그>
set -euo pipefail

TAG="${1:?사용법: scripts/build-image.sh <이미지 태그>}"
cd "$(dirname "$0")/.."

MODEL_DIR=$(python3 -I -c 'import sys; sys.path.insert(0, "."); from src.local_pipeline import MODEL_DIR, ROOT; print(MODEL_DIR.relative_to(ROOT).as_posix())')
MODEL_NAME=$(basename "$(dirname "$MODEL_DIR")")
STAGE="model/$MODEL_NAME"

if [ ! -f "$STAGE/stage2_config.json" ]; then
  mkdir -p "$STAGE"
  if [ -f "$MODEL_DIR/stage2_config.json" ]; then
    cp -R "$MODEL_DIR/." "$STAGE/"
  else
    aws s3 sync --only-show-errors "s3://dev-cking-deploy-551372961758/filter/models/$MODEL_NAME/best/" "$STAGE/"
  fi
fi
echo "모델 $MODEL_NAME → 이미지 안 $MODEL_DIR"

# Lambda는 여러 아키텍처를 묶은 이미지 목록을 받지 않으므로 출처 증명(attestation)을 붙이지 않는다.
docker build --platform linux/arm64 --provenance=false --sbom=false \
  --build-arg "MODEL_NAME=$MODEL_NAME" --build-arg "MODEL_DIR=$MODEL_DIR" -t "$TAG" .
