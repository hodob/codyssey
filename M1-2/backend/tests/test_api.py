import unittest
from unittest import mock

from fastapi.testclient import TestClient

from main import app
from services import llm
from services.firebase import get_db
from tests.fake_db import FakeDB


class ApiTest(unittest.TestCase):
    def setUp(self):
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
        self.assertEqual(self.c.get(f"/api/conversations/{cid}").json()["messages"], msgs)
        self.assertEqual(self.c.delete(f"/api/conversations/{cid}").status_code, 204)
        self.assertEqual(self.c.get(f"/api/conversations/{cid}").status_code, 404)
        bad = self.c.post("/api/conversations", json={"title": "t", "messages": [{"role": "system", "content": "x"}]})
        self.assertEqual(bad.status_code, 422)

    def test_chat_injects_summary_and_saves(self):
        self.add("2024-01-15", 420)
        with mock.patch.object(llm, "ask", return_value="답변") as ask:
            r = self.c.post("/api/chat", json={"message": "추세는?"})
            self.assertEqual(r.json()["reply"], "답변")
            self.assertEqual(ask.call_args.args[0]["count"], 1)
            cid = r.json()["conversation_id"]
            self.c.post("/api/chat", json={"message": "더?", "conversation_id": cid})
        conv = self.c.get(f"/api/conversations/{cid}").json()
        self.assertEqual([m["role"] for m in conv["messages"]], ["user", "assistant"] * 2)

    def test_chat_errors(self):
        with mock.patch.object(llm, "ask", side_effect=llm.LLMError("fail")):
            self.assertEqual(self.c.post("/api/chat", json={"message": "q"}).status_code, 502)
        self.assertEqual(self.c.post("/api/chat", json={"message": ""}).status_code, 422)
        self.assertEqual(self.c.post("/api/chat", json={"message": "q", "conversation_id": "nope"}).status_code, 404)

    def test_system_prompt(self):
        p = llm.build_system_prompt({"period": "a ~ b", "count": 3, "metrics": {"max": 1},
                                     "latest": None, "trend": {"description": "상승"}})
        self.assertIn("a ~ b", p)
        self.assertIn("3개", p)

    def test_cors(self):
        r = self.c.options("/api/data", headers={"Origin": "http://localhost:5500",
                                                 "Access-Control-Request-Method": "GET"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5500")


if __name__ == "__main__":
    unittest.main()
