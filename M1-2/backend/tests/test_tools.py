import json
import unittest
from unittest import mock

from services import daily, tools
from services import repository as repo
from tests.fake_db import FakeDB
from tests.test_daily import make_rows


def monthly_db(n=48):
    repo.clear_cache()
    db = FakeDB()
    for i in range(n):
        db.collection("data").document(f"m{i}").set(
            {"date": f"{2020 + i // 12}-{i % 12 + 1:02d}-15", "value": 400 + i, "memo": ""})
    return db


class ToolsTest(unittest.TestCase):
    def run_tool(self, name, args, db=None):
        return json.loads(tools.run_tool(name, args, db or monthly_db()))

    def test_schemas_are_valid_function_specs(self):
        names = [t["function"]["name"] for t in tools.TOOL_SCHEMAS]
        self.assertEqual(sorted(names), ["get_monthly_range", "get_recent_daily", "get_today_highlights"])
        self.assertEqual(set(names), set(tools._RUNNERS))

    def test_monthly_range_small_returns_values(self):
        out = self.run_tool("get_monthly_range", {"start": "2020-03", "end": "2020-05"})
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["values"], "2020-03:402;2020-04:403;2020-05:404")
        self.assertEqual(out["max"], ["2020-05", 404])

    def test_monthly_range_large_returns_stats_only(self):
        out = self.run_tool("get_monthly_range", {"start": "2020-01", "end": "2023-12"})
        self.assertEqual(out["n"], 48)
        self.assertNotIn("values", out)
        self.assertIn("통계만", out["note"])

    def test_monthly_range_validation(self):
        for bad in ({"start": "2020-13", "end": "2020-12"}, {"start": "2020", "end": "2021"}, {}):
            self.assertIn("error", self.run_tool("get_monthly_range", bad))
        self.assertIn("error", self.run_tool("get_monthly_range", {"start": "2021-05", "end": "2020-05"}))
        self.assertEqual(self.run_tool("get_monthly_range", {"start": "1990-01", "end": "1990-02"})["n"], 0)

    def test_recent_daily_clamps_and_validates(self):
        with mock.patch.object(daily, "fetch_rows", return_value=make_rows(days=60)):
            out = self.run_tool("get_recent_daily", {"days": 5})
            self.assertEqual(out["n"], 5)
            self.assertEqual(self.run_tool("get_recent_daily", {"days": 999})["days"], 30)
            self.assertEqual(self.run_tool("get_recent_daily", {})["days"], 7)
            self.assertIn("error", self.run_tool("get_recent_daily", {"days": "abc"}))

    def test_highlights_tool(self):
        with mock.patch.object(daily, "fetch_rows", return_value=make_rows()):
            out = self.run_tool("get_today_highlights", {})
        self.assertIn("facts", out)
        self.assertIn("NOAA", out["source"])
        self.assertIn("lag_days", out)

    def test_recent_daily_reports_freshness(self):
        with mock.patch.object(daily, "fetch_rows", return_value=make_rows(days=60)):
            out = self.run_tool("get_recent_daily", {"days": 3})
        self.assertEqual(out["latest_date"], make_rows(days=60)[-1][0].isoformat())
        self.assertGreaterEqual(out["lag_days"], 0)
        self.assertIn("today", out)

    def test_unavailable_source_becomes_error_text(self):
        with mock.patch.object(daily, "fetch_rows", side_effect=daily.DailyUnavailable("down")):
            self.assertEqual(self.run_tool("get_recent_daily", {}), {"error": "down"})

    def test_unknown_tool_and_bad_args_and_length_cap(self):
        self.assertIn("error", self.run_tool("drop_database", {}))
        self.assertIn("error", json.loads(tools.run_tool("get_recent_daily", "bad", monthly_db())))
        long = tools.run_tool("get_monthly_range", {"start": "2020-01", "end": "2022-12"}, monthly_db(), limit=100)
        self.assertLessEqual(len(long), 120)


if __name__ == "__main__":
    unittest.main()
