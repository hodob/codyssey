"""컨텍스트 주입: 데이터 요약을 시스템 프롬프트에 넣어 GPT 를 호출한다."""
import config

SYSTEM_TEMPLATE = """당신은 데이터 분석 비서입니다.
사용자의 데이터는 하와이 마우나로아 관측소의 월별 대기 CO2 농도(ppm)입니다.

[사용자 데이터 요약]
- 데이터 기간: {period}
- 총 레코드: {count}개
- 주요 지표: {metrics}
- 가장 최근 값: {latest}
- 최근 트렌드: {trend}

(recent_annual_growth_ppm = 완전한 연도 기준 최근 최대 10개 연간 증가량의 평균, 단위 ppm/년)

위 데이터를 기반으로 맞춤형 답변을 한국어로 간결하게 제공하세요.
요약에 없는 수치는 지어내지 말고, 모르면 모른다고 말하세요."""


class LLMError(Exception):
    pass


def build_system_prompt(summary: dict) -> str:
    return SYSTEM_TEMPLATE.format(
        period=summary["period"] or "없음", count=summary["count"],
        metrics=summary["metrics"] or "없음", latest=summary["latest"] or "없음",
        trend=summary["trend"]["description"],
    )


def ask(summary: dict, history: list[dict], question: str) -> str:
    if not config.OPENAI_API_KEY:
        raise LLMError("OPENAI_API_KEY 가 설정되지 않았습니다.")
    from openai import OpenAI, OpenAIError

    messages = [{"role": "system", "content": build_system_prompt(summary)}]
    messages += history[-config.CHAT_HISTORY_LIMIT:]
    messages.append({"role": "user", "content": question})
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=60,
                        base_url=config.OPENAI_BASE_URL or None)
        # GPT-5 계열은 max_tokens/temperature 대신 max_completion_tokens 를 쓴다.
        # 추론 토큰도 이 한도에 포함되므로 너무 작게 잡으면 답이 비어 버린다.
        res = client.chat.completions.create(
            model=config.OPENAI_MODEL, messages=messages,
            max_completion_tokens=config.OPENAI_MAX_TOKENS)
    except OpenAIError as e:
        raise LLMError(f"OpenAI 호출 실패: {type(e).__name__}") from e
    return (res.choices[0].message.content or "").strip()
