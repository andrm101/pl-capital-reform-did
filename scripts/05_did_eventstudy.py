"""
Stage 05 — DiD and event-study estimation.
Specification: TWFE with powiat FE + year FE.
Event-study: Y_it = α_i + λ_t + Σ_{k≠−1} β_k (D_i × 1[t−1999=k]) + ε_it
SE: clustered at powiat level (within-unit correlation).

Outputs:
  figures/f04_eventstudy_{outcome}.png  — event-study coefficient plots
  figures/t02_did_main.csv              — main 2×2 DiD table
  figures/t03_twfe.csv                  — preferred TWFE estimates
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

REFORM_YEAR = 1999
SOURCE_LINE = "Sources: GUS BDL; author calculations. SE clustered at powiat level."

PRIMARY_OUTCOMES = [
    ("ln_population",  "Log population"),
    ("firms_per_1k",   "REGON firms per 1,000 pop."),
    ("unemployment",   "Registered unemployment rate (%)"),
    ("ln_wages_avg",   "Log avg. gross wage"),
    ("nat_change_rate","Natural pop. change per 1,000 (births − deaths)"),
    ("birth_rate",     "Crude birth rate per 1,000"),
    ("death_rate",     "Crude death rate per 1,000"),
]

# Event-time window to plot (drop endpoints with few observations)
ET_WINDOW = (-4, 20)


def load_panel() -> pd.DataFrame:
    path = PROCESSED / "panel_powiat.parquet"
    if not path.exists():
        raise FileNotFoundError("panel_powiat.parquet not found.")
    df = pd.read_parquet(path)
    df["teryt_powiat"] = df["teryt_powiat"].astype(str).str.zfill(4)
    return df


def add_event_dummies(df: pd.DataFrame, et_min: int, et_max: int) -> tuple[pd.DataFrame, list[str]]:
    """
    Add event-time dummy interactions D_i × 1[event_time = k] for k in [et_min, et_max],
    omitting k = -1 (normalisation year).
    Returns modified df and list of dummy column names.
    """
    dummy_cols: list[str] = []
    for k in range(et_min, et_max + 1):
        if k == -1:
            continue
        col = f"et_{k}" if k >= 0 else f"et_neg{abs(k)}"
        df[col] = df["treated"] * (df["event_time"] == k).astype(int)
        dummy_cols.append(col)
    return df, dummy_cols


def run_twfe(
    df: pd.DataFrame,
    outcome: str,
    dummy_cols: list[str],
    entity_col: str = "teryt_powiat",
    time_col: str = "year",
) -> pd.DataFrame | None:
    """Run TWFE event-study with linearmodels.PanelOLS. Returns coefficient table."""
    if outcome not in df.columns or df[outcome].isna().all():
        print(f"[SKIP] {outcome}: all NaN.")
        return None

    # Restrict to years where the outcome is observed, then rebuild dummies
    obs_years = set(df.loc[df[outcome].notna(), time_col].unique())
    active_dummies = [
        col for col in dummy_cols
        if df.loc[df[col] > 0, time_col].isin(obs_years).any()
    ]
    # Drop dummies whose year has zero variance in the restricted sample
    sub = df[[entity_col, time_col, outcome] + active_dummies].dropna(subset=[outcome])
    # Further drop dummies that are constant (= 0) in sub
    active_dummies = [c for c in active_dummies if sub[c].sum() > 0]

    if sub.shape[0] < 100:
        print(f"[SKIP] {outcome}: too few observations ({sub.shape[0]}).")
        return None
    if not active_dummies:
        print(f"[SKIP] {outcome}: no event-time dummies with variation.")
        return None

    panel_df = sub[[entity_col, time_col, outcome] + active_dummies].set_index(
        [entity_col, time_col]
    )
    formula = f"{outcome} ~ " + " + ".join(active_dummies) + " + EntityEffects + TimeEffects"

    try:
        mod = PanelOLS.from_formula(formula, data=panel_df, drop_absorbed=True)
        res = mod.fit(cov_type="clustered", cluster_entity=True)
    except Exception as e:
        print(f"[ERROR] {outcome}: {e}")
        return None

    coef = res.params.reset_index()
    coef.columns = ["variable", "coef"]
    se = res.std_errors.reset_index()
    se.columns = ["variable", "se"]
    result = coef.merge(se, on="variable")
    result["ci_lo"] = result["coef"] - 1.96 * result["se"]
    result["ci_hi"] = result["coef"] + 1.96 * result["se"]

    # Extract event time from variable name
    def parse_et(v: str) -> int | float:
        if v.startswith("et_neg"):
            return -int(v.replace("et_neg", ""))
        if v.startswith("et_"):
            return int(v.replace("et_", ""))
        return np.nan

    result["event_time"] = result["variable"].map(parse_et)
    result = result.dropna(subset=["event_time"]).sort_values("event_time")

    # Append k=-1 row (reference, coef=0)
    ref_row = pd.DataFrame({"variable": ["et_neg1_ref"], "coef": [0.0], "se": [0.0],
                             "ci_lo": [0.0], "ci_hi": [0.0], "event_time": [-1.0]})
    result = pd.concat([result, ref_row], ignore_index=True).sort_values("event_time")

    print(f"\n[{outcome}] N={res.nobs}, entities={res.entity_info.total}, "
          f"R²(within)={res.rsquared_within:.3f}")

    return result


def plot_event_study(
    coef_df: pd.DataFrame,
    outcome: str,
    label: str,
) -> None:
    sub = coef_df[
        (coef_df["event_time"] >= ET_WINDOW[0]) &
        (coef_df["event_time"] <= ET_WINDOW[1])
    ].sort_values("event_time")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axhline(0, color="black", lw=0.8, ls="-")
    ax.axvline(-0.5, color="red", lw=1.5, ls="--", label="Reform (1999)")

    ax.errorbar(
        sub["event_time"], sub["coef"],
        yerr=1.96 * sub["se"],
        fmt="o", color="#1f77b4", ms=5, lw=1.5, capsize=3,
        label="β_k (95% CI)",
    )

    # Shade pre-period
    pre = sub[sub["event_time"] < 0]
    if len(pre) > 1:
        ax.fill_between(pre["event_time"], pre["ci_lo"], pre["ci_hi"],
                        alpha=0.12, color="#1f77b4", label="95% CI (pre-period)")
    post = sub[sub["event_time"] >= 0]
    if len(post) > 1:
        ax.fill_between(post["event_time"], post["ci_lo"], post["ci_hi"],
                        alpha=0.12, color="#ff7f0e")

    ax.set_xlabel("Years relative to 1999 reform")
    ax.set_ylabel(f"Coefficient (Δ {label})")
    ax.set_title(f"Event-study: effect of capital-status loss on {label}",
                 fontweight="bold", fontsize=11)
    ax.legend(fontsize=9)
    ax.text(0.01, -0.12, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")

    plt.tight_layout()
    fname = FIGURES / f"f04_eventstudy_{outcome}.png"
    plt.savefig(fname, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {fname.name}")


def run_naive_did(df: pd.DataFrame, outcome: str) -> dict:
    """2×2 DiD: compare pre-post means across treated and control."""
    if outcome not in df.columns:
        return {}
    means = df.groupby(["treated", "post"])[outcome].mean()
    try:
        did_estimate = (means[1, 1] - means[1, 0]) - (means[0, 1] - means[0, 0])
        return {
            "outcome": outcome,
            "demoted_pre": means[1, 0],
            "demoted_post": means[1, 1],
            "retained_pre": means[0, 0],
            "retained_post": means[0, 1],
            "DiD": did_estimate,
        }
    except KeyError:
        return {}


def main() -> None:
    print("=== Stage 05: DiD + Event Study ===\n")

    df = load_panel()

    # Exclude Wałbrzych structural break unit from main spec
    df_main = df[df["structural_break"] == 0].copy()

    # Add event-time dummies
    et_min = max(df_main["event_time"].min(), ET_WINDOW[0])
    et_max = min(df_main["event_time"].max(), ET_WINDOW[1])
    df_main, dummy_cols = add_event_dummies(df_main, et_min, et_max)

    # --- Naive 2×2 DiD ---
    naive_rows = []
    for outcome, label in PRIMARY_OUTCOMES:
        row = run_naive_did(df_main, outcome)
        if row:
            naive_rows.append(row)
    if naive_rows:
        naive_table = pd.DataFrame(naive_rows)
        naive_table.to_csv(FIGURES / "t02_did_naive.csv", index=False)
        print("Saved: t02_did_naive.csv")
        print("\nNaive 2×2 DiD estimates:")
        print(naive_table.to_string(index=False))

    # --- TWFE event study ---
    all_coefs: dict[str, pd.DataFrame] = {}
    for outcome, label in PRIMARY_OUTCOMES:
        if outcome not in df_main.columns:
            print(f"[SKIP] {outcome} not in panel. Download BDL data.")
            continue
        coef_df = run_twfe(df_main, outcome, dummy_cols)
        if coef_df is not None:
            all_coefs[outcome] = coef_df
            plot_event_study(coef_df, outcome, label)

    # Save coefficient table (all outcomes combined)
    if all_coefs:
        combined = pd.concat(
            [df.assign(outcome=k) for k, df in all_coefs.items()],
            ignore_index=True
        )
        combined.to_csv(FIGURES / "t03_twfe_eventstudy.csv", index=False)
        print("\nSaved: t03_twfe_eventstudy.csv")

    print("\nNote: Run Stage 06 for matched DiD and SCM robustness checks.")
    print("\n=== Stage 05 complete ===")


if __name__ == "__main__":
    main()
