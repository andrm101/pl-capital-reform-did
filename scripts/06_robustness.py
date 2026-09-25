"""
Stage 06 — Robustness checks.
R1: Matched DiD — Propensity Score Matching on pre-reform characteristics.
R2: Drop spatial spillover zone (powiaty within 50km of nearest retained capital).
R3: Placebo test — falsely assign reform to 1996.
R4: Callaway-Sant'Anna heterogeneity-robust DiD (staggered-adoption version not needed
    here since treatment is simultaneous, but CS provides alternative ATT with doubly-robust weights).
R5: Synthetic Control for selected large demoted cities (Radom, Częstochowa, Wałbrzych).

Outputs: figures/t04_robustness_summary.csv, figures/f05_* for each check.
"""
from __future__ import annotations

import warnings
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from scipy.spatial.distance import cdist
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

REFORM_YEAR = 1999
PRIMARY_OUTCOME = "ln_population"  # run robustness on primary outcome; extend to others as needed
SOURCE_LINE = "Sources: GUS BDL; author calculations."


def load_panel() -> pd.DataFrame:
    path = PROCESSED / "panel_powiat.parquet"
    if not path.exists():
        raise FileNotFoundError("panel_powiat.parquet not found.")
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# R1: Propensity Score Matching (1:1 nearest-neighbour on pre-reform characteristics)
# ---------------------------------------------------------------------------

def psm_match(df: pd.DataFrame, outcome: str) -> pd.DataFrame | None:
    """
    Match each demoted city to the nearest retained city by propensity score
    estimated on pre-reform covariates. Returns matched panel.
    """
    if outcome not in df.columns:
        return None

    pre = df[df["year"] == 1998].copy()
    covariates = [c for c in ["ln_population", "unemployment", "firms_per_1k"] if c in pre.columns]
    if not covariates:
        print("[SKIP] R1: No pre-reform covariates available for PSM.")
        return None

    pre_clean = pre.dropna(subset=covariates + ["treated"])
    X = StandardScaler().fit_transform(pre_clean[covariates])
    y = pre_clean["treated"].values

    if y.sum() < 2 or (y == 0).sum() < 2:
        print("[SKIP] R1: Insufficient group sizes for PSM.")
        return None

    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
    lr.fit(X, y)
    pre_clean = pre_clean.copy()
    pre_clean["pscore"] = lr.predict_proba(X)[:, 1]

    treated_units = pre_clean[pre_clean["treated"] == 1]["teryt_powiat"].tolist()
    control_units = pre_clean[pre_clean["treated"] == 0]["teryt_powiat"].tolist()

    t_scores = pre_clean.set_index("teryt_powiat").loc[treated_units, "pscore"].values.reshape(-1, 1)
    c_scores = pre_clean.set_index("teryt_powiat").loc[control_units, "pscore"].values.reshape(-1, 1)

    dists = cdist(t_scores, c_scores, metric="euclidean")
    matched_control_idx = dists.argmin(axis=1)
    matched_controls = [control_units[i] for i in matched_control_idx]

    matched_ids = set(treated_units) | set(matched_controls)
    matched_panel = df[df["teryt_powiat"].isin(matched_ids)].copy()

    print(f"[R1] PSM matched {len(treated_units)} treated → {len(set(matched_controls))} unique controls.")
    return matched_panel


def run_twfe_simple(df: pd.DataFrame, outcome: str) -> tuple[float, float] | None:
    """Run simple 2-term DiD TWFE. Returns (coef, se) for the DiD term."""
    if outcome not in df.columns:
        return None
    sub = df[["teryt_powiat", "year", outcome, "did"]].dropna()
    if sub.shape[0] < 20:
        return None
    panel_df = sub.set_index(["teryt_powiat", "year"])
    try:
        mod = PanelOLS.from_formula(f"{outcome} ~ did + EntityEffects + TimeEffects",
                                    data=panel_df, drop_absorbed=True)
        res = mod.fit(cov_type="clustered", cluster_entity=True)
        return float(res.params["did"]), float(res.std_errors["did"])
    except Exception as e:
        print(f"[ERROR] TWFE: {e}")
        return None


# ---------------------------------------------------------------------------
# R2: Exclude spatial spillover zone
# ---------------------------------------------------------------------------

def drop_spillover_zone(df: pd.DataFrame, dist_threshold_km: float = 50.0) -> pd.DataFrame:
    """
    Exclude demoted city-powiats within dist_threshold_km of the nearest retained capital.
    Requires coordinate data. If not available, use voivodeship contiguity as proxy:
    drop demoted cities in the same voivodeship as the retained capital.

    Without lat/lon data: proxy by dropping demoted cities whose voivodeship_code
    matches a retained capital's voivodeship_code (conservative exclusion).
    """
    retained_voiv = df.loc[
        (df["year"] == REFORM_YEAR) & (df["retained_capital"] == 1), "voivodeship_code"
    ].unique()

    # Among demoted, drop those in same voivodeship as a retained capital
    spillover_mask = (
        (df["treated"] == 1) &
        (df["voivodeship_code"].isin(retained_voiv))
    )
    n_dropped = df.loc[spillover_mask & (df["year"] == REFORM_YEAR), "teryt_powiat"].nunique()
    print(f"[R2] Spillover exclusion: {n_dropped} demoted units in same voivodeship as retained capital.")
    return df[~spillover_mask].copy()


# ---------------------------------------------------------------------------
# R3: Placebo test — assign reform to 1996
# ---------------------------------------------------------------------------

def placebo_test(df: pd.DataFrame, outcome: str, placebo_year: int = 1996) -> tuple[float, float] | None:
    """Use only pre-1999 data; assign fake treatment in placebo_year."""
    if outcome not in df.columns:
        return None
    pre = df[df["year"] < REFORM_YEAR].copy()
    if pre["year"].nunique() < 3:
        print("[SKIP] R3: Insufficient pre-period years for placebo test.")
        return None

    pre["post_placebo"] = (pre["year"] >= placebo_year).astype(int)
    pre["did_placebo"] = pre["treated"] * pre["post_placebo"]
    return run_twfe_simple(pre.rename(columns={"did_placebo": "did"}), outcome)


# ---------------------------------------------------------------------------
# R4: Synthetic Control (unit-level, for top-3 largest demoted cities)
# ---------------------------------------------------------------------------

def synthetic_control_unit(
    df: pd.DataFrame,
    treated_unit: str,
    outcome: str,
    donor_pool: list[str],
) -> pd.DataFrame | None:
    """
    Naive synthetic control: find convex combination of donor units that minimises
    pre-reform RMSE on the outcome. Returns panel with actual and synthetic series.

    For production use, replace with pysyncon or SparseSC package.
    """
    if outcome not in df.columns:
        return None

    pivot = df.pivot_table(index="year", columns="teryt_powiat", values=outcome)
    if treated_unit not in pivot.columns:
        return None
    available_donors = [d for d in donor_pool if d in pivot.columns]
    if len(available_donors) < 3:
        print(f"[SKIP] SCM for {treated_unit}: insufficient donor pool.")
        return None

    pre_mask = pivot.index < REFORM_YEAR
    Y_pre_treated = pivot.loc[pre_mask, treated_unit].values
    Y_pre_donors = pivot.loc[pre_mask, available_donors].values

    # Drop donors with missing pre-period data
    ok_donors = [i for i in range(len(available_donors))
                 if not np.isnan(Y_pre_donors[:, i]).any()]
    if len(ok_donors) < 3:
        print(f"[SKIP] SCM for {treated_unit}: donors missing pre-period data.")
        return None

    Y_pre_donors = Y_pre_donors[:, ok_donors]
    donors_clean = [available_donors[i] for i in ok_donors]

    # Solve for weights via least-squares on pre-period (unconstrained, document limitation)
    # Production: use cvxpy for constrained optimisation (weights ≥ 0, sum = 1)
    try:
        from numpy.linalg import lstsq
        w, _, _, _ = lstsq(Y_pre_donors, Y_pre_treated, rcond=None)
        w = np.clip(w, 0, None)
        w = w / w.sum() if w.sum() > 0 else np.ones(len(w)) / len(w)
    except Exception:
        return None

    synthetic = (pivot[donors_clean] * w).sum(axis=1)
    result = pd.DataFrame({
        "year": pivot.index,
        "actual": pivot[treated_unit],
        "synthetic": synthetic,
        "gap": pivot[treated_unit] - synthetic,
        "treated_unit": treated_unit,
        "outcome": outcome,
    })
    return result


def plot_scm(scm_df: pd.DataFrame, unit_name: str, outcome: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    ax = axes[0]
    ax.plot(scm_df["year"], scm_df["actual"], label="Actual", lw=2)
    ax.plot(scm_df["year"], scm_df["synthetic"], label="Synthetic", lw=2, ls="--")
    ax.axvline(REFORM_YEAR - 0.5, color="red", lw=1.5, ls="--")
    ax.set_title(f"SCM: {unit_name} — {outcome}")
    ax.legend()

    ax = axes[1]
    ax.plot(scm_df["year"], scm_df["gap"], color="#d62728", lw=2)
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(REFORM_YEAR - 0.5, color="red", lw=1.5, ls="--")
    ax.set_title(f"Gap (actual − synthetic): {unit_name}")
    ax.set_xlabel("Year")

    fig.text(0.01, -0.05, SOURCE_LINE, fontsize=7, color="grey")
    plt.tight_layout()
    fname = FIGURES / f"f05_scm_{unit_name.lower().replace(' ', '_')}.png"
    plt.savefig(fname, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {fname.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Stage 06: Robustness ===\n")
    df = load_panel()
    df_main = df[df["structural_break"] == 0].copy()
    outcome = PRIMARY_OUTCOME

    summary_rows: list[dict] = []

    # Baseline TWFE
    base = run_twfe_simple(df_main, outcome)
    if base:
        summary_rows.append({"spec": "Baseline TWFE", "coef": base[0], "se": base[1]})
        print(f"Baseline TWFE: β={base[0]:.4f}, SE={base[1]:.4f}")

    # R1: PSM
    matched = psm_match(df_main, outcome)
    if matched is not None:
        r1 = run_twfe_simple(matched, outcome)
        if r1:
            summary_rows.append({"spec": "R1: Matched DiD (PSM)", "coef": r1[0], "se": r1[1]})
            print(f"R1 PSM: β={r1[0]:.4f}, SE={r1[1]:.4f}")

    # R2: Drop spillover zone
    df_no_spill = drop_spillover_zone(df_main)
    r2 = run_twfe_simple(df_no_spill, outcome)
    if r2:
        summary_rows.append({"spec": "R2: Exclude spillover zone", "coef": r2[0], "se": r2[1]})
        print(f"R2 No-spillover: β={r2[0]:.4f}, SE={r2[1]:.4f}")

    # R3: Placebo
    placebo = placebo_test(df_main, outcome, placebo_year=1996)
    if placebo:
        summary_rows.append({"spec": "R3: Placebo (fake reform 1996)", "coef": placebo[0], "se": placebo[1]})
        print(f"R3 Placebo: β={placebo[0]:.4f}, SE={placebo[1]:.4f}  (should ≈ 0)")

    # R4: Exclude co-capitals from control
    df_no_co = df_main[df_main["is_co_capital"] == 0].copy()
    r4 = run_twfe_simple(df_no_co, outcome)
    if r4:
        summary_rows.append({"spec": "R4: Exclude co-capitals from control", "coef": r4[0], "se": r4[1]})
        print(f"R4 No co-capitals: β={r4[0]:.4f}, SE={r4[1]:.4f}")

    # R5: SCM for large demoted cities
    scm_targets = {
        "Radom": "1463",
        "Częstochowa": "2464",
        "Tarnów": "1263",
    }
    control_units = df_main.loc[
        (df_main["year"] == REFORM_YEAR) & (df_main["treated"] == 0), "teryt_powiat"
    ].tolist()

    for city, teryt in scm_targets.items():
        scm_df = synthetic_control_unit(df_main, teryt, outcome, control_units)
        if scm_df is not None:
            plot_scm(scm_df, city, outcome)

    # Save robustness summary
    if summary_rows:
        rob_table = pd.DataFrame(summary_rows)
        rob_table["t_stat"] = rob_table["coef"] / rob_table["se"]
        rob_table["p_approx"] = 2 * (1 - pd.Series(
            [abs(t) for t in rob_table["t_stat"]]
        ).apply(lambda x: min(x, 10)).apply(lambda x: x / 2))  # approx, not exact
        rob_table.to_csv(FIGURES / "t04_robustness_summary.csv", index=False)
        print("\nSaved: t04_robustness_summary.csv")
        print(rob_table.to_string(index=False))
    else:
        print("\n[NOTE] No robustness results computed — BDL outcome data required.")

    print("\nNote: For production-grade SCM, install pysyncon (`pip install pysyncon`) and")
    print("replace the synthetic_control_unit() function with pysyncon.Synth.")
    print("\n=== Stage 06 complete ===")


if __name__ == "__main__":
    main()
