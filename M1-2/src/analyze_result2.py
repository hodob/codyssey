"""Seasonal amplitude from one Scripps monthly record, following Jin et al. (2022).

The published structure is implemented; undocumented filter/GLS settings are
explicit project choices, not a claim of identical author-code reproduction.
"""
from __future__ import annotations

import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize_scalar
from scipy.signal import butter, sosfiltfilt
from scipy.stats import t as student_t
import statsmodels.api as sm

from display_values import format_number
from collect_data import ROOT, RAW, METADATA, parse

PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
IMAGES = ROOT / "images"
DAYS_PER_YEAR = 365.25
CUTOFF_PERIOD_DAYS = (540., 90.)
DEFAULT_ORDER = 2
DEFAULT_PADLEN = 36


def extract_seasonal(rows: list[dict], start: int = 1959, end: int = 2019,
                     order: int = DEFAULT_ORDER, padlen: int = DEFAULT_PADLEN,
                     filling: str = "linear") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Joint cubic + four harmonics; band-pass residual; yearly max minus min."""
    if filling not in ("linear", "provider"):
        raise ValueError("Unsupported filling method")
    d = pd.DataFrame(rows)
    d = d.loc[d.year.between(start, end)].copy().reset_index(drop=True)
    serials = (12*d.year+d.month).to_numpy()
    if len(d) != 12*(end-start+1) or np.any(np.diff(serials) != 1):
        raise ValueError("Expected full consecutive calendar years")
    d["date"] = pd.to_datetime(dict(year=d.year, month=d.month, day=15))
    missing = d.co2.isna()
    missing_months = d.loc[missing, "date"].dt.strftime("%Y-%m").tolist()
    if missing_months != ["1964-02", "1964-03", "1964-04"]:
        raise ValueError(f"Unexpected missing pattern; review before fitting: {missing_months}")
    d["linear_interpolated"] = missing & (filling == "linear")
    d["analysis_co2_ppm"] = (d.co2.interpolate(method="linear", limit_area="inside")
                              if filling == "linear" else d.co2_filled)
    if d.analysis_co2_ppm.isna().any():
        raise ValueError("Missing analysis concentrations after filling")
    time = d.decimal_year.astype(float).to_numpy()
    # Center/scale the polynomial, without changing its cubic function space.
    center = float(time.mean())
    scaled_time = (time-center)/10
    polynomial = np.column_stack([scaled_time**j for j in range(4)])
    harmonic = np.column_stack([f(2*np.pi*j*time)
                               for j in range(1, 5) for f in (np.sin, np.cos)])
    design = np.column_stack([polynomial, harmonic])
    values = d.analysis_co2_ppm.to_numpy(dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank != 12:
        raise ValueError("Rank-deficient joint polynomial/harmonic fit")
    d["polynomial_trend_ppm"] = polynomial @ coefficients[:4]
    d["climatological_harmonic_ppm"] = harmonic @ coefficients[4:]
    residual = values-design @ coefficients
    sos = butter(order, [DAYS_PER_YEAR/p for p in CUTOFF_PERIOD_DAYS],
                 btype="bandpass", fs=12., output="sos")
    filtered = sosfiltfilt(sos, residual, padtype="odd", padlen=padlen)
    d["joint_fit_residual_ppm"] = residual
    d["bandpassed_residual_ppm"] = filtered
    d["seasonal_component_ppm"] = d.climatological_harmonic_ppm+filtered
    d["remaining_residual_ppm"] = residual-filtered
    # Yearly centering is only for comparing shapes; max-min is unchanged.
    d["centered_seasonal_ppm"] = (d.seasonal_component_ppm
        - d.groupby("year").seasonal_component_ppm.transform("mean"))
    amplitudes = []
    for year, group in d.groupby("year"):
        high = group.loc[group.seasonal_component_ppm.idxmax()]
        low = group.loc[group.seasonal_component_ppm.idxmin()]
        amplitudes.append({"year": int(year),
                           "amplitude_ppm": float(high.seasonal_component_ppm-low.seasonal_component_ppm),
                           "peak_month": int(high.month), "trough_month": int(low.month),
                           "peak_value_ppm": float(high.seasonal_component_ppm),
                           "trough_value_ppm": float(low.seasonal_component_ppm),
                           "filled_months": int(group.co2.isna().sum())})
    annual = pd.DataFrame(amplitudes).set_index("year")
    details = {
        "start_year": start, "end_year": end, "monthly_n": len(d), "filling": filling,
        "filled_months": missing_months, "polynomial_degree": 3, "harmonics": 4,
        "polynomial_center_decimal_year": center, "polynomial_scale_years": 10,
        "joint_coefficients": coefficients.tolist(), "filter_order": order,
        "filter_cutoff_period_days": list(CUTOFF_PERIOD_DAYS), "sample_frequency_per_year": 12,
        "days_per_year": DAYS_PER_YEAR, "filter_implementation": "SciPy butter SOS + sosfiltfilt",
        "filter_padding": {"type": "odd", "length_months": padlen},
        "sos_coefficients": sos.tolist(),
    }
    return d, annual, details


def gls_ar1(annual: pd.DataFrame, start: int = 1959, end: int = 2019) -> dict:
    s = annual.loc[start:end, "amplitude_ppm"].dropna()
    years = s.index.to_numpy(dtype=int)
    n = len(s)
    if n < 5 or len(set(years)) != n:
        raise ValueError("Need distinct annual amplitudes and at least five years")
    x = np.column_stack([np.ones(n), (years-start)/10])
    y = s.to_numpy(dtype=float)
    distances = np.abs(years[:, None]-years[None, :])

    def evaluate(rho: float) -> tuple[float, np.ndarray, np.ndarray]:
        correlation = rho**distances
        factor = cho_factor(correlation, lower=True)
        inv_x = cho_solve(factor, x)
        normal = x.T @ inv_x
        beta = np.linalg.solve(normal, x.T @ cho_solve(factor, y))
        error = y-x @ beta
        rss = float(error @ cho_solve(factor, error))
        _, logdet_normal = np.linalg.slogdet(normal)
        logdet_correlation = float(2*np.log(np.diag(factor[0])).sum())
        objective = (n-2)*np.log(rss/(n-2))+logdet_correlation+logdet_normal
        covariance = np.linalg.inv(normal)*rss/(n-2)
        return float(objective), beta, covariance

    optimum = minimize_scalar(lambda rho: evaluate(rho)[0],
                              bounds=(-.95, .95), method="bounded",
                              options={"xatol": 1e-10})
    if not optimum.success or abs(optimum.x) > .949:
        raise ValueError("AR(1) REML optimum failed or hit boundary")
    _, beta, covariance = evaluate(float(optimum.x))
    se = float(np.sqrt(covariance[1, 1]))
    halfwidth = float(student_t.ppf(.975, n-2)*se)
    return {
        "start_year": start, "end_year": end, "n": n,
        "slope_ppm_per_decade": float(beta[1]), "slope_standard_error": se,
        "slope_ci95": [float(beta[1]-halfwidth), float(beta[1]+halfwidth)],
        "intercept_at_start_ppm": float(beta[0]), "rho_ar1": float(optimum.x),
        "method": "GLS, correlation=rho^calendar-year-distance, rho estimated by REML; t CI with n-2 df",
    }


def sensitivity(rows: list[dict], baseline: pd.DataFrame) -> list[dict]:
    result = []
    for order in range(1, 7):
        _, annual, _ = extract_seasonal(rows, order=order)
        result.append({"scenario": f"filter_order_{order}", **gls_ar1(annual)})
    for padlen in (12, 72):
        _, annual, _ = extract_seasonal(rows, padlen=padlen)
        result.append({"scenario": f"padding_{padlen}_months", **gls_ar1(annual)})
    _, provider, _ = extract_seasonal(rows, filling="provider")
    result.append({"scenario": "provider_fill_instead_of_linear", **gls_ar1(provider)})
    result.append({"scenario": "drop_boundary_years", **gls_ar1(baseline, 1960, 2018)})
    result.append({"scenario": "drop_interpolated_year_1964", **gls_ar1(baseline.drop(index=1964))})
    result.append({"scenario": "recent_paper_subperiod", **gls_ar1(baseline, 1986, 2019)})
    return result


def figures(monthly: pd.DataFrame, annual: pd.DataFrame, metrics: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold"})
    fig, ax = plt.subplots(figsize=(10, 5.8), layout="constrained")
    for start, end, color in ((1959, 1968, "#146b8b"), (2010, 2019, "#b64d29")):
        curve = monthly.loc[monthly.year.between(start, end)].groupby("month").centered_seasonal_ppm.mean()
        ax.plot(curve.index, curve, marker="o", color=color, lw=2, label=f"{start}–{end} mean seasonal shape")
    ax.axhline(0, color="#777777", lw=.8)
    ax.set(xticks=range(1, 13), xlabel="Month", ylabel="Year-centered seasonal component (ppm)",
           title="A larger seasonal swing, separate from the rising concentration")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=.15)
    fig.text(.99, -.02, "Source: Scripps CO2 Program, UC San Diego | Cubic + 4 harmonics; 90–540 day residual bandpass",
             fontsize=8, ha="right", color="#555555")
    fig.savefig(IMAGES / "result2_01_seasonal_shapes.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    main = metrics["main_gls"]
    years = annual.index.to_numpy()
    fig, ax = plt.subplots(figsize=(11, 5.8), layout="constrained")
    ax.plot(years, annual.amplitude_ppm, color="#7899aa", lw=1, marker="o", ms=3.5,
            label="Annual peak-to-trough amplitude")
    fitted = main["intercept_at_start_ppm"]+main["slope_ppm_per_decade"]*(years-1959)/10
    ax.plot(years, fitted, color="#b64d29", lw=2,
            label=f"GLS trend: +{main['slope_ppm_per_decade']:.3f} ppm/decade")
    for start, end, color in ((1959, 1968, "#146b8b"), (2010, 2019, "#b64d29")):
        value = annual.loc[start:end, "amplitude_ppm"].mean()
        ax.hlines(value, start, end, color=color, lw=3,
                  label=f"{start}–{end} mean amplitude: {value:.3f} ppm")
    ax.set(title="Seasonal amplitude increased, but not uniformly | 1959–2019",
           xlabel="Year", ylabel="Seasonal peak-to-trough amplitude (ppm)")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(alpha=.15)
    fig.text(.99, -.02, "Annual maximum − minimum of harmonic + filtered residual | Filter order 2; AR(1) GLS",
             fontsize=8, ha="right", color="#555555")
    fig.savefig(IMAGES / "result2_02_amplitude_trend.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Simplified Korean version for the presentation: labelled points and one trend line, large type.
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    korean = next((n for n in ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR",
                               "WenQuanYi Zen Hei") if n in available), "DejaVu Sans")
    rc = {"font.family": korean, "font.size": 16, "axes.unicode_minus": False}
    early_curve = monthly.loc[monthly.year.between(1959, 1968)].groupby("month").centered_seasonal_ppm.mean()
    late_curve = monthly.loc[monthly.year.between(2010, 2019)].groupby("month").centered_seasonal_ppm.mean()

    def amplitude_arrow(ax, curve, x, color, label, fontsize=17):
        top, bottom = float(curve.max()), float(curve.min())
        ax.hlines([top, bottom], 1, x, color=color, lw=1.3, ls=":")
        ax.annotate("", xy=(x, top), xytext=(x, bottom),
                    arrowprops=dict(arrowstyle="<->", color=color, lw=3))
        ax.text(x + .15, (top + bottom) / 2, label, color=color, fontsize=fontsize,
                fontweight="bold", va="center")

    with plt.rc_context(rc):
        # Slide 6: two mean seasonal cycles with the amplitude (maximum - minimum) marked on each.
        fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
        ax.plot(early_curve.index, early_curve, marker="o", ms=8, lw=3.5, color="#146b8b", label="1959–1968년 평균")
        ax.plot(late_curve.index, late_curve, marker="o", ms=8, lw=3.5, color="#b64d29", label="2010–2019년 평균")
        ax.axhline(0, color="#777777", lw=.8)
        amplitude_arrow(ax, early_curve, 12.6, "#146b8b", "진폭")
        amplitude_arrow(ax, late_curve, 13.8, "#b64d29", "진폭")
        ax.set(xticks=range(1, 13), xlim=(.5, 14.9), xlabel="월", ylabel="계절 성분 (ppm, 장기 상승분 제외)",
               title="계절 곡선과 진폭 (최고점과 최저점의 차)")
        ax.legend(loc="lower left", fontsize=15)
        ax.grid(alpha=.18)
        fig.savefig(IMAGES / "result2_04_seasonal_cycle_presentation.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

        # Slide 7: the amplitude is introduced on one cycle, then measured every year.
        fig, (cycle, trend) = plt.subplots(1, 2, figsize=(14, 6), layout="constrained",
                                           gridspec_kw={"width_ratios": [1, 2.1]}, sharey=False)
        cycle.plot(late_curve.index, late_curve, marker="o", ms=7, lw=3.5, color="#b64d29")
        cycle.axhline(0, color="#777777", lw=.8)
        amplitude_arrow(cycle, late_curve, 12.6, "#b64d29", "진폭")
        cycle.set(xticks=(1, 4, 7, 10), xlim=(.5, 14.2), xlabel="월 (예: 2010–2019년 평균)", ylabel="계절 성분 (ppm)",
                  title="한 해의 계절 곡선")
        trend.plot(years, annual.amplitude_ppm, color="#8aa5b4", lw=1.6, marker="o", ms=6, label="해마다 잰 진폭")
        trend.plot(years, fitted, color="#b64d29", lw=5, label="장기 추세")
        trend.set(title="진폭도 장기적으로 증가", xlabel="연도",
                  ylabel="진폭 (왼쪽 화살표의 길이, ppm)", ylim=(5, 8.3))
        trend.legend(loc="upper left", fontsize=15)
        trend.grid(alpha=.18)
        fig.savefig(IMAGES / "result2_03_amplitude_trend_presentation.png", dpi=180, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    raw = RAW.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != json.loads(METADATA.read_text(encoding="utf-8"))["sha256"]:
        raise ValueError("Raw snapshot hash mismatch")
    rows, _ = parse(raw)
    monthly, annual, details = extract_seasonal(rows)
    main_gls = gls_ar1(annual)
    early = float(annual.loc[1959:1968].amplitude_ppm.mean())
    late = float(annual.loc[2010:2019].amplitude_ppm.mean())
    extension_monthly, extension_annual, extension_details = extract_seasonal(rows, end=2025)
    ols = sm.OLS(annual.amplitude_ppm.to_numpy(), sm.add_constant((annual.index.to_numpy()-1959)/10)).fit(
        cov_type="HAC", cov_kwds={"maxlags": 3, "use_correction": True}, use_t=True)
    metrics = {
        "raw_sha256": digest, "method_details": details, "main_gls": main_gls,
        "paper_reference": {"period": [1959, 2019], "trend_ppm_per_decade": .22,
                            "reported_plus_minus": .034,
                            "doi": "10.1029/2021JD035892"},
        "early_vs_late": {"early_years": [1959, 1968], "late_years": [2010, 2019],
                          "early_mean_amplitude_ppm": early, "late_mean_amplitude_ppm": late,
                          "difference_ppm": late-early, "relative_change_percent": (late/early-1)*100},
        "ols_hac_crosscheck": {"slope_ppm_per_decade": float(ols.params[1]),
                               "slope_ci95": ols.conf_int()[1].tolist(), "hac_lags": 3},
        "sensitivity": sensitivity(rows, annual),
        "extended_method_details": extension_details,
        "extended_gls_1959_2025": gls_ar1(extension_annual, end=2025),
    }
    for folder in (PROCESSED, RESULTS, IMAGES):
        folder.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(PROCESSED / "result2_monthly.csv", index=False, float_format="%.10f")
    annual.to_csv(PROCESSED / "result2_amplitudes.csv", float_format="%.10f")
    extension_annual.to_csv(PROCESSED / "result2_amplitudes_extended.csv", float_format="%.10f")
    (RESULTS / "result2_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    figures(monthly, annual, metrics)
    print(json.dumps(main_gls, indent=2))
    print(json.dumps(metrics["early_vs_late"], indent=2))
    for item in metrics["sensitivity"]:
        print(item["scenario"], f"{item['slope_ppm_per_decade']:.6f}", item["slope_ci95"])
    print("Extension:", metrics["extended_gls_1959_2025"])
    print("Wrote metrics, 3 processed CSVs and 4 figures")


if __name__ == "__main__":
    main()
