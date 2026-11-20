import unittest

from services.summary import summarize


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


if __name__ == "__main__":
    unittest.main()
