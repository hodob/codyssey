"""최신 보조 출처: NOAA GML 마우나로아 일별 CO2 (잠정치).

월별(Scripps)은 1~2개월 늦다. 같은 관측소의 일별 자료로 '오늘의 특이사항'을 계산한다.
전체 파일(약 1.6만 행)을 Firestore 에 올리지 않고 서버 메모리에만 둔다 (무료 한도 보호).
"""
import time
import urllib.request
from datetime import date, timedelta
from statistics import mean, pstdev

URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.csv"
SOURCE = "NOAA GML 마우나로아 일별 (잠정치)"
TTL_SECONDS = 6 * 3600
BIG_MOVE_SIGMA = 2.5   # 전일 대비 변화가 최근 일간 변동의 이 배수를 넘으면 '큰 변동'
YOY_Z_LIMIT = 2.0      # 전년 대비 증가폭의 z-점수 한계
_cache = {"rows": None, "at": 0.0}


class DailyUnavailable(Exception):
    pass


def clear_cache() -> None:
    _cache["rows"], _cache["at"] = None, 0.0


def parse(text: str) -> list[tuple[date, float]]:
    """'#' 주석과 결측(-999.99 등)을 건너뛰고 (날짜, ppm) 목록을 만든다."""
    rows = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        p = line.split(",")
        if len(p) < 5:
            continue
        try:
            d, v = date(int(p[0]), int(p[1]), int(p[2])), float(p[4])
        except ValueError:
            continue
        if 200 < v < 1000:
            rows.append((d, v))
    rows.sort()
    return rows


def fetch_rows() -> list[tuple[date, float]]:
    if _cache["rows"] is not None and time.monotonic() - _cache["at"] < TTL_SECONDS:
        return _cache["rows"]
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "co2-ai-assistant/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            rows = parse(r.read().decode("utf-8", "replace"))
        if not rows:
            raise ValueError("no rows")
    except Exception as e:  # noqa: BLE001 - 네트워크/파싱 모두 같은 처리
        if _cache["rows"] is not None:   # 일시 장애: 오래된 값이라도 응답
            return _cache["rows"]
        raise DailyUnavailable("NOAA 일별 자료를 가져오지 못했습니다.") from e
    _cache["rows"], _cache["at"] = rows, time.monotonic()
    return rows


def recent(rows: list[tuple[date, float]], days: int) -> list[tuple[date, float]]:
    """가장 최근 관측일 기준 days 일 안의 관측."""
    if not rows:
        return []
    cut = rows[-1][0] - timedelta(days=days - 1)
    return [r for r in rows if r[0] >= cut]


def build_highlights(rows: list[tuple[date, float]], today: date | None = None) -> dict:
    """특이사항을 결정적으로 계산한다 (LLM 은 이 사실만 서술한다)."""
    if not rows:
        raise ValueError("no rows")
    by = dict(rows)
    d, v = rows[-1]
    out: dict = {"asof": d.isoformat(), "latest": {"date": d.isoformat(), "value": v},
                 "source": SOURCE, "facts": [], "notable": []}
    facts, notable = out["facts"], out["notable"]
    facts.append(f"가장 최근 관측일 {d.isoformat()}: {v:.2f} ppm")

    # 전일 대비 (직전 관측이 3일 이내일 때만)
    if len(rows) > 1 and (d - rows[-2][0]).days <= 3:
        change = v - rows[-2][1]
        out["change_vs_prev"] = round(change, 2)
        diffs = [b[1] - a[1] for a, b in zip(rows[-121:-1], rows[-120:]) if (b[0] - a[0]).days <= 3]
        sd = pstdev(diffs) if len(diffs) > 10 else 0
        text = f"전일({rows[-2][0].isoformat()}) 대비 {change:+.2f} ppm"
        if sd and abs(change) > BIG_MOVE_SIGMA * sd:
            notable.append("big_daily_move")
            text += f" — 최근 일간 변동 폭(σ={sd:.2f})에 비해 큰 변화"
        facts.append(text)

    # 최근 7일·30일 평균과 30일 범위
    r7, r30 = recent(rows, 7), recent(rows, 30)
    out["avg7"] = round(mean(x for _, x in r7), 2)
    out["avg30"] = round(mean(x for _, x in r30), 2)
    hi, lo = max(r30, key=lambda r: r[1]), min(r30, key=lambda r: r[1])
    out["range30"] = {"max": hi[1], "max_date": hi[0].isoformat(), "min": lo[1], "min_date": lo[0].isoformat()}
    facts.append(f"최근 7일 평균 {out['avg7']:.2f}, 30일 평균 {out['avg30']:.2f} ppm (오늘 값은 30일 평균보다 {v - out['avg30']:+.2f})")
    if len(r30) >= 10 and v == hi[1]:
        notable.append("max_30d")
        facts.append("최근 30일 중 최고치")
    elif len(r30) >= 10 and v == lo[1]:
        notable.append("min_30d")
        facts.append("최근 30일 중 최저치")

    # 전년 동기 대비: 1년 전 ±3일 평균과 비교, 최근 120일 분포로 z-점수
    def yoy(day: date):
        if day not in by:
            return None
        base = [by[b] for k in range(-3, 4) if (b := day - timedelta(days=365 + k)) in by]
        return by[day] - mean(base) if len(base) >= 3 else None

    now = yoy(d)
    if now is not None:
        out["yoy"] = {"diff": round(now, 2)}
        hist = [y for k in range(1, 121) if (y := yoy(d - timedelta(days=k))) is not None]
        text = f"작년 같은 시기보다 {now:+.2f} ppm"
        if len(hist) >= 30 and pstdev(hist) > 0:
            z = (now - mean(hist)) / pstdev(hist)
            out["yoy"]["z"] = round(z, 2)
            if abs(z) >= YOY_Z_LIMIT:
                notable.append("yoy_outlier_high" if z > 0 else "yoy_outlier_low")
                text += f" — 최근 4개월 평균 증가폭(≈{mean(hist):+.2f})보다 이례적으로 {'크다' if z > 0 else '작다'} (z={z:+.1f})"
        facts.append(text)

    if today is not None and (today - d).days >= 4:
        notable.append("stale")
        facts.append(f"최신 관측일이 {(today - d).days}일 전입니다 (NOAA 갱신 지연 가능)")
    if not notable:
        facts.append("특이사항 없음: 계절 변동과 장기 상승 추세 범위 안")
    return out
