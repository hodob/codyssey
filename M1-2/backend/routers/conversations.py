from fastapi import APIRouter, Depends, HTTPException

from schemas import ConversationIn, ConversationOut, ConversationSummary
from services import repository as repo
from services.firebase import get_db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201, summary="대화 저장")
def create(body: ConversationIn, db=Depends(get_db)):
    return repo.create_conversation(db, body.title, [m.model_dump() for m in body.messages])


@router.get("", response_model=list[ConversationSummary],
            summary="대화 목록 조회 (messages 미포함, 최신순)")
def list_all(db=Depends(get_db)):
    return repo.list_conversations(db)


@router.get("/{conv_id}", response_model=ConversationOut, summary="특정 대화 전체 messages 조회")
def get_one(conv_id: str, db=Depends(get_db)):
    conv = repo.get_conversation(db, conv_id)
    if conv is None:
        raise HTTPException(404, "대화를 찾을 수 없습니다.")
    return conv


@router.delete("/{conv_id}", status_code=204, summary="대화 삭제")
def delete(conv_id: str, db=Depends(get_db)):
    if not repo.delete_conversation(db, conv_id):
        raise HTTPException(404, "대화를 찾을 수 없습니다.")
