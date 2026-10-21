# 필터 서버를 Lambda(arm64) 컨테이너 이미지로 만든다. Lambda Web Adapter가 Lambda 호출을 FastAPI HTTP 요청으로 바꾼다.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 \
     /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /var/task

# 기본 PyPI의 linux/arm64 torch는 CUDA 패키지를 함께 받아 5.4GB가 된다. CPU 빌드(1.1GB)를 먼저 설치한다.
COPY requirements-image.txt ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu \
 && pip install --no-cache-dir -r requirements-image.txt

COPY server/ server/
COPY src/local_pipeline.py src/local_pipeline.py
COPY src/rules/ src/rules/
COPY results/kold-classifier/threat-ctx-v1-reviewed/best/ results/kold-classifier/threat-ctx-v1-reviewed/best/

# 모델 로딩이 Lambda 초기화 상한(10초)에 가까울 수 있어 준비 확인을 첫 호출로 넘긴다(AWS_LWA_ASYNC_INIT).
ENV AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_ASYNC_INIT=true \
    HF_HUB_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
