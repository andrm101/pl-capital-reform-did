"""
Stage 09b — Annual ARIMA Unemployment Robustness
Reads:  data/processed/panel_powiat.parquet    (annual unemployment, demoted cities)
        data/processed/pvar_forecasts.parquet  (VAR unemployment projection)
Writes: data/processed/arima_unemployment_forecast.parquet
        figures/f08b_arima_vs_var_unemp.png

Note: The BDL monthly CSV (bdl_unemployment_monthly.csv) covers county powiats
(ziemskie) only — demoted cities are city powiats (grodzkie) and are absent.
Annual ARIMA on panel_powiat data (T≈22 obs/city, 2000–2022) is used instead.
T≈22 at annual frequency is standard for ARIMA; cited limitation in report.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"

FORECAST_YEARS = list(range(2024, 2036))
N_STEPS = len(FORECAST_YEARS)

SHOWCASE = [
    "Radom", "Czestochowa", "Lomza", "Kielce",
    "Slupsk", "Legnica", "Zamosc", "Plock",
]


# ── Data loading ───────────────────────────────────────────────────────────────

def load_annual_unemployment() -> pd.DataFrame:
    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)
    demoted = panel[panel["treated"] == 1][
        ["teryt_powiat", "city_en", "year", "unemployment"]
    ].dropna(subset=["unemployment"])
    return demoted.sort_values(["teryt_powiat", "year"])


def load_var_unemployment() -> pd.DataFrame:
    pvar = pd.read_parquet(PROCESSED / "pvar_forecasts.parquet")
    return (
        pvar[
            (pvar["variable"] == "unemployment") &
            (pvar["path"] == "status_quo")
        ][["teryt_powiat", "city_en", "year", "value"]]
        .rename(columns={"value": "var_unemployment"})
    )


# ── ARIMA per city ─────────────────────────────────────────────────────────────

def fit_and_forecast(
    series: pd.Series,
    city_en: str,
    teryt: str,
) -> pd.DataFrame | None:
    try:
        import pmdarima as pm
    except ImportError:
        raise ImportError("pmdarima not installed — run: pip install pmdarima")

    series = series.dropna()
    if len(series) < 8:
        print(f"    [SKIP] {city_en}: only {len(series)} obs")
        return None

    try:
        model = pm.auto_arima(
            series,
            seasonal=False,          # annual frequency: no monthly seasonality
            max_p=3, max_q=3,
            d=None,                  # ADF test selects d
            information_criterion="aic",
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
        )
        fc,   conf80 = model.predict(N_STEPS, return_conf_int=True, alpha=0.20)
        fc95, conf95 = model.predict(N_STEPS, return_conf_int=True, alpha=0.05)

        order_str = f"ARIMA{model.order}"
        print(f"    {city_en}: {order_str}, n={len(series)}")

        return pd.DataFrame({
            "teryt_powiat":          teryt,
            "city_en":               city_en,
            "year":                  FORECAST_YEARS,
            "unemployment_forecast": fc,
            "lo80":                  conf80[:, 0],
            "hi80":                  conf80[:, 1],
            "lo95":                  conf95[:, 0],
            "hi95":                  conf95[:, 1],
            "model":                 order_str,
        })

    except Exception as exc:
        print(f"    [ERROR] {city_en}: {exc}")
        return None


# ── Cross-check plot ───────────────────────────────────────────────────────────

def resolve_name(name: str, available: list[str]) -> str | None:
    lower = name.lower()
    for c in available:
        if lower in c.lower() or c.lower() in lower:
            return c
    return None


def plot_cross_check(
    arima_fc: pd.DataFrame,
    var_unemp: pd.DataFrame,
    out_path: Path,
    check_year: int = 2030,
) -> None:
    available = arima_fc["city_en"].unique().tolist()
    cities = []
    for s in SHOWCASE:
        m = resolve_name(s, available)
        if m:
            cities.append(m)

    if not cities:
        print("  [WARN] No matching cities for cross-check plot")
        return

    n = min(len(cities), 8)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 3.5 * nrows))
    axes = axes.flatten() if n > 1 else [axes]
    fig.suptitle(
        f"Annual ARIMA vs Panel VAR — Unemployment Forecast at {check_year}\n"
        "(ARIMA fitted on 2000–2023 annual panel; VAR = Mean-Group Panel VAR)",
        fontsize=10,
    )

    for i, city in enumerate(cities[:n]):
        ax = axes[i]
        a_val = arima_fc.loc[
            (arima_fc["city_en"] == city) & (arima_fc["year"] == check_year),
            "unemployment_forecast",
        ]
        v_val = var_unemp.loc[
            (var_unemp["city_en"] == city) & (var_unemp["year"] == check_year),
            "var_unemployment",
        ]
        vals   = []
        labels = []
        colors = []
        if not a_val.empty:
            vals.append(float(a_val.iloc[0]))
            labels.append("ARIMA")
            colors.append("#4d7cff")
        if not v_val.empty:
            vals.append(float(v_val.iloc[0]))
            labels.append("PVAR")
            colors.append("#ff7c4d")

        ax.bar(labels, vals, color=colors, width=0.5)
        ax.set_title(city, fontsize=8)
        ax.set_ylabel("Unemp. (%)", fontsize=7)
        ax.tick_params(labelsize=7)

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path.name}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Stage 09b: Annual ARIMA Unemployment Robustness ===\n")
    print("  Note: monthly BDL CSV covers county powiats only; using annual panel data.\n")

    annual = load_annual_unemployment()
    cities = annual[["teryt_powiat", "city_en"]].drop_duplicates()
    print(f"  Demoted cities with annual unemployment: {len(cities)}")

    # Filter to years 2000-2023 (match VAR range)
    annual = annual[annual["year"].between(2000, 2023)]

    print("Fitting ARIMA per city...")
    forecasts = []
    for _, row in cities.iterrows():
        teryt = row["teryt_powiat"]
        city  = row["city_en"]
        series = (
            annual[annual["teryt_powiat"] == teryt]
            .set_index("year")["unemployment"]
            .sort_index()
        )
        fc_df = fit_and_forecast(series, city, teryt)
        if fc_df is not None:
            forecasts.append(fc_df)

    if not forecasts:
        print("[ERROR] No ARIMA forecasts produced.")
        return

    arima_fc = pd.concat(forecasts, ignore_index=True)
    print(f"\nARIMA forecasts: {len(arima_fc)} rows, {arima_fc['teryt_powiat'].nunique()} cities")

    # Save
    arima_fc.to_parquet(PROCESSED / "arima_unemployment_forecast.parquet", index=False)
    print("Saved -> data/processed/arima_unemployment_forecast.parquet")

    # Cross-check vs PVAR
    print("\nGenerating cross-check plot...")
    var_unemp = load_var_unemployment()
    plot_cross_check(arima_fc, var_unemp, FIGURES / "f08b_arima_vs_var_unemp.png")

    # Summary table
    print("\nForecast at 2030 (demoted cities with VAR data, first 8):")
    summ = (
        arima_fc[arima_fc["year"] == 2030]
        .merge(var_unemp[var_unemp["year"] == 2030], on=["teryt_powiat", "city_en"], how="left")
        [["city_en", "unemployment_forecast", "var_unemployment", "model"]]
        .head(8)
    )
    for _, r in summ.iterrows():
        arima_v = f"{r['unemployment_forecast']:.2f}" if pd.notna(r["unemployment_forecast"]) else "n/a"
        var_v   = f"{r['var_unemployment']:.2f}" if pd.notna(r["var_unemployment"]) else "n/a"
        print(f"  {r['city_en']:<22} ARIMA={arima_v}  VAR={var_v}  [{r['model']}]")

    print("\n=== Stage 09b complete ===")


if __name__ == "__main__":
    main()
