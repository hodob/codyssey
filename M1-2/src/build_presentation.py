"""Generate an offline, Korean presentation from the verified analysis metrics."""
from __future__ import annotations

import base64
import csv
import hashlib
from html import escape
import json
from string import Template

from collect_data import ROOT, RAW, METADATA
from build_report import load_result
from display_values import format_number


def main() -> None:
    digest = hashlib.sha256(RAW.read_bytes()).hexdigest()
    if json.loads(METADATA.read_text(encoding="utf-8"))["sha256"] != digest:
        raise ValueError("Raw snapshot hash mismatch")
    one = load_result("result1_metrics.json", digest)
    two = load_result("result2_metrics.json", digest)
    three = load_result("result3_metrics.json", digest)
    quality = load_result("data_quality_metrics.json", digest)
    comparison = one["comparison_1960s_vs_2015_2024"]
    gls = two["main_gls"]
    amplitude = two["early_vs_late"]
    following = three["following_year"]
    with (ROOT/"data/processed/result1_annual.csv").open(encoding="utf-8",newline="") as file:
        annual = [r for r in csv.DictReader(file) if 1959 <= int(r["year"]) <= 2025]
    values = [float(r["mean_ppm"]) for r in annual]
    growth = [(float(r["growth_ppm"]),int(r["year"])) for r in annual if r["growth_ppm"]]
    lowest_growth = min(growth)
    if any(g <= 0 for g,_ in growth):
        raise ValueError("Slide text states that every annual mean rose; data no longer supports it")
    sub = next(x for x in two["sensitivity"] if x["scenario"] == "recent_paper_subperiod")
    with (ROOT/"data/processed/result1_periods.csv").open(encoding="utf-8",newline="") as file:
        decades = {r["start_year"]: float(r["mean_growth_ppm"]) for r in csv.DictReader(file)}
    low, high = min(values), max(values)
    points = [(48+i/(len(values)-1)*538, 346-(value-low)/(high-low)*262)
              for i,value in enumerate(values)]
    path = " ".join(("M" if i == 0 else "L")+f"{x:.2f},{y:.2f}" for i,(x,y) in enumerate(points))
    context = {
        "RAW_SHA": digest, "COVER_PATH": path,
        "LEVEL_1959": f"{values[0]:.2f}", "GROWTH_YEARS": len(growth),
        "GROWTH_POSITIVE": sum(1 for g,_ in growth if g > 0),
        "LOWEST_GROWTH_YEAR": lowest_growth[1], "LOWEST_GROWTH": f"{lowest_growth[0]:.2f}",
        "OBSERVED_N": quality["observed_n"], "MAIN_MONTHS": quality["primary_analysis_calendar_n"],
        "MAIN_OBSERVED": quality["primary_analysis_observed_n"],
        "MAIN_FILLED": quality["primary_analysis_missing_n"],
        "EARLY": format_number(comparison["early_mean_ppm_per_year"]),
        "RECENT": format_number(comparison["recent_mean_ppm_per_year"]),
        "RATIO": f"{comparison['ratio']:.2f}",
        "R1_BETA": f"{one['main_trend']['slope_ppm_per_year2']:.5f}",
        "R1_CI": " ~ ".join(f"{v:.5f}" for v in one["main_trend"]["slope_ci95"]),
        "AMP_EARLY": format_number(amplitude["early_mean_amplitude_ppm"]),
        "AMP_LATE": format_number(amplitude["late_mean_amplitude_ppm"]),
        "AMP_PERCENT": f"{amplitude['relative_change_percent']:.2f}",
        "AMP_SLOPE": format_number(gls["slope_ppm_per_decade"]),
        "AMP_CI": " ~ ".join(format_number(v) for v in gls["slope_ci95"]),
        "AMP_SE": format_number(gls["slope_standard_error"]),
        "RECORD": format_number(three["target_growth_ppm"]),
        "PREVIOUS": format_number(three["previous_record"]["growth_ppm"]),
        "BASELINE": format_number(three["pre_event_baseline"]["mean_ppm_per_year"]),
        "EXCESS_PERCENT": f"{three['pre_event_baseline']['relative_excess_percent']:.2f}",
        "GROWTH_2025": format_number(following["growth_ppm"]),
        "DECLINE_PERCENT": f"{abs(following['growth_change_from_2024_percent']):.2f}",
        "LEVEL_2024": format_number(following["annual_mean_2024_ppm"]),
        "LEVEL_2025": format_number(following["annual_mean_2025_ppm"]),
        "LEVEL_2025_SHORT": f"{following['annual_mean_2025_ppm']:.2f}",
        "HISTORY_N": three["rank_through_2025"]["n"],
        "OUTLIER_N": quality["residual_diagnostic"]["candidate_count"],
        "OUTLIER_Z": f"{quality['residual_diagnostic']['threshold_abs_z']:g}",
        "MAD": f"{quality['residual_diagnostic']['residual_mad_ppm']:.4f}",
        "DELETED": quality["deleted_observations"],
        "SUB_SLOPE": f"{sub['slope_ppm_per_decade']:.4f}",
        "SUB_CI": "[" + ", ".join(f"{v:.4f}" for v in sub["slope_ci95"]) + "]",
        "DEC80": f"{decades['1980']:.4f}", "DEC90": f"{decades['1990']:.4f}",
    }
    images = ["result1_01_concentration.png", "result1_03_slope_comparison.png",
              "result2_04_seasonal_cycle_presentation.png", "result2_03_amplitude_trend_presentation.png",
              "result3_03_record_presentation.png"]
    for index, name in enumerate(images, 1):
        content = (ROOT/"images"/name).read_bytes()
        encoded = base64.b64encode(content).decode("ascii")
        context[f"IMAGE_{index}"] = "data:image/png;base64," + encoded
    safe = {key:escape(str(value),quote=True) for key,value in context.items()}
    template = Template((ROOT/"src/presentation_template.html").read_text(encoding="utf-8"))
    result = template.substitute(safe)
    (ROOT/"presentation.html").write_text(result,encoding="utf-8")
    print("Wrote presentation.html (13 slides; five embedded PNGs; no external assets)")


if __name__ == "__main__":
    main()
