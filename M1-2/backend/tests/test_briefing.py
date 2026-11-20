import unittest
from datetime import date
from unittest import mock

from services import briefing, daily, llm
from tests.fake_db import FakeDB
from tests.test_daily import make_rows


class BriefingTest(unittest.TestCase):
    def setUp(self):
        briefing._memory.clear()
        self.db = FakeDB()
        self.rows = make_rows()
        self.asof = self.rows[-1][0].isoformat()
        self.today = self.rows[-1][0]
        p = mock.patch.object(daily, "fetch_rows", return_value=self.rows)
        p.start()
        self.addCleanup(p.stop)

    def gen(self, **kw):
        return briefing.get_briefing(self.db, today=self.today)

    def test_generates_once_per_data_day_and_stores(self):
        with mock.patch.object(llm, "complete", return_value={"text": "오늘은 큰 이상 없음.", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}) as c:
            a = self.gen()
            b = self.gen()
        self.assertEqual(c.call_count, 1)
        self.assertTrue(a["ai"] and not a["cached"])
        self.assertTrue(b["cached"])
        self.assertEqual(a["asof"], self.asof)
        self.assertEqual(self.db.collection("briefings").document(self.asof).get().to_dict()["text"], "오늘은 큰 이상 없음.")

    def test_loads_from_firestore_after_restart(self):
        with mock.patch.object(llm, "complete", return_value={"text": "저장본", "usage": {}}):
            self.gen()
        briefing._memory.clear()   # 서버 재시작
        with mock.patch.object(llm, "complete", side_effect=AssertionError("should not call")) as c:
            out = self.gen()
        self.assertEqual(out["text"], "저장본")
        self.assertTrue(out["cached"])
        c.assert_not_called()

    def test_prompt_contains_only_computed_facts(self):
        with mock.patch.object(llm, "complete", return_value={"text": "x", "usage": {}}) as c:
            self.gen()
        user = c.call_args.args[1]
        self.assertIn("가장 최근 관측일", user)
        self.assertIn("작년 같은 시기보다", user)

    def test_llm_failure_falls_back_and_is_not_cached(self):
        with mock.patch.object(llm, "complete", side_effect=llm.LLMError("down")):
            out = self.gen()
        self.assertFalse(out["ai"])
        self.assertIn("가장 최근 관측일", out["text"])
        self.assertFalse(self.db.collection("briefings").document(self.asof).get().exists)
        with mock.patch.object(llm, "complete", return_value={"text": "복구", "usage": {}}):
            self.assertTrue(self.gen()["ai"])   # 다음 요청에서 다시 시도

    def test_empty_llm_text_falls_back(self):
        with mock.patch.object(llm, "complete", return_value={"text": "", "usage": {}}):
            self.assertFalse(self.gen()["ai"])

    def test_new_data_day_generates_new_briefing(self):
        with mock.patch.object(llm, "complete", return_value={"text": "t", "usage": {}}) as c:
            self.gen()
            longer = self.rows + [(date.fromordinal(self.rows[-1][0].toordinal() + 1), 410.0)]
            with mock.patch.object(daily, "fetch_rows", return_value=longer):
                briefing.get_briefing(self.db, today=longer[-1][0])
        self.assertEqual(c.call_count, 2)


if __name__ == "__main__":
    unittest.main()
