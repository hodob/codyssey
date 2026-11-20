"""챗봇이 호출하는 내부 도구(Function Calling). 인자는 신뢰하지 않고 검증한다."""
import json
import re
from datetime import datetime, timedelta, timezone

from services import daily
from services import repository as repo

KST = timezone(timedelta(hours=9))
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_MONTH_ROWS = 36

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_recent_daily",
        "description": "최근 N일의 일별 CO2(ppm, NOAA 잠정치). 오늘·어제·최근 며칠 값을 물을 때 사용.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 30, "description": "조회 일수(기본 7)"}}}}},
    {"type": "function", "function": {
        "name": "get_today_highlights",
        "description": "오늘의 특이사항(전일·전년 대비, 30일 범위, 이례 여부)을 계산한 결과. '오늘 특이사항/이상 있어?' 질문에 사용.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_monthly_range",
        "description": "월별 CO2(Scripps) 기간 조회. 특정 월·연도의 값이나 기간 비교에 사용. 36개월 초과 시 통계만 반환.",
        "parameters": {"type": "object", "properties": {
            "start": {"type": "string", "description": "시작 월 YYYY-MM"},
            "end": {"type": "string", "description": "끝 월 YYYY-MM"}},
            "required": ["start", "end"]}}},
]


def _freshness(latest) -> dict:
    """모델이 '오늘/어제'를 잘못 말하지 않게, 최신 관측일과 오늘 대비 지연 일수를 함께 준다."""
    today = datetime.now(KST).date()
    return {"today": today.isoformat(), "latest_date": latest.isoformat(), "lag_days": (today - latest).days}


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _recent_daily(args: dict, db) -> dict:
    try:
        days = int(args.get("days", 7))
    except (TypeError, ValueError):
        return {"error": "days 는 정수여야 합니다."}
    days = max(1, min(30, days))
    rows = daily.recent(daily.fetch_rows(), days)
    return {"source": daily.SOURCE, **(_freshness(rows[-1][0]) if rows else {}), "days": days, "n": len(rows),
            "avg": round(sum(v for _, v in rows) / len(rows), 2) if rows else None,
            "values": ";".join(f"{d.isoformat()[5:]}:{v:.2f}" for d, v in rows)}


def _today_highlights(args: dict, db) -> dict:
    h = daily.build_highlights(daily.fetch_rows())
    from datetime import date as _date
    return {"source": h["source"], **_freshness(_date.fromisoformat(h["asof"])),
            "facts": h["facts"], "notable": h["notable"]}


def _monthly_range(args: dict, db) -> dict:
    start, end = str(args.get("start", "")), str(args.get("end", ""))
    if not (MONTH_RE.match(start) and MONTH_RE.match(end)):
        return {"error": "start/end 는 YYYY-MM 형식이어야 합니다."}
    if start > end:
        return {"error": "start 가 end 보다 늦습니다."}
    rows = [r for r in repo.list_data(db) if start <= r["date"][:7] <= end]
    if not rows:
        return {"source": "Scripps 월별", "n": 0, "note": "해당 기간 데이터 없음"}
    vals = [r["value"] for r in rows]
    hi, lo = max(rows, key=lambda r: r["value"]), min(rows, key=lambda r: r["value"])
    out = {"source": "Scripps 월별", "n": len(rows), "avg": round(sum(vals) / len(vals), 2),
           "max": [hi["date"][:7], hi["value"]], "min": [lo["date"][:7], lo["value"]],
           "first": [rows[0]["date"][:7], rows[0]["value"]], "last": [rows[-1]["date"][:7], rows[-1]["value"]]}
    if len(rows) <= MAX_MONTH_ROWS:
        out["values"] = ";".join(f"{r['date'][:7]}:{r['value']}" for r in rows)
    else:
        out["note"] = f"{MAX_MONTH_ROWS}개월을 넘어 통계만 반환"
    return out


_RUNNERS = {"get_recent_daily": _recent_daily, "get_today_highlights": _today_highlights,
            "get_monthly_range": _monthly_range}


def run_tool(name: str, args: dict, db, limit: int = 2500) -> str:
    """도구 실행 결과를 JSON 문자열로. 오류도 모델이 읽을 수 있게 문자열로 돌려준다."""
    runner = _RUNNERS.get(name)
    if runner is None:
        return _dump({"error": f"알 수 없는 도구: {name}"})
    if not isinstance(args, dict):
        return _dump({"error": "인자가 객체가 아닙니다."})
    try:
        text = _dump(runner(args, db))
    except daily.DailyUnavailable as e:
        text = _dump({"error": str(e)})
    return text if len(text) <= limit else text[:limit] + '…(잘림)"}'
