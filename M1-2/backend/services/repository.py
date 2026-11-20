"""Firestore 읽기/쓰기. 컬렉션: data(분석 데이터), conversations(대화 기록)."""
import time
from datetime import datetime, timezone

from google.api_core.exceptions import GoogleAPICallError

from services.firebase import CONVERSATIONS, DATA

# data 컬렉션 전체(약 800개)를 요청마다 읽으면 Firestore 무료 읽기 한도(하루 5만 건)를 금방 넘는다.
# 서버 메모리에 캐시하고, 이 서버를 통한 쓰기는 즉시 무효화한다.
CACHE_TTL_SECONDS = 3600
_cache = {"items": None, "at": 0.0}


def clear_cache() -> None:
    _cache["items"], _cache["at"] = None, 0.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- data ----
def _data_item(doc) -> dict:
    d = doc.to_dict()
    return {"id": doc.id, "date": d["date"], "value": d["value"], "memo": d.get("memo", "")}


def list_data(db) -> list[dict]:
    if _cache["items"] is not None and time.monotonic() - _cache["at"] < CACHE_TTL_SECONDS:
        return list(_cache["items"])
    try:
        items = sorted((_data_item(d) for d in db.collection(DATA).stream()), key=lambda r: r["date"])
    except GoogleAPICallError:
        if _cache["items"] is not None:  # 한도 초과 등 일시 오류: 오래된 캐시라도 응답
            return list(_cache["items"])
        raise
    _cache["items"], _cache["at"] = items, time.monotonic()
    return list(items)


def create_data(db, payload: dict) -> dict:
    ref = db.collection(DATA).document()
    ref.set(payload)
    clear_cache()
    return {"id": ref.id, **payload}


def update_data(db, doc_id: str, payload: dict):
    ref = db.collection(DATA).document(doc_id)
    if not ref.get().exists:
        return None
    ref.set(payload)
    clear_cache()
    return {"id": doc_id, **payload}


def delete_data(db, doc_id: str) -> bool:
    ref = db.collection(DATA).document(doc_id)
    if not ref.get().exists:
        return False
    ref.delete()
    clear_cache()
    return True


# ---- conversations ----
def _conv(doc, with_messages: bool) -> dict:
    d = doc.to_dict()
    out = {"id": doc.id, "title": d["title"], "message_count": len(d["messages"]),
           "created_at": d["created_at"], "updated_at": d["updated_at"]}
    if with_messages:
        out["messages"] = d["messages"]
    return out


def create_conversation(db, title: str, messages: list[dict]) -> dict:
    ref = db.collection(CONVERSATIONS).document()
    ts = now()
    ref.set({"title": title, "messages": messages, "created_at": ts, "updated_at": ts})
    return _conv(ref.get(), True)


def get_conversation(db, conv_id: str):
    doc = db.collection(CONVERSATIONS).document(conv_id).get()
    return _conv(doc, True) if doc.exists else None


def list_conversations(db) -> list[dict]:
    items = [_conv(d, False) for d in db.collection(CONVERSATIONS).stream()]
    return sorted(items, key=lambda r: r["updated_at"], reverse=True)


def append_messages(db, conv_id: str, new_messages: list[dict]):
    ref = db.collection(CONVERSATIONS).document(conv_id)
    doc = ref.get()
    if not doc.exists:
        return None
    messages = doc.to_dict()["messages"] + new_messages
    ref.update({"messages": messages, "updated_at": now()})
    return _conv(ref.get(), True)


def delete_conversation(db, conv_id: str) -> bool:
    ref = db.collection(CONVERSATIONS).document(conv_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True
