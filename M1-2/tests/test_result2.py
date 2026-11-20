"""Raw-data, filter, GLS and output checks for result 2."""
import csv
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.signal import butter, filtfilt
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import analyze_result2 as analysis
from collect_data import RAW, parse


class Result2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RAW.read_bytes()
        cls.rows, _ = parse(cls.raw)
        cls.metrics = json.loads((ROOT / "results/result2_metrics.json").read_text())
        cls.monthly = pd.read_csv(ROOT / "data/processed/result2_monthly.csv")
        cls.annual = pd.read_csv(ROOT / "data/processed/result2_amplitudes.csv", index_col="year")

    def test_provenance_and_interpolation(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.metrics["raw_sha256"])
        self.assertEqual(len(self.monthly), 61*12)
        self.assertEqual(self.monthly.year.min(), 1959)
        self.assertEqual(self.monthly.year.max(), 2019)
        marked = self.monthly.loc[self.monthly.linear_interpolated, ["year", "month"]]
        self.assertEqual(marked.values.tolist(), [[1964, 2], [1964, 3], [1964, 4]])
        # Independently parse raw concentrations and interpolate by integer month.
        records = []
        for line in self.raw.decode("utf-8-sig").splitlines():
            fields = next(csv.reader([line]))
            if len(fields) == 11 and fields[0].strip().isdigit() and 1959 <= int(fields[0]) <= 2019:
                records.append(float(fields[4]))
        values = np.array(records)
        good = values != -99.99
        independent = np.interp(np.arange(len(values)), np.flatnonzero(good), values[good])
        np.testing.assert_allclose(self.monthly.analysis_co2_ppm, independent, atol=1e-9, rtol=0)

    def test_joint_fit_and_filter_independently(self):
        # Independent design, solve via pseudoinverse and direct-form filter.
        d = self.monthly
        time = d.decimal_year.to_numpy(dtype=float)
        z = (time-time.mean())/10
        polynomial = np.vstack([np.ones(len(z)), z, z*z, z*z*z]).T
        harmonic = np.column_stack([f(2*np.pi*k*time) for k in range(1, 5)
                                    for f in (np.sin, np.cos)])
        x = np.column_stack([polynomial, harmonic])
        y = d.analysis_co2_ppm.to_numpy()
        beta = np.linalg.pinv(x) @ y
        residual = y-x @ beta
        b, a = butter(2, [365.25/540, 365.25/90], btype="bandpass", fs=12)
        filtered = filtfilt(b, a, residual, padtype="odd", padlen=36)
        np.testing.assert_allclose(d.polynomial_trend_ppm, polynomial @ beta[:4], atol=2e-8, rtol=0)
        np.testing.assert_allclose(d.climatological_harmonic_ppm, harmonic @ beta[4:], atol=2e-8, rtol=0)
        np.testing.assert_allclose(d.bandpassed_residual_ppm, filtered, atol=2e-8, rtol=0)
        reconstructed = d.polynomial_trend_ppm+d.seasonal_component_ppm+d.remaining_residual_ppm
        np.testing.assert_allclose(reconstructed, y, atol=3e-9, rtol=0)

    def test_annual_amplitudes_and_shape_means(self):
        for year, group in self.monthly.groupby("year"):
            expected = group.seasonal_component_ppm.max()-group.seasonal_component_ppm.min()
            self.assertAlmostEqual(expected, self.annual.loc[year, "amplitude_ppm"], places=8)
            self.assertAlmostEqual(group.centered_seasonal_ppm.mean(), 0, places=8)
            peak = group.loc[group.seasonal_component_ppm.idxmax(), "month"]
            trough = group.loc[group.seasonal_component_ppm.idxmin(), "month"]
            self.assertEqual(peak, self.annual.loc[year, "peak_month"])
            self.assertEqual(trough, self.annual.loc[year, "trough_month"])
        early = self.annual.loc[1959:1968].amplitude_ppm.mean()
        late = self.annual.loc[2010:2019].amplitude_ppm.mean()
        self.assertAlmostEqual(early, self.metrics["early_vs_late"]["early_mean_amplitude_ppm"], places=8)
        self.assertAlmostEqual((late/early-1)*100,
                               self.metrics["early_vs_late"]["relative_change_percent"], places=8)

    def test_gls_against_statsmodels_and_reml_profile(self):
        main = self.metrics["main_gls"]
        years = self.annual.index.to_numpy()
        x = np.column_stack([np.ones(len(years)), (years-1959)/10])
        y = self.annual.amplitude_ppm.to_numpy()
        distance = abs(years[:, None]-years[None, :])
        rho = main["rho_ar1"]
        fit = sm.GLS(y, x, sigma=rho**distance).fit(use_t=True)
        self.assertAlmostEqual(fit.params[1], main["slope_ppm_per_decade"], places=8)
        self.assertAlmostEqual(fit.bse[1], main["slope_standard_error"], places=8)
        np.testing.assert_allclose(fit.conf_int()[1], main["slope_ci95"], atol=2e-8, rtol=0)

        def profile(r):
            correlation = r**distance
            inv = np.linalg.inv(correlation)
            normal = x.T @ inv @ x
            beta = np.linalg.inv(normal) @ x.T @ inv @ y
            e = y-x @ beta
            return ((len(y)-2)*np.log((e @ inv @ e)/(len(y)-2))
                    + np.linalg.slogdet(correlation)[1]+np.linalg.slogdet(normal)[1])
        minimum = profile(rho)
        for r in (-.5, 0., rho-.001, rho+.001, .5, .9):
            self.assertLessEqual(minimum, profile(r)+1e-8)

    def test_affine_trend_does_not_become_seasonal_amplitude(self):
        # Equal monthly times make interpolation commute with an affine addition.
        baseline = []
        changed = []
        for original in self.rows:
            a, b = dict(original), dict(original)
            time = a["year"]+(a["month"]-.5)/12
            a["decimal_year"] = b["decimal_year"] = time
            if b["co2"] is not None:
                b["co2"] += 20+2*(time-1959)
            baseline.append(a)
            changed.append(b)
        _, expected, _ = analysis.extract_seasonal(baseline)
        _, actual, _ = analysis.extract_seasonal(changed)
        np.testing.assert_allclose(expected.amplitude_ppm, actual.amplitude_ppm, atol=1e-8, rtol=0)

    def test_missing_pattern_and_settings_guard(self):
        changed = [dict(r) for r in self.rows]
        next(r for r in changed if r["year"] == 1980 and r["month"] == 1)["co2"] = None
        with self.assertRaises(ValueError):
            analysis.extract_seasonal(changed)
        with self.assertRaises(ValueError):
            analysis.extract_seasonal(self.rows, filling="unknown")
        with self.assertRaises(ValueError):
            analysis.extract_seasonal(self.rows, end=2026)

    def test_sensitivity_and_outputs(self):
        scenarios = self.metrics["sensitivity"]
        self.assertEqual(len(scenarios), 12)
        self.assertTrue({f"filter_order_{i}" for i in range(1, 7)}.issubset(
            {r["scenario"] for r in scenarios}))
        self.assertEqual(self.metrics["main_gls"]["n"], 61)
        self.assertEqual(self.metrics["extended_gls_1959_2025"]["n"], 67)
        self.assertEqual(next(r for r in scenarios if r["scenario"] == "drop_interpolated_year_1964")["n"], 60)
        images = sorted((ROOT / "images").glob("result2_*.png"))
        self.assertEqual(len(images), 4)
        for path in images:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                self.assertGreater(im.width, 1500)
                self.assertGreater(im.height, 800)
        text = (ROOT / "REPORT.md").read_text()
        self.assertIn(f"{self.metrics['main_gls']['slope_ppm_per_decade']:.4f}ppm", text)


if __name__ == "__main__":
    unittest.main()
