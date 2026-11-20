"""월별(Scripps) 최신 자료를 가져와 새 달만 data 컬렉션에 추가한다."""
import csv
import re
import time
import urllib.request

from services import repository as repo
from services.firebase import DATA

URL = "https://keelinglabsites.ucsd.edu/websitedataco2/monthly_in_situ_co2_mlo.csv"
COOLDOWN_SECONDS = 600
_last = {"at": None}


class Cooldown(Exception):
    def __init__(self, remaining: int):
        super().__init__(remaining)
        self.remaining = remaining


class SourceUnavailable(Exception):
    pass


def parse(text: str) -> list[dict]:
    """연도로 시작하는 행만 읽고, 결측(-99.99)·비정상 값은 건너뛴다. 실측 co2 열(5번째)만 쓴다."""
    out = []
    for line in text.splitlines():
        if not re.match(r"^\s*\d{4},", line):
            continue
        cells = [c.strip() for c in next(csv.reader([line], skipinitialspace=True))]
        if len(cells) < 11:
            continue
        try:
            year, month, value = int(cells[0]), int(cells[1]), float(cells[4])
        except ValueError:
            continue
        if not (1 <= month <= 12 and 200 < value < 1000):
            continue
        out.append({"id": f"mlo-{year:04d}-{month:02d}", "date": f"{year:04d}-{month:02d}-15",
                    "value": value, "memo": cells[10] or "MLO"})
    return out


def fetch() -> str:
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "co2-ai-assistant/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8-sig", "replace")
    except Exception as e:  # noqa: BLE001
        raise SourceUnavailable("Scripps 월별 자료를 가져오지 못했습니다.") from e


def refresh(db) -> dict:
    now = time.monotonic()
    if _last["at"] is not None and now - _last["at"] < COOLDOWN_SECONDS:
        raise Cooldown(int(COOLDOWN_SECONDS - (now - _last["at"])))
    _last["at"] = now   # 실패해도 연타를 막기 위해 시도 시점을 기록
    source = parse(fetch())
    if not source:
        raise SourceUnavailable("Scripps 자료에서 유효한 행을 찾지 못했습니다.")
    existing = repo.list_data(db)
    have_ids = {r["id"] for r in existing}
    have_months = {r["date"][:7] for r in existing}   # 직접 추가한 같은 달 데이터를 덮어쓰지 않는다
    new = [r for r in source if r["id"] not in have_ids and r["date"][:7] not in have_months]
    for r in new:
        db.collection(DATA).document(r["id"]).set({"date": r["date"], "value": r["value"], "memo": r["memo"]})
    if new:
        repo.clear_cache()
    return {"added": len(new), "added_months": [r["date"][:7] for r in new],
            "source_latest": source[-1]["date"][:7], "total": len(existing) + len(new)}
