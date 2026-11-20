"""시계열 요약·통계. 순수 함수라 DB 없이 테스트할 수 있다."""
from statistics import mean, median, stdev

FLAT_THRESHOLD_PCT = 0.1  # 변화율 절댓값이 이보다 작으면 '유지'
WINDOW = 12  # 12개월 평균은 계절 변동(±3ppm)을 상쇄한다
GROWTH_YEARS = 10  # 연간 증가량 평균에 쓰는 최근 연도 수


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


def yearly_means(rows: list[dict]) -> list[dict]:
    """연도별 평균. count 가 12 미만인 연도는 complete=False (부분 연도)."""
    by_year: dict[int, list[float]] = {}
    for r in rows:
        by_year.setdefault(int(r["date"][:4]), []).append(r["value"])
    return [{"year": y, "mean": round(mean(v), 2), "count": len(v), "complete": len(v) >= 12}
            for y, v in sorted(by_year.items())]


def annual_growth(yearly: list[dict]) -> list[dict]:
    """연속한 두 '완전한' 연도의 평균 차이 (ppm/년). 부분 연도는 비교에서 제외."""
    by = {y["year"]: y for y in yearly if y["complete"]}
    return [{"year": y, "growth": round(by[y]["mean"] - by[y - 1]["mean"], 2)}
            for y in sorted(by) if y - 1 in by]


def recent_growth(yearly: list[dict]):
    growth = annual_growth(yearly)[-GROWTH_YEARS:]
    return round(mean(g["growth"] for g in growth), 2) if growth else None


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
            "median": round(median(values), 2),
            "stdev": round(stdev(values), 2) if len(values) > 1 else 0.0,
            "max": hi["value"], "max_date": hi["date"],
            "min": lo["value"], "min_date": lo["date"],
            "recent_annual_growth_ppm": recent_growth(yearly_means(rows)),
        },
        "latest": {"date": rows[-1]["date"], "value": rows[-1]["value"]},
        "trend": _trend(values),
    }


def build_statistics(records: list[dict]) -> dict:
    """그래프·추가 지표용: 연평균 시계열과 연간 증가량."""
    rows = sorted(records, key=lambda r: r["date"])
    yearly = yearly_means(rows)
    growth = annual_growth(yearly)
    return {
        "yearly": yearly,
        "annual_growth": growth,
        "recent_annual_growth_ppm": recent_growth(yearly),
        "growth_basis": f"완전한 연도(12개월) 기준 최근 최대 {GROWTH_YEARS}개 연간 증가량 평균",
    }
