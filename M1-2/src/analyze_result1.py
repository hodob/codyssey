"""Result 1: concentration and long-run annual growth in one Scripps record.

Run after collect_data.py. No network access or changes to the raw snapshot.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from display_values import format_number
from collect_data import ROOT, RAW, METADATA, parse

PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
IMAGES = ROOT / "images"
# Fixed comparison windows, matching the decades in the literature and its last
# complete 10-year window ending in 2024. The latest 10 full years are also shown.
PERIODS = [(1960, 1969), (1970, 1979), (1980, 1989), (1990, 1999),
           (2000, 2009), (2010, 2019), (2015, 2024), (2016, 2025)]


def prepare(rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = pd.DataFrame(rows)
    monthly["date"] = pd.to_datetime(dict(year=monthly.year, month=monthly.month, day=15))
    monthly["provider_filled"] = monthly.co2.isna() & monthly.co2_filled.notna()
    monthly["growth_yoy_ppm"] = monthly.co2_filled.diff(12)
    # Trailing, not centered: the label is the final month of the window.
    monthly["trailing_12m_mean_ppm"] = monthly.co2_filled.rolling(12, min_periods=12).mean()
    annual = monthly.groupby("year").agg(
        observed_months=("co2", "count"), available_months=("co2_filled", "count"),
        observed_mean_ppm=("co2", "mean"), mean_ppm=("co2_filled", "mean"),
        provider_filled_months=("provider_filled", "sum"),
        alternative_station_months=("station", lambda x: int((x != "MLO").sum())),
    )
    annual.loc[annual.observed_months != 12, "observed_mean_ppm"] = np.nan
    annual.loc[annual.available_months != 12, "mean_ppm"] = np.nan
    # Keep all calendar years in the index: do not difference across missing years.
    annual["growth_ppm"] = annual.mean_ppm.diff()
    annual["observed_growth_ppm"] = annual.observed_mean_ppm.diff()
    annual["growth_uses_provider_fill"] = (
        annual.provider_filled_months + annual.provider_filled_months.shift(1).fillna(0)
    ) > 0
    return monthly, annual


def period_statistics(annual: pd.DataFrame) -> pd.DataFrame:
    records = []
    for start, end in PERIODS:
        window = annual.loc[start:end]
        records.append({
            "start_year": start, "end_year": end,
            "n_growth_years": int(window.growth_ppm.count()),
            "mean_growth_ppm": float(window.growth_ppm.mean()),
            "sd_growth_ppm": float(window.growth_ppm.std(ddof=1)),
            "observed_only_n": int(window.observed_growth_ppm.count()),
            "observed_only_mean_growth_ppm": float(window.observed_growth_ppm.mean()),
        })
    return pd.DataFrame(records)


def trend_fit(annual: pd.DataFrame, start: int, end: int, lag: int = 3,
              column: str = "growth_ppm") -> dict:
    s = annual.loc[start:end, column].dropna()
    if len(s) < 3 or np.any(np.diff(s.index.to_numpy()) != 1):
        raise ValueError("HAC trend needs consecutive annual growth values")
    x = sm.add_constant(s.index.to_numpy(dtype=float) - start)
    fit = sm.OLS(s.to_numpy(), x).fit(
        cov_type="HAC", cov_kwds={"maxlags": lag, "use_correction": True}, use_t=True,
    )
    interval = fit.conf_int(alpha=0.05)[1]
    return {
        "start_year": start, "end_year": end, "n": len(s), "column": column,
        "hac_lags": lag, "slope_ppm_per_year2": float(fit.params[1]),
        "slope_ci95": [float(v) for v in interval],
        "intercept_at_start_ppm_per_year": float(fit.params[0]),
        "r_squared": float(fit.rsquared),
        "residual_lag1_correlation": float(pd.Series(fit.resid).autocorr(1)),
        "inference": "OLS; Bartlett Newey-West HAC; n/(n-k) correction; t interval, df=n-k",
    }


def figures(monthly: pd.DataFrame, annual: pd.DataFrame,
            periods: pd.DataFrame, main: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white", "axes.titleweight": "bold"})
    # Only complete annual periods, not the partial boundary years, appear here.
    m = monthly.loc[monthly.year.between(1959, 2025)].copy()
    fig, ax = plt.subplots(figsize=(11, 5.7), layout="constrained")
    ax.plot(m.date, m.co2, color="#87a8bf", lw=.8, label="Monthly observations")
    ax.plot(m.date, m.trailing_12m_mean_ppm, color="#124c6a", lw=2,
            label="Trailing 12-month mean (provider-filled series)")
    filled = m.loc[m.provider_filled]
    ax.scatter(filled.date, filled.co2_filled, marker="x", color="#b6591b", s=35,
               label="Provider-filled months", zorder=5)
    for year in (1959, 2025):
        ax.annotate(f"{year}: {annual.loc[year, 'mean_ppm']:.2f} ppm annual mean",
                    (pd.Timestamp(year=year, month=7, day=1), annual.loc[year, "mean_ppm"]),
                    xytext=(10 if year == 1959 else -190, 22 if year == 1959 else -28),
                    textcoords="offset points", fontsize=10)
    ax.set(title="CO2 concentration keeps rising | 1959–2025", ylabel="CO2 (ppm)", xlabel="Year")
    ax.grid(alpha=.15)
    ax.legend(loc="upper left", fontsize=9)
    fig.text(.99, -.02, "Source: Scripps CO2 Program, UC San Diego | MLO record includes MKO replacement observations",
             ha="right", fontsize=8, color="#555555")
    fig.savefig(IMAGES / "result1_01_concentration.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    g = annual.loc[1960:2025, "growth_ppm"]
    fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
    ax.bar(g.index, g, color="#aec3ce", width=.8, label="Annual-mean difference")
    years = g.index.to_numpy()
    prediction = (main["intercept_at_start_ppm_per_year"]
                  + main["slope_ppm_per_year2"] * (years - main["start_year"]))
    ax.plot(years, prediction, color="#565656", lw=1.5, ls="--", label="Linear descriptive trend")
    for start, end, color in ((1960, 1969, "#146b8b"), (2015, 2024, "#b64d29")):
        value = float(periods.loc[periods.start_year == start, "mean_growth_ppm"].iloc[0])
        ax.hlines(value, start-.4, end+.4, color=color, lw=3,
                  label=f"{start}–{end} mean: {value:.3f} ppm/year")
        ax.axvspan(start-.4, end+.4, color=color, alpha=.055)
    ax.axhline(0, color="#444444", lw=.9)
    ax.set(title="The annual accumulation rate is higher in recent decades",
           xlabel="Year", ylabel="Annual CO2 increase (ppm/year)", ylim=(0, max(g)*1.2))
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=.15)
    fig.text(.99, -.02, "Annual increase = mean of year y − mean of year y−1 | Scripps provider-filled column",
             ha="right", fontsize=8, color="#555555")
    fig.savefig(IMAGES / "result1_02_annual_growth.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Both periods start from 0 ppm at the annual mean before their first year, so the rise over ten
    # years can be compared directly. Last value / 10 equals the period's mean annual increase.
    early = float(periods.loc[periods.start_year == 1960, "mean_growth_ppm"].iloc[0])
    recent = float(periods.loc[periods.start_year == 2015, "mean_growth_ppm"].iloc[0])
    c = annual.loc[1959:2025, "mean_ppm"].astype(float)
    rise_early = c.loc[1959:1969].to_numpy() - c[1959]
    rise_recent = c.loc[2014:2024].to_numpy() - c[2014]
    t = np.arange(11)
    fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
    ax.plot(t, rise_early, color="#2e8b57", lw=5, marker="o", ms=7,
            label=f"60 years ago (1959→1969): +{rise_early[-1]:.1f} ppm, {early:.2f} ppm/year")
    ax.plot(t, rise_recent, color="#c0392b", lw=5, marker="o", ms=7,
            label=f"Recent 10 years (2014→2024): +{rise_recent[-1]:.1f} ppm, {recent:.2f} ppm/year")
    ax.annotate("60 years ago", (10, rise_early[-1]), xytext=(-12, 14), textcoords="offset points",
                ha="right", fontsize=14, fontweight="bold", color="#2e8b57")
    ax.annotate("Recent 10 years", (10, rise_recent[-1]), xytext=(-12, 14), textcoords="offset points",
                ha="right", fontsize=14, fontweight="bold", color="#c0392b")
    ax.set(title=f"Same 10 years, {recent / early:.2f}x the CO2 increase",
           xlabel="Years since the start of each period", ylabel="CO2 increase since start (ppm)",
           xlim=(0, 10.3), ylim=(0, rise_recent[-1] * 1.12), xticks=range(0, 11))
    ax.grid(alpha=.15)
    ax.tick_params(labelsize=12)
    ax.legend(loc="upper left", fontsize=13)
    fig.text(.99, -.02, "Rise = annual mean CO2 minus the annual mean before the period start (1959 or 2014) | Scripps provider-filled column",
             ha="right", fontsize=8, color="#555555")
    fig.savefig(IMAGES / "result1_03_slope_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    raw = RAW.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != json.loads(METADATA.read_text(encoding="utf-8"))["sha256"]:
        raise ValueError("Raw snapshot hash mismatch")
    rows, _ = parse(raw)
    monthly, annual = prepare(rows)
    periods = period_statistics(annual)
    if not (periods.n_growth_years == 10).all():
        raise ValueError("One or more fixed comparison periods are incomplete")
    for path in (PROCESSED, RESULTS, IMAGES):
        path.mkdir(parents=True, exist_ok=True)
    early = float(periods.loc[periods.start_year == 1960, "mean_growth_ppm"].iloc[0])
    recent = float(periods.loc[periods.start_year == 2015, "mean_growth_ppm"].iloc[0])
    main_trend = trend_fit(annual, 1960, 2025)
    metrics = {
        "raw_sha256": digest, "main_column": "co2_filled",
        "annual_mean_years": [1959, 2025], "annual_growth_years": [1960, 2025],
        "main_period_provider_filled_months": monthly.loc[
            monthly.year.between(1959, 2025) & monthly.provider_filled, "date"
        ].dt.strftime("%Y-%m").tolist(),
        "comparison_1960s_vs_2015_2024": {
            "early_mean_ppm_per_year": early, "recent_mean_ppm_per_year": recent,
            "difference_ppm_per_year": recent-early, "ratio": recent/early,
        },
        "main_trend": main_trend,
        "trend_sensitivity": [trend_fit(annual, 1960, 2025, lag) for lag in (1, 3, 5, 10)]
            + [trend_fit(annual, a, b) for a, b in ((1960, 2024), (1970, 2025), (1980, 2025))]
            + [trend_fit(annual, 1966, 2025, column="observed_growth_ppm")],
    }
    monthly.to_csv(PROCESSED / "result1_monthly.csv", index=False, float_format="%.10f")
    annual.to_csv(PROCESSED / "result1_annual.csv", index=True, float_format="%.10f")
    periods.to_csv(PROCESSED / "result1_periods.csv", index=False, float_format="%.10f")
    (RESULTS / "result1_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    figures(monthly, annual, periods, main_trend)
    print(periods.to_string(index=False))
    print(json.dumps(metrics["comparison_1960s_vs_2015_2024"], indent=2))
    print(json.dumps(main_trend, indent=2))
    print("Wrote metrics, 3 processed CSVs, and 3 figures")


if __name__ == "__main__":
    main()
