"""Pydantic 요청/응답 모델. 잘못된 입력은 FastAPI 가 422 로 거절한다."""
import math
from datetime import date as Date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DataIn(BaseModel):
    date: Date
    value: float
    memo: str = Field(default="", max_length=200)

    @field_validator("value")
    @classmethod
    def finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be a finite number")
        return v


class DataOut(BaseModel):
    id: str
    date: Date
    value: float
    memo: str = ""


class DataList(BaseModel):
    total: int
    items: list[DataOut]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list, max_length=10)  # 이 답변에 사용된 도구 호출 기록


class ConversationIn(BaseModel):
    title: str = Field(default="새 대화", min_length=1, max_length=100)
    messages: list[Message] = Field(min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    """목록용: messages 는 포함하지 않는다 (불러오기는 GET /api/conversations/{id})."""
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationOut(ConversationSummary):
    messages: list[Message]


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


class ChatOut(BaseModel):
    reply: str
    conversation_id: str
    tools_used: list[str] = []
    usage: Optional[dict[str, int]] = None
    model: Optional[str] = None
