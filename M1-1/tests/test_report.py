"""Submission report, quality diagnostics and local-document integration checks."""
import hashlib
import json
import re
import statistics
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import build_report
from check_data_quality import residual_flags
from display_values import format_number


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = (ROOT / "REPORT.md").read_text(encoding="utf-8")
        cls.results = [json.loads((ROOT / f"results/result{i}_metrics.json").read_text())
                       for i in (1, 2, 3)]
        cls.quality = json.loads((ROOT / "results/data_quality_metrics.json").read_text())

    def test_same_snapshot_and_data_scope(self):
        digest = hashlib.sha256((ROOT / "data/raw/monthly_in_situ_co2_mlo.csv").read_bytes()).hexdigest()
        for item in self.results+[self.quality]:
            self.assertEqual(item["raw_sha256"], digest)
        self.assertEqual(self.quality["primary_analysis_calendar_n"], 804)
        self.assertEqual(self.quality["primary_analysis_observed_n"], 801)
        self.assertEqual(self.quality["deleted_observations"], 0)
        self.assertGreaterEqual(self.quality["observed_n"], 100)

    def test_report_sections_and_result_order(self):
        for heading in ("주제와 분석 질문", "데이터", "결측·이상치", "결과 1", "결과 2", "결과 3",
                        "종합 결론", "한계와 개선", "재현 방법", "AI 사용 로그", "출처와 상세 산출물", "부록: 상세 계산"):
            self.assertIn(heading, self.report)
        self.assertLess(self.report.index("## 4. 결과 1"),self.report.index("## 5. 결과 2"))
        self.assertLess(self.report.index("## 5. 결과 2"),self.report.index("## 6. 결과 3"))
        self.assertEqual(self.report.count("### 4.2 결론과 의의"),1)
        self.assertEqual(self.report.count("### 5.2 결론과 의의"),1)
        self.assertEqual(self.report.count("### 6.3 결론과 의의"),1)
        self.assertIn("사용자가 별도로 검증했다고 기재하지 않음",self.report)

    def test_local_links_and_seven_figures(self):
        documents = [ROOT / "REPORT.md",ROOT / "README.md"]
        documents += sorted((ROOT / "results").glob("*.md"))
        for doc in documents:
            text = doc.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)",text):
                if not target.startswith(("http:","https:","#")):
                    self.assertTrue((doc.parent/target).is_file(),f"{doc.name}: {target}")
        images = re.findall(r"!\[[^\]]+\]\((images/[^)]+)\)",self.report)
        self.assertEqual(len(images),7)
        self.assertEqual(len(set(images)),7)
        for path in images:
            with Image.open(ROOT/path) as im:
                im.verify()
        self.assertTrue((ROOT/"run_analysis.py").is_file())

    def test_report_numbers_follow_metrics(self):
        self.assertEqual(format_number(2.56425), "2.5643")
        self.assertEqual(format_number(2.564250000000004), "2.5643")
        self.assertEqual(format_number(1.5507499999999996), "1.5508")
        one,two,three = self.results
        c = one["comparison_1960s_vs_2015_2024"]
        for value in (f"{c['early_mean_ppm_per_year']:.4f}",f"{c['recent_mean_ppm_per_year']:.4f}",
                      f"{c['ratio']:.2f}배",
                      f"{two['main_gls']['slope_ppm_per_decade']:.4f}",
                      f"{two['early_vs_late']['relative_change_percent']:.2f}%",
                      f"{three['target_growth_ppm']:.6f}",
                      f"{three['pre_event_baseline']['relative_excess_percent']:.2f}%",
                      f"{three['following_year']['annual_mean_2025_ppm']:.4f}"):
            self.assertIn(value,self.report)
        self.assertIn("3.58",self.report)
        self.assertIn("3.41",self.report)
        self.assertIn("정확한 원인은 미확인",self.report)

    def test_quality_scores_independent_formula(self):
        saved = pd.read_csv(ROOT/"data/processed/quality_residual_flags.csv")
        valid = saved.co2.notna()
        residual = saved.loc[valid,"remaining_residual_ppm"].tolist()
        median = statistics.median(residual)
        mad = statistics.median(abs(v-median) for v in residual)
        expected = np.array([.6744897501960817*(v-median)/mad for v in residual])
        np.testing.assert_allclose(saved.loc[valid,"robust_z"],expected,atol=2e-9,rtol=0)
        self.assertTrue(saved.loc[~valid,"robust_z"].isna().all())
        self.assertEqual(int((abs(expected)>3.5).sum()),self.quality["residual_diagnostic"]["candidate_count"])
        self.assertEqual(int(saved.candidate.sum()),self.quality["residual_diagnostic"]["candidate_count"])

    def test_extreme_candidate_is_flagged_not_deleted(self):
        frame = pd.DataFrame({"date":pd.date_range("2000-01-01",periods=9,freq="MS"),
                              "year":[2000]*9,"month":range(1,10),"station":["MLO"]*9,
                              "co2":[400.]*8+[None],
                              "remaining_residual_ppm":[-3.,-2.,-1.,0.,1.,2.,3.,100.,1000.]})
        original = frame.copy(deep=True)
        flags,summary = residual_flags(frame)
        self.assertEqual(len(flags),9)
        self.assertEqual(summary["candidate_count"],1)
        self.assertTrue(flags.loc[7,"candidate"])
        self.assertFalse(flags.loc[8,"candidate"])
        pd.testing.assert_frame_equal(frame,original)
        with self.assertRaises(ValueError):
            residual_flags(frame.assign(remaining_residual_ppm=0.))

    def test_mixed_snapshot_metrics_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"results").mkdir()
            path = root/"results/dummy.json"
            path.write_text(json.dumps({"raw_sha256":"wrong"}))
            with patch.object(build_report,"ROOT",root):
                with self.assertRaises(ValueError):
                    build_report.load_result("dummy.json","expected")
                path.write_text(json.dumps({"raw_sha256":"expected"}))
                self.assertEqual(build_report.load_result("dummy.json","expected")["raw_sha256"],"expected")


if __name__ == "__main__":
    unittest.main()
