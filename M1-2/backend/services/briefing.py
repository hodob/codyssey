"""오늘의 AI 브리핑: 사실은 코드가 계산하고, GPT 는 서술만 한다. 새 데이터 날짜당 1회만 생성."""
import threading
from datetime import datetime, timedelta, timezone

import config
from services import daily, llm

COLLECTION = "briefings"
KST = timezone(timedelta(hours=9))
_lock = threading.Lock()
_memory: dict[str, dict] = {}

SYSTEM = ("당신은 CO2 관측 브리핑 작성자입니다. 주어진 사실만 사용해 한국어 3~4문장으로 '최근 관측의 특이사항'을 요약하세요. "
          "관측 자료는 1~2일 늦게 올라오므로 관측일을 '오늘'이라고 부르지 말고 '최근 관측일(날짜)'이라고 쓰세요. "
          "숫자는 그대로 쓰고 새 수치나 원인을 지어내지 마세요. 일별 값은 NOAA 잠정치임을 한 번 언급하세요. "
          "특이사항이 없으면 '큰 이상 없음'이라고 말하세요.")


def _fallback_text(h: dict) -> str:
    return " ".join(h["facts"][:3])


def _public(doc: dict, cached: bool) -> dict:
    return {**doc, "cached": cached}


def get_briefing(db, today=None) -> dict:
    today = today or datetime.now(KST).date()
    h = daily.build_highlights(daily.fetch_rows(), today)
    asof = h["asof"]
    if asof in _memory:
        return _public(_memory[asof], True)
    with _lock:                      # 동시 요청이 와도 GPT 호출은 한 번
        if asof in _memory:
            return _public(_memory[asof], True)
        ref = db.collection(COLLECTION).document(asof)
        try:
            snap = ref.get()
            if snap.exists:
                _memory[asof] = snap.to_dict()
                return _public(_memory[asof], True)
        except Exception:            # noqa: BLE001 - 저장소 장애여도 브리핑은 생성
            snap = None
        base = {"asof": asof, "latest": h["latest"], "facts": h["facts"], "notable": h["notable"],
                "source": h["source"], "generated_at": datetime.now(KST).isoformat()}
        try:
            res = llm.complete(SYSTEM, "\n".join(f"- {f}" for f in h["facts"]),
                               model=config.BRIEFING_MODEL, max_tokens=config.BRIEFING_MAX_TOKENS)
            if not res["text"]:
                raise llm.LLMError("빈 응답")
            doc = {**base, "text": res["text"], "ai": True, "model": config.BRIEFING_MODEL,
                   "usage": res["usage"]}
            try:
                ref.set(doc)
            except Exception:        # noqa: BLE001
                pass
            _memory[asof] = doc
            return _public(doc, False)
        except llm.LLMError:
            # AI 실패 시 계산된 사실로 대체. 저장·캐시하지 않아 다음 요청에서 다시 시도한다.
            return _public({**base, "text": _fallback_text(h), "ai": False, "model": None, "usage": None}, False)
