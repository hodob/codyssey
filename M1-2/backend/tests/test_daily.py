import unittest
from datetime import date, timedelta

from services import daily


def make_rows(days=800, start=date(2024, 1, 1), base=400.0, slope=0.007, noise=None):
    """1년에 약 2.5ppm 오르는 합성 일별 자료. noise: {offset일: 가산값}"""
    noise = noise or {}
    return [(start + timedelta(days=i), round(base + slope * i + noise.get(i, 0.0), 2)) for i in range(days)]


class ParseTest(unittest.TestCase):
    def test_skips_comments_missing_and_bad_rows(self):
        text = "# comment\n2026,11,17,2026.87,429.12\n2026,11,18,2026.88,-999.99\nbad,row\n2026,11,19,2026.88,xyz\n2026,11,16,2026.87,429.89\n"
        rows = daily.parse(text)
        self.assertEqual([(d.isoformat(), v) for d, v in rows], [("2026-11-16", 429.89), ("2026-11-17", 429.12)])


class HighlightsTest(unittest.TestCase):
    def test_basic_facts(self):
        rows = make_rows()
        h = daily.build_highlights(rows)
        self.assertEqual(h["asof"], rows[-1][0].isoformat())
        self.assertEqual(h["latest"]["value"], rows[-1][1])
        self.assertAlmostEqual(h["change_vs_prev"], rows[-1][1] - rows[-2][1], places=2)
        self.assertIn("yoy", h)
        self.assertAlmostEqual(h["yoy"]["diff"], 0.007 * 365, delta=0.1)   # 합성 기울기 그대로
        self.assertEqual(h["notable"], ["max_30d"])                         # 단조 증가라 30일 최고
        self.assertTrue(h["facts"][0].startswith("가장 최근 관측일"))

    def test_big_daily_move_and_yoy_outlier(self):
        rows = make_rows(noise={799: 6.0})   # 마지막 날만 6ppm 급등
        h = daily.build_highlights(rows)
        self.assertIn("big_daily_move", h["notable"])
        self.assertIn("yoy_outlier_high", h["notable"])
        self.assertGreater(h["yoy"]["z"], 2)

    def test_no_notable_message(self):
        # 홀수 날 +0.3, 짝수 날 -0.3 로 흔들리는 자료. 마지막 날(짝수)은 30일 최고/최저가 아니다
        rows = make_rows(days=801, noise={i: (0.3 if i % 2 else -0.3) for i in range(801)})
        h = daily.build_highlights(rows)
        self.assertEqual(h["notable"], [])
        self.assertTrue(h["facts"][-1].startswith("특이사항 없음"))

    def test_stale_data_flagged(self):
        rows = make_rows()
        h = daily.build_highlights(rows, today=rows[-1][0] + timedelta(days=6))
        self.assertIn("stale", h["notable"])

    def test_short_series_does_not_crash(self):
        h = daily.build_highlights(make_rows(days=5))
        self.assertNotIn("yoy", h)
        self.assertEqual(daily.build_highlights([(date(2026, 1, 1), 420.0)])["latest"]["value"], 420.0)
        with self.assertRaises(ValueError):
            daily.build_highlights([])

    def test_recent_window(self):
        rows = make_rows(days=40)
        self.assertEqual(len(daily.recent(rows, 7)), 7)
        self.assertEqual(daily.recent([], 7), [])


if __name__ == "__main__":
    unittest.main()
