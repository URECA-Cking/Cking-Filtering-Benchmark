#!/usr/bin/env bash
# 필터 이미지를 빌드한다. 모델 경로는 src/local_pipeline.py의 MODEL_DIR 한 곳에서만 정하고 여기서 읽는다.
# 모델 파일은 model/<모델 이름>/에 모은다. 로컬 학습 결과(MODEL_DIR)가 있으면 그것을, 없으면 개발 배포 버킷의
# filter/models/<모델 이름>/best/를 쓴다. 모델 이름은 MODEL_DIR의 상위 폴더 이름이다.
# 모은 모델 파일은 model.sha256과 목록·내용이 같아야 한다.
# 사용법: scripts/build-image.sh <이미지 태그>
set -euo pipefail

TAG="${1:?사용법: scripts/build-image.sh <이미지 태그>}"
cd "$(dirname "$0")/.."

MODEL_DIR=$(python3 -I -B -c 'import sys; sys.path.insert(0, "."); from src.local_pipeline import MODEL_DIR, ROOT; print(MODEL_DIR.relative_to(ROOT).as_posix())')
MODEL_NAME=$(basename "$(dirname "$MODEL_DIR")")
STAGE="model/$MODEL_NAME"
SUMS="$PWD/model.sha256"

# 매 실행마다 원본과 맞춘다. 로컬 결과는 임시 폴더에 모두 복사한 뒤 통째로 바꾸고, S3는 빠지거나 바뀐 파일을 받고
# 원본에 없는 파일은 지운다. 어느 쪽이든 실패하면 빌드 전에 멈추고, 끊긴 받기는 다음 실행이 이어 받는다.
mkdir -p model
if [ -d "$MODEL_DIR" ]; then
  TMP=$(mktemp -d "model/.$MODEL_NAME.XXXXXX")
  trap 'rm -rf "$TMP"' EXIT
  cp -R "$MODEL_DIR/." "$TMP/"
  rm -rf "$STAGE"
  mv "$TMP" "$STAGE"
else
  # 크기가 같은 파일은 시각이 정확히 같을 때만 건너뛴다(기본값은 크기가 같으면 건너뜀).
  aws s3 sync --delete --exact-timestamps --only-show-errors \
    "s3://dev-cking-deploy-551372961758/filter/models/$MODEL_NAME/best/" "$STAGE/"
fi

(cd "$STAGE" && shasum -a 256 --check --quiet --strict "$SUMS")
if ! diff <(cut -c67- "$SUMS" | sort) <(cd "$STAGE" && find . -type f | sed 's|^\./||' | sort); then
  echo "모델 파일 목록이 model.sha256과 다르다"
  exit 1
fi
echo "모델 $MODEL_NAME → 이미지 안 $MODEL_DIR"

# Lambda는 여러 아키텍처를 묶은 이미지 목록을 받지 않으므로 출처 증명(attestation)을 붙이지 않는다.
docker build --platform linux/arm64 --provenance=false --sbom=false \
  --build-arg "MODEL_NAME=$MODEL_NAME" --build-arg "MODEL_DIR=$MODEL_DIR" -t "$TAG" .
