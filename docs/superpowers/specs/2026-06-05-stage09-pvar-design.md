# Stage 09 — Panel VAR Forecast Design Spec
**Project:** PL-Capital-Reform-DiD  
**Date:** 2026-06-05  
**Status:** Approved  
**Context:** Poland serves as a quasi-experimental baseline for a Romania administrative-reform study. Stage 09 forecasts are a forward-looking narrative device, not core causal identification (that role belongs to Stages 05, 10, 11).

---

## 1. Objective

Produce per-city trajectory forecasts to 2035 for five socioeconomic outcomes, using a Mean-Group Panel VAR estimated on the 2000–2023 powiat panel. Deliver:
- status-quo path (from observed 2023 state)
- counterfactual path (from gsynth-adjusted population starting state, for demoted cities)
- Monthly ARIMA robustness check for unemployment

All outputs feed the pip-reform dashboard and the Romania-baseline section of the R Markdown report.

---

## 2. Architecture

```
scripts/09_pvar_forecast.py
  ├── prep_panel()          → balanced per-city subpanels
  ├── fit_unit_var()        → statsmodels VAR(p) per city
  ├── mean_group_pool()     → MG coefficient matrices
  ├── compute_irfs()        → MG IRFs, 20-period horizon
  ├── forecast_city()       → status_quo + counterfactual paths, 500-draw bootstrap
  ├── save_forecasts()      → pvar_forecasts.parquet
  └── plot_fan_charts()     → f08_forecast_{city_en}.png (8 cities)

scripts/09b_arima_unemp.py
  ├── parse_monthly_bdl()   → reshape wide CSV → long
  ├── match_demoted_cities()→ filter to 29–31 treated cities by TERYT
  ├── fit_arima_per_city()  → pmdarima.auto_arima(seasonal=True)
  ├── forecast_to_2035()    → monthly → aggregate to annual
  └── cross_check_vs_var()  → comparison table
```

**Data contract:** reads `panel_powiat.parquet` and `gsynth_gaps.parquet`; writes `pvar_forecasts.parquet` and `arima_unemployment_forecast.parquet`. No CSV round-trips.

---

## 3. Data Preparation

### 3.1 Year Range
2000–2023. Unemployment and wages are largely missing pre-2000 (binding constraint). Population and nat_change_rate have pre-2000 data but are restricted to match.

### 3.2 Per-City Balanced Subpanel
For each of 377 units: find all years where **all 5 variables** are simultaneously non-NA. Use only that window for that city's VAR. Cities with fewer than **10 complete joint observations** are excluded from the MG pool; their forecasts fall back to MG pooled coefficients.

Expected usable cities: ~300–340 (the ~25–30% missingness is concentrated in specific early years/units, not uniformly distributed post-2000).

### 3.3 Variables
| Role | Variables |
|---|---|
| Endogenous (5) | `ln_population`, `unemployment`, `firms_per_1k`, `ln_wages_avg`, `nat_change_rate` |
| Exogenous | None (see §3.4) |

### 3.4 WDI / Macro Controls
**WDI data was never downloaded.** Dropped entirely. Two-way demeaning (within-city + within-year) absorbs both unit FE and the common national macro trend, making WDI redundant. Methodological footnote required in report.

### 3.5 Two-Way Demeaning
Before fitting: subtract city mean and cross-sectional time mean from each variable (standard within-estimator for panel VAR). Residualises out unit and time fixed effects without adding year dummy columns.

---

## 4. Mean-Group VAR Estimation

### 4.1 Lag Order
BIC-selected per city, `p ∈ {1, 2}`. Max lag 2 is appropriate at annual frequency with T≈20, K=5 (VAR(2) uses 50 parameters — borderline but viable given N≈300+ cities for pooling).

### 4.2 Per-City Fit
```python
from statsmodels.tsa.api import VAR
model = VAR(demeaned_data)          # T × 5 array
result = model.fit(maxlags=2, ic='bic')
A = result.coefs                    # p × 5 × 5
Sigma = result.sigma_u              # 5 × 5
```
Store `A`, `Sigma`, `p`, `T` per city.

### 4.3 Mean-Group Pooling (Pesaran-Smith 1995)
$$\hat{A}^{MG} = \frac{1}{N_{valid}} \sum_i \hat{A}_i, \quad \hat{\Sigma}^{MG} = \frac{1}{N_{valid}} \sum_i \hat{\Sigma}_i$$

MG standard error (cross-city dispersion):
$$SE[\hat{A}^{MG}] = \frac{1}{\sqrt{N_{valid}}} \cdot SD_i[\hat{A}_i]$$

No bootstrap needed for the pooled IRFs — MG SE is analytic.

### 4.4 IRF Construction
Cholesky decomposition of $\hat{\Sigma}^{MG}$. Variable ordering (slowest → fastest adjusting):
```
ln_population → nat_change_rate → unemployment → firms_per_1k → ln_wages_avg
```
Horizon: 20 periods. 90% CI from MG SE propagated through IRF recursion. Output: `f08_pvar_irf.png` (5×5 grid, one shock per column).

---

## 5. Forecasting

### 5.1 Forecast Paths
| Path | Construction |
|---|---|
| `status_quo` | Project from city's observed 2023 state using city-specific $\hat{A}_i$ (or MG fallback) |
| `counterfactual` | For the 8 showcase demoted cities: replace `ln_population` 2023 starting state with `gsynth_gaps.counterfactual` at year 2023; re-project. All other variables stay at observed 2023. |

**Rationale for partial substitution:** gsynth only produced a counterfactual for `ln_population`. Substituting only population and letting the VAR propagate is methodologically honest — the counterfactual population feeds into the other variables through the estimated dynamics. Flagged in the report.

If a city is not in `gsynth_gaps` (2 cities were dropped for missing data), only the status_quo path is written; counterfactual is null.

### 5.2 Prediction Intervals
500 parametric bootstrap draws of $\hat{A}_i$ from $\mathcal{N}(\hat{A}_i, \hat{V}[\hat{A}_i])$ where $\hat{V}$ is the OLS coefficient covariance. Re-project each draw. Report 80% and 95% quantile bands.

Reduced from spec's 1,000 draws → 500. Sufficient for a narrative device; halves runtime.

### 5.3 Stage 13 Hook
Output schema includes `path` column with three values: `status_quo`, `counterfactual`, `innovation_hub`. The `innovation_hub` rows are written as null values, to be populated by Stage 13.

### 5.4 Output Schema
```
pvar_forecasts.parquet
  teryt_powiat  str    4-digit TERYT code
  city_en       str    English city name
  year          int    2024–2035
  variable      str    one of the 5 endogenous variables
  path          str    status_quo | counterfactual | innovation_hub
  value         float  point forecast
  lo80          float  80% lower bound
  hi80          float  80% upper bound
  lo95          float  95% lower bound
  hi95          float  95% upper bound
```

### 5.5 Showcase Cities (8)
Radom, Częstochowa, Łomża, Kielce, Słupsk, Legnica, Zamość, Płock.
Fan charts show `ln_population` (primary) and `unemployment` (secondary) for each. Both paths plotted where available.

---

## 6. Monthly ARIMA Robustness (Stage 09b)

### 6.1 Data
`data/raw/gus_bdl/bdl_unemployment_monthly.csv` — semicolon-separated, wide format, Polish headers. Columns: `Jednostka terytorialna`, `Kod` (12-digit TERYT), then `YYYYMXX` months. Coverage: 2011M01–2026M04 (~184 months/city).

Note: spec estimated T≈300; actual T≈184. Still viable for ARIMA; stated in methods.

### 6.2 TERYT Matching
The monthly file uses 12-digit TERYT (`011212006000`). The panel uses 4-digit powiat codes. Crosswalk: 12-digit → 4-digit via `str[2:6]` (characters 3–6 are the powiat code). Match to `treatment_cities.parquet` to identify demoted cities.

### 6.3 Fitting
`pmdarima.auto_arima` per city:
- `seasonal=True`, `m=12` (monthly seasonality)
- `max_p=3, max_q=3, max_P=1, max_Q=1, d=None` (ADF test for d)
- Information criterion: AIC
- Forecast horizon: Dec 2035 (→ ~117 months from 2026M04)

### 6.4 Outputs
- `arima_unemployment_forecast.parquet` — `teryt_powiat, city_en, year_month, unemployment_forecast, lo80, hi80, lo95, hi95`
- Annual aggregate by averaging monthly forecasts → cross-check table vs VAR unemployment projection

---

## 7. Orchestrator (`scripts/run_r_stages.py`)

Simple Python script. Enforces execution order, checks exit codes, logs to stdout.

```
Stage 10 (10_sdid.R)   → check exit 0
Stage 11 (11_gsynth.R) → check exit 0
Stage 11b (11b_nuts3_analysis.R) → check exit 0
Stage 08 (08_local_projections.py) → already done; skip if output exists
Stage 09 (09_pvar_forecast.py)     → run
Stage 09b (09b_arima_unemp.py)     → run
```

Uses `subprocess.run(["Rscript", script], cwd=PROJECT_ROOT, check=True)`. Clear error message if R or a package is missing. Python stages invoked with `subprocess.run(["python", script])` or via direct import.

---

## 8. Figures Summary

| File | Stage | Content |
|---|---|---|
| `f08_pvar_irf.png` | 09 | 5×5 MG IRF grid, 20-period, 90% CI |
| `f08_forecast_{city}.png` | 09 | Fan chart per showcase city: ln_pop + unemployment, both paths |
| `f08b_arima_vs_var_unemp.png` | 09b | Annual ARIMA vs VAR unemployment cross-check bar chart (8 demoted cities) |

---

## 9. Key Methodological Flags (for Report)

1. **WDI omitted:** Year demeaning absorbs national macro trend. Equivalent to including year FEs. Cite Pesaran (2006) for cross-sectional dependence robustness.
2. **T0=184 months (ARIMA):** BDL monthly data starts 2011, not 1999. Sufficient for ARIMA but cannot capture the full post-reform period. Noted as limitation.
3. **Counterfactual path is partial:** Only `ln_population` starting state is substituted from gsynth; other variables remain at 2023 observed. VAR dynamics propagate the population shock forward. This is a structural simulation, not a full GSC counterfactual.
4. **MG estimator assumption:** Slope homogeneity in the mean (heterogeneity averages out). Tested informally by checking cross-city dispersion of $\hat{A}_i$.
5. **Romania applicability:** Poland MG coefficients serve as prior for Romanian city dynamics. Transferability rests on structural similarity of post-communist urban labor markets — argued in report §10.

---

## 10. File Index

**New Python scripts:**
- `scripts/09_pvar_forecast.py`
- `scripts/09b_arima_unemp.py`
- `scripts/run_r_stages.py`

**New processed parquets:**
- `data/processed/pvar_forecasts.parquet`
- `data/processed/arima_unemployment_forecast.parquet`

**New figures:**
- `figures/f08_pvar_irf.png`
- `figures/f08_forecast_{city_en}.png` (8 files)
