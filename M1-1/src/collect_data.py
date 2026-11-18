"""Download and audit Scripps monthly CO2. Python 3.10+, standard library only.

Run: python3 src/collect_data.py
Refresh explicitly: python3 src/collect_data.py --download
The original bytes are kept unchanged; audits never replace missing values.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/monthly_in_situ_co2_mlo.csv"
METADATA = ROOT / "data/raw/download_metadata.json"
AUDIT = ROOT / "data/data_audit.json"
URL = "https://keelinglabsites.ucsd.edu/websitedataco2/monthly_in_situ_co2_mlo.csv"
COLUMNS = ["year", "month", "excel_date", "decimal_year", "co2",
           "seasonally_adjusted", "fit", "seasonally_adjusted_fit",
           "co2_filled", "seasonally_adjusted_filled", "station"]
VALUE_COLUMNS = COLUMNS[4:10]


def parse(raw: bytes) -> tuple[list[dict], str]:
    text = raw.decode("utf-8-sig")
    rows = []
    for line in text.splitlines():
        if not re.match(r"^\s*\d{4},", line):
            continue
        cells = next(csv.reader([line], skipinitialspace=True))
        if len(cells) != len(COLUMNS):
            raise ValueError(f"Expected 11 fields, got {len(cells)}: {line}")
        row = dict(zip(COLUMNS, (cell.strip() for cell in cells)))
        row["year"], row["month"] = int(row["year"]), int(row["month"])
        if not 1 <= row["month"] <= 12:
            raise ValueError(f"Invalid month: {row}")
        for name in VALUE_COLUMNS:
            number = float(row[name])
            row[name] = None if number == -99.99 else number
            if row[name] is not None and not 200 < number < 1000:
                raise ValueError(f"Unexpected concentration: {row}")
        rows.append(row)
    if not rows:
        raise ValueError("No monthly data rows in response")
    serials = [r["year"] * 12 + r["month"] for r in rows]
    if any(b != a + 1 for a, b in zip(serials, serials[1:])):
        raise ValueError("Duplicate, out-of-order or missing calendar months")
    return rows, text


def month_label(row: dict) -> str:
    return f"{row['year']:04d}-{row['month']:02d}"


def summarize(rows: list[dict], text: str, digest: str) -> dict:
    available = [r for r in rows if r["co2"] is not None]
    complete = {}
    for column in ("co2", "co2_filled"):
        means = {}
        for year in sorted({r["year"] for r in rows}):
            values = [r[column] for r in rows if r["year"] == year and r[column] is not None]
            if len(values) == 12:
                means[year] = statistics.mean(values)
        complete[column] = means
    annual_checks = {}
    for column, means in complete.items():
        annual_checks[column] = {
            "complete_years": list(means),
            "reference_checks": {
                str(year): {
                    "annual_mean_ppm": means.get(year),
                    "previous_mean_ppm": means.get(year - 1),
                    "annual_mean_difference_ppm": (
                        means[year] - means[year - 1]
                        if year in means and year - 1 in means else None),
                } for year in (2016, 2024)
            },
        }
    return {
        "raw_sha256": digest,
        "audit_created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_archive_header": [line.strip(' \"') for line in text.splitlines()
                                  if "Baseline data" in line],
        "calendar_row_count": len(rows),
        "calendar_start": month_label(rows[0]),
        "calendar_end": month_label(rows[-1]),
        "observed_start": month_label(available[0]),
        "observed_end": month_label(available[-1]),
        "valid_observed_count": len(available),
        "columns_in_file": COLUMNS,
        "missing_marker": -99.99,
        "missing_by_column": {c: [month_label(r) for r in rows if r[c] is None]
                              for c in VALUE_COLUMNS},
        "source_filled_months": [month_label(r) for r in rows
                                 if r["co2"] is None and r["co2_filled"] is not None],
        "stations": dict(Counter(r["station"] for r in rows)),
        "non_MLO_rows": [{"month": month_label(r), "station": r["station"],
                          "co2_ppm": r["co2"]} for r in rows if r["station"] != "MLO"],
        "annual_completeness_and_reference_checks": annual_checks,
        "notes": [
            "Annual checks are arithmetic means of 12 available monthly values, then differences.",
            "Calendar rows can include empty months; calendar end is not last observation.",
            "Filled columns are provider estimates, not additional observations.",
            "Latest source revisions need not match rounded historical announcements exactly.",
            "No rows are imputed, excluded as outliers, or seasonally adjusted by this script.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly replace raw snapshot")
    args = parser.parse_args()
    if args.download or not RAW.exists():
        request = urllib.request.Request(URL, headers={"User-Agent": "CO2-course-project/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
            parse(content)  # Validate before replacing local snapshot.
            metadata = {
                "requested_url": URL,
                "resolved_url": response.geturl(),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "http_last_modified": response.headers.get("Last-Modified"),
                "content_type": response.headers.get("Content-Type"),
                "byte_count": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_bytes(content)
        METADATA.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    content = RAW.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if METADATA.exists():
        metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        if metadata["sha256"] != digest:
            raise ValueError("Raw snapshot hash does not match download metadata")
    else:
        raise ValueError("Missing download metadata; use --download to record provenance")
    rows, text = parse(content)
    result = summarize(rows, text, digest)
    AUDIT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Raw: {RAW.relative_to(ROOT)}")
    print(f"Audit: {AUDIT.relative_to(ROOT)}")
    print(f"Calendar rows: {len(rows)}; valid observed values: {result['valid_observed_count']}")
    print(f"Observed range: {result['observed_start']} to {result['observed_end']}")
    print(f"Source-filled months: {result['source_filled_months']}")
    print(f"Non-MLO rows: {result['non_MLO_rows']}")
    for column, item in result["annual_completeness_and_reference_checks"].items():
        print(column, json.dumps(item["reference_checks"], ensure_ascii=False))


if __name__ == "__main__":
    main()
