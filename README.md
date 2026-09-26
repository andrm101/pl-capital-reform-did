# PL-Capital-Reform-DiD

![Status](https://img.shields.io/badge/status-complete-brightgreen) ![R](https://img.shields.io/badge/R-4.x-blue) ![Framing](https://img.shields.io/badge/framing-causal--DiD-success) ![Units](https://img.shields.io/badge/units-377%20cities-lightgrey)

> Causal quasi-experimental analysis of Poland's 1999 administrative reform, which demoted **31 cities** from province capitals.

This is the **causal baseline** of a three-project research programme: Poland's estimated reform cost and MG-VAR dynamics are transferred as structural priors to a parallel [RO-Administrative-Reform](https://github.com/andrm101/ro-administrative-reform) analysis, and its powiat-level suitability scoring links into [EU-MegaCampus-Siting](https://github.com/andrm101/eu-megacampus-siting).

---

## Key findings

- **SDiD ATT on ln(population) = −0.045** (SE = 0.017, significant) — demoted cities lost ~4.5% population relative to synthetic control
- Generalized Synthetic Control (gsynth): average ATT = **−0.015** across 29 treated cities × 29 years — directionally consistent, smaller magnitude
- Triangulated across 6 estimators (TWFE, SDiD, gsynth, Local Projections, MG-VAR, ARIMA) for robustness, not relying on a single identification strategy
- Innovation ROI (Stage 13): per-city Tier-1 multiplier computed for 8 showcase cities using MegaCampus suitability scores — none currently clear the 0.70 Tier-1 gate, so the flat baseline rate applies to all 8 (a verified-correct finding, not an unmodelled gap)
- Interactive dashboard live with a JSON data contract export, including an Innovation Hub scenario toggle

## Identification strategy

Difference-in-Differences with multiple complementary estimators to triangulate the treatment effect of capital-city demotion:

| Estimator | Role |
|---|---|
| TWFE event study | Core identification (05) |
| Synthetic DiD (SDiD) | ATT = −0.045 (SE = 0.017) |
| Generalized Synthetic Control | Avg. ATT = −0.015, 29×29 |
| Local Projections | Impulse-response functions |
| Mixed-Group Panel VAR | 372/377 cities fitted, forward forecasts with fan charts |
| ARIMA | Unemployment forecasting cross-check |

---

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
    Crosswalk --> SDiD["10_sdid.R<br/>ATT = -0.045"]
    Crosswalk --> Gsynth["11_gsynth.R<br/>ATT = -0.015"]
    Crosswalk --> NUTS3["11b_nuts3_analysis.R"]
    Crosswalk --> LP["08_local_projections.py"]
    Crosswalk --> PVAR["09_pvar_forecast.py<br/>MG-VAR"]
    Crosswalk --> ARIMA["09b_arima_unemp.py"]
    MegaCampus["EU-MegaCampus-Siting<br/>suitability scores"] --> Suitability["build_powiat_suitability.py<br/>8 showcase cities"]
    Suitability --> ROI["13_innovation_roi.R"]
    DiD --> Export["Data contract export (JSON)"]
    SDiD --> Export
    Gsynth --> Export
    ROI --> Export
    Export --> Dashboard["dashboard/"]
    Export --> Report["reports/main.Rmd"]
```

---

## Statistical rigour

> Findings are reported as treatment-effect estimates from a quasi-experimental causal design (DiD/SDiD/gsynth), not observational correlations — causal language is appropriate here given the identification strategy, per the project's own causal-inference contract. Effect sizes with standard errors are reported alongside significance throughout.

---

## Status

All estimation stages (01–11b, 09, 09b, 13) are complete; the dashboard is live with a JSON data contract export. Final report (`main.Rmd`) pending separate confirmation.

---

## Running it

```bash
conda env create -f environment.yml
python scripts/01_ingest.py
python scripts/run_r_stages.py   # orchestrates R stages; --force to re-run, --stages to select
```
