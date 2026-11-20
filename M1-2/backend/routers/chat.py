from fastapi import APIRouter, Depends, HTTPException

import config
from schemas import ChatIn, ChatOut
from services import llm, tools
from services import repository as repo
from services.firebase import get_db
from services.summary import summarize

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatOut,
             summary="AI 대화 (월별 요약 컨텍스트 주입 + 도구 호출 + 자동 저장)")
def chat(body: ChatIn, db=Depends(get_db)):
    history = []
    if body.conversation_id:
        conv = repo.get_conversation(db, body.conversation_id)
        if conv is None:
            raise HTTPException(404, "대화를 찾을 수 없습니다.")
        history = conv["messages"]

    summary = summarize(repo.list_data(db))                  # 1. 요약 조회
    try:                                                      # 2~3. 프롬프트 삽입 + GPT 호출(필요 시 도구)
        result = llm.ask(summary, history, body.message,
                         run_tool=lambda name, args: tools.run_tool(name, args, db))
    except llm.LLMError as e:
        raise HTTPException(502, str(e))

    reply = result["reply"] or "(빈 응답)"
    new = [{"role": "user", "content": body.message},
           {"role": "assistant", "content": reply, "tools": result["tools_used"]}]
    if body.conversation_id:                                  # 4. 자동 저장
        repo.append_messages(db, body.conversation_id, new)
        conv_id = body.conversation_id
    else:
        conv_id = repo.create_conversation(db, body.message[:30], new)["id"]
    return {"reply": reply, "conversation_id": conv_id,
            "tools_used": result["tools_used"], "usage": result["usage"], "model": config.OPENAI_MODEL}
