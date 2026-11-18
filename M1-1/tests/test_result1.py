"""Independent raw-data and numerical checks. Run after generating result 1.

python3 -m unittest discover -s tests -v
"""
import csv
import hashlib
import json
import re
import statistics
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.stats import t

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import analyze_result1 as analysis
from collect_data import parse


class Result1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "data/raw/monthly_in_situ_co2_mlo.csv").read_bytes()
        # Parse independently of the collection/analysis parser.
        cls.records = []
        for line in cls.raw.decode("utf-8-sig").splitlines():
            fields = next(csv.reader([line]))
            if len(fields) == 11 and fields[0].strip().isdigit():
                cls.records.append((int(fields[0]), int(fields[1]),
                                    float(fields[4]), float(fields[8]), fields[10].strip()))
        cls.means = {}
        cls.observed_means = {}
        for year in {r[0] for r in cls.records}:
            values = [r[3] for r in cls.records if r[0] == year and r[3] != -99.99]
            observed = [r[2] for r in cls.records if r[0] == year and r[2] != -99.99]
            if len(values) == 12:
                cls.means[year] = statistics.mean(values)
            if len(observed) == 12:
                cls.observed_means[year] = statistics.mean(observed)
        cls.annual = pd.read_csv(ROOT / "data/processed/result1_annual.csv", index_col="year")
        cls.periods = pd.read_csv(ROOT / "data/processed/result1_periods.csv")
        cls.metrics = json.loads((ROOT / "results/result1_metrics.json").read_text())

    def test_hash_and_calendar(self):
        digest = hashlib.sha256(self.raw).hexdigest()
        metadata = json.loads((ROOT / "data/raw/download_metadata.json").read_text())
        self.assertEqual(digest, metadata["sha256"])
        self.assertEqual(digest, self.metrics["raw_sha256"])
        serial = [r[0] * 12 + r[1] for r in self.records]
        self.assertTrue(all(b == a + 1 for a, b in zip(serial, serial[1:])))
        self.assertGreater(sum(r[2] != -99.99 for r in self.records), 100)

    def test_annual_values_and_missing_years(self):
        for year, actual in self.annual.iterrows():
            for column, means in (("mean_ppm", self.means),
                                  ("observed_mean_ppm", self.observed_means)):
                if year in means:
                    self.assertAlmostEqual(actual[column], means[year], places=8)
                else:
                    self.assertTrue(pd.isna(actual[column]))
            for column, means in (("growth_ppm", self.means),
                                  ("observed_growth_ppm", self.observed_means)):
                if year in means and year-1 in means:
                    self.assertAlmostEqual(actual[column], means[year]-means[year-1], places=8)
                else:
                    self.assertTrue(pd.isna(actual[column]))
        self.assertTrue(pd.isna(self.annual.loc[2026, "growth_ppm"]))
        self.assertTrue(pd.isna(self.annual.loc[1965, "observed_growth_ppm"]))

    def test_periods_and_telescoping(self):
        for row in self.periods.itertuples():
            growth = [self.means[y]-self.means[y-1]
                      for y in range(row.start_year, row.end_year+1)]
            self.assertEqual(len(growth), row.n_growth_years)
            self.assertAlmostEqual(statistics.mean(growth), row.mean_growth_ppm, places=8)
            endpoint = (self.means[row.end_year]-self.means[row.start_year-1])/len(growth)
            self.assertAlmostEqual(endpoint, row.mean_growth_ppm, places=8)
        # Internal imputed-year perturbation cancels from the 10-year mean.
        changed = dict(self.means)
        changed[1964] += 100
        changed_mean = statistics.mean(changed[y]-changed[y-1] for y in range(1960, 1970))
        self.assertAlmostEqual(changed_mean, self.periods.iloc[0].mean_growth_ppm, places=8)

    def test_slope_and_hac_independently(self):
        # Direct NumPy OLS + Newey-West covariance, not statsmodels fit.
        years = np.arange(1960, 2026)
        y = np.array([self.means[v]-self.means[v-1] for v in years])
        x = np.column_stack([np.ones(len(years)), years-1960])
        coefficients = np.linalg.lstsq(x, y, rcond=None)[0]
        residuals = y-x @ coefficients
        scores = x*residuals[:, None]
        meat = scores.T @ scores
        lag = 3
        for j in range(1, lag+1):
            cross = scores[j:].T @ scores[:-j]
            meat += (1-j/(lag+1))*(cross+cross.T)
        bread = np.linalg.inv(x.T @ x)
        covariance = bread @ meat @ bread * len(y)/(len(y)-2)
        width = t.ppf(.975, len(y)-2)*np.sqrt(covariance[1, 1])
        main = self.metrics["main_trend"]
        self.assertAlmostEqual(coefficients[1], main["slope_ppm_per_year2"], places=12)
        np.testing.assert_allclose(main["slope_ci95"], coefficients[1]+np.array([-width,width]),
                                   rtol=1e-10, atol=1e-12)

    def test_monthly_transformations(self):
        saved = pd.read_csv(ROOT / "data/processed/result1_monthly.csv")
        for i, r in enumerate(self.records):
            if i >= 12 and r[3] != -99.99 and self.records[i-12][3] != -99.99:
                self.assertAlmostEqual(saved.loc[i, "growth_yoy_ppm"],
                                       r[3]-self.records[i-12][3], places=8)
            window = self.records[max(0, i-11):i+1]
            if len(window) == 12 and all(s[3] != -99.99 for s in window):
                self.assertAlmostEqual(saved.loc[i, "trailing_12m_mean_ppm"],
                                       statistics.mean(s[3] for s in window), places=8)
            else:
                self.assertTrue(pd.isna(saved.loc[i, "trailing_12m_mean_ppm"]))

    def test_invalid_data_rejected(self):
        for bad in (b"<html>Error</html>", b"2024,01,1",
                    b"2024,13,0,0,400,400,400,400,400,400,MLO",
                    b"2024,01,0,0,nan,400,400,400,400,400,MLO"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse(bad)
        # The trend routine must reject gaps instead of compressing calendar time.
        with self.assertRaises(ValueError):
            analysis.trend_fit(self.annual, 1960, 2025, column="observed_growth_ppm")

    def test_outputs_and_local_report_links(self):
        paths = sorted((ROOT / "images").glob("result1_*.png"))
        self.assertEqual(len(paths), 3)
        for path in paths:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                self.assertGreaterEqual(im.width, 1500)
                self.assertGreaterEqual(im.height, 800)
        content = (ROOT / "REPORT.md").read_text()
        comparison = self.metrics["comparison_1960s_vs_2015_2024"]
        self.assertAlmostEqual(comparison["ratio"],
            self.periods.loc[self.periods.start_year == 2015, "mean_growth_ppm"].iloc[0]
            / self.periods.iloc[0].mean_growth_ppm, places=8)
        self.assertIn(f"{comparison['ratio']:.2f}배", content)


if __name__ == "__main__":
    unittest.main()
