# PL-Capital-Reform-DiD — Session Handoff Document

**Last updated:** 2026-06-05  
**Purpose:** Resume context for new chat sessions when the context window is exhausted.  
**Strategic context:** See `../VISION.md` for the full multi-project research programme.

---

## Project Goal

**Phase 1 of a three-phase research programme** (see `../VISION.md`).

Quantify the socioeconomic effects of Poland's 1999 administrative reform on the 31 cities demoted from province capitals. Serves as the **causal baseline** for the Romania analysis:

- Poland findings → calibrate "reform cost" priors for Romanian cities
- MG-VAR coefficients → transfer as structural priors for Romanian city dynamics
- Stage 13 (Innovation ROI) → quantify what a mega-campus investment offsets vs. the reform cost
- Ultimate target: Romania, where an analogous administrative reform represents both a threat (decline) and a policy window (investment opportunity tied to EU-MegaCampus-Siting suitability)

**This project is COMPLETE** — all estimation stages run, dashboard live, JSON data contract exported. Remaining: report (`main.Rmd`) awaiting separate user confirmation.

---

## Execution Order (from spec)

```
01–07 → 10_sdid.R → 11_gsynth.R → 11b_nuts3.R → 08_lp.py → 09_pvar.py → 09b_arima.py → export
```

---

## Stage Status

| Stage | Script | Status | Key Output | Notes |
|---|---|---|---|---|
| 01 ingest | `scripts/01_ingest.py` | ✅ DONE | `bdl_interim.parquet`, `eurostat_interim.parquet` | |
| 02 treatment | `scripts/02_build_treatment.py` | ✅ DONE | `treatment_cities.parquet`, `treatment_panel.parquet` | 31 demoted cities |
| 03 crosswalk | `scripts/03_crosswalk_merge.py` | ✅ DONE | `panel_powiat.parquet` | 377 units, 1995–2024 |
| 04 EDA | `scripts/04_eda.py` | ✅ DONE | figures | |
| 05 DiD event study | `scripts/05_did_eventstudy.py` | ✅ DONE | TWFE estimates | core identification |
| 06 robustness | `scripts/06_robustness.py` | ✅ DONE | robustness checks | |
| 07 translate | `scripts/07_translate.py` | ✅ DONE | English city names | |
| 08 LP | `scripts/08_local_projections.py` | ✅ DONE | `lp_irfs.parquet`, `lp_unit_residuals.parquet` | 29 rows (2 treated cities missing base year) |
| 10 SDiD | `scripts/r/10_sdid.R` | ✅ DONE | `sdid_estimates.parquet` | ATT ln_pop = −0.045 (SE=0.017, sig.) |
| 11 gsynth | `scripts/r/11_gsynth.R` | ✅ DONE | `gsynth_gaps.parquet` | 29 cities × 29 years; r*=2; avg ATT = −0.015 |
| 11b NUTS-3 | `scripts/r/11b_nuts3_analysis.R` | ✅ DONE | `nuts3_lp_irfs.parquet`, `nuts3_gsynth_gaps.parquet` | T0=1 for GSC (Eurostat GDP starts 2000); r*=0 |
| 09 Panel VAR | `scripts/09_pvar_forecast.py` | ✅ DONE | `pvar_forecasts.parquet` | MG-VAR, 372/377 cities fitted, 8 fan charts, 3 paths |
| 09b ARIMA | `scripts/09b_arima_unemp.py` | ✅ DONE | `arima_unemployment_forecast.parquet` | Annual ARIMA (monthly CSV covers wrong geo level — see note) |
| run_r_stages | `scripts/run_r_stages.py` | ✅ DONE | orchestrator | --force to re-run, --stages to select |
| 13 Innovation ROI | `scripts/r/13_innovation_roi.R` | ✅ PASS | `pvar_forecasts.parquet` (innovation_hub path populated; value_pessimistic/value_optimistic three-estimate bracket; Estimate B now uses a per-city MegaCampus Tier-1 multiplier via `scripts/build_powiat_suitability.py`, falling back to flat T3 per-city where no Tier-1 type clears the 0.70 gate -- confirmed empty for all 8 showcase cities given current MegaCampus scores, so output is numerically identical to the earlier flat-T3 version, an honest verified result not a bug). Dashboard toggle-enable logic verified against real JSON (live browser check still open -- broken local streamlit/starlette install, unrelated) |

---

## Processed Parquets (current state)

```
data/processed/
  bdl_interim.parquet
  eurostat_interim.parquet
  treatment_cities.parquet
  treatment_panel.parquet
  panel_powiat.parquet          ← 377 units × 34 cols × 1995–2024
  nuts3_panel.parquet           ← 73 NUTS-3 × 11 cols × 2000–2024
  lp_irfs.parquet               ← Stage 08 output
  lp_unit_residuals.parquet     ← Stage 08 HTE hook
  sdid_estimates.parquet        ← Stage 10 output (3 outcomes)
  gsynth_gaps.parquet           ← Stage 11 output (29 cities × 1995–2023)
  nuts3_lp_irfs.parquet         ← Stage 11b LP (23 horizons)
  nuts3_gsynth_gaps.parquet     ← Stage 11b GSC (696 rows, 29 NUTS-3)
```

**All estimation outputs now present:**
```
  pvar_forecasts.parquet              (1380 rows: 8 cities × 12 years × 5 vars × 3 paths)
  arima_unemployment_forecast.parquet (360 rows: 30 cities × 12 years)
```

---

## Key Data Facts

### panel_powiat.parquet
- 377 units (31 treated, 346 control), years 1995–2024
- 34 columns including: `teryt_powiat` (4-digit str), `city_en`, `treated`, `year`
- Outcome coverage: `ln_population` 96%, `nat_change_rate` 96%, `ln_wages_avg` 76%, `firms_per_1k` 72%, `unemployment` 69%
- Missing unemployment/wages concentrated in pre-2000 years — post-2000 coverage is much higher

### gsynth_gaps.parquet
- Columns: `teryt_powiat, year, actual, counterfactual, gap, se_gap, att_avg`
- 29 treated cities (2 dropped for missing data at base year 1998)
- Years 1995–2023 (29 years)
- `gap` = actual − counterfactual (negative = demotion cost)
- `att_avg` = per-city average post-treatment gap (HTE hook for Stage 12)

### Monthly unemployment CSV
- `data/raw/gus_bdl/bdl_unemployment_monthly.csv`
- Semicolon-separated, wide format, Polish headers
- Columns: `Jednostka terytorialna`, `Kod` (12-digit TERYT), then `YYYYMXX` months
- Coverage: 2011M01–2026M04 (~184 months; spec assumed 300 — note the discrepancy)
- TERYT crosswalk: 12-digit `Kod[2:6]` → 4-digit powiat code in panel

### WDI data
- **NOT DOWNLOADED.** `data/raw/worldbank_wdi/` contains only a README.
- Design decision: replaced by two-way demeaning in PVAR (year dummies absorb national macro trend). No action needed.

### NUTS-3 GDP
- Eurostat `nama_10r_3gdp.tsv` starts 2000 — no pre-1999 data at NUTS-3
- This is a hard constraint, documented in 11b output and report footnote

---

## Design Decisions (for Stage 09)

Full spec: `docs/superpowers/specs/2026-06-05-stage09-pvar-design.md`

### Approach: Mean-Group VAR (Pesaran-Smith 1995)
- `statsmodels.tsa.VAR` per city on its maximal balanced subpanel (all 5 vars non-NA simultaneously)
- Year range: 2000–2023; min 10 complete joint obs to include a city in MG pool
- BIC lag selection, `p ∈ {1, 2}`
- Two-way demeaning (unit FE + time FE) before fitting
- MG pooling: simple average of city-level A matrices; MG SE = cross-city SD / √N
- IRFs from MG coefficients, Cholesky-identified (ordering: ln_pop → nat_change → unemp → firms → wages)
- Forecasts: city-specific A if estimable, MG fallback otherwise
- Bootstrap: 500 parametric draws from N(Â_i, V̂[Â_i])

### Counterfactual Path (narrative device, not core ID)
- Status quo: project from observed 2023 state
- Counterfactual: for 8 showcase cities, substitute `ln_population` 2023 starting value with `gsynth_gaps.counterfactual` at year 2023; let VAR propagate the shock to other variables
- Other 4 variables remain at observed 2023 state (gsynth has no counterfactual for them)
- Cities not in gsynth_gaps: status_quo only, counterfactual = null
- Stage 13 hook: `innovation_hub` path written as null

### 8 Showcase Cities
Radom, Częstochowa, Łomża, Kielce, Słupsk, Legnica, Zamość, Płock

### ARIMA (Stage 09b) — IMPORTANT DATA NOTE
- Monthly BDL CSV (`bdl_unemployment_monthly.csv`) covers **county powiats (ziemskie)** only.
  Demoted cities are **city powiats (grodzkie)** — zero overlap. This is a download error from a prior session.
- **Workaround:** Annual ARIMA fitted on `panel_powiat.parquet` unemployment (T≈20, 2000–2023).
- `pmdarima.auto_arima`, seasonal=False (annual frequency), AIC selection.
- 30/31 demoted cities fitted; 1 city had insufficient unemployment data.
- Forecast to 2035; cross-check vs VAR → `f08b_arima_vs_var_unemp.png`
- Note in report: "Annual ARIMA on T≈20; monthly data unavailable at city-powiat level."

---

## Technical Quirks Found During Implementation

### R issues (already fixed)
- `synthdid_estimate` requires manual matrix construction (Y, N0, T0) — `panel.matrices()` fails with "no variation in treatment status" in current package version
- `synthdid_placebo_variance` does not exist → use `vcov(est, method="placebo")`
- gsynth output: use `out$eff` (T×N, rownames=years, colnames=teryt) not `out$Y.bar` (NULL in current version)
- lubridate masks `year` name in dplyr pipelines → use `.data[["year"]]` or base R subsetting
- gsynth's built-in `plot()` fails with "plot.new has not been called yet" → use ggplot2 from the gaps data directly

### Python issues (already fixed)
- Stage 08 LP: `h=-4` skipped because 1994 not in panel; threshold for test updated to ≥28 rows

### R executable path (Windows)
```
"C:\Program Files\R\R-4.5.1\bin\Rscript.exe"
```
Not on PATH — must use full path in PowerShell. In `run_r_stages.py` use `shutil.which("Rscript")` with fallback to this path.

### Package version warnings (harmless)
- `arrow`, `tidyverse`, `ggplot2`, `readr`, `forcats` built under R 4.5.2/4.5.3 but running on 4.5.1. Warnings only, not errors.

---

## How to Resume

### Run completed R stages (already done, idempotent)
```powershell
Set-Location "C:\Users\andre\Desktop\Sandbox\PL-Capital-Reform-DiD"
& "C:\Program Files\R\R-4.5.1\bin\Rscript.exe" scripts/r/10_sdid.R
& "C:\Program Files\R\R-4.5.1\bin\Rscript.exe" scripts/r/11_gsynth.R
& "C:\Program Files\R\R-4.5.1\bin\Rscript.exe" scripts/r/11b_nuts3_analysis.R
```

### All estimation stages + export + dashboard complete. Next: report only.

```bash
# Run full pipeline
python scripts/run_r_stages.py          # all stages (skip if outputs exist)
python scripts/export_to_json.py        # regenerate dashboard JSON

# Launch dashboard
streamlit run dashboard/app.py          # from PL-Capital-Reform-DiD/ root

# Remaining
reports/main.Rmd      ← awaiting separate confirmation from user
```

---

## What's Done vs Remaining

**Dashboard:** Streamlit app at `dashboard/app.py`. Run: `streamlit run dashboard/app.py` from project root.
  - 5 tabs: Overview | City Analysis | Forecasts | LP IRFs | NUTS-3 GDP
  - JSON data contract at `data/dashboard/` (6 files, ~473 KB total)
  - React dashboard planned for Romania phase (not Poland — Streamlit is sufficient here)

### Done ✅
- All estimation stages (01–11b, 08, 09, 09b)
- Export pipeline → `data/dashboard/*.json`
- Streamlit dashboard → 5 tabs, all data wired
- Orchestrator `run_r_stages.py`
- Strategic vision documented in `../VISION.md`

### Remaining in This Project
| Item | Status | Notes |
|---|---|---|
| `reports/main.Rmd` §4–§8 | ⏳ Awaiting user confirmation | All data ready; §"Innovation Hub Scenario" now filled in under Discussion |
| Stage 13 (`13_innovation_roi.R`) | ✅ PASS | Three-estimate bracket implemented 2026-09-25; Estimate B uses a flat T3 multiplier pending a Poland-specific MegaCampus ecosystem-type overlay (future work) |
| Stage 12 (Causal Forest) | Out of scope | Hooks exist in `lp_unit_residuals.parquet` + `gsynth_gaps.att_avg` |

### Sibling Projects (see `../VISION.md`)
As of 2026-09-25, RO-Administrative-Reform (data pipeline, MG-VAR/GSC, Stage 13,
and its React dashboard) is complete, not planned -- see that project's own
`PROGRESS.md`. This project's Stage 13 and RO-Administrative-Reform's Stage 13
now share two cross-repo artifacts: `EU-Innovation-Panel/analysis/p11_archetype_growth_premium.csv`
(Estimate A) and this repo's own `analysis/retained_capital_benchmark.csv`
(Estimate C, read cross-repo by RO's Stage 13).

---

## Git State

Branch: `main`  
All stage scripts committed. PROGRESS.md is a living document — update it after each session.

To see what's changed since the last commit:
```bash
git status
git log --oneline -10
```
