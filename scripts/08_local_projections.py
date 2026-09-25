"""
Stage 08 — Local Projections (Jordà 2005).

For a single-date treatment (1999 reform), the LP is cross-sectional per horizon:
  ΔY_i(h) = β_h D_i + ε_i
  where ΔY_i(h) = Y_{i, 1998+h} - Y_{i, 1998}

D_i (treated) is time-invariant so panel entity FEs would absorb it. The correct
specification is cross-sectional OLS for each horizon, using 1998 as the base year.
HC3 robust SEs. This is equivalent to a 2×2 DiD at each horizon h.

Outputs:
  data/processed/lp_irfs.parquet        — IRF coefficients for all outcomes × horizons
  data/processed/lp_unit_residuals.parquet — unit-level residuals at h=20 (HTE hook)
  figures/f07_lp_irf_{outcome}.png      — IRF plots
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

SOURCE_LINE = "Sources: GUS BDL; author calculations. LP cross-sectional DiD per horizon (Jordà 2005)."

OUTCOMES = [
    ("ln_population",   "Log population"),
    ("firms_per_1k",    "REGON firms per 1,000 pop."),
    ("unemployment",    "Registered unemployment rate (%)"),
    ("ln_wages_avg",    "Log avg. gross wage"),
    ("nat_change_rate", "Natural pop. change per 1,000"),
    ("birth_rate",      "Crude birth rate per 1,000"),
    ("death_rate",      "Crude death rate per 1,000"),
]

ET_MIN, ET_MAX = -4, 20
BASE_YEAR = 1998  # last pre-reform year (t-1 relative to 1999)


def run_lp_single(df: pd.DataFrame, outcome: str, h: int,
                  entity_col: str = "teryt_powiat",
                  time_col: str = "year") -> dict | None:
    """
    Cross-sectional LP for horizon h.
    LHS = Y_{i, BASE_YEAR+h} - Y_{i, BASE_YEAR}
    Regressed on D_i (treated) via OLS with HC3 robust SEs.
    """
    target_year = BASE_YEAR + h
    years = df[time_col].unique()
    if target_year not in years or BASE_YEAR not in years:
        return None

    base   = df[df[time_col] == BASE_YEAR][[entity_col, outcome, "treated"]].copy()
    target = df[df[time_col] == target_year][[entity_col, outcome]].copy()
    base   = base.rename(columns={outcome: "y_base"})
    target = target.rename(columns={outcome: "y_target"})

    merged = base.merge(target, on=entity_col, how="inner")
    merged["lhs"] = merged["y_target"] - merged["y_base"]
    merged = merged.dropna(subset=["lhs", "treated"])

    if len(merged) < 30 or merged["treated"].sum() == 0 or merged["treated"].nunique() < 2:
        return None

    try:
        res  = smf.ols("lhs ~ treated", data=merged).fit(cov_type="HC3")
        beta = float(res.params["treated"])
        se   = float(res.bse["treated"])
        return {
            "horizon": h, "coef": beta, "se": se,
            "ci_lo_90": beta - 1.645 * se, "ci_hi_90": beta + 1.645 * se,
            "ci_lo_95": beta - 1.960 * se, "ci_hi_95": beta + 1.960 * se,
            "nobs": int(res.nobs),
        }
    except Exception as e:
        print(f"  [SKIP] h={h}: {e}")
        return None


def run_lp(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Run LP for all horizons for a single outcome."""
    records = []
    for h in range(ET_MIN, ET_MAX + 1):
        row = run_lp_single(df, outcome, h)
        if row is not None:
            row["outcome"] = outcome
            records.append(row)
    return pd.DataFrame(records)


def plot_irf(coef_df: pd.DataFrame, outcome: str, label: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    sub = coef_df.sort_values("horizon")

    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(-0.5, color="#e8ff47", lw=1.5, ls="--", label="Reform (1999)")

    ax.fill_between(sub["horizon"], sub["ci_lo_95"], sub["ci_hi_95"],
                    alpha=0.15, color="#4d7cff", label="95% CI")
    ax.fill_between(sub["horizon"], sub["ci_lo_90"], sub["ci_hi_90"],
                    alpha=0.30, color="#4d7cff", label="90% CI")
    ax.plot(sub["horizon"], sub["coef"], "o-", color="#4d7cff",
            ms=4, lw=1.8, label="LP coefficient")

    ax.set_xlabel("Years relative to 1999 reform")
    ax.set_ylabel(f"LP coefficient (Δ {label})")
    ax.set_title(f"Local Projection IRF: {label}", fontweight="bold", fontsize=11)
    ax.legend(fontsize=9)
    ax.text(0.01, -0.12, SOURCE_LINE, transform=ax.transAxes,
            fontsize=7, color="grey")

    plt.tight_layout()
    path = FIGURES / f"f07_lp_irf_{outcome}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path.name}")


def main() -> None:
    print("=== Stage 08: Local Projections ===\n")

    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)

    all_irfs: list[pd.DataFrame] = []
    unit_residuals: list[dict] = []

    for outcome, label in OUTCOMES:
        if outcome not in panel.columns:
            print(f"[SKIP] {outcome} not in panel.")
            continue
        if panel[outcome].isna().all():
            print(f"[SKIP] {outcome}: all NaN.")
            continue

        print(f"\n[{outcome}]")
        irf = run_lp(panel, outcome)
        if irf.empty:
            print("  No estimates produced.")
            continue

        all_irfs.append(irf)
        plot_irf(irf, outcome, label)

        # HTE hook: store per-city residual at h=20 for ln_population
        # Residual = city's actual ΔY(20) minus aggregate β_20
        if outcome == "ln_population":
            row_h20 = run_lp_single(panel, outcome, 20)
            if row_h20:
                base_yr   = panel[panel["year"] == BASE_YEAR][["teryt_powiat", outcome, "treated"]].copy()
                target_yr = panel[panel["year"] == BASE_YEAR + 20][["teryt_powiat", outcome]].copy()
                base_yr   = base_yr.rename(columns={outcome: "y_base"})
                target_yr = target_yr.rename(columns={outcome: "y_target"})
                merged_h20 = base_yr.merge(target_yr, on="teryt_powiat", how="inner")
                merged_h20["lhs"] = merged_h20["y_target"] - merged_h20["y_base"]
                treated_at_base = merged_h20[
                    (merged_h20["treated"] == 1) & merged_h20["lhs"].notna()
                ]
                for _, r in treated_at_base.iterrows():
                    unit_residuals.append({
                        "teryt_powiat": r["teryt_powiat"],
                        "residual_h20": r["lhs"] - row_h20["coef"],
                    })

        h_vals = sorted(irf["horizon"].astype(int).tolist())
        print(f"  Horizons: {h_vals[0]}…{h_vals[-1]}  ({len(irf)} estimates)")

    if all_irfs:
        combined = pd.concat(all_irfs, ignore_index=True)
        combined.to_parquet(PROCESSED / "lp_irfs.parquet", index=False)
        print(f"\nSaved → lp_irfs.parquet  ({len(combined)} rows)")

    if unit_residuals:
        res_df = pd.DataFrame(unit_residuals)
        res_df.to_parquet(PROCESSED / "lp_unit_residuals.parquet", index=False)
        print(f"Saved → lp_unit_residuals.parquet  ({len(res_df)} rows)")

    print("\n=== Stage 08 complete ===")


if __name__ == "__main__":
    main()
