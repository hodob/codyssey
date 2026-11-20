"""Independent Decimal/raw checks for the 2024 event and its interpretation."""
import csv
from decimal import Decimal
import hashlib
import json
import re
import statistics
import sys
import unittest
from pathlib import Path

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import analyze_result3 as analysis
from collect_data import RAW, parse
from analyze_result1 import prepare


class Result3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RAW.read_bytes()
        cls.metrics = json.loads((ROOT / "results/result3_metrics.json").read_text())
        cls.saved = pd.read_csv(ROOT / "data/processed/result3_annual.csv", index_col="year")
        cls.comparisons = pd.read_csv(ROOT / "data/processed/result3_publication_comparison.csv")
        # Decimal and separate CSV reader, not the analysis parser or pandas means.
        by_year = {}
        observed_by_year = {}
        for line in cls.raw.decode("utf-8-sig").splitlines():
            fields = next(csv.reader([line]))
            if len(fields) == 11 and fields[0].strip().isdigit():
                year = int(fields[0])
                value, obs = Decimal(fields[8].strip()), Decimal(fields[4].strip())
                if value != Decimal('-99.99'):
                    by_year.setdefault(year, []).append(value)
                if obs != Decimal('-99.99'):
                    observed_by_year.setdefault(year, []).append(obs)
        cls.means = {y: sum(v)/12 for y, v in by_year.items() if len(v) == 12}
        cls.growth = {y: cls.means[y]-cls.means[y-1] for y in cls.means if y-1 in cls.means}
        cls.observed_means = {y: sum(v)/12 for y, v in observed_by_year.items() if len(v) == 12}

    def test_hash_annual_means_and_differences(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.metrics["raw_sha256"])
        self.assertEqual(self.saved.index.tolist(), list(range(1960, 2026)))
        self.assertNotIn(2026, self.saved.index)
        for year, row in self.saved.iterrows():
            self.assertAlmostEqual(row.mean_ppm, float(self.means[year]), places=8)
            self.assertAlmostEqual(row.growth_ppm, float(self.growth[year]), places=8)
        self.assertAlmostEqual(float(self.growth[2024]), self.metrics["target_growth_ppm"], places=10)

    def test_ranking_and_top_five(self):
        for end in (2024, 2025):
            window = {y: v for y, v in self.growth.items() if 1960 <= y <= end}
            expected = 1+sum(v > self.growth[2024] for v in window.values())
            record = self.metrics[f"rank_through_{end}"]
            self.assertEqual(expected, record["rank_descending_min"])
            self.assertEqual(len(window), record["n"])
            ecdf = 100*sum(v <= self.growth[2024] for v in window.values())/len(window)
            self.assertAlmostEqual(ecdf, record["empirical_cdf_percent"], places=9)
            for year, row in self.saved.iterrows():
                if year <= end:
                    rank = 1+sum(v > self.growth[year] for v in window.values())
                    self.assertEqual(row[f"rank_through_{end}"], rank)
                else:
                    self.assertTrue(pd.isna(row[f"rank_through_{end}"]))
        expected = sorted(((y, v) for y, v in self.growth.items() if 1960 <= y <= 2025),
                          key=lambda pair: pair[1], reverse=True)[:5]
        self.assertEqual([y for y, _ in expected],
                         [row["year"] for row in self.metrics["top_5_through_2025"]])
        previous = max(((y,v) for y,v in self.growth.items() if 1960 <= y <= 2023),
                       key=lambda pair:pair[1])
        self.assertEqual(previous[0], self.metrics["previous_record"]["year"])

    def test_baseline_effect_sizes_and_no_lookahead(self):
        values = [float(self.growth[y]) for y in range(2014, 2024)]
        mean, sd = statistics.mean(values), statistics.stdev(values)
        target = float(self.growth[2024])
        b = self.metrics["pre_event_baseline"]
        self.assertEqual((b["start_year"], b["end_year"], b["n"]), (2014, 2023, 10))
        self.assertAlmostEqual(mean, b["mean_ppm_per_year"], places=10)
        self.assertAlmostEqual(sd, b["sample_sd_ppm_per_year"], places=10)
        self.assertAlmostEqual((target/mean-1)*100, b["relative_excess_percent"], places=9)
        self.assertAlmostEqual((target-mean)/sd, b["descriptive_sd_units"], places=9)
        _, annual = prepare(parse(self.raw)[0])
        changed = annual.copy()
        changed.loc[2024, "growth_ppm"] += 10
        changed.loc[2025, "growth_ppm"] += 100
        altered, _, _ = analysis.summarize(changed)
        self.assertAlmostEqual(altered["pre_event_baseline"]["mean_ppm_per_year"], mean, places=9)
        self.assertAlmostEqual(altered["pre_event_baseline"]["sample_sd_ppm_per_year"], sd, places=9)
        self.assertEqual(altered["rank_through_2024"]["rank_descending_min"], 1)
        self.assertEqual(altered["rank_through_2025"]["rank_descending_min"], 2)

    def test_published_and_current_values_kept_separate(self):
        self.assertEqual(set(self.comparisons.year), {2016, 2024})
        for row in self.comparisons.itertuples():
            expected = self.growth[row.year]
            self.assertAlmostEqual(float(expected), row.current_growth_ppm, places=9)
            self.assertEqual(row.published_growth_ppm, analysis.PUBLISHED[row.year])
            delta = float(expected-Decimal(str(analysis.PUBLISHED[row.year])))
            self.assertAlmostEqual(delta, row.current_minus_published_ppm, places=9)
            observed = self.observed_means[row.year]-self.observed_means[row.year-1]
            self.assertAlmostEqual(float(observed), row.current_observed_only_growth_ppm, places=9)
        # No assumption that rounding reproduces the historical announcement.
        self.assertNotEqual(round(float(self.growth[2016]), 2), analysis.PUBLISHED[2016])
        self.assertNotEqual(round(float(self.growth[2024]), 2), analysis.PUBLISHED[2024])
        self.assertIn("Unresolved", self.metrics["historical_value_difference_status"])

    def test_following_year_concentration_vs_growth(self):
        f = self.metrics["following_year"]
        self.assertAlmostEqual(f["growth_ppm"], float(self.growth[2025]), places=10)
        self.assertAlmostEqual(f["growth_change_from_2024_percent"],
                               float((self.growth[2025]/self.growth[2024]-1)*100), places=9)
        for year in (2023, 2024, 2025):
            self.assertAlmostEqual(f[f"annual_mean_{year}_ppm"], float(self.means[year]), places=9)
        self.assertLess(self.growth[2025], self.growth[2024])
        self.assertGreater(self.means[2025], self.means[2024])

    def test_rank_ties_and_invalid_context(self):
        sample = pd.Series([1.,2.,2.+1e-12,3.], index=[2000,2001,2002,2003])
        r = analysis.historical_position(sample,2001)
        self.assertEqual(r["rank_descending_min"],2)
        self.assertEqual(r["equal_count_including_target"],2)
        self.assertEqual(r["empirical_cdf_percent"],75.)
        with self.assertRaises(ValueError):
            analysis.historical_position(sample,1990)
        with self.assertRaises(ValueError):
            analysis.historical_position(pd.Series([1,2],index=[2024,2024]),2024)
        _, annual = prepare(parse(self.raw)[0])
        with self.assertRaises(ValueError):
            analysis.summarize(annual.drop(index=2025))
        annual.loc[2024,"growth_ppm"] = float('nan')
        with self.assertRaises(ValueError):
            analysis.summarize(annual)

    def test_png_report_links_and_metrics(self):
        paths = sorted((ROOT / "images").glob("result3_*.png"))
        self.assertEqual(len(paths),3)
        for path in paths:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                self.assertGreater(im.width,1500)
                self.assertGreater(im.height,800)
        text = (ROOT / "REPORT.md").read_text()
        self.assertIn(f"{self.metrics['target_growth_ppm']:.6f}ppm",text)


if __name__ == "__main__":
    unittest.main()
