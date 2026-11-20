"""키 없이 화면/API 를 점검하는 개발용 서버 (Firestore=메모리, GPT=가짜 응답).

실행 (backend/ 에서): python dev_server.py   → http://localhost:8000/docs
운영(Render)에서는 사용하지 않는다. 운영 진입점은 main:app.
"""
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from main import app  # noqa: E402
from seed_firestore import build_records  # noqa: E402
from services import llm  # noqa: E402
from services.firebase import DATA, get_db  # noqa: E402
from tests.fake_db import FakeDB  # noqa: E402

db = FakeDB()
for doc_id, payload in build_records():
    db.collection(DATA).document(doc_id).set(payload)
app.dependency_overrides[get_db] = lambda: db


def fake_ask(summary, history, question):
    # 실제 GPT 대신 주입된 요약을 그대로 보여 주는 답변 (컨텍스트 주입 확인용)
    return (f"[개발용 가짜 응답] 질문: {question}\n"
            f"기간 {summary['period']}, {summary['count']}개, 평균 {summary['metrics'].get('average')} ppm, "
            f"트렌드 {summary['trend']['description']}")


llm.ask = fake_ask

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
