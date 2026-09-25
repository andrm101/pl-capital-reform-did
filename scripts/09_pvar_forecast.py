"""
Stage 09 — Mean-Group Panel VAR Forecast
Reads:  data/processed/panel_powiat.parquet
        data/processed/gsynth_gaps.parquet
Writes: data/processed/pvar_forecasts.parquet
        figures/f08_pvar_irf.png
        figures/f08_forecast_{city_en}.png  (8 showcase cities)

Method: Pesaran-Smith (1995) Mean Group VAR.
  - VAR(p, p∈{1,2} by BIC) per city on maximal balanced subpanel, 2000-2023
  - Per-city constant absorbs unit FE; year effects pooled out via MG
  - IRFs from MG coefficient matrices, Cholesky-identified
  - Forecasts: residual-bootstrap CIs (500 draws)
  - Counterfactual path: gsynth ln_population gap applied to 2023 starting state
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

OUTCOMES = ["ln_population", "unemployment", "firms_per_1k", "ln_wages_avg", "nat_change_rate"]
OUTCOME_LABELS = {
    "ln_population": "Log population",
    "unemployment": "Unemployment rate (%)",
    "firms_per_1k": "Firms per 1,000 pop.",
    "ln_wages_avg": "Log avg. wages",
    "nat_change_rate": "Natural change rate",
}
# Cholesky ordering: slowest → fastest adjusting
CHOL_ORDER = ["ln_population", "nat_change_rate", "unemployment", "firms_per_1k", "ln_wages_avg"]

YEAR_START = 2000
YEAR_END = 2023
MIN_OBS = 10
MAX_LAG = 2
N_BOOT = 500
FORECAST_YEARS = list(range(2024, 2036))
N_STEPS = len(FORECAST_YEARS)

SHOWCASE = ["Radom", "Czestochowa", "Lomza", "Kielce", "Slupsk", "Legnica", "Zamosc", "Plock"]
# Also try with Polish diacritics as stored in city_en
SHOWCASE_VARIANTS = {
    "Czestochowa": ["Częstochowa", "Czestochowa"],
    "Lomza":       ["Łomża", "Lomza"],
    "Zamosc":      ["Zamość", "Zamosc"],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_panel() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    df = df[df["year"].between(YEAR_START, YEAR_END)].copy()
    df["teryt_powiat"] = df["teryt_powiat"].astype(str).str.zfill(4)
    return df


def load_gsynth_gaps() -> pd.DataFrame:
    g = pd.read_parquet(PROCESSED / "gsynth_gaps.parquet")
    g["teryt_powiat"] = g["teryt_powiat"].astype(str).str.zfill(4)
    return g


def get_city_data(df: pd.DataFrame, teryt: str) -> pd.DataFrame:
    """Return sorted, balanced subpanel for one city (all 5 outcomes non-NA)."""
    sub = (
        df[df["teryt_powiat"] == teryt][["year"] + OUTCOMES]
        .dropna(subset=OUTCOMES)
        .sort_values("year")
        .reset_index(drop=True)
    )
    return sub


def fit_var(data: pd.DataFrame) -> dict | None:
    """Fit VAR(p) with BIC lag selection. Returns dict with coefs, sigma, p, fitted result."""
    if len(data) < MIN_OBS:
        return None
    mat = data[OUTCOMES].values.astype(float)
    try:
        model = VAR(mat)
        result = model.fit(maxlags=MAX_LAG, ic="bic", trend="c")
        return {
            "result": result,
            "coefs": result.coefs.copy(),        # p × K × K
            "const": result.coefs_exog.copy(),   # 1 × K  (trend='c')
            "sigma_u": result.sigma_u.copy(),    # K × K
            "p": result.k_ar,
            "n_obs": len(mat),
            "years": data["year"].values,
        }
    except Exception as exc:
        return None


def mean_group_pool(city_fits: dict[str, dict | None]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pool VAR coefficients via Mean Group (Pesaran-Smith 1995).
    Returns A_mg (p×K×K), A_se, const_mg (K,), Sigma_mg (K×K).
    """
    valid = {t: v for t, v in city_fits.items() if v is not None}
    K = len(OUTCOMES)

    coef_list  = [v["coefs"]  for v in valid.values()]
    const_list = [v["const"]  for v in valid.values()]
    sigma_list = [v["sigma_u"] for v in valid.values()]

    max_p = max(c.shape[0] for c in coef_list)

    def pad(A: np.ndarray) -> np.ndarray:
        if A.shape[0] < max_p:
            return np.concatenate([A, np.zeros((max_p - A.shape[0], K, K))], axis=0)
        return A

    A_arr    = np.stack([pad(c) for c in coef_list])   # N × max_p × K × K
    const_arr = np.stack([c.squeeze() for c in const_list])  # N × K
    sigma_arr = np.stack(sigma_list)                    # N × K × K

    N = len(A_arr)
    A_mg     = A_arr.mean(axis=0)
    A_se     = A_arr.std(axis=0) / np.sqrt(N)
    const_mg = const_arr.mean(axis=0)
    sigma_mg = sigma_arr.mean(axis=0)

    print(f"  Mean Group pool: {N} cities, max_p={max_p}, K={K}")
    return A_mg, A_se, const_mg, sigma_mg


# ── IRF ────────────────────────────────────────────────────────────────────────

def compute_irfs(A_mg: np.ndarray, Sigma_mg: np.ndarray, n_periods: int = 20) -> np.ndarray:
    """Cholesky-identified IRFs. Returns array (K_shock × K_resp × n_periods)."""
    K = Sigma_mg.shape[0]
    p = A_mg.shape[0]

    # Reorder to Cholesky ordering
    idx = [OUTCOMES.index(v) for v in CHOL_ORDER]
    A_r = A_mg[:, :, :][:, idx, :][:, :, idx]
    S_r = Sigma_mg[np.ix_(idx, idx)]

    try:
        P = np.linalg.cholesky(S_r)
    except np.linalg.LinAlgError:
        P = np.diag(np.sqrt(np.diag(S_r)))

    # Moving-average representation: Φ_h = Σ_{j=1}^{p} A_j Φ_{h-j}
    Phi = np.zeros((n_periods + 1, K, K))
    Phi[0] = np.eye(K)
    for h in range(1, n_periods + 1):
        for j in range(1, min(p, h) + 1):
            Phi[h] += A_r[j - 1] @ Phi[h - j]

    # Structural IRF: Ψ_h = Φ_h P
    Psi = np.einsum("hij,jk->hik", Phi, P)  # n_periods+1 × K × K
    return Psi   # (shock index = col of P) × resp × period


def plot_irfs(irfs: np.ndarray, out_path: Path) -> None:
    K = len(CHOL_ORDER)
    fig, axes = plt.subplots(K, K, figsize=(14, 11), sharex=True)
    fig.suptitle("Mean-Group Panel VAR — Impulse Response Functions\n(Cholesky identification, 20-year horizon)", fontsize=11)

    short_labels = ["ln Pop", "Nat. Chg", "Unemp", "Firms/1k", "ln Wages"]

    for r in range(K):  # response
        for c in range(K):  # shock
            ax = axes[r, c]
            irf_rc = irfs[1:, r, c]  # skip h=0 (identity)
            ax.plot(range(1, len(irf_rc) + 1), irf_rc, color="#4d7cff", lw=1.5)
            ax.axhline(0, color="grey", lw=0.7, ls="--")
            ax.set_title(f"Shock: {short_labels[c]}", fontsize=7, pad=2)
            if c == 0:
                ax.set_ylabel(short_labels[r], fontsize=7)
            ax.tick_params(labelsize=6)

    for ax in axes[-1]:
        ax.set_xlabel("Years", fontsize=7)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path.name}")


# ── Forecast ───────────────────────────────────────────────────────────────────

def _project_forward(
    start_state: list[np.ndarray],
    coefs: np.ndarray,
    const: np.ndarray,
    residuals: np.ndarray,
    n_steps: int,
    n_boot: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Residual-bootstrap VAR forecast.
    start_state: list of arrays [y_t, y_{t-1}, ..., y_{t-p+1}]
    Returns point, lo80, hi80, lo95, hi95  each (n_steps × K).
    """
    K = coefs.shape[1]
    p = coefs.shape[0]

    def _forecast_one(state: list[np.ndarray], resid_draw: np.ndarray | None) -> np.ndarray:
        st = [s.copy() for s in state]
        path = np.zeros((n_steps, K))
        for h in range(n_steps):
            y_next = const.copy()
            for lag in range(p):
                y_next += coefs[lag] @ st[lag]
            if resid_draw is not None:
                y_next += resid_draw[h % len(resid_draw)]
            path[h] = y_next
            st.insert(0, y_next)
            if len(st) > p:
                st.pop()
        return path

    point = _forecast_one(start_state, None)

    boot = np.zeros((n_boot, n_steps, K))
    T_res = len(residuals)
    for b in range(n_boot):
        idx = np.random.randint(0, T_res, size=n_steps)
        boot[b] = _forecast_one(start_state, residuals[idx])

    lo80 = np.percentile(boot, 10, axis=0)
    hi80 = np.percentile(boot, 90, axis=0)
    lo95 = np.percentile(boot, 2.5, axis=0)
    hi95 = np.percentile(boot, 97.5, axis=0)

    return point, lo80, hi80, lo95, hi95


def forecast_city(
    city_fit: dict | None,
    mg_coefs: np.ndarray,
    mg_const: np.ndarray,
    mg_sigma: np.ndarray,
    state_2023: np.ndarray,
    n_steps: int = N_STEPS,
    n_boot: int = N_BOOT,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Forecast using city-specific fit if available, else MG coefficients."""
    if city_fit is not None:
        coefs   = city_fit["coefs"]
        const   = city_fit["const"].squeeze()
        resids  = city_fit["result"].resid
        p       = city_fit["p"]
        data    = city_fit["result"].model.endog
        history = [data[-(lag + 1)] for lag in range(p)]
        history[0] = state_2023
    else:
        coefs   = mg_coefs
        const   = mg_const
        resids  = np.random.multivariate_normal(np.zeros(mg_sigma.shape[0]), mg_sigma, size=50)
        p       = coefs.shape[0]
        history = [state_2023] + [state_2023] * (p - 1)

    start_state = history[:p]
    return _project_forward(start_state, coefs, const, resids, n_steps, n_boot)


# ── Fan chart plots ─────────────────────────────────────────────────────────────

def plot_fan_chart(
    city_en: str,
    teryt: str,
    sq_forecasts: dict,
    cf_forecasts: dict | None,
    out_path: Path,
) -> None:
    """Plot status-quo and (if available) counterfactual fan charts for ln_pop + unemployment."""
    show_vars = ["ln_population", "unemployment"]
    ncols = len(show_vars)
    fig, axes = plt.subplots(1, ncols, figsize=(12, 4))
    fig.suptitle(f"{city_en} (TERYT {teryt}) — VAR Forecast 2024–2035", fontsize=11)

    for col, var in enumerate(show_vars):
        ax = axes[col]
        vi = OUTCOMES.index(var)
        yrs = FORECAST_YEARS

        # Status-quo
        sq = sq_forecasts
        ax.fill_between(yrs, sq["lo95"][:, vi], sq["hi95"][:, vi],
                        alpha=0.12, color="#4d7cff", label="95% CI (SQ)")
        ax.fill_between(yrs, sq["lo80"][:, vi], sq["hi80"][:, vi],
                        alpha=0.22, color="#4d7cff", label="80% CI (SQ)")
        ax.plot(yrs, sq["point"][:, vi], color="#4d7cff", lw=2, label="Status quo")

        # Counterfactual
        if cf_forecasts is not None:
            cf = cf_forecasts
            ax.fill_between(yrs, cf["lo95"][:, vi], cf["hi95"][:, vi],
                            alpha=0.10, color="#4dffb4")
            ax.fill_between(yrs, cf["lo80"][:, vi], cf["hi80"][:, vi],
                            alpha=0.18, color="#4dffb4")
            ax.plot(yrs, cf["point"][:, vi], color="#16a34a", lw=2,
                    ls="--", label="Counterfactual")

        ax.set_title(OUTCOME_LABELS[var], fontsize=9)
        ax.set_xlabel("Year")
        ax.axvline(2024, color="grey", lw=0.7, ls=":")
        if col == 0:
            ax.legend(fontsize=7)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    np.random.seed(42)
    print("=== Stage 09: Mean-Group Panel VAR ===\n")

    panel = load_panel()
    gaps  = load_gsynth_gaps()

    # Resolve showcase city names (handle diacritics)
    city_map = panel[["teryt_powiat", "city_en"]].drop_duplicates()
    all_city_names = city_map["city_en"].unique()

    def resolve_city(name: str) -> str | None:
        variants = SHOWCASE_VARIANTS.get(name, [name])
        for v in variants:
            if v in all_city_names:
                return v
        # Fuzzy fallback: case-insensitive partial match
        lower = name.lower()
        matches = [c for c in all_city_names if lower in c.lower() or c.lower() in lower]
        return matches[0] if matches else None

    showcase_resolved = {}
    for name in SHOWCASE:
        resolved = resolve_city(name)
        if resolved:
            teryt = city_map[city_map["city_en"] == resolved]["teryt_powiat"].iloc[0]
            showcase_resolved[resolved] = teryt
        else:
            print(f"  [WARN] Could not resolve showcase city: {name}")

    print(f"Showcase cities resolved: {list(showcase_resolved.keys())}\n")

    # ── Fit per-city VARs ──
    print("Fitting per-city VAR models...")
    all_teryts = panel["teryt_powiat"].unique()
    city_fits: dict[str, dict | None] = {}

    failed = 0
    for t in all_teryts:
        data = get_city_data(panel, t)
        if len(data) < MIN_OBS:
            city_fits[t] = None
            failed += 1
            continue
        fit = fit_var(data)
        city_fits[t] = fit
        if fit is None:
            failed += 1

    n_valid = sum(1 for v in city_fits.values() if v is not None)
    print(f"  Valid fits: {n_valid}/{len(all_teryts)}  (failed/insufficient: {failed})\n")

    # ── Mean Group pooling ──
    print("Pooling via Mean Group estimator...")
    A_mg, A_se, const_mg, Sigma_mg = mean_group_pool(city_fits)

    # ── IRFs ──
    print("Computing Mean-Group IRFs...")
    irfs = compute_irfs(A_mg, Sigma_mg, n_periods=20)
    plot_irfs(irfs, FIGURES / "f08_pvar_irf.png")

    # ── Forecasts ──
    print(f"\nForecasting {N_STEPS} steps (2024-2035) for all units, {N_BOOT} bootstrap draws...")

    # Build gsynth lookup: teryt → counterfactual ln_population at year 2023
    gaps_2023 = (
        gaps[gaps["year"] == YEAR_END][["teryt_powiat", "counterfactual"]]
        .set_index("teryt_powiat")["counterfactual"]
        .to_dict()
    )

    rows = []

    for city_en, teryt in showcase_resolved.items():
        print(f"  Forecasting: {city_en} ({teryt})")
        fit = city_fits.get(teryt)

        # Get 2023 observed state
        city_data = get_city_data(panel, teryt)
        obs_2023 = city_data[city_data["year"] == YEAR_END]
        if obs_2023.empty:
            print(f"    [WARN] No 2023 data for {city_en}, skipping")
            continue

        state_2023 = obs_2023[OUTCOMES].values[0].astype(float)

        # Status-quo forecast
        pt, l80, h80, l95, h95 = forecast_city(
            fit, A_mg, const_mg, Sigma_mg, state_2023
        )
        sq_store = {"point": pt, "lo80": l80, "hi80": h80, "lo95": l95, "hi95": h95}

        for h, yr in enumerate(FORECAST_YEARS):
            for vi, var in enumerate(OUTCOMES):
                rows.append({
                    "teryt_powiat": teryt,
                    "city_en": city_en,
                    "year": yr,
                    "variable": var,
                    "path": "status_quo",
                    "value": pt[h, vi],
                    "lo80": l80[h, vi],
                    "hi80": h80[h, vi],
                    "lo95": l95[h, vi],
                    "hi95": h95[h, vi],
                })

        # Counterfactual forecast
        cf_store = None
        cf_ln_pop = gaps_2023.get(teryt)
        if cf_ln_pop is not None:
            state_cf = state_2023.copy()
            pop_idx = OUTCOMES.index("ln_population")
            state_cf[pop_idx] = cf_ln_pop

            pt_cf, l80_cf, h80_cf, l95_cf, h95_cf = forecast_city(
                fit, A_mg, const_mg, Sigma_mg, state_cf
            )
            cf_store = {"point": pt_cf, "lo80": l80_cf, "hi80": h80_cf, "lo95": l95_cf, "hi95": h95_cf}

            for h, yr in enumerate(FORECAST_YEARS):
                for vi, var in enumerate(OUTCOMES):
                    rows.append({
                        "teryt_powiat": teryt,
                        "city_en": city_en,
                        "year": yr,
                        "variable": var,
                        "path": "counterfactual",
                        "value": pt_cf[h, vi],
                        "lo80": l80_cf[h, vi],
                        "hi80": h80_cf[h, vi],
                        "lo95": l95_cf[h, vi],
                        "hi95": h95_cf[h, vi],
                    })

        # Stage 13 hook: innovation_hub path (null values)
        for yr in FORECAST_YEARS:
            for var in OUTCOMES:
                rows.append({
                    "teryt_powiat": teryt, "city_en": city_en,
                    "year": yr, "variable": var, "path": "innovation_hub",
                    "value": None, "lo80": None, "hi80": None, "lo95": None, "hi95": None,
                })

        # Fan chart
        out_fig = FIGURES / f"f08_forecast_{city_en.replace(' ', '_')}.png"
        plot_fan_chart(city_en, teryt, sq_store, cf_store, out_fig)
        print(f"    Saved: {out_fig.name}")

    # ── Save parquet ──
    forecasts = pd.DataFrame(rows)
    out_path = PROCESSED / "pvar_forecasts.parquet"
    forecasts.to_parquet(out_path, index=False)
    print(f"\nSaved -> data/processed/pvar_forecasts.parquet  ({len(forecasts)} rows)")
    print(f"  Cities: {forecasts['city_en'].nunique()}")
    print(f"  Paths:  {forecasts['path'].unique().tolist()}")
    print(f"  Years:  {forecasts['year'].min()}–{forecasts['year'].max()}")
    print("\n=== Stage 09 complete ===")


if __name__ == "__main__":
    main()
