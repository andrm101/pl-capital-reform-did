# Forecasting Expansion — Design Spec
**Project:** PL-Capital-Reform-DiD  
**Date:** 2026-06-04  
**Phase:** 1 of 2 (Phase 2 = Stage 13 Innovation ROI, separate spec)  
**Status:** Approved

---

## 1. Objective

Extend the existing TWFE event-study pipeline with state-of-the-art causal forecasting and forward projections. Produce per-city counterfactual trajectories, panel-level identification robustness, a NUTS-3 GDP analysis, and city-level forecasts to 2035. Integrate all outputs into the pip-reform dashboard and R Markdown report. Leave clean hooks for Stage 13 (Innovation ROI scenarios).

---

## 2. Architecture

```
Python                         R (via subprocess)             Shared contract
─────────────────────────────  ─────────────────────────────  ──────────────────
08_local_projections.py    →  lp_irfs.parquet            ─┐
09_pvar_forecast.py        →  pvar_forecasts.parquet     ─┤
  (reads gsynth_gaps first)    monthly_unemployment.pq    ─┤  export_to_json.py
                               arima_unemp_forecast.pq   ─┤       ↓
r/10_sdid.R               →  sdid_estimates.parquet     ─┤  pip-reform JSON
r/11_gsynth.R             →  gsynth_gaps.parquet        ─┤
r/11b_nuts3_analysis.R    →  nuts3_panel.parquet        ─┤  main.Rmd
                               nuts3_lp_irfs.parquet     ─┤
                               nuts3_gsynth_gaps.parquet ─┘

Orchestrator: scripts/run_r_stages.py
Stage 13 hook: r/13_innovation_roi.R (stub only)
```

**Data contract:** all stages read/write `data/processed/*.parquet` via `arrow`. No CSV round-trips. Python is the single entry point via `run_r_stages.py`.

**Execution order (enforced by orchestrator):**
`01–07` → `10_sdid.R` → `11_gsynth.R` → `11b_nuts3.R` → `08_lp.py` → `09_pvar.py` → `export`

---

## 3. New Data Downloads

| File | Source | Stage |
|---|---|---|
| `eurostat_regio/nama_10r_3gdp.tsv` | Eurostat bulk download | 01 (already wired) |
| `eurostat_regio/demo_r_pjangrp3.tsv` | Eurostat bulk download | 01 (already wired) |
| Monthly unemployment (BDL VAR ~396xxx) | BDL API (confirm ID) | 09 sub-script |

---

## 4. Stage 08 — Local Projections

**Method:** Jordà (2005) LP. For each outcome $Y$ and horizon $h \in \{-4,\ldots,20\}$:

$$Y_{i,t+h} - Y_{i,t-1} = \alpha_i + \lambda_t + \beta_h D_i + \varepsilon_{i,t+h}$$

- $D_i = 1$ for demoted cities
- SEs: clustered at powiat level with Driscoll-Kraay correction across horizons
- Outcomes: all 7 (ln_population, firms_per_1k, unemployment, ln_wages_avg, nat_change_rate, birth_rate, death_rate)
- Adaptive event-window per outcome (existing pattern from Stage 05)

**Outputs:**
- `data/processed/lp_irfs.parquet` — `outcome, horizon, coef, se, ci_lo_90, ci_hi_90, ci_lo_95, ci_hi_95`
- `figures/f07_lp_irf_{outcome}.png` — IRF plot with shaded 90/95% bands (7 figures)

**HTE hook:** LP residuals at $h=20$ stored as `lp_unit_residuals.parquet` — proxy $\hat\tau_i$ for Stage 12 causal forest input.

**Why LP over TWFE:** Robust to misspecification of the dynamic path. Current gold standard in applied macro/labor (Ramey 2016, Nakamura-Steinsson 2018).

---

## 5. Stage 09 — Panel VAR + Monthly Robustness

### 5a. Primary: Panel VAR

**Method:** VAR(p) on all 377 units, lag order by panel BIC (expected p=1–2 at annual frequency).

- Endogenous: `[ln_population, unemployment, firms_per_1k, ln_wages_avg, nat_change_rate]`
- Exogenous: treatment dummy $D_i$, WDI national macro covariates (GDP growth, CPI)
- NUTS-3 GDP/capita merged as additional exogenous variable via TERYT→NUTS-3 crosswalk

**Two forecast paths per city (2024–2035):**

| Path | Construction |
|---|---|
| `status_quo` | VAR unconditional forecast from observed 2023 state |
| `counterfactual` | Replace 1999–2023 actuals with GSC counterfactual series, re-project |

Both paths: 80% and 95% prediction intervals via 1,000 bootstrap draws of VAR coefficients.

**Outputs:**
- `data/processed/pvar_forecasts.parquet` — `teryt_powiat, city_en, year, variable, path, value, lo80, hi80, lo95, hi95`
- `figures/f08_pvar_irf.png` — Panel VAR IRFs
- `figures/f08_forecast_{city_en}.png` — fan charts for 8 cities: Radom, Częstochowa, Łomża, Kielce, Słupsk, Legnica, Zamość, Płock

**Stage 13 hook:** `pvar_forecasts.parquet` includes a `innovation_hub` path column, populated as `null` until Stage 13 runs.

### 5b. Robustness: Monthly Unemployment ARIMA

- Download BDL monthly unemployment for 31 demoted cities (~300 obs/city)
- Fit ARIMAX(p,d,q) per city, AIC selection — T≈300 makes this viable
- Forecast to Dec 2035, aggregate to annual
- Cross-check against Panel VAR unemployment projection
- Output: `arima_unemployment_forecast.parquet`

---

## 6. Stage 10 — Synthetic DiD (R)

**Package:** `synthdid` (Arkhangelsky et al. 2021, *PNAS*)

**Method:** Constructs optimal unit weights (SC) + time weights (DiD) simultaneously. Addresses parallel trends concern without assuming it.

**Outcomes (SDiD-viable = have pre-1999 data):**
- `ln_population` (primary)
- `nat_change_rate` (secondary)
- `birth_rate` (secondary)

**Specification:**
- Pre-period: 1995–1998
- Control pool: 328 never-capital powiaty
- Inference: placebo variance (permutation over control units)

**Outputs:**
- `data/processed/sdid_estimates.parquet` — `outcome, estimator, att, se, ci_lo, ci_hi`
- `figures/f09_sdid_weights.png` — unit weight visualisation
- `figures/f09_sdid_trend.png` — weighted pre/post trend comparison

**Role in paper:** One cell in the three-estimator robustness table (TWFE / SDiD / GSC). If all three agree → strong credibility claim.

---

## 7. Stage 11 — Generalised Synthetic Control (R)

**Package:** `gsynth` (Xu 2017)

**Method:** Interactive fixed-effects factor model. Handles all 31 treated units simultaneously. Does not require convex-combination constraint. Per-city counterfactual trajectories.

**Specification:**
- Outcome: `ln_population` (primary), `nat_change_rate` (secondary)
- Control pool: 328 never-capital powiaty
- Factors: cross-validated over r ∈ {0…5}
- Inference: parametric bootstrap, 1,000 draws
- Pre-period: T_pre=4 (1995–1998); viable given N_control=328

**T_pre caveat:** Factor model identified from cross-sectional variation (large N). Sensitivity to r choice reported. Flagged in methods footnote.

**Outputs:**
- `data/processed/gsynth_gaps.parquet` — `teryt_powiat, city_en, year, actual, counterfactual, gap, se_gap, att_avg`
- `att_avg` per city = Stage 12 HTE outcome variable (hook)
- `figures/f10_gsynth_aggregate.png` — average gap + bootstrap CI
- `figures/f10_gsynth_grid.png` — 3×4 grid, 12 cities
- `figures/f10_gsynth_ebar.png` — ordered bar chart of per-city ATTs

**Dependency:** Stage 09 reads `gsynth_gaps.parquet` for counterfactual path construction.

---

## 8. Stage 11b — NUTS-3 Parallel GDP Analysis (R)

**Why:** GDP per capita does not exist at powiat level. Finest resolution is NUTS-3 (Eurostat). Parallel analysis establishes the GDP impact of administrative demotion.

**Treatment assignment at NUTS-3:**
- `n_demoted`: count of demoted capitals in NUTS-3 region
- `any_demoted`: binary
- `treatment_intensity`: n_demoted / n_old_capitals_in_nuts3 (continuous spec)
- Via TERYT→NUTS-3 crosswalk (already in Stage 03)

**Estimators:**
- LP at NUTS-3: `gdp_per_cap_pps` outcome, `any_demoted` treatment
- GSC at NUTS-3: control pool = NUTS-3 regions with zero demoted cities (~40 units). N_control is borderline for GSC factor estimation — report cross-validated r and run sensitivity check with r=1 fixed as robustness

**Outputs:**
- `data/processed/nuts3_panel.parquet`
- `data/processed/nuts3_lp_irfs.parquet`
- `data/processed/nuts3_gsynth_gaps.parquet`
- `figures/f11_nuts3_lp_gdp.png`
- `figures/f11_nuts3_gsynth_gdp.png`

**Stage 13 hook:** `nuts3_gsynth_gaps.parquet` provides the GDP baseline. Stage 13 adds innovation premium on top → `innovation_hub` GDP path → ROI numerator.

---

## 9. R Orchestrator + Bridge

**`scripts/run_r_stages.py`:** Single entry point. Runs R stages via `subprocess.run(["Rscript", ...])` with exit-code checking. Enforces execution order. Clear diagnostics if R/packages missing.

**`scripts/r/install_packages.R`:** One-time setup. Packages: `synthdid, gsynth, did, plm, arrow, tidyverse`.

**`renv.lock`** in `scripts/r/` pins R package versions.

**`scripts/r/13_innovation_roi.R`:** Stub file only. Reads `nuts3_gsynth_gaps.parquet` + `innovation_scenarios.parquet` (written by Python Stage 13 when built).

---

## 10. Export Pipeline Updates

**`scripts/export_to_json.py` gains:**
- `load_gsynth_gaps()` → per-city counterfactual series
- `load_pvar_forecasts()` → status_quo + counterfactual paths 2024–2035
- `load_nuts3_gdp_gaps()` → NUTS-3 GDP counterfactual

**Per-city region JSON new fields:**
```json
{
  "counterfactualSeries": [
    {"year": 1999, "actual": 232000, "counterfactual": 235000, "gap": -3000}
  ],
  "forecastSeries": [
    {"year": 2024, "path": "status_quo",     "value": 198000,
     "lo80": 191000, "hi80": 205000, "lo95": 186000, "hi95": 210000},
    {"year": 2024, "path": "counterfactual", "value": 215000,
     "lo80": 207000, "hi80": 223000, "lo95": 201000, "hi95": 229000},
    {"year": 2024, "path": "innovation_hub", "value": null}
  ],
  "reformCost2035": -17000,
  "innovationScenario": null
}
```

**New choropleth layer:** `counterfactual-gap.json` — diverging red/green, reform cost magnitude per NUTS-2 region.

---

## 11. Dashboard New Components

### `CounterfactualChart.tsx`
- Replaces `PopChart` for demoted PL cities
- Dual-line: observed (solid blue) + GSC counterfactual (dashed green)
- Shaded reform-cost area (red when actual < counterfactual)
- Bottom annotation: "Reform cost to {year}: −{n}k residents"
- Falls back to `PopChart` for non-demoted cities

### `ForecastPanel.tsx`
- Fan chart 2024–2035
- Two paths: status_quo + counterfactual
- 80% CI inner band, 95% CI outer band
- Path toggles: `[STATUS QUO] [COUNTERFACTUAL] [INNOVATION HUB (locked)]`
- `INNOVATION HUB` greyed-out + lock icon until Stage 13 data present

### `RegionPanel.tsx` changes
- Conditional render: `CounterfactualChart` + `ForecastPanel` for demoted cities only
- All other cities: existing `PopChart` unchanged

### `LayerSwitcher.tsx` change
- Adds `counterfactual-gap` as fifth layer
- Accent colour: diverging (matches reform-impact but using GSC gap values)

---

## 12. Report Integration (`reports/main.Rmd`)

| Section | Reads | Content |
|---|---|---|
| §4 Local Projections | `lp_irfs.parquet` | IRF plots × 7 + coefficient table at h={5,10,15,20} |
| §5 Identification Robustness | `sdid_estimates.parquet`, `gsynth_gaps.parquet`, existing TWFE CSV | Three-estimator comparison table |
| §6 City-Level Counterfactuals | `gsynth_gaps.parquet` | 3×4 city grid + ordered ATT bar chart + 3 case studies |
| §7 GDP at NUTS-3 | `nuts3_lp_irfs.parquet`, `nuts3_gsynth_gaps.parquet` | LP IRFs + GSC GDP counterfactuals |
| §8 Projections to 2035 | `pvar_forecasts.parquet`, `arima_unemployment_forecast.parquet` | Fan charts × 8 cities + aggregate loss table + ARIMA robustness note |
| §9 Innovation ROI | *(stub)* | `# TODO Stage 13` |

---

## 13. Stage 13 Hook Summary (Phase 2 — separate spec)

**What Stage 13 will build:**
- **A:** Archetype premium from EU Innovation Panel regression (GDP growth ~ archetype, controls)
- **B:** Literature multipliers (Moretti 2010, EIB innovation hub studies)
- **C:** Polish SC donors — Kraków, Wrocław, Trójmiasto as counterfactual benchmark

Three independent premium estimates → bracketed range (pessimistic/central/optimistic) → `innovation_hub` path in `pvar_forecasts.parquet` + `nuts3_gsynth_gaps.parquet` → ROI = NPV(GDP_innovation − GDP_status_quo) / Investment_cost.

**Hooks already in place after Phase 1:**
- `innovationScenario: null` in region JSONs
- `innovation_hub` path column (null) in `pvar_forecasts.parquet`
- `r/13_innovation_roi.R` stub
- `§9 Innovation ROI` stub in `main.Rmd`
- `ForecastPanel` locked toggle
- `nuts3_gsynth_gaps.parquet` (GDP baseline for ROI numerator)

---

## 14. File Index

**New Python scripts:**
- `scripts/08_local_projections.py`
- `scripts/09_pvar_forecast.py`
- `scripts/run_r_stages.py`

**New R scripts:**
- `scripts/r/install_packages.R`
- `scripts/r/10_sdid.R`
- `scripts/r/11_gsynth.R`
- `scripts/r/11b_nuts3_analysis.R`
- `scripts/r/13_innovation_roi.R` *(stub)*

**New processed parquets:**
`lp_irfs.parquet`, `lp_unit_residuals.parquet`, `pvar_forecasts.parquet`, `monthly_unemployment.parquet`, `arima_unemployment_forecast.parquet`, `sdid_estimates.parquet`, `gsynth_gaps.parquet`, `nuts3_panel.parquet`, `nuts3_lp_irfs.parquet`, `nuts3_gsynth_gaps.parquet`

**New figures:** f07–f11 series (see individual stage specs above)

**Dashboard:** `components/CounterfactualChart.tsx`, `components/ForecastPanel.tsx`, updates to `RegionPanel.tsx`, `LayerSwitcher.tsx`, `app/page.tsx`

**Export:** `scripts/export_to_json.py` (updated)
