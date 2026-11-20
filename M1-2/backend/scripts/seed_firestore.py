"""마우나로아 실측 CO2 를 Firestore data 컬렉션에 적재 (여러 번 실행해도 안전).

실행 (backend/ 에서): python scripts/seed_firestore.py
- value = 실측 co2 (결측·제공처 보간 월 제외), memo = 관측소
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "src"))

from collect_data import RAW, parse  # noqa: E402
from services.firebase import DATA, get_db  # noqa: E402


def build_records() -> list[tuple[str, dict]]:
    rows, _ = parse(RAW.read_bytes())
    out = []
    for r in rows:
        if r["co2"] is None:
            continue
        doc_id = f"mlo-{r['year']:04d}-{r['month']:02d}"
        out.append((doc_id, {"date": f"{r['year']:04d}-{r['month']:02d}-15",
                             "value": r["co2"], "memo": r["station"]}))
    return out


def main() -> None:
    db = get_db()
    records = build_records()
    for i in range(0, len(records), 400):
        batch = db.batch()
        for doc_id, payload in records[i:i + 400]:
            batch.set(db.collection(DATA).document(doc_id), payload)
        batch.commit()
    print(f"{len(records)}개 레코드 적재 완료")


if __name__ == "__main__":
    main()
