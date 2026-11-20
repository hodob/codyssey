import unittest
from unittest import mock

from fastapi.testclient import TestClient

from main import app
from google.api_core.exceptions import ResourceExhausted

from services import llm
from services import repository as repo
from services.firebase import get_db
from tests.fake_db import FakeDB


class ApiTest(unittest.TestCase):
    def setUp(self):
        repo.clear_cache()
        self.db = FakeDB()
        app.dependency_overrides[get_db] = lambda: self.db
        self.c = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def add(self, date="2024-01-15", value=420.5, memo="MLO"):
        return self.c.post("/api/data", json={"date": date, "value": value, "memo": memo})

    def test_data_crud(self):
        r = self.add()
        self.assertEqual(r.status_code, 201)
        i = r.json()["id"]
        self.assertEqual(self.c.get("/api/data").json()["total"], 1)
        r = self.c.put(f"/api/data/{i}", json={"date": "2024-01-15", "value": 421.0, "memo": "x"})
        self.assertEqual(r.json()["value"], 421.0)
        self.assertEqual(self.c.delete(f"/api/data/{i}").status_code, 204)
        self.assertEqual(self.c.delete(f"/api/data/{i}").status_code, 404)
        self.assertEqual(self.c.put(f"/api/data/{i}", json={"date": "2024-01-15", "value": 1}).status_code, 404)

    def test_validation(self):
        self.assertEqual(self.add(date="2024-13-40").status_code, 422)
        self.assertEqual(self.add(value="abc").status_code, 422)
        self.assertEqual(self.add(memo="x" * 201).status_code, 422)
        self.assertEqual(self.c.get("/api/data?limit=0").status_code, 422)

    def test_summary_endpoint(self):
        self.add("2024-01-15", 420)
        self.add("2024-02-15", 424)
        s = self.c.get("/api/data/summary").json()
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["metrics"]["average"], 422.0)

    def test_conversations(self):
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
        cid = self.c.post("/api/conversations", json={"title": "t", "messages": msgs}).json()["id"]
        lst = self.c.get("/api/conversations").json()
        self.assertEqual(lst[0]["message_count"], 2)
        self.assertNotIn("messages", lst[0])
        got = self.c.get(f"/api/conversations/{cid}").json()["messages"]
        self.assertEqual([{k: m[k] for k in ("role", "content")} for m in got], msgs)
        self.assertEqual([m["tools"] for m in got], [[], []])      # 도구 기록 필드는 기본 빈 목록
        self.assertEqual(self.c.delete(f"/api/conversations/{cid}").status_code, 204)
        self.assertEqual(self.c.get(f"/api/conversations/{cid}").status_code, 404)
        bad = self.c.post("/api/conversations", json={"title": "t", "messages": [{"role": "system", "content": "x"}]})
        self.assertEqual(bad.status_code, 422)

    def test_chat_injects_summary_and_saves(self):
        self.add("2024-01-15", 420)
        out = {"reply": "답변", "tools_used": ["get_recent_daily(days=3)"], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
        with mock.patch.object(llm, "ask", return_value=out) as ask:
            r = self.c.post("/api/chat", json={"message": "추세는?"})
            self.assertEqual(r.json()["reply"], "답변")
            self.assertEqual(r.json()["tools_used"], ["get_recent_daily(days=3)"])
            self.assertEqual(r.json()["usage"]["prompt_tokens"], 7)
            self.assertEqual(ask.call_args.args[0]["count"], 1)
            cid = r.json()["conversation_id"]
            self.c.post("/api/chat", json={"message": "더?", "conversation_id": cid})
        conv = self.c.get(f"/api/conversations/{cid}").json()
        self.assertEqual([m["role"] for m in conv["messages"]], ["user", "assistant"] * 2)
        self.assertEqual(conv["messages"][1]["tools"], ["get_recent_daily(days=3)"])   # 도구 호출 기록이 저장됨
        self.assertEqual(conv["messages"][0]["tools"], [])

    def test_chat_errors(self):
        with mock.patch.object(llm, "ask", side_effect=llm.LLMError("fail")):
            self.assertEqual(self.c.post("/api/chat", json={"message": "q"}).status_code, 502)
        self.assertEqual(self.c.post("/api/chat", json={"message": ""}).status_code, 422)
        self.assertEqual(self.c.post("/api/chat", json={"message": "q", "conversation_id": "nope"}).status_code, 404)

    def test_system_prompt(self):
        p = llm.build_system_prompt({"period": "a ~ b", "count": 3, "metrics": {"max": 1},
                                     "latest": None, "trend": {"direction": "상승"}})
        self.assertIn("a ~ b", p)
        self.assertIn("3개", p)

    def test_statistics_endpoint(self):
        for i in range(24):
            self.add(f"{2000 + i // 12}-{i % 12 + 1:02d}-15", 400 + i)
        st = self.c.get("/api/data/statistics").json()
        self.assertEqual([y["year"] for y in st["yearly"]], [2000, 2001])
        self.assertEqual(st["recent_annual_growth_ppm"], 12.0)

    def test_export_csv_and_json(self):
        self.add("2024-01-15", 420.5, "=SUM(1)")
        self.add("2024-02-15", 421.0, "정상,메모")
        r = self.c.get("/api/data/export?format=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn("co2_data.csv", r.headers["content-disposition"])
        text = r.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("id,date,value,memo"))
        self.assertIn("'=SUM(1)", text)       # 수식 주입 방지
        self.assertIn('"정상,메모"', text)     # 쉼표는 따옴표로 감쌈
        j = self.c.get("/api/data/export?format=json")
        self.assertEqual([i["date"] for i in j.json()], ["2024-01-15", "2024-02-15"])
        self.assertIn("co2_data.json", j.headers["content-disposition"])
        self.assertEqual(self.c.get("/api/data/export?format=xml").status_code, 422)

    def test_data_list_is_cached_and_invalidated_on_write(self):
        self.add("2024-01-15", 420)
        reads = []
        orig = self.db.collection

        def counting(name):
            col = orig(name)
            stream = col.stream
            col.stream = lambda: (reads.append(1), stream())[1]
            return col

        self.db.collection = counting
        for _ in range(3):
            self.c.get("/api/data/summary")
        self.assertEqual(len(reads), 1)                       # 3번 요청해도 Firestore 는 1번만 읽음
        self.add("2024-02-15", 424)                           # 쓰기 → 캐시 무효화
        self.assertEqual(self.c.get("/api/data/summary").json()["count"], 2)
        self.assertEqual(len(reads), 2)

    def test_quota_error_serves_stale_cache_then_503_with_cors(self):
        self.add("2024-01-15", 420)
        self.c.get("/api/data/summary")                       # 캐시 채움
        repo._cache["at"] = -10_000                           # 만료시킴
        self.db.collection = lambda name: (_ for _ in ()).throw(ResourceExhausted("quota"))
        self.assertEqual(self.c.get("/api/data/summary").json()["count"], 1)   # 오래된 캐시로 응답
        repo.clear_cache()
        r = self.c.get("/api/data/summary", headers={"Origin": "http://localhost:5500"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("한도", r.json()["detail"])
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5500")

    def test_briefing_endpoint(self):
        from services import briefing, daily
        from tests.test_daily import make_rows
        briefing._memory.clear()
        with mock.patch.object(daily, "fetch_rows", return_value=make_rows()), \
                mock.patch.object(llm, "complete", return_value={"text": "브리핑", "usage": {}}):
            r = self.c.get("/api/briefing")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["text"], "브리핑")
        self.assertTrue(r.json()["facts"])
        briefing._memory.clear()
        with mock.patch.object(daily, "fetch_rows", side_effect=daily.DailyUnavailable("down")):
            self.assertEqual(self.c.get("/api/briefing").status_code, 503)

    def test_refresh_endpoint(self):
        from services import monthly
        from tests.test_monthly import SAMPLE
        monthly._last["at"] = None
        with mock.patch.object(monthly, "fetch", return_value=SAMPLE):
            r = self.c.post("/api/data/refresh")
            self.assertEqual(r.json()["added"], 3)
            self.assertEqual(self.c.post("/api/data/refresh").status_code, 429)   # 쿨다운
        monthly._last["at"] = None
        with mock.patch.object(monthly, "fetch", side_effect=monthly.SourceUnavailable("x")):
            self.assertEqual(self.c.post("/api/data/refresh").status_code, 502)
        monthly._last["at"] = None

    def test_cors(self):
        r = self.c.options("/api/data", headers={"Origin": "http://localhost:5500",
                                                 "Access-Control-Request-Method": "GET"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5500")


if __name__ == "__main__":
    unittest.main()
