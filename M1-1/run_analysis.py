"""Rebuild all outputs and run tests using the current Python environment.

Usage: python run_analysis.py
Run from any directory. Existing raw data are reused without network access.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STEPS = ["src/collect_data.py", "src/analyze_result1.py", "src/analyze_result2.py",
         "src/analyze_result3.py", "src/check_data_quality.py", "src/build_report.py",
         "src/build_presentation.py"]


def main() -> None:
    for step in STEPS:
        print(f"\n=== {step} ===", flush=True)
        subprocess.run([sys.executable, str(ROOT / step)], cwd=ROOT, check=True)
    print("\n=== automated tests ===", flush=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=ROOT, check=True)
    print("\nAll analysis steps and tests completed. See REPORT.md and presentation.html.", flush=True)


if __name__ == "__main__":
    main()
