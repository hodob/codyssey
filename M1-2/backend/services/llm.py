"""GPT 호출: 컨텍스트 주입(월별 요약) + 도구 호출(최신·기간 조회) + 컨텍스트 예산 관리.

컨텍스트 최적화 원칙
1. 항상 필요한 것(월별 요약)만 시스템 프롬프트에 넣고, 최신값·특정 기간은 필요할 때 도구로 조회한다.
2. 고정 지침을 앞에, 바뀌는 데이터를 뒤에 둔다 (프롬프트 접두 캐시에 유리).
3. 이전 대화는 개수·글자수 상한을 두고, 오래된 긴 답변은 잘라 보낸다.
4. 도구 결과는 압축 JSON 으로 만들고 길이를 제한한다. 왕복 횟수에도 상한을 둔다.
"""
import json
from datetime import datetime, timedelta, timezone

from openai import OpenAI, OpenAIError

import config
from services import tools as tool_mod

SYSTEM_TEMPLATE = """당신은 마우나로아 CO2(ppm) 데이터 분석 비서입니다. 한국어로 간결하게 답하세요.
- 아래 요약과 도구 결과에 있는 수치만 쓰고, 없으면 모른다고 하세요. 원인·수치를 지어내지 마세요.
- 오늘·어제·최근 며칠 값이나 특이사항은 get_recent_daily / get_today_highlights, 특정 월·기간 값은 get_monthly_range 도구로 조회하세요.
- 일별 값은 NOAA 잠정치이며 월별(Scripps)과 방법이 달라 값이 조금 다를 수 있음을 밝히세요.
- 관측 자료는 1~2일 늦게 올라옵니다. 오늘·어제 값이 아직 없으면 있는 것처럼 말하지 말고 '가장 최근 관측일'의 값임을 날짜와 함께 알려주세요.

[사용자 데이터 요약 - 월별 Scripps]
- 오늘 날짜(KST) {today}
- 기간 {period}, {count}개월
- 평균 {average}, 중앙값 {median}, 표준편차 {stdev}
- 최고 {max} ({max_date}), 최저 {min} ({min_date})
- 최근 월 {latest}
- 추세 {trend}; 연간 증가 {growth}"""


class LLMError(Exception):
    pass


def _fmt(value, suffix=""):
    return "-" if value is None else f"{value}{suffix}"


KST = timezone(timedelta(hours=9))


def build_system_prompt(summary: dict, today=None) -> str:
    today = today or datetime.now(KST).date()
    m, latest, trend = summary.get("metrics") or {}, summary.get("latest"), summary.get("trend") or {}
    t = trend.get("direction", "판단불가")
    if "change" in trend:
        t += f" ({trend['change']:+} ppm, {trend['change_pct']:+}%, 최근12개월 vs 직전12개월)"
    return SYSTEM_TEMPLATE.format(
        today=today.isoformat(), period=summary.get("period") or "없음", count=summary.get("count", 0),
        average=_fmt(m.get("average")), median=_fmt(m.get("median")), stdev=_fmt(m.get("stdev")),
        max=_fmt(m.get("max")), max_date=_fmt(m.get("max_date")),
        min=_fmt(m.get("min")), min_date=_fmt(m.get("min_date")),
        latest=f"{latest['value']} ({latest['date']})" if latest else "없음", trend=t,
        growth=_fmt(m.get("recent_annual_growth_ppm"), " ppm/년(최근 10개 연도 평균)"))


def trim_history(history: list[dict]) -> list[dict]:
    """최근 N개 → 글자수 예산 안에서 최신부터 채우고, 오래된 긴 메시지는 잘라서 보낸다."""
    msgs = [{"role": m["role"], "content": m["content"]}
            for m in history[-config.CHAT_HISTORY_LIMIT:] if m.get("content")]
    out, used = [], 0
    for i, m in enumerate(reversed(msgs)):
        text = m["content"]
        if i > 0 and len(text) > config.HISTORY_PER_MESSAGE_CHARS:
            text = text[:config.HISTORY_PER_MESSAGE_CHARS] + "…"
        if out and used + len(text) > config.HISTORY_MAX_CHARS:
            break
        out.append({"role": m["role"], "content": text})
        used += len(text)
    out.reverse()
    while out and out[0]["role"] == "assistant":   # 역할 교대 유지
        out.pop(0)
    return out


def _client():
    if not config.OPENAI_API_KEY:
        raise LLMError("OPENAI_API_KEY 가 설정되지 않았습니다.")
    return OpenAI(api_key=config.OPENAI_API_KEY, timeout=60, base_url=config.OPENAI_BASE_URL or None)


def _add_usage(total: dict, res) -> None:
    u = getattr(res, "usage", None)
    if u:
        total["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
        total["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0


def _label(name: str, args) -> str:
    inner = ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else ""
    return f"{name}({inner})"


def ask(summary: dict, history: list[dict], question: str, run_tool=None) -> dict:
    """반환: {'reply', 'tools_used': [라벨], 'usage': {...}}. run_tool(name, args) -> str."""
    client = _client()
    messages = ([{"role": "system", "content": build_system_prompt(summary)}]
                + trim_history(history) + [{"role": "user", "content": question}])
    used, usage = [], {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        for round_no in range(config.MAX_TOOL_ROUNDS + 1):
            kwargs = {"model": config.OPENAI_MODEL, "messages": messages,
                      "max_completion_tokens": config.OPENAI_MAX_TOKENS}
            if run_tool is not None and round_no < config.MAX_TOOL_ROUNDS:   # 마지막 왕복은 도구 없이 답하게 강제
                kwargs["tools"] = tool_mod.TOOL_SCHEMAS
            res = client.chat.completions.create(**kwargs)
            _add_usage(usage, res)
            msg = res.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                return {"reply": (msg.content or "").strip(), "tools_used": used, "usage": usage}
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]})
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                used.append(_label(c.function.name, args))
                out = run_tool(c.function.name, args if args is not None else "bad")
                messages.append({"role": "tool", "tool_call_id": c.id, "content": out})
    except OpenAIError as e:
        raise LLMError(f"OpenAI 호출 실패: {type(e).__name__}") from e
    raise LLMError("도구 호출이 끝나지 않았습니다.")


def complete(system: str, user: str, model: str | None = None, max_tokens: int | None = None) -> dict:
    """도구 없는 단발 호출 (브리핑 등). 반환: {'text', 'usage'}."""
    client = _client()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        res = client.chat.completions.create(
            model=model or config.OPENAI_MODEL, max_completion_tokens=max_tokens or config.OPENAI_MAX_TOKENS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except OpenAIError as e:
        raise LLMError(f"OpenAI 호출 실패: {type(e).__name__}") from e
    _add_usage(usage, res)
    return {"text": (res.choices[0].message.content or "").strip(), "usage": usage}
