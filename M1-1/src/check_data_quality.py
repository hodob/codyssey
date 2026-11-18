"""Summarize one raw snapshot and flag, but never delete, residual candidates."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from collect_data import ROOT, RAW, METADATA, parse
from analyze_result2 import extract_seasonal

RESULTS = ROOT / "results"
PROCESSED = ROOT / "data/processed"
THRESHOLD = 3.5
NORMAL_MAD_FACTOR = 0.6744897501960817


def residual_flags(monthly: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Robust standardized residuals, fitting the scale to measured months only."""
    result = monthly[["date", "year", "month", "station", "co2", "remaining_residual_ppm"]].copy()
    observed = result.co2.notna()
    values = result.loc[observed, "remaining_residual_ppm"].to_numpy()
    median = float(np.median(values))
    mad = float(np.median(np.abs(values-median)))
    if mad <= 0 or not np.isfinite(mad):
        raise ValueError("Residual MAD must be finite and positive")
    result["robust_z"] = np.nan
    result.loc[observed, "robust_z"] = NORMAL_MAD_FACTOR*(values-median)/mad
    result["candidate"] = result.robust_z.abs() > THRESHOLD
    return result, {"method": "0.6744897501960817 * (residual - median) / MAD",
                    "residual_definition": "C - cubic trend - (four harmonics + 90–540 day residual bandpass)",
                    "filter_order": 2, "padding_months": 36,
                    "period": [1959, 2025], "observed_n": len(values),
                    "residual_median_ppm": median, "residual_mad_ppm": mad,
                    "threshold_abs_z": THRESHOLD,
                    "candidate_count": int(result.candidate.sum()),
                    "candidate_months": result.loc[result.candidate, "date"].dt.strftime("%Y-%m").tolist(),
                    "action": "retain all observations; candidate is not a confirmed measurement error"}


def main() -> None:
    raw = RAW.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if digest != metadata["sha256"]:
        raise ValueError("Raw snapshot hash mismatch")
    rows, _ = parse(raw)
    data = pd.DataFrame(rows)
    measured = data.loc[data.co2.notna()]
    analysis = data.loc[data.year.between(1959, 2025)]
    seasonal, _, _ = extract_seasonal(rows, end=2025)
    flags, diagnostic = residual_flags(seasonal)
    result = {
        "raw_sha256": digest,
        "calendar_n": len(data), "observed_n": len(measured),
        "observed_start": f"{measured.iloc[0].year:04d}-{measured.iloc[0].month:02d}",
        "observed_end": f"{measured.iloc[-1].year:04d}-{measured.iloc[-1].month:02d}",
        "raw_missing_n": int(data.co2.isna().sum()),
        "primary_analysis_calendar_n": len(analysis),
        "primary_analysis_observed_n": int(analysis.co2.notna().sum()),
        "primary_analysis_missing_n": int(analysis.co2.isna().sum()),
        "observed_analysis_min_ppm": float(analysis.co2.min()),
        "observed_analysis_max_ppm": float(analysis.co2.max()),
        "primary_analysis_station_counts": analysis.station.value_counts().to_dict(),
        "plausibility_screen": "Finite concentration strictly between 200 and 1000 ppm; not a physical error criterion",
        "residual_diagnostic": diagnostic,
        "deleted_observations": 0,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    flags.to_csv(PROCESSED / "quality_residual_flags.csv", index=False, float_format="%.10f")
    (RESULTS / "data_quality_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
