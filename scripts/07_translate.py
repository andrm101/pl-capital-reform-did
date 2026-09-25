"""
Stage 07 — Policy translation layer.
Converts TWFE coefficients to % / absolute magnitudes.
Produces policy-readable summary table and heterogeneity scatter.
Outputs: figures/t05_policy_translation.csv, figures/f06_heterogeneity.png
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

SOURCE_LINE = "Sources: GUS BDL; Eurostat REGIO; author calculations."

LOG_OUTCOMES = {"ln_population", "ln_wages_avg", "ln_births", "ln_deaths"}
# For level outcomes (rates), policy magnitude = β with unit interpretation


def load_coef_table() -> pd.DataFrame | None:
    path = FIGURES / "t03_twfe_eventstudy.csv"
    if not path.exists():
        print("[SKIP] t03_twfe_eventstudy.csv not found — run Stage 05 first.")
        return None
    return pd.read_csv(path)


def load_panel() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "panel_powiat.parquet")


def translate_coefficient(
    beta: float,
    se: float,
    outcome: str,
    baseline_mean: float,
) -> dict:
    """Translate regression coefficient to policy magnitude."""
    ci_lo, ci_hi = beta - 1.96 * se, beta + 1.96 * se

    if outcome in LOG_OUTCOMES:
        # β on log(Y): % effect ≈ 100*(exp(β)−1)
        pct = 100 * (np.exp(beta) - 1)
        pct_lo = 100 * (np.exp(ci_lo) - 1)
        pct_hi = 100 * (np.exp(ci_hi) - 1)
        magnitude = f"{pct:+.1f}% (95% CI: {pct_lo:+.1f}% to {pct_hi:+.1f}%)"
    else:
        # Level outcome: absolute change, also express as % of baseline mean
        pct = 100 * beta / baseline_mean if baseline_mean != 0 else np.nan
        pct_lo = 100 * ci_lo / baseline_mean if baseline_mean != 0 else np.nan
        pct_hi = 100 * ci_hi / baseline_mean if baseline_mean != 0 else np.nan
        magnitude = (f"Δ{beta:+.2f} pp (95% CI: {ci_lo:+.2f} to {ci_hi:+.2f}); "
                     f"≈{pct:+.1f}% of pre-reform mean")

    return {
        "outcome": outcome,
        "beta": beta,
        "se": se,
        "ci_lo_95": ci_lo,
        "ci_hi_95": ci_hi,
        "baseline_mean": baseline_mean,
        "policy_magnitude": magnitude,
    }


def build_translation_table(coef_df: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Select long-run coefficients (event_time = 10, 15, 20) and translate."""
    horizons = [5, 10, 15, 20]
    rows: list[dict] = []

    for outcome in coef_df["outcome"].unique():
        sub = coef_df[coef_df["outcome"] == outcome]
        pre_mean = panel.loc[
            (panel["year"] < 1999) & (panel["treated"] == 1), outcome
        ].mean() if outcome in panel.columns else np.nan

        for h in horizons:
            row = sub[sub["event_time"] == h]
            if row.empty:
                continue
            beta = row["coef"].values[0]
            se = row["se"].values[0]
            translated = translate_coefficient(beta, se, outcome, pre_mean)
            translated["horizon_years"] = h
            rows.append(translated)

    return pd.DataFrame(rows)


def plot_heterogeneity(panel: pd.DataFrame, outcome: str = "ln_population") -> None:
    """
    Scatter: pre-reform city size (log population) vs. post-reform cumulative change.
    Stratify by treated/control to visualise size moderation (H2).
    """
    if outcome not in panel.columns:
        return

    pre = panel[panel["year"] == 1998][["teryt_powiat", "treated", outcome]].copy()
    post = panel[panel["year"] == 2019][["teryt_powiat", outcome]].copy()
    if pre.empty or post.empty:
        return

    merged = pre.merge(post, on="teryt_powiat", suffixes=("_pre", "_post"))
    merged["change"] = merged[f"{outcome}_post"] - merged[f"{outcome}_pre"]

    fig, ax = plt.subplots(figsize=(9, 6))
    for treated, label, color in [(1, "Demoted (treated)", "#d62728"), (0, "Retained (control)", "#1f77b4")]:
        sub = merged[merged["treated"] == treated]
        ax.scatter(sub[f"{outcome}_pre"], sub["change"],
                   label=label, color=color, alpha=0.75, s=60, edgecolors="white", lw=0.4)

    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_xlabel("Log population (1998, pre-reform)", fontsize=10)
    ax.set_ylabel(f"Δ log population (1998–2019)", fontsize=10)
    ax.set_title("Heterogeneity by pre-reform city size (H2 test)", fontweight="bold")
    ax.legend()
    ax.text(0.01, -0.1, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(FIGURES / "f06_heterogeneity_size.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Saved: f06_heterogeneity_size.png")


def print_policy_brief(table: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("POLICY TRANSLATION — LONG-RUN EFFECTS OF CAPITAL-STATUS LOSS")
    print("=" * 70)
    for _, row in table.iterrows():
        print(f"\n[t+{int(row['horizon_years'])}] {row['outcome']}")
        print(f"  {row['policy_magnitude']}")
    print("\nInterpretation note: Estimates are ATT (average treatment effect on the")
    print("treated) from TWFE DiD. Causal interpretation requires parallel trends.")
    print("Results are robust to [see t04_robustness_summary.csv for specifications].")
    print("Do NOT interpret as causal without passing pre-trend test (see f01_group_trends.png).")
    print("=" * 70)


def main() -> None:
    print("=== Stage 07: Policy Translation ===\n")

    coef_df = load_coef_table()
    panel = load_panel()

    if coef_df is not None:
        table = build_translation_table(coef_df, panel)
        if not table.empty:
            table.to_csv(FIGURES / "t05_policy_translation.csv", index=False)
            print("Saved: t05_policy_translation.csv")
            print_policy_brief(table)
        else:
            print("[NOTE] No long-run coefficients found. Check event-study window.")
    else:
        print("[NOTE] Coefficient table not found. Run Stage 05 first.")

    plot_heterogeneity(panel)

    print("\n=== Stage 07 complete ===")
    print(f"\nAll outputs in: {FIGURES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
