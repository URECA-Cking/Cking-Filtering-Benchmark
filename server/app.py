from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.local_pipeline import LocalFilter, MODEL_DIR

RULE_VERSION = "local-1"                 # 규칙을 바꿀 때마다 올린다
MODEL_VERSION = MODEL_DIR.parent.name    # threat-ctx-v1-reviewed

COMMENT_MAX_LENGTH = 500                 # Cking-BE의 댓글 최대 길이(CreatorPostComment.MAX_CONTENT_LENGTH)와 같다

app = FastAPI()
local_filter = LocalFilter()             # 서버가 켜질 때 한 번만 모델을 읽는다


class ModerateRequest(BaseModel):
    commentId: int
    content: str = Field(min_length=1, max_length=COMMENT_MAX_LENGTH)


@app.exception_handler(RequestValidationError)
def invalid_request(_request: Request, _error: RequestValidationError):
    # 기본 422 응답은 `input`에 요청 값을 그대로 돌려주는데, 그러면 댓글 원문이 호출한 쪽 로그에 남을 수 있다. 값은 빼고 상태만 알린다.
    return JSONResponse(status_code=422, content={"detail": "요청 형식이 올바르지 않습니다."})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/moderate")                   # async가 아니라 일반 def: 스레드 풀에서 돌아 서버가 막히지 않는다
def moderate(request: ModerateRequest):
    record = local_filter.moderate(request.content)
    return {
        "action": record["final"]["action"],
        "reasons": record["final"]["reasons"],
        "ruleVersion": RULE_VERSION,
        "modelVersion": MODEL_VERSION,
    }
