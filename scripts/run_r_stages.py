"""
Orchestrator: runs all R and Python estimation stages in dependency order.
Safe to re-run: skips stages whose primary output already exists (use --force to override).

Execution order (per spec):
  01-07  (assumed already done — panel_powiat.parquet must exist)
  R: 10_sdid.R            → sdid_estimates.parquet
  R: 11_gsynth.R          → gsynth_gaps.parquet
  R: 11b_nuts3_analysis.R → nuts3_lp_irfs.parquet
  Py: 08_local_projections.py → lp_irfs.parquet
  Py: 09_pvar_forecast.py     → pvar_forecasts.parquet
  Py: 09b_arima_unemp.py      → arima_unemployment_forecast.parquet

Usage:
  python scripts/run_r_stages.py
  python scripts/run_r_stages.py --force          # re-run all stages
  python scripts/run_r_stages.py --stages 10 11   # run specific R stages only
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"

# Full path fallback for Windows where Rscript may not be on PATH
RSCRIPT_FALLBACK = r"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"


def find_rscript() -> str:
    r = shutil.which("Rscript")
    if r:
        return r
    if Path(RSCRIPT_FALLBACK).exists():
        return RSCRIPT_FALLBACK
    raise RuntimeError(
        "Rscript not found. Install R or add it to PATH.\n"
        f"Expected fallback: {RSCRIPT_FALLBACK}"
    )


STAGES = [
    {
        "id": "10",
        "label": "Stage 10 — Synthetic DiD (R)",
        "type": "R",
        "script": "scripts/r/10_sdid.R",
        "output": PROCESSED / "sdid_estimates.parquet",
    },
    {
        "id": "11",
        "label": "Stage 11 — Generalised Synthetic Control (R)",
        "type": "R",
        "script": "scripts/r/11_gsynth.R",
        "output": PROCESSED / "gsynth_gaps.parquet",
    },
    {
        "id": "11b",
        "label": "Stage 11b — NUTS-3 GDP Analysis (R)",
        "type": "R",
        "script": "scripts/r/11b_nuts3_analysis.R",
        "output": PROCESSED / "nuts3_lp_irfs.parquet",
    },
    {
        "id": "08",
        "label": "Stage 08 — Local Projections (Python)",
        "type": "Python",
        "script": "scripts/08_local_projections.py",
        "output": PROCESSED / "lp_irfs.parquet",
    },
    {
        "id": "09",
        "label": "Stage 09 — Panel VAR Forecast (Python)",
        "type": "Python",
        "script": "scripts/09_pvar_forecast.py",
        "output": PROCESSED / "pvar_forecasts.parquet",
    },
    {
        "id": "09b",
        "label": "Stage 09b — ARIMA Unemployment (Python)",
        "type": "Python",
        "script": "scripts/09b_arima_unemp.py",
        "output": PROCESSED / "arima_unemployment_forecast.parquet",
    },
]


def run_stage(stage: dict, rscript: str, force: bool) -> bool:
    label  = stage["label"]
    script = ROOT / stage["script"]
    output = stage["output"]

    if not force and output.exists():
        print(f"  [SKIP]  {label}  (output exists: {output.name})")
        return True

    if not script.exists():
        print(f"  [ERROR] Script not found: {script}")
        return False

    print(f"\n{'='*60}")
    print(f"  Running: {label}")
    print(f"  Script:  {stage['script']}")
    print(f"{'='*60}")

    t0 = time.time()
    if stage["type"] == "R":
        cmd = [rscript, str(script)]
    else:
        cmd = [sys.executable, str(script)]

    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n  [FAILED] {label} (exit {result.returncode}, {elapsed:.1f}s)")
        return False

    print(f"\n  [OK]    {label}  ({elapsed:.1f}s)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run estimation stages in order.")
    parser.add_argument("--force", action="store_true", help="Re-run all stages (ignore existing outputs)")
    parser.add_argument("--stages", nargs="+", metavar="ID", help="Run only these stage IDs (e.g. 10 11 09)")
    args = parser.parse_args()

    # Preflight: panel_powiat.parquet must exist
    panel_path = PROCESSED / "panel_powiat.parquet"
    if not panel_path.exists():
        print(f"ERROR: {panel_path} not found. Run stages 01-07 first.")
        sys.exit(1)

    try:
        rscript = find_rscript()
        print(f"Rscript: {rscript}")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    stages_to_run = STAGES
    if args.stages:
        ids = set(args.stages)
        stages_to_run = [s for s in STAGES if s["id"] in ids]
        if not stages_to_run:
            print(f"ERROR: No stages matched IDs: {args.stages}")
            sys.exit(1)

    print(f"\nPL-Capital-Reform-DiD — Estimation Orchestrator")
    print(f"Stages to run: {[s['id'] for s in stages_to_run]}")
    print(f"Force re-run:  {args.force}\n")

    failed = []
    for stage in stages_to_run:
        ok = run_stage(stage, rscript, force=args.force)
        if not ok:
            failed.append(stage["id"])
            print(f"\nAborting: stage {stage['id']} failed.")
            break

    print(f"\n{'='*60}")
    if failed:
        print(f"FAILED stages: {failed}")
        sys.exit(1)
    else:
        completed = [s["id"] for s in stages_to_run]
        print(f"All stages complete: {completed}")
        # Report output sizes
        for s in stages_to_run:
            p = s["output"]
            if p.exists():
                kb = p.stat().st_size / 1024
                print(f"  {p.name:<45} {kb:>8.1f} KB")


if __name__ == "__main__":
    main()
