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


def fake_ask(summary, history, question, run_tool=None):
    # 실제 GPT 대신: 질문에 '오늘/최근'이 있으면 도구를 실제로 실행해 보여 준다 (배선 확인용)
    used, extra = [], ""
    if run_tool and any(w in question for w in ("오늘", "어제", "최근", "특이")):
        used.append("get_today_highlights()")
        extra = "\n도구 결과: " + run_tool("get_today_highlights", {})[:300]
    return {"reply": f"[개발용 가짜 응답] 질문: {question}\n월별 {summary['count']}개, 평균 {summary['metrics'].get('average')} ppm{extra}",
            "tools_used": used, "usage": {"prompt_tokens": 0, "completion_tokens": 0}}


def fake_complete(system, user, model=None, max_tokens=None):
    return {"text": "[개발용 가짜 브리핑] " + user.splitlines()[0].lstrip("- "), "usage": {}}


llm.ask = fake_ask
llm.complete = fake_complete

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
