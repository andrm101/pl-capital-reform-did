"""
PL Capital Reform — Interactive Dashboard
Run: streamlit run dashboard/app.py
     (from PL-Capital-Reform-DiD/ root)

Tabs:
  Overview        — summary cards + three-estimator robustness table
  City Analysis   — per-city counterfactual trajectory (GSC gaps)
  Forecasts       — fan chart 2024-2035, status_quo vs counterfactual
  LP Impulse Resp — local projection IRFs per outcome
  NUTS-3 GDP      — GDP counterfactual at NUTS-3 level
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DASH = ROOT / "data" / "dashboard"

st.set_page_config(
    page_title="PL Capital Reform Dashboard",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BLUE   = "#4d7cff"
GREEN  = "#16a34a"
RED    = "#dc2626"
YELLOW = "#d97706"
GREY   = "#6b7280"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
})


# ── Data loaders (cached) ───────────────────────────────────────────────────────

@st.cache_data
def load_json(name: str):
    with open(DASH / name, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_regions() -> pd.DataFrame:
    data = load_json("regions.json")
    df = pd.DataFrame(data)
    return df


@st.cache_data
def load_forecasts() -> dict:
    return {d["teryt_powiat"]: d for d in load_json("forecasts.json")}


@st.cache_data
def load_sdid() -> pd.DataFrame:
    return pd.DataFrame(load_json("sdid_estimates.json"))


@st.cache_data
def load_lp_irfs() -> pd.DataFrame:
    return pd.DataFrame(load_json("lp_irfs.json"))


@st.cache_data
def load_nuts3() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = load_json("nuts3_gdp.json")
    return pd.DataFrame(raw["gsc_gaps"]), pd.DataFrame(raw["lp_irfs"])


@st.cache_data
def load_summary() -> dict:
    return load_json("summary.json")


# ── Sidebar ────────────────────────────────────────────────────────────────────

def sidebar() -> None:
    with st.sidebar:
        st.title("🏛️ PL Reform")
        st.caption("Poland 1999 Administrative Reform")
        st.markdown("---")
        s = load_summary()
        st.metric("Demoted cities", s["n_demoted_cities"])
        st.metric("Reform year", s["reform_year"])
        att = s.get("sdid_att_ln_pop")
        if att is not None:
            st.metric("SDiD ATT (ln pop)", f"{att:.3f}", delta=f"{att*100:.1f}%", delta_color="inverse")
        gsc = s.get("gsc_avg_att_ln_pop")
        if gsc is not None:
            st.metric("GSC avg ATT (ln pop)", f"{gsc:.3f}")
        st.markdown("---")
        st.caption("Data: BDL/GUS, Eurostat. Estimation: SDiD, GSC, MG-PVAR.")


# ── Tab 1: Overview ────────────────────────────────────────────────────────────

def tab_overview() -> None:
    st.header("Reform Impact — Overview")
    s = load_summary()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cities demoted", s["n_demoted_cities"])
    c2.metric("Control cities", s["n_control_cities"])
    att = s.get("sdid_att_ln_pop")
    c3.metric("SDiD ATT (ln pop)", f"{att:.3f}" if att else "n/a",
              help="Log-point change in population attributable to demotion")
    pop = s.get("total_demoted_pop_2023")
    c4.metric("Demoted cities pop. (2023)", f"{int(pop/1000):,}k" if pop else "n/a")

    st.markdown("---")
    st.subheader("Three-Estimator Robustness Table")
    st.caption(
        "TWFE = Two-Way Fixed Effects event study; SDiD = Synthetic DiD "
        "(Arkhangelsky et al. 2021); GSC = Generalised Synthetic Control (Xu 2017). "
        "All estimates for ln(population). Agreement across estimators strengthens credibility."
    )

    sdid = load_sdid()
    if not sdid.empty:
        # Format for display
        disp = sdid[["estimator", "outcome", "att", "se", "ci_lo", "ci_hi"]].copy()
        disp.columns = ["Estimator", "Outcome", "ATT", "SE", "CI lo (95%)", "CI hi (95%)"]
        for col in ["ATT", "SE", "CI lo (95%)", "CI hi (95%)"]:
            disp[col] = disp[col].apply(lambda x: f"{x:.4f}" if pd.notna(x) and x is not None else "—")
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.warning("sdid_estimates.json is empty.")

    st.markdown("---")
    st.subheader("All Demoted Cities — GSC Reform Cost (ln population, avg post-1999)")
    regions = load_regions()
    dem = regions[regions["treated"]].copy()
    dem["gsc_att_avg_pct"] = pd.to_numeric(dem["gsc_att_avg_pct"], errors="coerce")
    dem = dem.dropna(subset=["gsc_att_avg_pct"]).sort_values("gsc_att_avg_pct")

    fig, ax = plt.subplots(figsize=(10, max(4, len(dem) * 0.3)))
    colors = [RED if v < 0 else GREEN for v in dem["gsc_att_avg_pct"]]
    ax.barh(dem["city_en"], dem["gsc_att_avg_pct"], color=colors, height=0.7)
    ax.axvline(0, color=GREY, lw=1)
    ax.set_xlabel("Avg. GSC gap (log-points × 100 = approx. %)")
    ax.set_title("Per-city average GSC gap 1999–2023 (ln population)")
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ── Tab 2: City Analysis ───────────────────────────────────────────────────────

def tab_city_analysis() -> None:
    st.header("City-Level Counterfactual Analysis")

    regions = load_regions()
    dem = regions[regions["treated"]].sort_values("city_en")

    city_options = dem["city_en"].tolist()
    selected = st.selectbox("Select city", city_options, index=0)

    city_row = dem[dem["city_en"] == selected].iloc[0]
    teryt = city_row["teryt_powiat"]

    col1, col2, col3 = st.columns(3)
    col1.metric("TERYT", teryt)
    col2.metric("Pop. 1998 (k)", city_row.get("pop_1998_k", "n/a"))
    att = city_row.get("gsc_att_avg_pct")
    col3.metric("GSC reform cost", f"{att:.2f}%" if att is not None else "n/a",
                delta_color="inverse")

    # Counterfactual series
    series = city_row.get("counterfactualSeries", [])
    if not series:
        st.warning("No counterfactual series for this city.")
        return

    df = pd.DataFrame(series)
    df = df[df["actual"].notna() & df["counterfactual"].notna()]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    # Left: observed vs counterfactual (ln pop)
    ax = axes[0]
    ax.plot(df["year"], df["actual"], color=BLUE, lw=2, label="Observed")
    ax.plot(df["year"], df["counterfactual"], color=GREEN, lw=2, ls="--",
            label="GSC counterfactual")
    ax.fill_between(df["year"],
                    df["actual"], df["counterfactual"],
                    where=df["actual"] < df["counterfactual"],
                    alpha=0.15, color=RED, label="Reform cost")
    ax.axvline(1999, color=YELLOW, lw=1.2, ls=":", label="Reform (1999)")
    ax.set_title(f"{selected} — ln population: actual vs counterfactual")
    ax.set_xlabel("Year"); ax.set_ylabel("ln(population)")
    ax.legend(fontsize=8)

    # Right: gap over time
    ax2 = axes[1]
    ax2.bar(df["year"], df["gap"],
            color=[RED if g < 0 else GREEN for g in df["gap"]],
            width=0.8, alpha=0.8)
    ax2.axhline(0, color=GREY, lw=1)
    ax2.axvline(1999, color=YELLOW, lw=1.2, ls=":")
    ax2.set_title(f"{selected} — GSC gap (actual − counterfactual)")
    ax2.set_xlabel("Year"); ax2.set_ylabel("Gap (log-points)")

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    # Data table
    with st.expander("Show raw gap data"):
        st.dataframe(df.round(4), use_container_width=True, hide_index=True)


# ── Tab 3: Forecasts ───────────────────────────────────────────────────────────

OUTCOME_LABELS = {
    "ln_population":  "Log population",
    "unemployment":   "Unemployment rate (%)",
    "firms_per_1k":   "Firms per 1,000 pop.",
    "ln_wages_avg":   "Log avg. wages",
    "nat_change_rate":"Natural change rate",
}

def tab_forecasts() -> None:
    st.header("City-Level Forecasts 2024–2035")
    st.caption(
        "Mean-Group Panel VAR (Pesaran-Smith 1995). Status-quo = forecast from observed 2023 state. "
        "Counterfactual = starting population adjusted by GSC gap at 2023, then re-projected. "
        "Bands: inner 80%, outer 95% prediction interval (500-draw residual bootstrap)."
    )

    forecasts = load_forecasts()
    if not forecasts:
        st.error("forecasts.json is empty.")
        return

    city_options = sorted(forecasts.keys())
    city_labels  = {t: forecasts[t]["city_en"] for t in city_options}

    col1, col2 = st.columns([2, 1])
    selected_teryt = col1.selectbox(
        "Select city",
        city_options,
        format_func=lambda t: city_labels[t],
    )
    selected_var = col2.selectbox("Outcome", list(OUTCOME_LABELS.keys()),
                                  format_func=lambda v: OUTCOME_LABELS[v])

    city_fc = forecasts[selected_teryt]["forecasts"]
    var_fc  = city_fc.get(selected_var, {})

    show_cf = st.checkbox("Show counterfactual path", value=True)
    innovation_available = "innovation_hub" in var_fc and any(
        r["value"] is not None for r in var_fc.get("innovation_hub", [])
    )
    show_hub = st.checkbox(
        "Show Innovation Hub scenario", value=False, disabled=not innovation_available
    )

    fig, ax = plt.subplots(figsize=(10, 4.5))

    for path_key, color, label, ls in [
        ("status_quo",    BLUE,   "Status quo", "-"),
        ("counterfactual", GREEN, "Counterfactual (no reform)", "--"),
        ("innovation_hub", YELLOW, "Innovation hub", ":"),
    ]:
        if path_key not in var_fc:
            continue
        if path_key == "counterfactual" and not show_cf:
            continue
        if path_key == "innovation_hub" and not show_hub:
            continue

        rows = var_fc[path_key]
        years  = [r["year"]  for r in rows]
        values = [r["value"] for r in rows]
        lo80   = [r["lo80"]  for r in rows]
        hi80   = [r["hi80"]  for r in rows]
        lo95   = [r["lo95"]  for r in rows]
        hi95   = [r["hi95"]  for r in rows]

        # Filter out None
        valid = [(y, v, l8, h8, l9, h9)
                 for y, v, l8, h8, l9, h9 in zip(years, values, lo80, hi80, lo95, hi95)
                 if v is not None]
        if not valid:
            continue
        yrs, vals, l80v, h80v, l95v, h95v = zip(*valid)

        ax.fill_between(yrs, l95v, h95v, alpha=0.10, color=color)
        ax.fill_between(yrs, l80v, h80v, alpha=0.20, color=color)
        ax.plot(yrs, vals, color=color, lw=2, ls=ls, label=label)

    ax.axvline(2024, color=GREY, lw=0.8, ls=":")
    ax.set_xlabel("Year")
    ax.set_ylabel(OUTCOME_LABELS[selected_var])
    ax.set_title(f"{city_labels[selected_teryt]} — {OUTCOME_LABELS[selected_var]} forecast")
    ax.legend(fontsize=9)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    if innovation_available:
        st.caption(
            "Innovation Hub scenario (Stage 13): three-estimate bracket "
            "(pessimistic/central/optimistic) is available in the underlying "
            "data; the chart currently shows the central estimate only."
        )
    else:
        st.caption("🔒 Innovation Hub scenario locked — available after Stage 13.")


# ── Tab 4: LP IRFs ────────────────────────────────────────────────────────────

def tab_lp_irfs() -> None:
    st.header("Local Projection Impulse Response Functions")
    st.caption(
        "Jordà (2005) LP. Each panel shows the cumulative effect of demotion on one outcome "
        "at horizons h = −4 … +20 years relative to reform (1999). "
        "Bands: inner 90%, outer 95% CI (Driscoll-Kraay SE). "
        "Dashed vertical line = reform year."
    )

    lp = load_lp_irfs()
    if lp.empty:
        st.error("lp_irfs.json is empty.")
        return

    outcomes = lp["outcome"].unique().tolist()
    n = len(outcomes)
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows))
    axes_flat = axes.flatten() if n > 1 else [axes]

    for i, outcome in enumerate(outcomes):
        ax  = axes_flat[i]
        sub = lp[lp["outcome"] == outcome].sort_values("horizon")
        h   = sub["horizon"].values

        ax.fill_between(h, sub["ci_lo_95"], sub["ci_hi_95"], alpha=0.12, color=BLUE)
        ax.fill_between(h, sub["ci_lo_90"], sub["ci_hi_90"], alpha=0.22, color=BLUE)
        ax.plot(h, sub["coef"], color=BLUE, lw=2)
        ax.axhline(0, color=GREY, lw=0.8, ls="--")
        ax.axvline(0, color=YELLOW, lw=1, ls=":")
        ax.set_title(OUTCOME_LABELS.get(outcome, outcome), fontsize=9)
        ax.set_xlabel("Horizon (years)")
        ax.set_ylabel("Coefficient")

    for j in range(len(outcomes), len(axes_flat)):
        axes_flat[j].set_visible(False)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# ── Tab 5: NUTS-3 GDP ─────────────────────────────────────────────────────────

def tab_nuts3() -> None:
    st.header("NUTS-3 GDP per Capita — Parallel Analysis")
    st.caption(
        "GDP/cap (PPS) analysis at NUTS-3 level. Eurostat data starts 2000 — no pre-treatment GDP available. "
        "LP: cross-sectional at each year horizon from 2000 baseline (HC2 SE). "
        "GSC: r*=0 (degenerates to TWFE with T0=1); interpret with caution. "
        "Primary causal evidence remains at powiat level."
    )

    gaps, lp = load_nuts3()

    tab_a, tab_b = st.tabs(["GSC Gap (mean over demoted NUTS-3)", "LP: GDP effect over horizons"])

    with tab_a:
        if gaps.empty:
            st.warning("No GSC gaps data.")
        else:
            dem_gaps = gaps[gaps["year"] >= 2001].copy()
            agg = dem_gaps.groupby("year")["gap"].mean().reset_index()
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(agg["year"], agg["gap"], color=BLUE, lw=2)
            ax.fill_between(agg["year"], agg["gap"], 0,
                            where=agg["gap"] < 0, alpha=0.2, color=RED, label="Below counterfactual")
            ax.fill_between(agg["year"], agg["gap"], 0,
                            where=agg["gap"] >= 0, alpha=0.2, color=GREEN)
            ax.axhline(0, color=GREY, lw=0.8)
            ax.axvline(2001, color=YELLOW, lw=1, ls=":", label="Treatment indicator starts")
            ax.set_xlabel("Year"); ax.set_ylabel("Mean GSC gap (ln GDP/cap)")
            ax.set_title("Average NUTS-3 GSC gap: demoted vs counterfactual GDP trajectory")
            ax.legend(fontsize=8)
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    with tab_b:
        if lp.empty:
            st.warning("No LP IRFs data.")
        else:
            lp["year"] = lp["horizon"] + 2000
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.fill_between(lp["year"], lp["ci_lo_95"], lp["ci_hi_95"], alpha=0.12, color=BLUE)
            ax.fill_between(lp["year"], lp["ci_lo_90"], lp["ci_hi_90"], alpha=0.22, color=BLUE)
            ax.plot(lp["year"], lp["coef"], color=BLUE, lw=2)
            ax.axhline(0, color=GREY, lw=0.8, ls="--")
            ax.set_xlabel("Year (baseline = 2000)")
            ax.set_ylabel("Coefficient (demoted vs control ln GDP/cap)")
            ax.set_title("NUTS-3 LP: GDP per capita gap over horizons")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sidebar()
    tabs = st.tabs([
        "📊 Overview",
        "🏙️ City Analysis",
        "📈 Forecasts",
        "📉 LP IRFs",
        "🗺️ NUTS-3 GDP",
    ])
    with tabs[0]: tab_overview()
    with tabs[1]: tab_city_analysis()
    with tabs[2]: tab_forecasts()
    with tabs[3]: tab_lp_irfs()
    with tabs[4]: tab_nuts3()


if __name__ == "__main__":
    main()
