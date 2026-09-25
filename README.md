# PL-Capital-Reform-DiD

Causal quasi-experimental analysis of Poland's 1999 administrative reform, which demoted 31 cities from province capitals. Serves as the **causal baseline** for a broader multi-project research programme: Poland's estimated "reform cost" and MG-VAR dynamics are transferred as structural priors to a parallel Romania analysis.

## Status: complete

All estimation stages (01–11b, 09, 09b) are done; dashboard is live with a JSON data contract export. Stage 13 (Innovation ROI) is a stubbed Phase 2 extension. Final report (`main.Rmd`) pending separate confirmation.

## Identification strategy

Difference-in-Differences with multiple complementary estimators to triangulate the treatment effect of capital-city demotion:

- **TWFE event study** — core identification (05)
- **Synthetic Difference-in-Differences (SDiD)** — ATT on ln(population) = −0.045 (SE = 0.017, significant)
- **Generalized Synthetic Control (gsynth)** — 29 treated cities × 29 years, average ATT = −0.015
- **Local Projections** — impulse-response functions
- **Mixed-Group Panel VAR** — 372/377 cities fitted, forward forecasts with fan charts
- **ARIMA** — unemployment forecasting cross-check

## Architecture

```mermaid
flowchart TD
    BDL["BDL (Polish stats office)"] --> Ingest["01_ingest.py"]
    Eurostat["Eurostat"] --> Ingest
    Ingest --> Treatment["02_build_treatment.py<br/>31 demoted cities"]
    Treatment --> Crosswalk["03_crosswalk_merge.py<br/>377 units, 1995-2024"]
    Crosswalk --> EDA["04_eda.py"]
    Crosswalk --> DiD["05_did_eventstudy.py<br/>TWFE"]
    DiD --> Robust["06_robustness.py"]
    Crosswalk --> SDiD["10_sdid.R"]
    Crosswalk --> Gsynth["11_gsynth.R"]
    Crosswalk --> NUTS3["11b_nuts3_analysis.R"]
    Crosswalk --> LP["08_local_projections.py"]
    Crosswalk --> PVAR["09_pvar_forecast.py<br/>MG-VAR"]
    Crosswalk --> ARIMA["09b_arima_unemp.py"]
    DiD --> Export["Data contract export (JSON)"]
    SDiD --> Export
    Gsynth --> Export
    Export --> Dashboard["dashboard/"]
    Export --> Report["reports/main.Rmd"]
```

## Running it

```bash
conda env create -f environment.yml
python scripts/01_ingest.py
python scripts/run_r_stages.py   # orchestrates R stages; --force to re-run, --stages to select
```

## Statistical rigour

Findings are reported as treatment-effect estimates from a quasi-experimental causal design (DiD/SDiD/gsynth), not observational correlations — causal language is appropriate here given the identification strategy, per the project's own causal-inference contract. Effect sizes with standard errors are reported alongside significance throughout.
