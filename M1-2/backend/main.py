from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from routers import chat, conversations, data

app = FastAPI(
    title="CO2 데이터 AI 비서 API",
    description="마우나로아 월별 CO2 시계열을 요약해 GPT 에 주입하는 챗봇 백엔드",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "docs": "/docs"}
