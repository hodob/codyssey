"""Result 3: 2024 annual CO2 increase in historical and recent context.

Uses the same preserved Scripps series as results 1 and 2. No network access.
"""
from __future__ import annotations

import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from collect_data import ROOT, RAW, METADATA, parse
from analyze_result1 import prepare

PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
IMAGES = ROOT / "images"
TARGET_YEAR = 2024
LAST_YEAR = 2025
TIE_DECIMALS = 10
PUBLISHED = {2016: 3.41, 2024: 3.58}


def historical_position(growth: pd.Series, year: int) -> dict:
    """Minimum descending rank; ECDF includes ties and target itself."""
    clean = growth.dropna().round(TIE_DECIMALS)
    if year not in clean.index or clean.index.has_duplicates:
        raise ValueError("Target missing or duplicate years")
    target = float(clean.loc[year])
    return {
        "year": year, "n": len(clean),
        "period_start": int(clean.index.min()), "period_end": int(clean.index.max()),
        "rank_descending_min": int(1+(clean > target).sum()),
        "equal_count_including_target": int((clean == target).sum()),
        "empirical_cdf_percent": float((clean <= target).mean()*100),
        "tie_rounding_decimal_places": TIE_DECIMALS,
    }


def summarize(annual: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    full = annual.loc[1960:LAST_YEAR].copy()
    if full.index.tolist() != list(range(1960, LAST_YEAR+1)) or full.growth_ppm.isna().any():
        raise ValueError("Historical context must contain every complete annual difference")
    g = full.growth_ppm
    target = float(g.loc[TARGET_YEAR])
    before = g.loc[:TARGET_YEAR-1]
    baseline = g.loc[TARGET_YEAR-10:TARGET_YEAR-1]
    if len(baseline) != 10:
        raise ValueError("Need ten pre-event years")
    previous_year = int(before.idxmax())
    previous = float(before.loc[previous_year])
    mean = float(baseline.mean())
    std = float(baseline.std(ddof=1))
    following = float(g.loc[TARGET_YEAR+1])
    full["rank_through_2024"] = g.loc[:TARGET_YEAR].round(TIE_DECIMALS).rank(
        method="min", ascending=False)
    full["rank_through_2025"] = g.round(TIE_DECIMALS).rank(method="min", ascending=False)
    official_rows = []
    for year, reference in PUBLISHED.items():
        actual = float(g.loc[year])
        observed = float(full.loc[year, "observed_growth_ppm"])
        official_rows.append({"year": year, "publication_date": "2025-01-16",
                              "published_growth_ppm": reference,
                              "current_growth_ppm": actual,
                              "current_observed_only_growth_ppm": observed,
                              "current_minus_published_ppm": actual-reference})
    comparisons = pd.DataFrame(official_rows)
    top = g.sort_values(ascending=False, kind="stable").head(5)
    metrics = {
        "target_year": TARGET_YEAR, "last_complete_year_in_analysis": LAST_YEAR,
        "growth_definition": "Arithmetic mean of 12 months in y minus arithmetic mean in y-1",
        "main_column": "co2_filled", "target_growth_ppm": target,
        "rank_through_2024": historical_position(g.loc[:TARGET_YEAR], TARGET_YEAR),
        "rank_through_2025": historical_position(g, TARGET_YEAR),
        "observed_only_rank_through_2024": historical_position(
            full.loc[:TARGET_YEAR, "observed_growth_ppm"], TARGET_YEAR),
        "observed_only_rank_through_2025": historical_position(full.observed_growth_ppm, TARGET_YEAR),
        "previous_record": {"year": previous_year, "growth_ppm": previous,
                            "difference_ppm": target-previous,
                            "relative_difference_percent": (target/previous-1)*100},
        "pre_event_baseline": {"start_year": int(baseline.index.min()),
                               "end_year": int(baseline.index.max()), "n": len(baseline),
                               "mean_ppm_per_year": mean, "sample_sd_ppm_per_year": std,
                               "excess_ppm": target-mean,
                               "relative_excess_percent": (target/mean-1)*100,
                               "descriptive_sd_units": (target-mean)/std,
                               "interpretation": "Descriptive comparison, not a detrended anomaly or p-value"},
        "following_year": {"year": TARGET_YEAR+1, "growth_ppm": following,
                           "growth_difference_from_2024_ppm": following-target,
                           "growth_change_from_2024_percent": (following/target-1)*100,
                           "annual_mean_2023_ppm": float(annual.loc[2023, "mean_ppm"]),
                           "annual_mean_2024_ppm": float(annual.loc[2024, "mean_ppm"]),
                           "annual_mean_2025_ppm": float(annual.loc[2025, "mean_ppm"])},
        "top_5_through_2025": [{"year": int(y), "growth_ppm": float(v)} for y, v in top.items()],
        "official_reference_comparison": comparisons.to_dict("records"),
        "historical_value_difference_status": "Unresolved; archived values not retrieved",
        "published_record_difference_ppm": PUBLISHED[2024]-PUBLISHED[2016],
        "published_record_relative_difference_percent": (PUBLISHED[2024]/PUBLISHED[2016]-1)*100,
        "notes": ["2026 is incomplete and excluded.",
                  "MKO replacement observations are retained as supplied.",
                  "ECDF/rank describe the sample; they are not exceedance probabilities or return periods.",
                  "No emissions, ENSO or sink time series is used to estimate causal contributions."],
    }
    return metrics, full, comparisons


def figures(annual: pd.DataFrame, metrics: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold"})
    fig, (ax, ranking) = plt.subplots(1, 2, figsize=(12, 5.8),
                                    gridspec_kw={"width_ratios": [1.8, 1]}, layout="constrained")
    recent = annual.loc[2014:2025, "growth_ppm"]
    colors = ["#b64d29" if year == 2024 else "#146b8b" if year == 2016
              else "#344e62" if year == 2025 else "#b6c9d2" for year in recent.index]
    ax.bar(recent.index, recent, color=colors)
    baseline = metrics["pre_event_baseline"]["mean_ppm_per_year"]
    ax.axhline(baseline, color="#777777", ls="--", lw=1.3,
               label=f"2014–2023 mean: {baseline:.3f}")
    for year in (2016, 2024, 2025):
        ax.text(year, recent.loc[year]+.07, f"{recent.loc[year]:.3f}", ha="center", fontsize=10)
    ax.set(title="2024 in its recent context", xlabel="Year",
           ylabel="Annual CO2 increase (ppm/year)", ylim=(0, 4.1), xticks=recent.index)
    ax.tick_params(axis="x", rotation=50)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=.15)
    top = metrics["top_5_through_2025"]
    ranking.barh(range(len(top)), [r["growth_ppm"] for r in top],
                 color=["#b64d29" if r["year"] == 2024 else "#7899aa" for r in top])
    ranking.set(yticks=range(len(top)), yticklabels=[str(r["year"]) for r in top],
                xlabel="Annual CO2 increase (ppm/year)", title="Top 5 | 1960–2025", xlim=(0, 4.1))
    ranking.invert_yaxis()
    for i, r in enumerate(top):
        ranking.text(r["growth_ppm"]+.06, i, f"{r['growth_ppm']:.3f}", va="center", fontsize=9)
    ranking.grid(axis="x", alpha=.15)
    fig.text(.99, -.02, "Source: Scripps CO2 Program, UC San Diego | Current snapshot; 12-month annual-mean differences",
             fontsize=8, ha="right", color="#555555")
    fig.savefig(IMAGES / "result3_01_record_context.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Korean presentation version: every annual increase since 1960, with the 2024 record marked.
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    korean = next((n for n in ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR",
                               "WenQuanYi Zen Hei") if n in available), "DejaVu Sans")
    with plt.rc_context({"font.family": korean, "font.size": 16, "axes.unicode_minus": False}):
        every = annual.loc[1960:2025, "growth_ppm"]
        fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
        ax.bar(every.index, every, color=["#b64d29" if y == 2024 else "#b6c9d2" for y in every.index], width=.8)
        ax.text(2025.6, 3.72, f"2024년 {every.loc[2024]:.2f}ppm\n(역대 최대)", ha="right", va="bottom",
                fontsize=18, fontweight="bold", color="#b64d29")
        ax.text(2016.4, 3.46, f"2016년 {every.loc[2016]:.2f}ppm\n(이전 최고)", ha="right", va="bottom",
                fontsize=15, color="#444444")
        ax.set(title="연도별 CO₂ 증가량 (1960–2025년)", xlabel="연도",
               ylabel="1년 동안의 CO₂ 증가량 (ppm)", ylim=(0, 4.2), xlim=(1958.5, 2026.5))
        ax.grid(axis="y", alpha=.18)
        fig.savefig(IMAGES / "result3_03_record_presentation.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    fig, (cdf, level) = plt.subplots(1, 2, figsize=(12, 5.6), layout="constrained")
    historical = np.sort(annual.loc[1960:2023, "growth_ppm"].to_numpy())
    target = metrics["target_growth_ppm"]
    # Extend beyond the largest pre-event value so the 100% plateau is visible.
    xx = np.r_[historical[0]-.1, historical, max(target, historical[-1])+.15]
    yy = np.r_[0, np.arange(1, len(historical)+1)/len(historical), 1]
    cdf.step(xx, yy*100, where="post", color="#146b8b", lw=2)
    cdf.axvline(target, color="#b64d29", ls="--", lw=1.3)
    cdf.scatter([target], [100], color="#b64d29", zorder=5)
    cdf.annotate(f"2024: {target:.3f} ppm/year\nAbove all 64 prior values",
                 (target, 100), xytext=(.50, .35), textcoords="axes fraction", fontsize=10,
                 bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85})
    cdf.set(title="Position relative to 1960–2023", xlabel="Annual CO2 increase (ppm/year)",
            ylabel="Share of prior years at or below this rate (%)", ylim=(-2, 106))
    cdf.grid(alpha=.15)
    years = np.array([2023, 2024, 2025])
    levels = annual.loc[years, "mean_ppm"].to_numpy()
    level.plot(years, levels, marker="o", color="#344e62", lw=2)
    for year, value in zip(years, levels):
        level.annotate(f"{value:.3f}", (year, value), xytext=(0, 12),
                       textcoords="offset points", ha="center", fontsize=10)
    for year, value in ((2023.5, annual.loc[2024, "growth_ppm"]),
                        (2024.5, annual.loc[2025, "growth_ppm"])):
        level.text(year, levels[0]+(year-2023)*(levels[-1]-levels[0])/2-.6,
                   f"+{value:.3f} ppm", ha="center", color="#b64d29", fontsize=10)
    level.set(title="Slower growth still raises concentration", xlabel="Year",
              ylabel="Annual mean CO2 (ppm)", xticks=years,
              xlim=(2022.8, 2025.2), ylim=(levels.min()-.8, levels.max()+1))
    level.grid(alpha=.15)
    fig.text(.99, -.02, "Empirical distribution is descriptive, not a stationary probability model | Same Scripps record",
             fontsize=8, ha="right", color="#555555")
    fig.savefig(IMAGES / "result3_02_distribution_and_concentration.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    raw = RAW.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != json.loads(METADATA.read_text(encoding="utf-8"))["sha256"]:
        raise ValueError("Raw snapshot hash mismatch")
    rows, _ = parse(raw)
    _, annual = prepare(rows)
    metrics, context, comparisons = summarize(annual)
    metrics["raw_sha256"] = digest
    metrics["annual_growth_2023_ppm"] = float(annual.loc[2023, "growth_ppm"])
    for folder in (PROCESSED, RESULTS, IMAGES):
        folder.mkdir(parents=True, exist_ok=True)
    context.to_csv(PROCESSED / "result3_annual.csv", float_format="%.10f")
    comparisons.to_csv(PROCESSED / "result3_publication_comparison.csv", index=False, float_format="%.10f")
    (RESULTS / "result3_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    figures(annual, metrics)
    for key in ("target_growth_ppm", "rank_through_2024", "rank_through_2025",
                "previous_record", "pre_event_baseline", "following_year"):
        print(key, json.dumps(metrics[key], ensure_ascii=False))
    print(comparisons.to_string(index=False))
    print("Wrote metrics, 2 CSVs and 3 figures")


if __name__ == "__main__":
    main()
