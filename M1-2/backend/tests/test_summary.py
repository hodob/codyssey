import unittest

from services.summary import annual_growth, build_statistics, summarize, yearly_means


def series(n, start=400.0, step=1.0):
    return [{"date": f"{2000 + i // 12:04d}-{i % 12 + 1:02d}-15", "value": start + i * step}
            for i in range(n)]


class SummaryTest(unittest.TestCase):
    def test_empty(self):
        s = summarize([])
        self.assertEqual(s["count"], 0)
        self.assertEqual(s["trend"]["direction"], "판단불가")

    def test_basic_metrics(self):
        s = summarize(series(30))
        self.assertEqual(s["count"], 30)
        self.assertEqual(s["period"], "2000-01 ~ 2002-06")
        self.assertEqual(s["metrics"]["max"], 429.0)
        self.assertEqual(s["metrics"]["min"], 400.0)
        self.assertEqual(s["latest"]["value"], 429.0)

    def test_rising_and_falling_and_flat(self):
        self.assertEqual(summarize(series(30))["trend"]["direction"], "상승")
        self.assertEqual(summarize(series(30, step=-1))["trend"]["direction"], "하락")
        self.assertEqual(summarize(series(30, step=0))["trend"]["direction"], "유지")

    def test_unsorted_input(self):
        rows = series(30)[::-1]
        self.assertEqual(summarize(rows)["latest"]["value"], 429.0)

    def test_extra_metrics(self):
        s = summarize(series(30))  # 2000~2002-06, 값 400..429
        self.assertEqual(s["metrics"]["median"], 414.5)
        self.assertGreater(s["metrics"]["stdev"], 8)
        # 2000, 2001 만 완전한 연도: 평균 차이는 정확히 12
        self.assertEqual(s["metrics"]["recent_annual_growth_ppm"], 12.0)

    def test_partial_years_excluded_from_growth(self):
        yearly = yearly_means(series(30))
        self.assertEqual([y["complete"] for y in yearly], [True, True, False])
        self.assertEqual(annual_growth(yearly), [{"year": 2001, "growth": 12.0}])

    def test_growth_needs_consecutive_complete_years(self):
        rows = [r for r in series(36) if not r["date"].startswith("2001-05")]  # 2001 불완전
        self.assertEqual(annual_growth(yearly_means(rows)), [])
        self.assertIsNone(summarize(rows)["metrics"]["recent_annual_growth_ppm"])

    def test_statistics(self):
        st = build_statistics(series(30))
        self.assertEqual(len(st["yearly"]), 3)
        self.assertEqual(st["recent_annual_growth_ppm"], 12.0)
        self.assertEqual(build_statistics([])["yearly"], [])


if __name__ == "__main__":
    unittest.main()
