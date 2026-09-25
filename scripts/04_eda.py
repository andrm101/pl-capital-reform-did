"""
Stage 04 — Exploratory data analysis.
Produces: coverage map, trend plots, balance table, pre-trend visual test,
ADF/KPSS stationarity, ACF, cross-correlation.
All figures saved to figures/ at 300 DPI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.gridspec import GridSpec
from scipy import stats
from statsmodels.graphics.tsaplots import plot_acf
from statsmodels.tsa.stattools import adfuller, kpss

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 300,
    "figure.figsize": (10, 6),
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

OUTCOMES = {
    "ln_population":  "Log population",
    "pop_growth":     "Population growth (YoY)",
    "firms_per_1k":   "REGON firms per 1,000 pop.",
    "unemployment":   "Registered unemployment rate (%)",
    "ln_wages_avg":   "Log avg. gross wage (PLN)",
    "migration_net":  "Net migration",
}

SOURCE_LINE = "Sources: GUS BDL; author calculations."


def load_panel() -> pd.DataFrame:
    path = PROCESSED / "panel_powiat.parquet"
    if not path.exists():
        raise FileNotFoundError("panel_powiat.parquet not found — run stages 01–03 first.")
    return pd.read_parquet(path)


def available_outcomes(df: pd.DataFrame) -> dict[str, str]:
    return {k: v for k, v in OUTCOMES.items() if k in df.columns}


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def plot_coverage(df: pd.DataFrame) -> None:
    avail = {k: v for k, v in OUTCOMES.items() if k in df.columns}
    if not avail:
        print("[SKIP] No outcome columns present yet.")
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    coverage = (
        df.groupby("year")[list(avail.keys())]
        .apply(lambda x: x.notna().mean())
        .reset_index()
        .melt(id_vars="year", var_name="variable", value_name="coverage")
    )
    for var, label in avail.items():
        sub = coverage[coverage["variable"] == var]
        ax.plot(sub["year"], sub["coverage"], label=label, marker="o", ms=3)

    ax.axvline(1999, color="red", lw=1.5, ls="--", label="Reform (1999)")
    ax.set_xlabel("Year")
    ax.set_ylabel("Share of powiaty non-missing")
    ax.set_title("Data coverage by outcome variable (powiat panel)", fontweight="bold")
    ax.legend(fontsize=8, loc="lower left")
    ax.text(0.01, -0.12, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(FIGURES / "f00_coverage.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Saved: f00_coverage.png")


# ---------------------------------------------------------------------------
# Group trend plots (pre-trend diagnostic)
# ---------------------------------------------------------------------------

def plot_group_trends(df: pd.DataFrame) -> None:
    avail = available_outcomes(df)
    if not avail:
        return

    group_means = df.groupby(["year", "treated"])[list(avail.keys())].mean().reset_index()
    group_means["group"] = group_means["treated"].map({1: "Demoted (treated)", 0: "Retained (control)"})

    n_cols = 2
    n_rows = int(np.ceil(len(avail) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 4 * n_rows), sharex=True)
    axes = axes.flatten()

    for i, (var, label) in enumerate(avail.items()):
        ax = axes[i]
        for grp, sub in group_means.groupby("group"):
            ax.plot(sub["year"], sub[var], label=grp, lw=1.8)
        ax.axvline(1999, color="red", lw=1.2, ls="--", alpha=0.7)
        ax.set_title(label, fontsize=9)
        ax.set_xlabel("Year")
        if i == 0:
            ax.legend(fontsize=8)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Group-mean trends: demoted vs. retained capitals", fontweight="bold", y=1.01)
    fig.text(0.01, -0.01, SOURCE_LINE, fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(FIGURES / "f01_group_trends.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Saved: f01_group_trends.png")


# ---------------------------------------------------------------------------
# Balance table
# ---------------------------------------------------------------------------

def balance_table(df: pd.DataFrame) -> pd.DataFrame:
    pre = df[df["year"] < 1999].copy()
    avail = available_outcomes(pre)
    if not avail:
        print("[SKIP] No outcome data for balance table.")
        return pd.DataFrame()

    rows = []
    for var, label in avail.items():
        grp = pre.groupby("treated")[var].agg(["mean", "std"])
        if 1 not in grp.index or 0 not in grp.index:
            continue
        d_mean, d_std = grp.loc[1, "mean"], grp.loc[1, "std"]
        r_mean, r_std = grp.loc[0, "mean"], grp.loc[0, "std"]

        # Two-sample t-test
        treated_vals = pre.loc[pre["treated"] == 1, var].dropna()
        control_vals = pre.loc[pre["treated"] == 0, var].dropna()
        t_stat, p_val = stats.ttest_ind(treated_vals, control_vals, equal_var=False)

        # Normalised difference (Imbens-Rubin)
        norm_diff = (d_mean - r_mean) / np.sqrt((d_std**2 + r_std**2) / 2) if (d_std + r_std) > 0 else np.nan

        rows.append({
            "Variable": label,
            "Demoted (mean)": f"{d_mean:.2f}",
            "Demoted (sd)": f"{d_std:.2f}",
            "Retained (mean)": f"{r_mean:.2f}",
            "Retained (sd)": f"{r_std:.2f}",
            "t-stat": f"{t_stat:.2f}",
            "p-value": f"{p_val:.3f}",
            "Norm. diff.": f"{norm_diff:.3f}",
        })

    table = pd.DataFrame(rows)
    table.to_csv(FIGURES / "t01_balance_table.csv", index=False)
    print("Saved: t01_balance_table.csv")
    print("\nBalance Table (pre-reform period):")
    print(table.to_string(index=False))
    return table


# ---------------------------------------------------------------------------
# Stationarity tests
# ---------------------------------------------------------------------------

def stationarity_tests(df: pd.DataFrame) -> None:
    avail = available_outcomes(df)
    if not avail:
        return

    print("\n--- Stationarity Tests (group means) ---")
    print(f"{'Variable':<30} {'ADF p':>8} {'ADF concl':>12} {'KPSS stat':>10} {'KPSS concl':>12}")
    print("-" * 74)

    for var in avail:
        series = df.groupby("year")[var].mean().dropna()
        if len(series) < 10:
            continue
        adf_p = adfuller(series, autolag="AIC")[1]
        try:
            kpss_stat, kpss_p, *_ = kpss(series, regression="c", nlags="auto")
            kpss_concl = "non-stationary" if kpss_p < 0.05 else "stationary"
        except Exception:
            kpss_stat, kpss_concl = np.nan, "error"

        adf_concl = "stationary" if adf_p < 0.05 else "non-stationary"
        print(f"{var:<30} {adf_p:>8.3f} {adf_concl:>12} {kpss_stat:>10.3f} {kpss_concl:>12}")

    print("\nNote: For DiD with unit+time FE, within-unit stationarity of the outcome in logs")
    print("is less critical than in pure time-series regression. Document for appendix.")


# ---------------------------------------------------------------------------
# ACF of main outcome
# ---------------------------------------------------------------------------

def plot_acf_main(df: pd.DataFrame, primary_outcome: str = "ln_population") -> None:
    if primary_outcome not in df.columns:
        return

    series = df.groupby("year")[primary_outcome].mean().dropna()
    fig, ax = plt.subplots(figsize=(8, 4))
    plot_acf(series, lags=min(15, len(series) // 2 - 1), ax=ax, title="")
    ax.set_title(f"ACF — group-mean {primary_outcome}", fontweight="bold")
    ax.set_xlabel("Lag (years)")
    ax.text(0.01, -0.15, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(FIGURES / "f02_acf.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Saved: f02_acf.png")


# ---------------------------------------------------------------------------
# Distribution comparison pre-reform
# ---------------------------------------------------------------------------

def plot_distribution(df: pd.DataFrame, primary_outcome: str = "ln_population") -> None:
    if primary_outcome not in df.columns:
        return

    pre = df[df["year"] == 1998]
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, grp in pre.groupby("treated"):
        name = "Demoted" if label == 1 else "Retained"
        vals = grp[primary_outcome].dropna()
        ax.hist(vals, bins=12, alpha=0.6, label=f"{name} (n={len(vals)})", density=True)

    ax.set_xlabel(OUTCOMES.get(primary_outcome, primary_outcome))
    ax.set_ylabel("Density")
    ax.set_title("Distribution in 1998 (pre-reform)", fontweight="bold")
    ax.legend()
    ax.text(0.01, -0.12, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")
    plt.tight_layout()
    plt.savefig(FIGURES / "f03_distribution_pre.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Saved: f03_distribution_pre.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Stage 04: EDA ===\n")

    df = load_panel()
    print(f"Panel: {df['teryt_powiat'].nunique()} units, "
          f"{df['year'].nunique()} years ({df['year'].min()}–{df['year'].max()})")
    print(f"Treated (demoted): {df.loc[df['year']==1999,'treated'].sum()}")
    print(f"Control (retained): {df.loc[df['year']==1999,'treated'].eq(0).sum()}\n")

    avail = available_outcomes(df)
    if not avail:
        print("No outcome variables found. Download BDL data and run stages 01–03.")
    else:
        print(f"Available outcomes: {list(avail.keys())}\n")

    plot_coverage(df)
    plot_group_trends(df)
    balance_table(df)
    stationarity_tests(df)
    plot_acf_main(df)
    plot_distribution(df)

    print("\n=== Stage 04 complete ===")
    print(f"Figures in {FIGURES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
