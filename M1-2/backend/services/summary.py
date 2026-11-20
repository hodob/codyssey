"""시계열 요약. 순수 함수라 DB 없이 테스트할 수 있다."""
from statistics import mean

FLAT_THRESHOLD_PCT = 0.1  # 변화율 절댓값이 이보다 작으면 '유지'
WINDOW = 12  # 12개월 평균은 계절 변동(±3ppm)을 상쇄한다


def _trend(values: list[float]) -> dict:
    n = len(values)
    if n >= 2 * WINDOW:
        recent, prev = values[-WINDOW:], values[-2 * WINDOW:-WINDOW]
        basis = f"최근 {WINDOW}개 평균 vs 직전 {WINDOW}개 평균"
    elif n >= 4:
        half = n // 2
        recent, prev = values[-half:], values[:half]
        basis = "후반부 평균 vs 전반부 평균"
    else:
        return {"direction": "판단불가", "description": "데이터가 부족해 추세를 계산할 수 없음"}
    change = mean(recent) - mean(prev)
    pct = change / mean(prev) * 100 if mean(prev) else 0.0
    direction = "유지" if abs(pct) < FLAT_THRESHOLD_PCT else ("상승" if change > 0 else "하락")
    return {
        "direction": direction,
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "basis": basis,
        "description": f"{direction} ({basis}: {change:+.2f}, {pct:+.2f}%)",
    }


def summarize(records: list[dict]) -> dict:
    """records: [{'date': 'YYYY-MM-DD', 'value': float}, ...]"""
    if not records:
        return {"period": None, "count": 0, "metrics": {}, "latest": None,
                "trend": {"direction": "판단불가", "description": "데이터 없음"}}
    rows = sorted(records, key=lambda r: r["date"])
    values = [r["value"] for r in rows]
    hi = max(rows, key=lambda r: r["value"])
    lo = min(rows, key=lambda r: r["value"])
    return {
        "period": f"{rows[0]['date'][:7]} ~ {rows[-1]['date'][:7]}",
        "count": len(rows),
        "metrics": {
            "average": round(mean(values), 2),
            "max": hi["value"], "max_date": hi["date"],
            "min": lo["value"], "min_date": lo["date"],
        },
        "latest": {"date": rows[-1]["date"], "value": rows[-1]["value"]},
        "trend": _trend(values),
    }
