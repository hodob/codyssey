from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted

import config
from routers import briefing, chat, conversations, data

app = FastAPI(
    title="CO2 데이터 AI 비서 API",
    description="마우나로아 월별 CO2 시계열을 요약해 GPT 에 주입하는 챗봇 백엔드",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(GoogleAPICallError)
async def firestore_error(request: Request, exc: GoogleAPICallError):
    # 처리하지 않은 500 은 CORS 헤더가 붙지 않아 브라우저에 'CORS 오류'로만 보인다.
    # 여기서 503 으로 바꾸면 CORS 헤더가 유지되고 화면에 원인이 표시된다.
    quota = isinstance(exc, ResourceExhausted)
    msg = ("데이터베이스(Firestore) 무료 사용량 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
           if quota else "데이터베이스 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
    return JSONResponse(status_code=503, content={"detail": msg})


app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(briefing.router)
app.include_router(chat.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "docs": "/docs"}
