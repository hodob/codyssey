"""Static integrity and rebuild checks for the offline presentation.

Real Chromium interaction, responsive layout and print checks are recorded
separately in results/presentation_validation.json.
"""
import base64
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from display_values import format_number


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements=[]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag,dict(attrs)))


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(ROOT/"presentation.html").read_text(encoding="utf-8")
        cls.elements=Document(cls.text).elements

    def test_fifteen_slides_notes_and_headings(self):
        slides=[a for t,a in self.elements if t=="section" and "slide" in a.get("class","").split()]
        self.assertEqual(len(slides),11)
        self.assertEqual(len({s["data-title"] for s in slides}),11)
        notes=[a for _,a in self.elements if "notes-only" in a.get("class","").split()]
        self.assertEqual(len(notes),11)
        scripts=re.findall(r'<aside class="notes-only">(.*?)</aside>',self.text,re.S)
        for script in scripts:
            self.assertRegex(script,r"니다\.$")
            self.assertNotRegex(script,r"질문받으면|이 장을 사용|읽으면 안|해석하면 안")
        self.assertTrue(all("\n\n" in script for script in scripts))
        self.assertNotIn("2024년 연간 증가량을 중심으로",self.text)
        self.assertIn("1959~2025년 월별 관측자료를 이용한",self.text)
        self.assertNotIn("숫자를 구분해야, 그 의미도 구분할 수 있다",self.text)
        self.assertNotIn("시간 규모와 탄소순환의 의미를 함께 읽어야 한다",self.text)
        ids=[a["id"] for _,a in self.elements if "id" in a]
        self.assertEqual(len(ids),len(set(ids)))
        for slide in slides:
            self.assertIn(slide["aria-labelledby"],ids)
        self.assertIn('lang="ko"',self.text)

    def test_values_and_provenance_follow_metrics(self):
        one,two,three=[json.loads((ROOT/"results"/f"result{i}_metrics.json").read_text()) for i in (1,2,3)]
        for value in (one["comparison_1960s_vs_2015_2024"]["early_mean_ppm_per_year"],
                      one["comparison_1960s_vs_2015_2024"]["recent_mean_ppm_per_year"],
                      two["main_gls"]["slope_ppm_per_decade"],three["target_growth_ppm"],
                      three["following_year"]["annual_mean_2025_ppm"]):
            self.assertIn(format_number(value),self.text)
        sha=hashlib.sha256((ROOT/"data/raw/monthly_in_situ_co2_mlo.csv").read_bytes()).hexdigest()
        self.assertIn(('meta',{'name':'data-sha256','content':sha}),self.elements)
        self.assertNotRegex(self.text,r"\$[A-Z][A-Z_]+")
        self.assertIn("직전 10년 평균보다",self.text)
        quality=json.loads((ROOT/"results/data_quality_metrics.json").read_text())
        scope=f"관측 {quality['primary_analysis_observed_n']}개월 + 보충 {quality['primary_analysis_missing_n']}개월"
        self.assertIn(scope,self.text)
        self.assertIn("계절 진폭 확대는 북반구 식물의 계절 활동이 커졌다는 신호",self.text)

    def test_assets_links_and_offline_dependencies(self):
        images=[]
        for tag,attrs in self.elements:
            if tag in ("script","link"):
                self.assertNotIn("src",attrs)
                if tag=="link":
                    self.assertNotIn("stylesheet",attrs.get("rel",""))
            for key in ("src","href"):
                target=attrs.get(key,"")
                if not target or target.startswith("#"):
                    continue
                if target.startswith("data:image/png;base64,"):
                    self.assertEqual((tag,key),("img","src"))
                    decoded=base64.b64decode(target.split(",",1)[1],validate=True)
                    self.assertEqual(decoded,(ROOT/attrs["data-source"]).read_bytes())
                    continue
                if target.startswith(("https://","http://")):
                    self.assertEqual((tag,key),("a","href"))
                    self.assertIn("noopener",attrs.get("rel",""))
                else:
                    path=(ROOT/target).resolve()
                    self.assertTrue(path.is_relative_to(ROOT))
                    self.assertTrue(path.is_file(),target)
            if tag=="img":
                self.assertTrue(attrs.get("alt"))
                images.append(attrs["src"])
        self.assertEqual(len(images),5)
        self.assertEqual(len(set(images)),5)
        self.assertNotIn("fetch(",self.text)
        self.assertNotIn("@import",self.text)
        self.assertNotIn("@font-face",self.text)

    def test_navigation_accessibility_and_print_contract(self):
        ids={attrs.get("id") for _,attrs in self.elements}
        self.assertTrue({"prev","next","toc","notes","readerToggle","fullscreen","print"}<=ids)
        self.assertIn('aria-live="polite"',self.text)
        self.assertIn("prefers-reduced-motion",self.text)
        self.assertIn("@media print",self.text)
        self.assertIn(".slide[hidden]{display:flex!important",self.text)
        self.assertIn("if(event.defaultPrevented",self.text)
        self.assertIn("history.replaceState",self.text)
        self.assertIn("noscript",self.text)

    def test_cover_curve_is_the_actual_annual_series(self):
        paths=[a["d"] for t,a in self.elements if t=="path" and a.get("stroke")=="#d9ec79"]
        self.assertEqual(len(paths),1)
        points=[(float(x),float(y)) for x,y in re.findall(r"[ML]([\d.]+),([\d.]+)",paths[0])]
        with (ROOT/"data/processed/result1_annual.csv").open(newline="") as file:
            rows=list(csv.DictReader(file))
        values=[float(row["mean_ppm"]) for row in rows if 1959<=int(row["year"])<=2025]
        self.assertEqual(len(points),len(values))
        for i,((x,y),v) in enumerate(zip(points,values)):
            self.assertAlmostEqual(x,48+i/(len(values)-1)*538,places=2)
            self.assertAlmostEqual(y,346-(v-min(values))/(max(values)-min(values))*262,places=2)

    def test_rebuild_elsewhere_and_reject_mixed_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="co2-presentation-test-") as directory:
            base=Path(directory)/"project"
            (base/"src").mkdir(parents=True)
            for path in (ROOT/"src").iterdir():
                if path.is_file() and path.suffix in (".py",".html"):
                    shutil.copy2(path,base/"src"/path.name)
            for relative in ["data/raw/monthly_in_situ_co2_mlo.csv","data/raw/download_metadata.json",
                             "data/processed/result1_annual.csv", "results/data_quality_metrics.json"]+[
                                 str(path.relative_to(ROOT)) for path in sorted((ROOT/"images").glob("*.png"))]+[
                                 f"results/result{i}_metrics.json" for i in (1,2,3)]:
                destination=base/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/relative,destination)
            command=[sys.executable,str(base/"src/build_presentation.py")]
            result=subprocess.run(command,cwd=directory,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((base/"presentation.html").read_bytes(),(ROOT/"presentation.html").read_bytes())
            path=base/"results/result2_metrics.json"
            data=json.loads(path.read_text())
            data["raw_sha256"]="0"*64
            path.write_text(json.dumps(data))
            failed=subprocess.run(command,cwd=directory,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn("result2_metrics.json",failed.stderr)
            self.assertEqual((base/"presentation.html").read_bytes(),(ROOT/"presentation.html").read_bytes())


if __name__=="__main__":
    unittest.main()
