"""Rebuild in a clean temporary copy with network disabled; compare outputs.

python src/verify_rebuild.py [--python /path/to/installed/environment/python]
The selected Python must already have the project dependencies installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    # Do not resolve symlinks: venv/bin/python may link to the system executable,
    # but its original location is what activates that environment's packages.
    python = str(Path(args.python).expanduser().absolute())
    generated = [ROOT/"REPORT.md", ROOT/"presentation.html"]
    for pattern in ("results/*_metrics.json",
                    "data/processed/*.csv", "images/*.png"):
        generated.extend(sorted(ROOT.glob(pattern)))
    if len(generated) < 20 or any(not p.is_file() for p in generated):
        raise ValueError("Generate all outputs before verifying a rebuild")
    before = {str(p.relative_to(ROOT)): sha(p) for p in generated}
    raw_hash = sha(ROOT/"data/raw/monthly_in_situ_co2_mlo.csv")
    with tempfile.TemporaryDirectory(prefix="co2-clean-rebuild-") as temporary:
        base = Path(temporary)
        clone = base/"project"
        shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "pi-session-*.html"))
        for relative in before:
            (clone/relative).unlink()
        (clone/"data/data_audit.json").unlink(missing_ok=True)
        guard = base/"network_guard"
        guard.mkdir()
        (guard/"sitecustomize.py").write_text(
            "import socket\n"
            "def blocked(*args, **kwargs):\n"
            "    raise RuntimeError('Network disabled during clean rebuild')\n"
            "socket.create_connection = blocked\n"
            "socket.socket.connect = blocked\n", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(guard)
        result = subprocess.run([python, str(clone/"run_analysis.py")], cwd=base,
                                env=env, capture_output=True, text=True, timeout=180)
        log = result.stdout+"\n"+result.stderr
        if result.returncode:
            raise RuntimeError(f"Clean rebuild failed:\n{log}")
        counts = re.findall(r"Ran (\d+) tests", log)
        if not counts or "\nOK\n" not in log:
            raise ValueError(f"Missing successful test run:\n{log}")
        after = {relative: sha(clone/relative) for relative in before}
        changed = [relative for relative in before if before[relative] != after[relative]]
        if changed:
            raise ValueError(f"Non-identical generated artifacts: {changed}")
        if sha(clone/"data/raw/monthly_in_situ_co2_mlo.csv") != raw_hash:
            raise ValueError("Raw snapshot was changed")
    version = subprocess.run([python,"-V"],capture_output=True,text=True,check=True).stdout.strip()
    summary = {
        "status": "passed", "python_version": version,
        "raw_sha256": raw_hash,
        "clean_copy": True, "generated_outputs_removed_before_run": True,
        "working_directory_outside_project": True, "network_disabled_in_child_python": True,
        "automated_tests_passed": int(counts[-1]),
        "byte_identical_artifact_count": len(before), "artifacts_sha256": before,
        "notes": ["Selected installed interpreter, different source/output directory; dependency installation is verified separately.",
                  "Audit creation timestamp is intentionally excluded from byte equality.",
                  "This check does not perform a GitHub upload or retrieve historical data."],
    }
    path = ROOT/"results/rebuild_verification.json"
    path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: clean offline rebuild, {len(before)} byte-identical artifacts, {counts[-1]} tests")
    print("Raw snapshot unchanged")
    print(f"Saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
