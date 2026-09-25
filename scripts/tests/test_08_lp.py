"""Tests for Stage 08 Local Projections."""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROCESSED = ROOT / "data" / "processed"


def test_lp_irfs_schema():
    """lp_irfs.parquet must have required columns and non-null values at h=0."""
    path = PROCESSED / "lp_irfs.parquet"
    assert path.exists(), "Run scripts/08_local_projections.py first"
    df = pd.read_parquet(path)
    required = {"outcome", "horizon", "coef", "se", "ci_lo_90", "ci_hi_90",
                "ci_lo_95", "ci_hi_95"}
    assert required.issubset(df.columns), f"Missing columns: {required - set(df.columns)}"
    # Must have at least ln_population estimates
    pop = df[df["outcome"] == "ln_population"]
    assert len(pop) > 0, "No ln_population rows in lp_irfs"
    # CI ordering: lo_95 <= lo_90 <= hi_90 <= hi_95
    assert (pop["ci_lo_95"] <= pop["ci_lo_90"]).all()
    assert (pop["ci_lo_90"] <= pop["ci_hi_90"]).all()
    assert (pop["ci_hi_90"] <= pop["ci_hi_95"]).all()


def test_lp_unit_residuals_schema():
    """lp_unit_residuals.parquet must have teryt_powiat and residual_h20 columns."""
    path = PROCESSED / "lp_unit_residuals.parquet"
    assert path.exists()
    df = pd.read_parquet(path)
    assert "teryt_powiat" in df.columns
    assert "residual_h20" in df.columns
    # Should have one row per treated city (at least 30)
    assert len(df) >= 28, f"Expected >=28 rows, got {len(df)}"


def test_lp_horizon_range():
    """IRFs must cover horizons -3 through at least 15 (h=-4 skipped: 1994 not in panel)."""
    df = pd.read_parquet(PROCESSED / "lp_irfs.parquet")
    pop = df[df["outcome"] == "ln_population"]
    horizons = set(pop["horizon"].astype(int))
    for h in [-3, -2, 0, 5, 10, 15]:
        assert h in horizons, f"Missing horizon h={h}"
