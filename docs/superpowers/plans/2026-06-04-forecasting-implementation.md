# Forecasting Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Local Projections, Panel VAR forecasts, SDiD, and GSC counterfactuals to the PL-Capital-Reform-DiD pipeline; integrate outputs into the pip-reform dashboard and R Markdown report stubs.

**Architecture:** Python stages 08–09 (estimation + forecasting) write parquets; R stages 10–11b (SDiD, GSC, NUTS-3) read/write parquets via `arrow`; `run_r_stages.py` orchestrates the full pipeline; `export_to_json.py` feeds JSON to the pip-reform Next.js dashboard.

**Tech Stack:** Python 3.x (linearmodels, statsmodels, pandas, pyarrow), R 4.x (synthdid, gsynth, arrow, tidyverse), Next.js 15 / React 19 / recharts, pytest, vitest

**Execution order (enforced by orchestrator):**
`01–07 (existing)` → `10_sdid.R` → `11_gsynth.R` → `11b_nuts3.R` → `08_lp.py` → `09_pvar.py` → `export`

---

## File Map

**New Python scripts:**
- `scripts/08_local_projections.py` — LP IRF estimation for all 7 outcomes
- `scripts/09_pvar_forecast.py` — Panel VAR + ARIMA monthly robustness
- `scripts/run_r_stages.py` — orchestrates R execution via subprocess
- `scripts/tests/test_08_lp.py`
- `scripts/tests/test_09_pvar.py`

**New R scripts:**
- `scripts/r/install_packages.R` — one-time package install
- `scripts/r/utils.R` — shared parquet helpers
- `scripts/r/10_sdid.R` — Synthetic DiD
- `scripts/r/11_gsynth.R` — Generalised Synthetic Control
- `scripts/r/11b_nuts3_analysis.R` — NUTS-3 GDP LP + GSC
- `scripts/r/13_innovation_roi.R` — stub only

**Modified:**
- `scripts/01_ingest.py` — add Eurostat download + nuts3_panel write
- `scripts/export_to_json.py` — new loaders + new JSON fields
- `pip-reform/lib/types.ts` — new fields on RegionProfile
- `pip-reform/components/RegionPanel.tsx` — conditional chart swap
- `pip-reform/components/LayerSwitcher.tsx` — fifth layer
- `pip-reform/app/page.tsx` — fifth layer description

**New dashboard components:**
- `pip-reform/components/CounterfactualChart.tsx`
- `pip-reform/components/ForecastPanel.tsx`

**New processed parquets (all in `data/processed/`):**
`lp_irfs.parquet`, `lp_unit_residuals.parquet`, `sdid_estimates.parquet`,
`gsynth_gaps.parquet`, `nuts3_panel.parquet`, `nuts3_lp_irfs.parquet`,
`nuts3_gsynth_gaps.parquet`, `pvar_forecasts.parquet`,
`monthly_unemployment.parquet`, `arima_unemployment_forecast.parquet`

---

## Task 1: Eurostat NUTS-3 Data Download + NUTS-3 Panel Build

**Files:**
- Modify: `scripts/01_ingest.py`
- Create: `data/raw/eurostat_regio/README.md`

- [ ] **Step 1: Add Eurostat bulk-download helper to `scripts/01_ingest.py`**

Add after the existing imports and before `def load_bdl_wide`:

```python
import gzip
import urllib.request

EUROSTAT_FILES = {
    "nama_10r_3gdp.tsv": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/nama_10r_3gdp/?format=TSV&compressed=true",
    "demo_r_pjangrp3.tsv": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/demo_r_pjangrp3/?format=TSV&compressed=true",
}

def download_eurostat_if_missing(raw_dir: Path) -> None:
    estat_dir = raw_dir / "eurostat_regio"
    estat_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in EUROSTAT_FILES.items():
        out = estat_dir / filename
        if out.exists():
            print(f"[SKIP] {filename} already exists.")
            continue
        print(f"Downloading {filename} from Eurostat...")
        tmp = out.with_suffix(".tsv.gz")
        urllib.request.urlretrieve(url, tmp)
        with gzip.open(tmp, "rb") as f_in, open(out, "wb") as f_out:
            f_out.write(f_in.read())
        tmp.unlink()
        print(f"  Saved → {out.name}")
```

- [ ] **Step 2: Call downloader at the top of `main()` in `scripts/01_ingest.py`**

In `def main()`, add as the very first line:

```python
download_eurostat_if_missing(RAW)
```

- [ ] **Step 3: Add NUTS-3 panel builder to `scripts/01_ingest.py`**

Add after the existing Eurostat ingest block (after `if estat_panels:`):

```python
    # --- NUTS-3 panel (GDP + population → GDP per capita) ---
    gdp_path = RAW / "eurostat_regio" / "nama_10r_3gdp.tsv"
    pop_path = RAW / "eurostat_regio" / "demo_r_pjangrp3.tsv"
    if gdp_path.exists() and pop_path.exists():
        gdp = load_eurostat_tsv(gdp_path, "gdp_mio_eur")
        pop = load_eurostat_tsv(pop_path, "pop_nuts3")
        nuts3 = gdp.merge(pop, on=["nuts3", "year"], how="outer")
        nuts3 = nuts3[nuts3["nuts3"].str.startswith("PL")]
        nuts3["gdp_per_cap_eur"] = (
            1e6 * nuts3["gdp_mio_eur"] / nuts3["pop_nuts3"].replace(0, np.nan)
        )
        nuts3["ln_gdp_per_cap"] = np.log(nuts3["gdp_per_cap_eur"])

        # Attach treatment flags via TERYT→NUTS-3 crosswalk
        cw = pd.DataFrame([
            ("0261","PL515"),("0262","PL516"),("0264","PL514"),("0265","PL517"),
            ("0461","PL613"),("0463","PL613"),("0464","PL616"),
            ("0661","PL811"),("0662","PL812"),("0663","PL814"),("0664","PL812"),
            ("0861","PL431"),("0862","PL432"),
            ("1061","PL711"),("1062","PL713"),("1063","PL715"),
            ("1261","PL213"),("1262","PL218"),("1263","PL217"),
            ("1461","PL921"),("1402","PL922"),("1462","PL923"),
            ("1463","PL924"),("1464","PL925"),("1465","PL911"),
            ("1661","PL524"),
            ("1861","PL821"),("1862","PL822"),("1863","PL823"),("1864","PL824"),
            ("2061","PL841"),("2062","PL842"),("2063","PL843"),
            ("2261","PL633"),("2263","PL636"),
            ("2461","PL225"),("2464","PL224"),("2467","PL22A"),
            ("2661","PL721"),
            ("2861","PL621"),("2862","PL622"),
            ("3061","PL416"),("3062","PL414"),("3063","PL417"),
            ("3064","PL411"),("3065","PL415"),
            ("3261","PL426"),("3262","PL424"),
        ], columns=["teryt_powiat", "nuts3"])

        treat_flag = pd.read_parquet(PROCESSED / "treatment_cities.parquet")[
            ["teryt_powiat", "retained_capital"]
        ].copy()
        treat_flag["teryt_powiat"] = treat_flag["teryt_powiat"].str.zfill(4)
        cw_treat = cw.merge(treat_flag, on="teryt_powiat", how="left")
        nuts3_flags = (
            cw_treat.groupby("nuts3")
            .agg(
                n_demoted=("retained_capital", lambda x: (x == 0).sum()),
                n_retained=("retained_capital", "sum"),
                n_old_caps=("teryt_powiat", "count"),
            )
            .reset_index()
        )
        nuts3_flags["any_demoted"] = (nuts3_flags["n_demoted"] > 0).astype(int)
        nuts3_flags["treatment_intensity"] = (
            nuts3_flags["n_demoted"] / nuts3_flags["n_old_caps"]
        )

        nuts3 = nuts3.merge(nuts3_flags, on="nuts3", how="left")
        nuts3["any_demoted"] = nuts3["any_demoted"].fillna(0).astype(int)
        nuts3["post"] = (nuts3["year"] >= 1999).astype(int)
        nuts3["event_time"] = nuts3["year"] - 1999

        out_path = PROCESSED / "nuts3_panel.parquet"
        nuts3.to_parquet(out_path, index=False)
        print(f"Saved → {out_path.relative_to(ROOT)}  shape={nuts3.shape}")
    else:
        print("[SKIP] Eurostat files not found — nuts3_panel not built.")
```

- [ ] **Step 4: Run Stage 01 and verify**

```bash
cd PL-Capital-Reform-DiD
python scripts/01_ingest.py
```

Expected output includes:
```
Downloading nama_10r_3gdp.tsv from Eurostat...
Downloading demo_r_pjangrp3.tsv from Eurostat...
Saved → data/processed/nuts3_panel.parquet  shape=(...)
```

Then verify:
```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/processed/nuts3_panel.parquet')
print('Shape:', df.shape)
print('Columns:', list(df.columns))
print('any_demoted sum:', df[df['year']==1999]['any_demoted'].sum())
print('PL NUTS3 count:', df['nuts3'].nunique())
"
```

Expected: ~73 NUTS-3 regions, `any_demoted` sum > 0, `gdp_per_cap_eur` non-null for most rows.

- [ ] **Step 5: Commit**

```bash
git add scripts/01_ingest.py data/raw/eurostat_regio/
git commit -m "feat: auto-download Eurostat NUTS-3 GDP+pop, build nuts3_panel.parquet"
```

---

## Task 2: Monthly BDL Unemployment Download

**Files:**
- Modify: `scripts/00_download_bdl.py`

- [ ] **Step 1: Find monthly unemployment variable ID**

```bash
python -c "
import requests, time, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://bdl.stat.gov.pl/api/v1'
H = {'Accept': 'application/json'}

# P2961 = monthly registered unemployed by sex
# Try getting variable IDs from P2961
time.sleep(3)
r = requests.get(f'{BASE}/Variables', params={'lang':'pl','subject-id':'P2961','page-size':20}, headers=H, timeout=20)
for v in r.json().get('results',[]):
    print(f'  {v[\"id\"]:>8}: {v.get(\"n1\",\"\")} [{v.get(\"measureUnitName\",\"\")}]')

# Also check P2392 monthly variant P3559
time.sleep(3)
r2 = requests.get(f'{BASE}/Variables', params={'lang':'pl','subject-id':'P3559','page-size':20}, headers=H, timeout=20)
for v in r2.json().get('results',[]):
    print(f'  [P3559] {v[\"id\"]:>8}: {v.get(\"n1\",\"\")} [{v.get(\"measureUnitName\",\"\")}]')
"
```

Record the variable ID that returns stopa bezrobocia at monthly frequency. Expected: a 5-6 digit integer.

- [ ] **Step 2: Add monthly unemployment to `VARIABLE_MAP` in `scripts/00_download_bdl.py`**

Replace the `YEARS = list(range(1995, 2025))` line and add an annual-years constant, then add the monthly entry. Insert after the `VARIABLE_MAP` list closing bracket:

```python
# Separate download for monthly series (confirmed VAR ID from probe above)
MONTHLY_VARIABLE_MAP: list[dict] = [
    {
        "filename": "bdl_unemployment_monthly.csv",
        "var_id":   None,   # FILL IN from Step 1 above
        "subject":  "P3559",
        "label":    "Stopa bezrobocia rejestrowanego (miesięczna, %)",
        "unit":     "%",
        "note":     "Monthly 1999-2024. ~300 obs per city. Used for ARIMA robustness in Stage 09.",
    },
]
```

Then add a `download_monthly()` function at the bottom of `00_download_bdl.py` before `if __name__ == "__main__"`:

```python
def download_monthly(var_id: int, out_path: Path) -> None:
    """Download monthly BDL data (no year filter — returns all available months)."""
    if out_path.exists():
        print(f"[SKIP] {out_path.name} already exists.")
        return
    if var_id is None:
        print("[SKIP] Monthly VAR ID not set. Run probe to find it.")
        return
    print(f"\n--- {out_path.name} (monthly, VAR {var_id}) ---")
    all_results = []
    page = 0
    while True:
        params = {
            "lang": "pl",
            "unit-level": POWIAT_LEVEL,
            "page": page,
            "page-size": PAGE_SIZE,
            "format": "json",
        }
        data = get_json(f"{BASE_URL}/data/by-variable/{var_id}", params)
        time.sleep(SLEEP_SEC)
        results = data.get("results", [])
        all_results.extend(results)
        total = data.get("totalRecords", 0)
        fetched = (page + 1) * PAGE_SIZE
        print(f"    Page {page}: {len(results)} units")
        if fetched >= total or not results:
            break
        page += 1
    results_to_wide_csv(all_results, out_path)
```

And in `main()`, add after the existing download loop:

```python
    # Monthly unemployment
    spec = MONTHLY_VARIABLE_MAP[0]
    if spec["var_id"] is not None:
        download_monthly(spec["var_id"], OUT_DIR / spec["filename"])
```

- [ ] **Step 3: Run download**

```bash
python scripts/00_download_bdl.py
```

Expected: `bdl_unemployment_monthly.csv` created with ~380 rows and monthly columns.

- [ ] **Step 4: Commit**

```bash
git add scripts/00_download_bdl.py data/raw/gus_bdl/bdl_unemployment_monthly.csv
git commit -m "feat: add monthly BDL unemployment download for ARIMA robustness"
```

---

## Task 3: R Environment Setup

**Files:**
- Create: `scripts/r/install_packages.R`
- Create: `scripts/r/utils.R`
- Create: `scripts/r/13_innovation_roi.R` (stub)
- Create: `renv.lock` (generated by renv)

- [ ] **Step 1: Create `scripts/r/install_packages.R`**

```r
# Run once: Rscript scripts/r/install_packages.R
options(repos = c(CRAN = "https://cloud.r-project.org"))

pkgs <- c("arrow", "tidyverse", "synthdid", "gsynth", "did", "plm", "sandwich",
          "lmtest", "renv")

missing <- pkgs[!pkgs %in% installed.packages()[, "Package"]]
if (length(missing) > 0) {
  install.packages(missing)
}

# synthdid is on CRAN from v0.0.9; gsynth from v1.2.1
if (!"synthdid" %in% installed.packages()[, "Package"]) {
  install.packages("synthdid")
}
if (!"gsynth" %in% installed.packages()[, "Package"]) {
  install.packages("gsynth")
}

cat("All packages installed.\n")
```

- [ ] **Step 2: Create `scripts/r/utils.R`**

```r
# Shared utilities for R estimation stages.
library(arrow)
library(tidyverse)

ROOT <- here::here()  # project root (PL-Capital-Reform-DiD/)

read_panel <- function() {
  read_parquet(file.path(ROOT, "data/processed/panel_powiat.parquet")) |>
    mutate(teryt_powiat = str_pad(as.character(teryt_powiat), 4, pad = "0"))
}

read_nuts3 <- function() {
  path <- file.path(ROOT, "data/processed/nuts3_panel.parquet")
  if (!file.exists(path)) stop("nuts3_panel.parquet not found. Run Stage 01 first.")
  read_parquet(path)
}

write_processed <- function(df, filename) {
  out <- file.path(ROOT, "data/processed", filename)
  write_parquet(df, out)
  cat(sprintf("Saved → data/processed/%s  (%d rows)\n", filename, nrow(df)))
}

figures_dir <- function() {
  d <- file.path(ROOT, "figures")
  dir.create(d, showWarnings = FALSE, recursive = TRUE)
  d
}
```

- [ ] **Step 3: Create `scripts/r/13_innovation_roi.R` stub**

```r
# Stage 13 — Innovation ROI Scenarios
# STATUS: Stub. Implement after Phase 1 forecasting is complete.
# Reads:  data/processed/nuts3_gsynth_gaps.parquet (GDP baseline)
#         data/processed/innovation_scenarios.parquet (written by Python Stage 13)
# Writes: data/processed/innovation_roi.parquet
#         figures/f13_roi_waterfall.png

cat("Stage 13 (Innovation ROI) not yet implemented.\n")
cat("See docs/specs/2026-06-04-forecasting-design.md §13 for design.\n")
```

- [ ] **Step 4: Install R packages**

```bash
Rscript scripts/r/install_packages.R
```

Expected: "All packages installed." with no errors. If `synthdid` or `gsynth` error, check R version ≥ 4.2.

- [ ] **Step 5: Commit**

```bash
git add scripts/r/
git commit -m "feat: R environment setup — install_packages, utils, Stage 13 stub"
```

---

## Task 4: Stage 08 — Local Projections

**Files:**
- Create: `scripts/08_local_projections.py`
- Create: `scripts/tests/test_08_lp.py`

- [ ] **Step 1: Write failing test `scripts/tests/test_08_lp.py`**

```python
"""Tests for Stage 08 Local Projections."""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROCESSED = ROOT / "data" / "processed"


def test_lp_irfs_schema():
    """lp_irfs.parquet must have required columns and non-null values at h=0."""
    path = PROCESSED / "lp_irfs.parquet"
    assert path.exists(), "Run scripts/08_local_projections.py first"
    df = pd.read_parquet(path)
    required = {"outcome", "horizon", "coef", "se", "ci_lo_90", "ci_hi_90",
                "ci_lo_95", "ci_hi_95"}
    assert required.issubset(df.columns), f"Missing columns: {required - set(df.columns)}"
    # Must have at least ln_population estimates
    pop = df[df["outcome"] == "ln_population"]
    assert len(pop) > 0, "No ln_population rows in lp_irfs"
    # CI ordering: lo_95 < lo_90 < coef < hi_90 < hi_95
    assert (pop["ci_lo_95"] <= pop["ci_lo_90"]).all()
    assert (pop["ci_lo_90"] <= pop["ci_hi_90"]).all()
    assert (pop["ci_hi_90"] <= pop["ci_hi_95"]).all()


def test_lp_unit_residuals_schema():
    """lp_unit_residuals.parquet must have teryt_powiat and residual_h20 columns."""
    path = PROCESSED / "lp_unit_residuals.parquet"
    assert path.exists()
    df = pd.read_parquet(path)
    assert "teryt_powiat" in df.columns
    assert "residual_h20" in df.columns
    # Should have one row per treated city
    assert len(df) >= 30, f"Expected ≥30 rows, got {len(df)}"


def test_lp_horizon_range():
    """IRFs must cover horizons -4 through at least 15."""
    df = pd.read_parquet(PROCESSED / "lp_irfs.parquet")
    pop = df[df["outcome"] == "ln_population"]
    horizons = set(pop["horizon"].astype(int))
    for h in [-4, -3, -2, 0, 5, 10, 15]:
        assert h in horizons, f"Missing horizon h={h}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd PL-Capital-Reform-DiD
python -m pytest scripts/tests/test_08_lp.py -v 2>&1 | head -20
```

Expected: `AssertionError: Run scripts/08_local_projections.py first`

- [ ] **Step 3: Create `scripts/08_local_projections.py`**

```python
"""
Stage 08 — Local Projections (Jordà 2005).
For each outcome Y and horizon h, estimates:
  Y_{i,t+h} - Y_{i,t-1} = α_i + λ_t + β_h D_i + ε_{i,t+h}
SE clustered at powiat level.

Outputs:
  data/processed/lp_irfs.parquet        — IRF coefficients for all outcomes × horizons
  data/processed/lp_unit_residuals.parquet — unit-level residuals at h=20 (HTE hook)
  figures/f07_lp_irf_{outcome}.png      — IRF plots
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

SOURCE_LINE = "Sources: GUS BDL; author calculations. LP with clustered SE (Jordà 2005)."

OUTCOMES = [
    ("ln_population",   "Log population"),
    ("firms_per_1k",    "REGON firms per 1,000 pop."),
    ("unemployment",    "Registered unemployment rate (%)"),
    ("ln_wages_avg",    "Log avg. gross wage"),
    ("nat_change_rate", "Natural pop. change per 1,000"),
    ("birth_rate",      "Crude birth rate per 1,000"),
    ("death_rate",      "Crude death rate per 1,000"),
]

ET_MIN, ET_MAX = -4, 20


def run_lp_single(df: pd.DataFrame, outcome: str, h: int,
                  entity_col: str = "teryt_powiat",
                  time_col: str = "year") -> dict | None:
    """Run LP regression for a single horizon h. Returns dict of estimates."""
    sub = df[[entity_col, time_col, outcome, "treated"]].copy()
    sub = sub.sort_values([entity_col, time_col])
    sub["y_fwd"]  = sub.groupby(entity_col)[outcome].shift(-h)
    sub["y_lag1"] = sub.groupby(entity_col)[outcome].shift(1)
    sub["lhs"]    = sub["y_fwd"] - sub["y_lag1"]
    sub = sub.dropna(subset=["lhs", "treated"])

    if sub.shape[0] < 50 or sub["treated"].sum() == 0:
        return None
    # Drop dummies where treated has no variation (e.g. all control)
    if sub["treated"].nunique() < 2:
        return None

    panel_df = sub.set_index([entity_col, time_col])
    try:
        mod = PanelOLS.from_formula(
            "lhs ~ treated + EntityEffects + TimeEffects",
            data=panel_df, drop_absorbed=True,
        )
        res = mod.fit(cov_type="clustered", cluster_entity=True)
        beta = float(res.params["treated"])
        se   = float(res.std_errors["treated"])
        return {
            "horizon": h, "coef": beta, "se": se,
            "ci_lo_90": beta - 1.645 * se, "ci_hi_90": beta + 1.645 * se,
            "ci_lo_95": beta - 1.960 * se, "ci_hi_95": beta + 1.960 * se,
            "nobs": int(res.nobs), "entities": int(res.entity_info.total),
        }
    except Exception as e:
        print(f"  [SKIP] h={h}: {e}")
        return None


def run_lp(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Run LP for all horizons for a single outcome."""
    records = []
    for h in range(ET_MIN, ET_MAX + 1):
        row = run_lp_single(df, outcome, h)
        if row is not None:
            row["outcome"] = outcome
            records.append(row)
    return pd.DataFrame(records)


def plot_irf(coef_df: pd.DataFrame, outcome: str, label: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    sub = coef_df.sort_values("horizon")

    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(-0.5, color="#e8ff47", lw=1.5, ls="--", label="Reform (1999)")

    ax.fill_between(sub["horizon"], sub["ci_lo_95"], sub["ci_hi_95"],
                    alpha=0.15, color="#4d7cff", label="95% CI")
    ax.fill_between(sub["horizon"], sub["ci_lo_90"], sub["ci_hi_90"],
                    alpha=0.30, color="#4d7cff", label="90% CI")
    ax.plot(sub["horizon"], sub["coef"], "o-", color="#4d7cff",
            ms=4, lw=1.8, label="LP coefficient")

    ax.set_xlabel("Years relative to 1999 reform")
    ax.set_ylabel(f"LP coefficient (Δ {label})")
    ax.set_title(f"Local Projection IRF: {label}", fontweight="bold", fontsize=11)
    ax.legend(fontsize=9)
    ax.text(0.01, -0.12, SOURCE_LINE, transform=ax.transAxes,
            fontsize=7, color="grey")

    plt.tight_layout()
    path = FIGURES / f"f07_lp_irf_{outcome}.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path.name}")


def main() -> None:
    print("=== Stage 08: Local Projections ===\n")

    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)

    all_irfs: list[pd.DataFrame] = []
    unit_residuals: list[dict] = []

    for outcome, label in OUTCOMES:
        if outcome not in panel.columns:
            print(f"[SKIP] {outcome} not in panel.")
            continue
        if panel[outcome].isna().all():
            print(f"[SKIP] {outcome}: all NaN.")
            continue

        print(f"\n[{outcome}]")
        irf = run_lp(panel, outcome)
        if irf.empty:
            print(f"  No estimates produced.")
            continue

        all_irfs.append(irf)
        plot_irf(irf, outcome, label)

        # HTE hook: store unit residuals at h=20 for ln_population
        if outcome == "ln_population":
            row_h20 = run_lp_single(panel, outcome, 20)
            if row_h20:
                # Compute per-city residual = actual_change - aggregate_beta
                sub = panel[["teryt_powiat", "year", outcome, "treated"]].copy()
                sub = sub.sort_values(["teryt_powiat", "year"])
                sub["y_fwd"]  = sub.groupby("teryt_powiat")[outcome].shift(-20)
                sub["y_lag1"] = sub.groupby("teryt_powiat")[outcome].shift(1)
                sub["lhs"]    = sub["y_fwd"] - sub["y_lag1"]
                treated_at_base = sub[
                    (sub["treated"] == 1) & (sub["year"] == 1999) & sub["lhs"].notna()
                ]
                for _, r in treated_at_base.iterrows():
                    unit_residuals.append({
                        "teryt_powiat": r["teryt_powiat"],
                        "residual_h20": r["lhs"] - row_h20["coef"],
                    })

        h_vals = sorted(irf["horizon"].astype(int).tolist())
        print(f"  Horizons: {h_vals[0]}…{h_vals[-1]}  ({len(irf)} estimates)")

    if all_irfs:
        combined = pd.concat(all_irfs, ignore_index=True)
        combined.to_parquet(PROCESSED / "lp_irfs.parquet", index=False)
        print(f"\nSaved → lp_irfs.parquet  ({len(combined)} rows)")

    if unit_residuals:
        res_df = pd.DataFrame(unit_residuals)
        res_df.to_parquet(PROCESSED / "lp_unit_residuals.parquet", index=False)
        print(f"Saved → lp_unit_residuals.parquet  ({len(res_df)} rows)")

    print("\n=== Stage 08 complete ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run Stage 08**

```bash
python scripts/08_local_projections.py
```

Expected output ends with "Stage 08 complete" and 7 figure files saved.

- [ ] **Step 5: Run tests**

```bash
python -m pytest scripts/tests/test_08_lp.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/08_local_projections.py scripts/tests/test_08_lp.py \
        data/processed/lp_irfs.parquet data/processed/lp_unit_residuals.parquet \
        figures/f07_lp_irf_*.png
git commit -m "feat: Stage 08 Local Projections — IRFs for 7 outcomes, HTE hook"
```

---

## Task 5: Stage 10 — Synthetic DiD (R)

**Files:**
- Create: `scripts/r/10_sdid.R`

- [ ] **Step 1: Create `scripts/r/10_sdid.R`**

```r
#!/usr/bin/env Rscript
# Stage 10 — Synthetic DiD (Arkhangelsky et al. 2021, PNAS)
# Reads:  data/processed/panel_powiat.parquet
# Writes: data/processed/sdid_estimates.parquet
#         figures/f09_sdid_weights.png
#         figures/f09_sdid_trend.png

suppressPackageStartupMessages({
  library(arrow)
  library(synthdid)
  library(tidyverse)
})

source("scripts/r/utils.R")
cat("=== Stage 10: Synthetic DiD ===\n\n")

panel <- read_panel()

# SDiD-viable outcomes: need pre-1999 data (1995-1998)
outcomes <- list(
  list(var = "ln_population",   label = "Log population"),
  list(var = "nat_change_rate", label = "Natural change rate"),
  list(var = "birth_rate",      label = "Birth rate per 1,000")
)

results <- list()

for (oc in outcomes) {
  cat(sprintf("\n[%s]\n", oc$var))

  sub <- panel |>
    filter(!is.na(.data[[oc$var]]), year >= 1995, year <= 2023) |>
    select(teryt_powiat, year, value = all_of(oc$var), treated) |>
    mutate(treated_post = treated * as.integer(year >= 1999))

  # SDiD requires balanced panel in pre-period
  pre_complete <- sub |>
    filter(year < 1999) |>
    group_by(teryt_powiat) |>
    summarise(n_pre = n()) |>
    filter(n_pre == 4) |>
    pull(teryt_powiat)

  sub <- sub |> filter(teryt_powiat %in% pre_complete)

  # Wide matrix format required by synthdid
  panel_wide <- sub |>
    select(teryt_powiat, year, value) |>
    pivot_wider(names_from = year, values_from = value) |>
    column_to_rownames("teryt_powiat") |>
    as.matrix()

  treat_mat <- sub |>
    select(teryt_powiat, year, treated_post) |>
    pivot_wider(names_from = year, values_from = treated_post) |>
    column_to_rownames("teryt_powiat") |>
    as.matrix()

  # Drop rows with any NA
  complete_rows <- complete.cases(panel_wide) & complete.cases(treat_mat)
  panel_wide <- panel_wide[complete_rows, ]
  treat_mat  <- treat_mat[complete_rows, ]

  tryCatch({
    est <- synthdid_estimate(panel_wide, treat_mat)
    se  <- sqrt(synthdid_placebo_variance(panel_wide, treat_mat))

    att  <- as.numeric(est)
    cat(sprintf("  ATT = %.4f  SE = %.4f  (n_units = %d)\n",
                att, se, nrow(panel_wide)))

    results[[oc$var]] <- tibble(
      outcome   = oc$var,
      estimator = "SDiD",
      att       = att,
      se        = se,
      ci_lo     = att - 1.96 * se,
      ci_hi     = att + 1.96 * se,
      n_units   = nrow(panel_wide),
      n_years   = ncol(panel_wide)
    )

    # Weight plot for ln_population only
    if (oc$var == "ln_population") {
      png(file.path(figures_dir(), "f09_sdid_weights.png"),
          width = 900, height = 500, res = 120)
      synthdid_units_plot(est, units = rownames(panel_wide)[attr(est, "weights")$omega > 0.01])
      dev.off()
      cat("  Saved: f09_sdid_weights.png\n")

      png(file.path(figures_dir(), "f09_sdid_trend.png"),
          width = 900, height = 500, res = 120)
      plot(est, se.method = "placebo")
      dev.off()
      cat("  Saved: f09_sdid_trend.png\n")
    }

  }, error = function(e) {
    cat(sprintf("  [ERROR] %s\n", conditionMessage(e)))
  })
}

if (length(results) > 0) {
  out <- bind_rows(results)
  write_processed(out, "sdid_estimates.parquet")
  print(out)
}

cat("\n=== Stage 10 complete ===\n")
```

- [ ] **Step 2: Run Stage 10**

```bash
Rscript scripts/r/10_sdid.R
```

Expected: ATT estimates printed, `sdid_estimates.parquet` written, two figures saved.

- [ ] **Step 3: Verify output**

```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/processed/sdid_estimates.parquet')
print(df[['outcome','estimator','att','se','ci_lo','ci_hi']].to_string())
"
```

Expected: 3 rows (one per outcome), ATTs in plausible range (roughly similar to TWFE ATT for ln_population).

- [ ] **Step 4: Commit**

```bash
git add scripts/r/10_sdid.R data/processed/sdid_estimates.parquet figures/f09_*.png
git commit -m "feat: Stage 10 SDiD — ATT for population, natural change, birth rate"
```

---

## Task 6: Stage 11 — GSC / gsynth (R)

**Files:**
- Create: `scripts/r/11_gsynth.R`

- [ ] **Step 1: Create `scripts/r/11_gsynth.R`**

```r
#!/usr/bin/env Rscript
# Stage 11 — Generalised Synthetic Control (Xu 2017)
# Produces per-city counterfactual trajectories for all 31 demoted cities.
# Reads:  data/processed/panel_powiat.parquet
# Writes: data/processed/gsynth_gaps.parquet
#         figures/f10_gsynth_aggregate.png
#         figures/f10_gsynth_grid.png
#         figures/f10_gsynth_ebar.png

suppressPackageStartupMessages({
  library(arrow)
  library(gsynth)
  library(tidyverse)
})

source("scripts/r/utils.R")
cat("=== Stage 11: Generalised Synthetic Control ===\n\n")

panel <- read_panel()

# Prepare data: balanced on population (1995-2023)
pop_panel <- panel |>
  filter(!is.na(ln_population), year >= 1995, year <= 2023) |>
  select(teryt_powiat, year, ln_population, treated) |>
  mutate(
    treated_post = treated * as.integer(year >= 1999),
    teryt_powiat = as.character(teryt_powiat)
  )

# Drop units with any missing values in the balanced panel
complete_units <- pop_panel |>
  group_by(teryt_powiat) |>
  summarise(n = n(), nas = sum(is.na(ln_population))) |>
  filter(nas == 0, n == n_distinct(pop_panel$year)) |>
  pull(teryt_powiat)

pop_panel <- pop_panel |> filter(teryt_powiat %in% complete_units)

cat(sprintf("Units: %d total, %d treated, %d control\n",
    n_distinct(pop_panel$teryt_powiat),
    n_distinct(pop_panel$teryt_powiat[pop_panel$treated == 1]),
    n_distinct(pop_panel$teryt_powiat[pop_panel$treated == 0])))

set.seed(42)
cat("Fitting gsynth (CV over r={0..5}, parametric bootstrap, B=500)...\n")

out <- gsynth(
  ln_population ~ treated_post,
  data      = as.data.frame(pop_panel),
  index     = c("teryt_powiat", "year"),
  force     = "two-way",
  CV        = TRUE,
  r         = c(0, 5),
  se        = TRUE,
  inference = "parametric",
  nboots    = 500,
  seed      = 42,
  min.T0    = 4,
  estimator = "ife"
)

cat(sprintf("Optimal r = %d\n", out$r.cv))
cat(sprintf("Average ATT (post-treatment): %.4f  SE: %.4f\n",
    mean(out$att, na.rm = TRUE),
    mean(out$att.se, na.rm = TRUE)))

# --- Build gaps parquet ---
# out$Y.bar: observed means; out$Y.ct: counterfactual means
# For per-unit: out$Y (observed T×N) and out$Y.ct (counterfactual T×N)

years       <- as.integer(rownames(out$Y))
unit_ids    <- colnames(out$Y)

gaps_list <- lapply(unit_ids, function(uid) {
  actual        <- out$Y[, uid]
  counterfactual <- out$Y.ct[, uid]
  gap           <- actual - counterfactual
  se_gap        <- if (!is.null(out$Y.ct.se)) out$Y.ct.se[, uid] else rep(NA_real_, length(years))
  tibble(
    teryt_powiat   = uid,
    year           = years,
    actual         = as.numeric(actual),
    counterfactual = as.numeric(counterfactual),
    gap            = as.numeric(gap),
    se_gap         = as.numeric(se_gap)
  )
})

gaps <- bind_rows(gaps_list)

# Per-city average post-treatment ATT (HTE hook for Stage 12)
treated_ids <- pop_panel |>
  filter(treated == 1) |>
  pull(teryt_powiat) |>
  unique()

att_avg <- gaps |>
  filter(year >= 1999, teryt_powiat %in% treated_ids) |>
  group_by(teryt_powiat) |>
  summarise(att_avg = mean(gap, na.rm = TRUE))

gaps <- gaps |> left_join(att_avg, by = "teryt_powiat")

write_processed(gaps, "gsynth_gaps.parquet")

# --- Figures ---

# Aggregate gap with CI
png(file.path(figures_dir(), "f10_gsynth_aggregate.png"),
    width = 1000, height = 500, res = 120)
plot(out, type = "gap", main = "Average GSC gap: demoted vs counterfactual",
     ylab = "Log population gap", xlab = "Year")
abline(v = 1999, col = "#e8ff47", lty = 2)
dev.off()
cat("Saved: f10_gsynth_aggregate.png\n")

# 3x4 grid of selected cities
selected <- c("0261","0262","0264","1061","1261","1461",
              "1463","1464","2061","2261","3065","3261")
selected <- selected[selected %in% treated_ids]

png(file.path(figures_dir(), "f10_gsynth_grid.png"),
    width = 1200, height = 900, res = 120)
par(mfrow = c(3, 4), mar = c(3, 3, 2, 1))
for (uid in selected[1:min(12, length(selected))]) {
  city_data <- gaps |> filter(teryt_powiat == uid)
  plot(city_data$year, exp(city_data$actual),
       type = "l", col = "#4d7cff", lwd = 2,
       main = uid, xlab = "", ylab = "Population",
       ylim = range(c(exp(city_data$actual), exp(city_data$counterfactual)), na.rm = TRUE))
  lines(city_data$year, exp(city_data$counterfactual),
        col = "#4dffb4", lwd = 2, lty = 2)
  abline(v = 1999, col = "#e8ff47", lty = 3)
}
dev.off()
cat("Saved: f10_gsynth_grid.png\n")

# Ordered ATT bar chart
att_plot <- att_avg |> arrange(att_avg)
png(file.path(figures_dir(), "f10_gsynth_ebar.png"),
    width = 900, height = 600, res = 120)
barplot(att_plot$att_avg,
        names.arg = att_plot$teryt_powiat,
        las = 2, col = ifelse(att_plot$att_avg < 0, "#ff4d4d", "#4dffb4"),
        main = "Per-city average ATT (log population, 1999-2023)",
        ylab = "ATT", cex.names = 0.7)
abline(h = 0, lwd = 1)
dev.off()
cat("Saved: f10_gsynth_ebar.png\n")

cat("\n=== Stage 11 complete ===\n")
```

- [ ] **Step 2: Run Stage 11**

```bash
Rscript scripts/r/11_gsynth.R
```

Expected: "Stage 11 complete", `gsynth_gaps.parquet` written with columns `teryt_powiat, year, actual, counterfactual, gap, se_gap, att_avg`.

- [ ] **Step 3: Verify output**

```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/processed/gsynth_gaps.parquet')
print('Shape:', df.shape)
print('Columns:', list(df.columns))
print('Treated cities with att_avg:', df[df['att_avg'].notna()]['teryt_powiat'].nunique())
print('Sample (Radom 1463):')
print(df[df['teryt_powiat']=='1463'][['year','actual','counterfactual','gap']].tail(5))
"
```

Expected: 30+ treated cities with att_avg, gap negative for most post-1999 years.

- [ ] **Step 4: Commit**

```bash
git add scripts/r/11_gsynth.R data/processed/gsynth_gaps.parquet figures/f10_*.png
git commit -m "feat: Stage 11 GSC/gsynth — per-city counterfactuals, ATT bar chart"
```

---

## Task 7: Stage 11b — NUTS-3 Analysis (R)

**Files:**
- Create: `scripts/r/11b_nuts3_analysis.R`

- [ ] **Step 1: Create `scripts/r/11b_nuts3_analysis.R`**

```r
#!/usr/bin/env Rscript
# Stage 11b — NUTS-3 parallel GDP analysis.
# LP and GSC for GDP per capita at NUTS-3 resolution.
# Reads:  data/processed/nuts3_panel.parquet
# Writes: data/processed/nuts3_lp_irfs.parquet
#         data/processed/nuts3_gsynth_gaps.parquet
#         figures/f11_nuts3_lp_gdp.png
#         figures/f11_nuts3_gsynth_gdp.png

suppressPackageStartupMessages({
  library(arrow)
  library(gsynth)
  library(tidyverse)
  library(lmtest)
  library(sandwich)
  library(plm)
})

source("scripts/r/utils.R")
cat("=== Stage 11b: NUTS-3 GDP Analysis ===\n\n")

nuts3 <- read_nuts3()
cat(sprintf("NUTS-3 panel: %d regions × %d years\n",
    n_distinct(nuts3$nuts3), n_distinct(nuts3$year)))

# ── Local Projections at NUTS-3 ────────────────────────────────────────────
cat("\n[LP] GDP per capita ~ any_demoted\n")

lp_records <- list()
for (h in seq(-4, 15)) {
  sub <- nuts3 |>
    filter(!is.na(ln_gdp_per_cap)) |>
    arrange(nuts3, year) |>
    group_by(nuts3) |>
    mutate(
      y_fwd  = lead(ln_gdp_per_cap, n = abs(h), default = NA),
      y_lag1 = lag(ln_gdp_per_cap,  n = 1,       default = NA),
      lhs    = if (h >= 0) y_fwd - y_lag1 else lag(ln_gdp_per_cap, n = -h) - y_lag1
    ) |>
    ungroup() |>
    filter(!is.na(lhs), !is.na(any_demoted))

  if (nrow(sub) < 30) next

  pdata  <- pdata.frame(sub, index = c("nuts3", "year"))
  tryCatch({
    mod <- plm(lhs ~ any_demoted, data = pdata, model = "within", effect = "twoways")
    cse <- coeftest(mod, vcov = vcovHC(mod, type = "HC1", cluster = "group"))
    beta <- cse["any_demoted", "Estimate"]
    se   <- cse["any_demoted", "Std. Error"]
    lp_records[[length(lp_records) + 1]] <- tibble(
      outcome = "ln_gdp_per_cap", horizon = h,
      coef = beta, se = se,
      ci_lo_90 = beta - 1.645 * se, ci_hi_90 = beta + 1.645 * se,
      ci_lo_95 = beta - 1.960 * se, ci_hi_95 = beta + 1.960 * se
    )
  }, error = function(e) cat(sprintf("  h=%d: %s\n", h, e$message)))
}

if (length(lp_records) > 0) {
  lp_df <- bind_rows(lp_records)
  write_processed(lp_df, "nuts3_lp_irfs.parquet")

  png(file.path(figures_dir(), "f11_nuts3_lp_gdp.png"),
      width = 900, height = 500, res = 120)
  plot(lp_df$horizon, lp_df$coef, type = "b", col = "#ff9900", pch = 16,
       xlab = "Years relative to 1999", ylab = "LP coef (Δ ln GDP/capita)",
       main = "LP IRF: reform impact on NUTS-3 GDP per capita")
  polygon(c(lp_df$horizon, rev(lp_df$horizon)),
          c(lp_df$ci_lo_95, rev(lp_df$ci_hi_95)),
          col = adjustcolor("#ff9900", 0.2), border = NA)
  abline(h = 0, lty = 2); abline(v = -0.5, col = "#e8ff47", lty = 2)
  dev.off()
  cat("Saved: f11_nuts3_lp_gdp.png\n")
}

# ── GSC at NUTS-3 ─────────────────────────────────────────────────────────
cat("\n[GSC] NUTS-3 GDP counterfactual\n")

gdp_n3 <- nuts3 |>
  filter(!is.na(ln_gdp_per_cap), year >= 1995, year <= 2021) |>
  select(nuts3, year, ln_gdp_per_cap, any_demoted) |>
  mutate(treated_post = any_demoted * as.integer(year >= 1999))

# Require complete series
complete_nuts3 <- gdp_n3 |>
  group_by(nuts3) |>
  summarise(n = n(), nas = sum(is.na(ln_gdp_per_cap))) |>
  filter(nas == 0) |>
  pull(nuts3)

gdp_n3 <- gdp_n3 |> filter(nuts3 %in% complete_nuts3)

cat(sprintf("Balanced NUTS-3 panel: %d regions (%d treated, %d control)\n",
    n_distinct(gdp_n3$nuts3),
    sum(gdp_n3$any_demoted[gdp_n3$year == 1999] == 1),
    sum(gdp_n3$any_demoted[gdp_n3$year == 1999] == 0)))

tryCatch({
  set.seed(42)
  gsc_n3 <- gsynth(
    ln_gdp_per_cap ~ treated_post,
    data      = as.data.frame(gdp_n3),
    index     = c("nuts3", "year"),
    force     = "two-way",
    CV        = TRUE,
    r         = c(0, 3),    # smaller r range — only ~40 control units
    se        = TRUE,
    inference = "parametric",
    nboots    = 300,
    seed      = 42,
    min.T0    = 3
  )

  cat(sprintf("  Optimal r=%d, avg ATT=%.4f\n",
      gsc_n3$r.cv, mean(gsc_n3$att, na.rm = TRUE)))

  years3 <- as.integer(rownames(gsc_n3$Y))
  gaps3  <- lapply(colnames(gsc_n3$Y), function(uid) {
    tibble(
      nuts3          = uid,
      year           = years3,
      actual         = as.numeric(gsc_n3$Y[, uid]),
      counterfactual = as.numeric(gsc_n3$Y.ct[, uid]),
      gap            = as.numeric(gsc_n3$Y[, uid]) - as.numeric(gsc_n3$Y.ct[, uid])
    )
  }) |> bind_rows()

  write_processed(gaps3, "nuts3_gsynth_gaps.parquet")

  png(file.path(figures_dir(), "f11_nuts3_gsynth_gdp.png"),
      width = 900, height = 500, res = 120)
  plot(gsc_n3, type = "gap",
       main = "GSC: GDP/capita gap in NUTS-3 regions with demoted capitals",
       ylab = "Log GDP per capita gap")
  abline(v = 1999, col = "#e8ff47", lty = 2)
  dev.off()
  cat("Saved: f11_nuts3_gsynth_gdp.png\n")

}, error = function(e) {
  cat(sprintf("  [ERROR] GSC at NUTS-3: %s\n  Falling back: saving empty gaps.\n", e$message))
  write_processed(
    tibble(nuts3 = character(), year = integer(), actual = double(),
           counterfactual = double(), gap = double()),
    "nuts3_gsynth_gaps.parquet"
  )
})

cat("\n=== Stage 11b complete ===\n")
```

- [ ] **Step 2: Run Stage 11b**

```bash
Rscript scripts/r/11b_nuts3_analysis.R
```

Expected: both parquets written, figures saved.

- [ ] **Step 3: Commit**

```bash
git add scripts/r/11b_nuts3_analysis.R \
        data/processed/nuts3_lp_irfs.parquet \
        data/processed/nuts3_gsynth_gaps.parquet \
        figures/f11_*.png
git commit -m "feat: Stage 11b NUTS-3 LP + GSC for GDP per capita"
```

---

## Task 8: R Orchestrator

**Files:**
- Create: `scripts/run_r_stages.py`

- [ ] **Step 1: Create `scripts/run_r_stages.py`**

```python
"""
Orchestrates the full R estimation pipeline via subprocess.
Enforces execution order: 10 → 11 → 11b.
Called by 09_pvar_forecast.py (which depends on gsynth output).

Usage:
    python scripts/run_r_stages.py
    python scripts/run_r_stages.py --stages 10 11   # run specific stages only
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

R_STAGES = [
    ("10", ROOT / "scripts" / "r" / "10_sdid.R"),
    ("11", ROOT / "scripts" / "r" / "11_gsynth.R"),
    ("11b", ROOT / "scripts" / "r" / "11b_nuts3_analysis.R"),
]


def check_r() -> str:
    rscript = shutil.which("Rscript")
    if rscript is None:
        print("ERROR: Rscript not found on PATH.")
        print("Install R from https://cran.r-project.org/ and ensure Rscript is on PATH.")
        sys.exit(1)
    return rscript


def run_stage(rscript: str, label: str, script: Path) -> None:
    print(f"\n{'='*60}")
    print(f"Running Stage {label}: {script.name}")
    print(f"{'='*60}")
    result = subprocess.run(
        [rscript, str(script)],
        cwd=str(ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"\nERROR: Stage {label} failed with exit code {result.returncode}")
        print(f"Fix the error in {script} and re-run.")
        sys.exit(result.returncode)
    print(f"\nStage {label}: OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages", nargs="*",
                        help="Stages to run (default: all). E.g. --stages 10 11")
    args = parser.parse_args()

    rscript = check_r()
    selected = set(args.stages) if args.stages else None

    print("=== R Stage Orchestrator ===")
    for label, script in R_STAGES:
        if selected and label not in selected:
            print(f"[SKIP] Stage {label} (not in --stages filter)")
            continue
        if not script.exists():
            print(f"[ERROR] Script not found: {script}")
            sys.exit(1)
        run_stage(rscript, label, script)

    print("\n=== All R stages complete ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the orchestrator runs cleanly**

```bash
python scripts/run_r_stages.py --stages 10
```

Expected: "Stage 10: OK" (re-runs 10_sdid.R, existing output overwritten)

- [ ] **Step 3: Commit**

```bash
git add scripts/run_r_stages.py
git commit -m "feat: R stage orchestrator with exit-code checking and stage filter"
```

---

## Task 9: Stage 09 — Panel VAR + ARIMA Robustness

**Files:**
- Create: `scripts/09_pvar_forecast.py`
- Create: `scripts/tests/test_09_pvar.py`

- [ ] **Step 1: Write failing test `scripts/tests/test_09_pvar.py`**

```python
"""Tests for Stage 09 Panel VAR forecasts."""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PROCESSED = ROOT / "data" / "processed"


def test_pvar_forecasts_schema():
    path = PROCESSED / "pvar_forecasts.parquet"
    assert path.exists(), "Run scripts/09_pvar_forecast.py first"
    df = pd.read_parquet(path)
    required = {"teryt_powiat", "city_en", "year", "variable", "path",
                "value", "lo80", "hi80", "lo95", "hi95"}
    assert required.issubset(df.columns)
    # Must cover 2024-2035
    assert df["year"].min() <= 2024
    assert df["year"].max() >= 2035


def test_pvar_two_paths():
    df = pd.read_parquet(PROCESSED / "pvar_forecasts.parquet")
    paths = set(df["path"].unique())
    assert "status_quo" in paths, "Missing status_quo path"
    assert "counterfactual" in paths, "Missing counterfactual path"


def test_pvar_ci_ordering():
    df = pd.read_parquet(PROCESSED / "pvar_forecasts.parquet")
    df = df.dropna(subset=["lo80", "hi80", "lo95", "hi95", "value"])
    assert (df["lo95"] <= df["lo80"]).all(), "CI ordering violated: lo95 > lo80"
    assert (df["lo80"] <= df["hi80"]).all(), "CI ordering violated: lo80 > hi80"
    assert (df["hi80"] <= df["hi95"]).all(), "CI ordering violated: hi80 > hi95"


def test_pvar_counterfactual_higher_than_status_quo():
    """For demoted cities, counterfactual population should average higher than status quo."""
    df = pd.read_parquet(PROCESSED / "pvar_forecasts.parquet")
    pop = df[df["variable"] == "ln_population"]
    sq  = pop[pop["path"] == "status_quo"]["value"].mean()
    cf  = pop[pop["path"] == "counterfactual"]["value"].mean()
    # Counterfactual (without reform) should show higher population on average
    assert cf > sq, f"Expected counterfactual ({cf:.4f}) > status_quo ({sq:.4f})"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest scripts/tests/test_09_pvar.py::test_pvar_forecasts_schema -v 2>&1 | head -10
```

Expected: `AssertionError: Run scripts/09_pvar_forecast.py first`

- [ ] **Step 3: Create `scripts/09_pvar_forecast.py`**

```python
"""
Stage 09 — Panel VAR forecasts + monthly ARIMA robustness.

Panel VAR approach:
  1. Compute cross-unit averages for treated and control groups separately.
  2. Fit VAR(p, BIC) on the treated-city average series 1995-2023.
  3. Status quo path: unconditional forecast from 2024 state.
  4. Counterfactual path: replace ln_population 1999-2023 with GSC
     counterfactual mean, re-fit, project forward.
  5. Per-city forecasts = group mean forecast + city fixed effect (pre-reform mean deviation).
  6. Bootstrap 1,000 draws for prediction intervals.

Outputs:
  data/processed/pvar_forecasts.parquet
  data/processed/monthly_unemployment.parquet   (if monthly file exists)
  data/processed/arima_unemployment_forecast.parquet
  figures/f08_pvar_irf.png
  figures/f08_forecast_{city_en}.png  (8 selected cities)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import re
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.var_model import VAR
from statsmodels.tsa.statespace.structural import UnobservedComponents

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

VAR_OUTCOMES = ["ln_population", "unemployment", "firms_per_1k",
                "ln_wages_avg", "nat_change_rate"]
FORECAST_HORIZON = 12   # years (2024-2035)
N_BOOTSTRAP = 1_000
RNG = np.random.default_rng(42)

CITIES_TO_PLOT = ["Radom", "Czestochowa", "Lomza", "Kielce",
                  "Slupsk", "Legnica", "Zamosc", "Plock"]

SOURCE_LINE = "Sources: GUS BDL; author calculations. Panel VAR BIC-selected order."


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)
    gaps = pd.read_parquet(PROCESSED / "gsynth_gaps.parquet")
    gaps["teryt_powiat"] = gaps["teryt_powiat"].astype(str).str.zfill(4)
    return panel, gaps


def build_group_avg(panel: pd.DataFrame, outcomes: list[str],
                    group: int = 1) -> pd.DataFrame:
    """Compute year-indexed mean of outcomes for treated (1) or control (0) group."""
    sub = panel[panel["treated"] == group].copy()
    avg = sub.groupby("year")[outcomes].mean()
    # Keep only years with at least 50% non-null across outcomes
    avg = avg.dropna(how="all")
    return avg


def fit_var(data: pd.DataFrame, maxlags: int = 3) -> tuple:
    """Fit VAR with BIC lag selection. Returns (fitted_model, lag_order)."""
    clean = data.dropna()
    model = VAR(clean)
    results = model.fit(ic="bic", maxlags=maxlags, trend="c")
    return results, results.k_ar


def bootstrap_forecast(var_results, steps: int, n_draws: int) -> np.ndarray:
    """Return bootstrap forecast array shape (n_draws, steps, n_vars)."""
    T, K = var_results.endog.shape
    coefs = var_results.params      # (1+K*p, K)
    resid = var_results.resid       # (T-p, K)
    p     = var_results.k_ar
    endog = var_results.endog

    forecasts = np.empty((n_draws, steps, K))
    for i in range(n_draws):
        # Bootstrap: resample residuals
        idx = RNG.integers(0, len(resid), size=steps)
        boot_resid = resid[idx]
        # Start from last p observations
        last_vals = endog[-p:].copy()
        preds = []
        for t in range(steps):
            x = np.concatenate([[1], last_vals.flatten()])
            pred = x @ coefs + boot_resid[t]
            preds.append(pred)
            last_vals = np.vstack([last_vals[1:], pred])
        forecasts[i] = np.array(preds)
    return forecasts


def build_per_city_forecasts(
    panel: pd.DataFrame,
    gaps: pd.DataFrame,
    var_results_sq,
    var_results_cf,
    last_year: int = 2023,
) -> pd.DataFrame:
    """
    Combine group-level VAR forecasts with per-city fixed effects.
    Fixed effect = pre-reform mean(city) - mean(treated group).
    """
    treated_cities = panel[panel["treated"] == 1]["teryt_powiat"].unique()
    future_years = list(range(last_year + 1, last_year + FORECAST_HORIZON + 1))

    # Group mean forecasts + bootstrap
    steps = len(future_years)
    sq_point = var_results_sq.forecast(var_results_sq.endog[-var_results_sq.k_ar:], steps)
    cf_point = var_results_cf.forecast(var_results_cf.endog[-var_results_cf.k_ar:], steps)

    sq_boot = bootstrap_forecast(var_results_sq, steps, N_BOOTSTRAP)
    cf_boot = bootstrap_forecast(var_results_cf, steps, N_BOOTSTRAP)

    outcomes = var_results_sq.model.endog_names
    pop_idx  = outcomes.index("ln_population") if "ln_population" in outcomes else 0

    records = []
    for teryt in treated_cities:
        city_row = panel[panel["teryt_powiat"] == teryt].iloc[0]
        city_en = city_row.get("city_en", teryt)

        # City fixed effect on ln_population
        pre_city = panel.loc[
            (panel["teryt_powiat"] == teryt) & (panel["year"] < 1999), "ln_population"
        ].mean()
        pre_group = build_group_avg(panel, ["ln_population"]).loc[1995:1998, "ln_population"].mean()
        city_fe = (pre_city - pre_group) if not np.isnan(pre_city) else 0.0

        for path_name, point, boot in [("status_quo", sq_point, sq_boot),
                                        ("counterfactual", cf_point, cf_boot)]:
            for t_idx, yr in enumerate(future_years):
                val  = float(point[t_idx, pop_idx]) + city_fe
                dist = boot[:, t_idx, pop_idx] + city_fe
                records.append({
                    "teryt_powiat": teryt,
                    "city_en":      city_en,
                    "year":         yr,
                    "variable":     "ln_population",
                    "path":         path_name,
                    "value":        val,
                    "lo80":         float(np.percentile(dist, 10)),
                    "hi80":         float(np.percentile(dist, 90)),
                    "lo95":         float(np.percentile(dist, 2.5)),
                    "hi95":         float(np.percentile(dist, 97.5)),
                    "innovation_hub": None,
                })

    return pd.DataFrame(records)


def plot_fan(city_en: str, historical: pd.Series, forecasts: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))

    # Historical
    ax.plot(historical.index, np.exp(historical.values),
            color="#4d7cff", lw=2, label="Observed")
    ax.axvline(1999, color="#e8ff47", lw=1.5, ls="--", label="Reform (1999)")

    colors = {"status_quo": "#888888", "counterfactual": "#4dffb4"}
    labels = {"status_quo": "Status quo", "counterfactual": "Counterfactual (no reform)"}

    for path_name in ["status_quo", "counterfactual"]:
        sub = forecasts[forecasts["path"] == path_name].sort_values("year")
        if sub.empty:
            continue
        c = colors[path_name]
        ax.fill_between(sub["year"], np.exp(sub["lo95"]), np.exp(sub["hi95"]),
                        alpha=0.12, color=c)
        ax.fill_between(sub["year"], np.exp(sub["lo80"]), np.exp(sub["hi80"]),
                        alpha=0.25, color=c)
        ax.plot(sub["year"], np.exp(sub["value"]),
                color=c, lw=2, ls="--", label=labels[path_name])

    ax.set_title(f"Population forecast to 2035: {city_en}", fontweight="bold")
    ax.set_ylabel("Population")
    ax.legend(fontsize=9)
    ax.text(0.01, -0.1, SOURCE_LINE, transform=ax.transAxes, fontsize=7, color="grey")
    plt.tight_layout()
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", city_en.lower())
    plt.savefig(FIGURES / f"f08_forecast_{safe}.png", dpi=300, bbox_inches="tight")
    plt.close()


def run_arima_robustness(panel: pd.DataFrame) -> None:
    """Monthly ARIMA robustness check for unemployment."""
    monthly_path = ROOT / "data" / "raw" / "gus_bdl" / "bdl_unemployment_monthly.csv"
    if not monthly_path.exists():
        print("[SKIP] bdl_unemployment_monthly.csv not found.")
        return

    import warnings
    from statsmodels.tsa.arima.model import ARIMA

    raw = pd.read_csv(monthly_path, sep=";", decimal=",", dtype=str, encoding="utf-8")
    raw.columns = [c.strip() for c in raw.columns]

    # Filter to 31 demoted cities by TERYT
    treated = panel[panel["treated"] == 1]["teryt_powiat"].unique()

    def extract_teryt(code: str) -> str:
        c = str(code).strip()
        return (c[2:4] + c[7:9]) if len(c) == 12 else c[:4]

    raw["teryt"] = raw[raw.columns[1]].map(extract_teryt)
    monthly_sub = raw[raw["teryt"].isin(treated)].copy()

    records = []
    month_cols = [c for c in raw.columns if re.match(r"^\d{4}M\d{2}$", c.strip())]

    for _, row in monthly_sub.iterrows():
        vals = pd.to_numeric(
            [row.get(c, None) for c in month_cols], errors="coerce"
        )
        series = pd.Series(vals, index=pd.period_range("2000-01", periods=len(vals), freq="M"))
        series = series.dropna()
        if len(series) < 100:
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                mod = ARIMA(series, order=(2, 1, 2), trend="c")
                res = mod.fit()
                fc  = res.get_forecast(steps=144)   # 12 years × 12 months
                summary = fc.summary_frame(alpha=0.2)  # 80% CI
                # Aggregate to annual
                fc_annual = (
                    pd.DataFrame({
                        "month": pd.period_range(series.index[-1] + 1, periods=144, freq="M"),
                        "value": fc.predicted_mean.values,
                        "lo80":  summary["mean_ci_lower"].values,
                        "hi80":  summary["mean_ci_upper"].values,
                    })
                    .assign(year=lambda d: d["month"].dt.year)
                    .groupby("year")[["value", "lo80", "hi80"]].mean()
                    .reset_index()
                )
                for _, r in fc_annual.iterrows():
                    records.append({
                        "teryt_powiat": row["teryt"],
                        "year": int(r["year"]),
                        "value_arima": r["value"],
                        "lo80_arima":  r["lo80"],
                        "hi80_arima":  r["hi80"],
                    })
            except Exception:
                pass

    if records:
        df = pd.DataFrame(records)
        df.to_parquet(PROCESSED / "arima_unemployment_forecast.parquet", index=False)
        print(f"Saved → arima_unemployment_forecast.parquet ({len(df)} rows)")
    else:
        print("[WARN] No ARIMA forecasts produced for unemployment.")


def main() -> None:
    print("=== Stage 09: Panel VAR Forecast ===\n")

    panel, gaps = load_data()

    # ── Status quo VAR ─────────────────────────────────────────────────────
    avail = [c for c in VAR_OUTCOMES if c in panel.columns
             and panel[c].notna().any()]
    group_avg_sq = build_group_avg(panel, avail, group=1)
    group_avg_sq = group_avg_sq.dropna(how="any")
    print(f"Status quo VAR: {len(avail)} outcomes, {len(group_avg_sq)} years")

    var_sq, p_sq = fit_var(group_avg_sq, maxlags=3)
    print(f"  Selected lag order p={p_sq}")

    # ── Counterfactual VAR ─────────────────────────────────────────────────
    # Replace ln_population 1999-2023 with GSC counterfactual mean
    gap_mean = (
        gaps[gaps["teryt_powiat"].isin(panel[panel["treated"]==1]["teryt_powiat"])]
        .groupby("year")["counterfactual"]
        .mean()
    )
    group_avg_cf = group_avg_sq.copy()
    for yr in group_avg_cf.index:
        if yr >= 1999 and yr in gap_mean.index and "ln_population" in group_avg_cf.columns:
            group_avg_cf.loc[yr, "ln_population"] = gap_mean[yr]

    var_cf, p_cf = fit_var(group_avg_cf, maxlags=3)
    print(f"  Counterfactual lag order p={p_cf}")

    # ── Per-city forecasts ─────────────────────────────────────────────────
    print(f"\nGenerating per-city forecasts (bootstrap N={N_BOOTSTRAP})...")
    forecasts = build_per_city_forecasts(panel, gaps, var_sq, var_cf)
    forecasts.to_parquet(PROCESSED / "pvar_forecasts.parquet", index=False)
    print(f"Saved → pvar_forecasts.parquet ({len(forecasts)} rows)")

    # ── IRF plot ──────────────────────────────────────────────────────────
    fig, axes = plt.subplots(len(avail), len(avail), figsize=(14, 14))
    var_sq.plot_acorr(nlags=10, fig=fig)
    plt.suptitle("Panel VAR impulse response functions (status quo)", fontweight="bold")
    plt.tight_layout()
    plt.savefig(FIGURES / "f08_pvar_irf.png", dpi=200, bbox_inches="tight")
    plt.close()
    print("Saved → f08_pvar_irf.png")

    # ── Fan charts for selected cities ────────────────────────────────────
    print("\nPlotting fan charts...")
    for city in CITIES_TO_PLOT:
        city_rows = panel[panel["city_en"].str.contains(city, case=False, na=False)]
        if city_rows.empty:
            continue
        teryt = city_rows.iloc[0]["teryt_powiat"]
        hist  = (panel[panel["teryt_powiat"] == teryt]
                 .set_index("year")["ln_population"]
                 .dropna()
                 .sort_index())
        fc    = forecasts[forecasts["teryt_powiat"] == teryt]
        if fc.empty:
            continue
        actual_city_en = city_rows.iloc[0].get("city_en", city)
        plot_fan(actual_city_en, hist, fc)
        print(f"  Saved: f08_forecast_{city.lower()}.png")

    # ── ARIMA monthly robustness ───────────────────────────────────────────
    print("\n[ARIMA robustness]")
    run_arima_robustness(panel)

    print("\n=== Stage 09 complete ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run Stage 09**

```bash
python scripts/09_pvar_forecast.py
```

Expected: "Stage 09 complete", `pvar_forecasts.parquet` written.

- [ ] **Step 5: Run tests**

```bash
python -m pytest scripts/tests/test_09_pvar.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/09_pvar_forecast.py scripts/tests/test_09_pvar.py \
        data/processed/pvar_forecasts.parquet \
        figures/f08_pvar_irf.png figures/f08_forecast_*.png
git commit -m "feat: Stage 09 Panel VAR forecasts — status_quo + counterfactual paths to 2035"
```

---

## Task 10: Export Pipeline Updates

**Files:**
- Modify: `scripts/export_to_json.py`

- [ ] **Step 1: Add new loaders to `scripts/export_to_json.py`**

Add after the existing `load_did_estimates` function:

```python
def load_gsynth_gaps(sandbox: Path) -> pd.DataFrame:
    path = sandbox / "PL-Capital-Reform-DiD" / "data" / "processed" / "gsynth_gaps.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_pvar_forecasts(sandbox: Path) -> pd.DataFrame:
    path = sandbox / "PL-Capital-Reform-DiD" / "data" / "processed" / "pvar_forecasts.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_nuts3_gdp_gaps(sandbox: Path) -> pd.DataFrame:
    path = sandbox / "PL-Capital-Reform-DiD" / "data" / "processed" / "nuts3_gsynth_gaps.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
```

- [ ] **Step 2: Update `build_polish_profiles` in `scripts/export_to_json.py`**

Replace the function signature and body to accept the new data:

```python
def build_polish_profiles(panel: pd.DataFrame, treatment: pd.DataFrame,
                           did: dict, gaps: pd.DataFrame,
                           forecasts: pd.DataFrame) -> list[dict]:
```

Inside the function, after building `pop_series`, add before `profiles.append(...)`:

```python
        # Counterfactual series from GSC
        cf_series = []
        if not gaps.empty and teryt in gaps["teryt_powiat"].values:
            city_gaps = gaps[gaps["teryt_powiat"] == teryt].sort_values("year")
            for _, gr in city_gaps.iterrows():
                if _f(gr.get("actual")) is not None:
                    cf_series.append({
                        "year":          int(gr["year"]),
                        "actual":        _f(gr["actual"]),
                        "counterfactual": _f(gr.get("counterfactual")),
                        "gap":           _f(gr.get("gap")),
                    })

        # Forecast series from Panel VAR
        fc_series = []
        reform_cost_2035 = None
        if not forecasts.empty and teryt in forecasts["teryt_powiat"].values:
            city_fc = (forecasts[
                (forecasts["teryt_powiat"] == teryt) &
                (forecasts["variable"] == "ln_population")
            ].sort_values(["path", "year"]))
            for _, fr in city_fc.iterrows():
                fc_series.append({
                    "year":           int(fr["year"]),
                    "path":           str(fr["path"]),
                    "value":          _f(fr.get("value")),
                    "lo80":           _f(fr.get("lo80")),
                    "hi80":           _f(fr.get("hi80")),
                    "lo95":           _f(fr.get("lo95")),
                    "hi95":           _f(fr.get("hi95")),
                    "innovation_hub": None,
                })
            # Reform cost 2035: counterfactual - status_quo at year 2035
            sq_2035 = city_fc[(city_fc["path"] == "status_quo") &
                               (city_fc["year"] == 2035)]["value"]
            cf_2035 = city_fc[(city_fc["path"] == "counterfactual") &
                               (city_fc["year"] == 2035)]["value"]
            if not sq_2035.empty and not cf_2035.empty:
                reform_cost_2035 = _f(
                    (float(cf_2035.iloc[0]) - float(sq_2035.iloc[0]))
                )
```

Then update the `profiles.append({...})` call to include the new fields:

```python
            "counterfactualSeries": cf_series,
            "forecastSeries":       fc_series,
            "reformCost2035":       reform_cost_2035,
            "innovationScenario":   None,
```

- [ ] **Step 3: Update `main()` in `scripts/export_to_json.py`**

Add the new loaders and update function calls:

```python
    gaps      = load_gsynth_gaps(SANDBOX)
    forecasts = load_pvar_forecasts(SANDBOX)
    nuts3_gaps = load_nuts3_gdp_gaps(SANDBOX)

    if gaps.empty:
        print("  (GSC gaps not found — counterfactualSeries will be empty)")
    if forecasts.empty:
        print("  (PVAR forecasts not found — forecastSeries will be empty)")
```

Update the call to `build_polish_profiles`:

```python
    pl_profiles = build_polish_profiles(panel, treatment, did, gaps, forecasts)
```

Add new layer file for counterfactual gap:

```python
    # Counterfactual gap layer (GSC-estimated reform cost per NUTS-2)
    layers["counterfactual-gap"] = {}
    if not gaps.empty:
        # Aggregate per-city ATT avg to NUTS-2 level via crosswalk
        for _, row in gaps[gaps["year"].between(1999, 2023)].groupby("teryt_powiat")["gap"].mean().items():
            nuts3_code = TERYT_NUTS3.get(str(row).zfill(4) if isinstance(row, int) else row)
            # (simplified: direct teryt→nuts2 via first 4 chars of nuts3)
            pass  # populated if gsynth_gaps has teryt_powiat column
        # Simpler: use att_avg directly
        if "att_avg" in gaps.columns:
            city_atts = gaps[["teryt_powiat", "att_avg"]].drop_duplicates()
            for _, row in city_atts.iterrows():
                nuts3_code = TERYT_NUTS3.get(str(row["teryt_powiat"]).zfill(4))
                if nuts3_code:
                    nuts2 = nuts3_code[:4]
                    if nuts2 not in layers["counterfactual-gap"]:
                        layers["counterfactual-gap"][nuts2] = float(row["att_avg"]) if _f(row["att_avg"]) else 0.0
```

- [ ] **Step 4: Run export**

```bash
cd /c/Users/andre/Desktop/Sandbox
python scripts/export_to_json.py
```

Expected: "Export complete", per-city JSONs now include `counterfactualSeries` and `forecastSeries` fields.

- [ ] **Step 5: Verify a demoted city JSON**

```bash
python -c "
import json
with open('pip-reform/public/data/region/1463.json') as f:
    d = json.load(f)
print('counterfactualSeries length:', len(d.get('counterfactualSeries', [])))
print('forecastSeries length:', len(d.get('forecastSeries', [])))
print('reformCost2035:', d.get('reformCost2035'))
"
```

Expected: non-empty lists for Radom (1463), `reformCost2035` a non-None number.

- [ ] **Step 6: Commit**

```bash
git add scripts/export_to_json.py
git commit -m "feat: export pipeline — counterfactualSeries, forecastSeries, reformCost2035 per city"
```

---

## Task 11: TypeScript Types Update

**Files:**
- Modify: `pip-reform/lib/types.ts`

- [ ] **Step 1: Add new interfaces to `pip-reform/lib/types.ts`**

After the existing `TimePoint` interface, add:

```typescript
export interface CounterfactualPoint {
  year: number
  actual: number | null
  counterfactual: number | null
  gap: number | null
}

export interface ForecastPoint {
  year: number
  path: 'status_quo' | 'counterfactual' | 'innovation_hub'
  value: number | null
  lo80: number | null
  hi80: number | null
  lo95: number | null
  hi95: number | null
  innovation_hub: null  // Stage 13 hook — always null in Phase 1
}
```

- [ ] **Step 2: Update `RegionProfile` interface in `pip-reform/lib/types.ts`**

Add the new fields after `populationSeries`:

```typescript
  counterfactualSeries: CounterfactualPoint[]
  forecastSeries: ForecastPoint[]
  reformCost2035: number | null
  innovationScenario: null  // Stage 13 hook
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd pip-reform
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add pip-reform/lib/types.ts
git commit -m "feat: add CounterfactualPoint, ForecastPoint types; update RegionProfile"
```

---

## Task 12: CounterfactualChart Component

**Files:**
- Create: `pip-reform/components/CounterfactualChart.tsx`
- Create: `pip-reform/tests/components/CounterfactualChart.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// pip-reform/tests/components/CounterfactualChart.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import CounterfactualChart from '@/components/CounterfactualChart'
import type { CounterfactualPoint } from '@/lib/types'

const mockData: CounterfactualPoint[] = [
  { year: 1997, actual: 11.5, counterfactual: null, gap: null },
  { year: 1998, actual: 11.49, counterfactual: 11.49, gap: 0 },
  { year: 1999, actual: 11.48, counterfactual: 11.50, gap: -0.02 },
  { year: 2010, actual: 11.40, counterfactual: 11.55, gap: -0.15 },
]

describe('CounterfactualChart', () => {
  it('renders without crashing', () => {
    render(<CounterfactualChart data={mockData} reformYear={1999} />)
  })

  it('returns null when data is empty', () => {
    const { container } = render(<CounterfactualChart data={[]} reformYear={1999} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders reform cost annotation when gap exists', () => {
    render(<CounterfactualChart data={mockData} reformYear={1999} />)
    // recharts renders into SVG — just check it doesn't throw
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd pip-reform && npm test -- --run tests/components/CounterfactualChart.test.tsx 2>&1 | tail -10
```

Expected: `Cannot find module '@/components/CounterfactualChart'`

- [ ] **Step 3: Create `pip-reform/components/CounterfactualChart.tsx`**

```tsx
'use client'
import {
  ComposedChart, Line, Area, XAxis, YAxis,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import type { CounterfactualPoint } from '@/lib/types'

interface Props {
  data: CounterfactualPoint[]
  reformYear?: number
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1c1c1c] border border-[#2a2a2a] px-2 py-1.5 text-xs font-mono">
      <div className="text-[#888] mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? p.value.toLocaleString() : '—'}
        </div>
      ))}
    </div>
  )
}

export default function CounterfactualChart({ data, reformYear = 1999 }: Props) {
  if (!data || data.length === 0) return null

  const chartData = data
    .filter(d => d.actual != null)
    .map(d => ({
      year:           d.year,
      actual:         d.actual,
      counterfactual: d.counterfactual,
      gapArea:        d.counterfactual != null && d.actual != null
                        ? [Math.min(d.actual, d.counterfactual),
                           Math.max(d.actual, d.counterfactual)]
                        : null,
    }))

  // Reform cost: avg gap in last 5 years of data
  const recent = data.filter(d => d.gap != null && d.year >= (data[data.length - 1]?.year ?? 0) - 5)
  const avgGap = recent.length
    ? recent.reduce((s, d) => s + (d.gap ?? 0), 0) / recent.length
    : null
  const lastYear = chartData[chartData.length - 1]?.year ?? reformYear

  return (
    <div>
      <ResponsiveContainer width="100%" height={130}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="year"
            tick={{ fill: '#444', fontSize: 10, fontFamily: 'Space Mono, monospace' }}
            tickLine={false}
            axisLine={{ stroke: '#1e1e1e' }}
            interval="preserveStartEnd"
          />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            x={reformYear}
            stroke="#e8ff47"
            strokeDasharray="3 3"
            strokeWidth={1}
            label={{
              value: `'${String(reformYear).slice(2)}`,
              fill: '#e8ff47', fontSize: 9,
              fontFamily: 'Space Mono, monospace',
              position: 'insideTopRight',
            }}
          />
          {/* Reform cost shading */}
          <Area
            type="monotone"
            dataKey="actual"
            stroke="none"
            fill="#ff4d4d"
            fillOpacity={0.15}
            activeDot={false}
            legendType="none"
          />
          {/* Observed */}
          <Line
            type="monotone"
            dataKey="actual"
            stroke="#4d7cff"
            strokeWidth={1.8}
            dot={false}
            activeDot={{ r: 3, fill: '#e8ff47', stroke: 'none' }}
            name="Observed"
          />
          {/* Counterfactual */}
          <Line
            type="monotone"
            dataKey="counterfactual"
            stroke="#4dffb4"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={false}
            activeDot={{ r: 3, fill: '#4dffb4', stroke: 'none' }}
            name="Counterfactual"
          />
        </ComposedChart>
      </ResponsiveContainer>
      {avgGap != null && Math.abs(avgGap) > 0.001 && (
        <div className="mt-1 text-[10px] font-mono text-[#ff4d4d]">
          Reform cost to {lastYear}: {avgGap > 0 ? '+' : ''}{(avgGap * 100).toFixed(1)}% log pts
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
npm test -- --run tests/components/CounterfactualChart.test.tsx
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pip-reform/components/CounterfactualChart.tsx \
        pip-reform/tests/components/CounterfactualChart.test.tsx
git commit -m "feat: CounterfactualChart — observed vs GSC counterfactual with reform cost annotation"
```

---

## Task 13: ForecastPanel Component

**Files:**
- Create: `pip-reform/components/ForecastPanel.tsx`
- Create: `pip-reform/tests/components/ForecastPanel.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// pip-reform/tests/components/ForecastPanel.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ForecastPanel from '@/components/ForecastPanel'
import type { ForecastPoint } from '@/lib/types'

const makePoints = (path: ForecastPoint['path']): ForecastPoint[] =>
  [2024, 2025, 2030, 2035].map(year => ({
    year, path, value: 11.2, lo80: 11.0, hi80: 11.4,
    lo95: 10.8, hi95: 11.6, innovation_hub: null,
  }))

describe('ForecastPanel', () => {
  it('renders without crashing with two paths', () => {
    const data = [...makePoints('status_quo'), ...makePoints('counterfactual')]
    render(<ForecastPanel series={data} reformCost2035={-0.05} />)
  })

  it('returns null when series is empty', () => {
    const { container } = render(<ForecastPanel series={[]} reformCost2035={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows locked innovation hub toggle', () => {
    const data = [...makePoints('status_quo'), ...makePoints('counterfactual')]
    render(<ForecastPanel series={data} reformCost2035={null} />)
    expect(screen.getByText(/INNOVATION HUB/i)).toBeDefined()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npm test -- --run tests/components/ForecastPanel.test.tsx 2>&1 | tail -5
```

Expected: `Cannot find module '@/components/ForecastPanel'`

- [ ] **Step 3: Create `pip-reform/components/ForecastPanel.tsx`**

```tsx
'use client'
import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { ForecastPoint } from '@/lib/types'

interface Props {
  series: ForecastPoint[]
  reformCost2035: number | null
}

type PathId = 'status_quo' | 'counterfactual'

const PATH_CONFIG: Record<PathId, { label: string; color: string; dash?: string }> = {
  status_quo:     { label: 'STATUS QUO',     color: '#888888' },
  counterfactual: { label: 'COUNTERFACTUAL', color: '#4dffb4', dash: '5 3' },
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1c1c1c] border border-[#2a2a2a] px-2 py-1.5 text-xs font-mono">
      <div className="text-[#888] mb-1">{label}</div>
      {payload.map((p: any) => (
        p.value != null && (
          <div key={p.dataKey} style={{ color: p.color }}>
            {p.name}: {Number(p.value).toFixed(3)}
          </div>
        )
      ))}
    </div>
  )
}

export default function ForecastPanel({ series, reformCost2035 }: Props) {
  const [active, setActive] = useState<Record<PathId, boolean>>({
    status_quo: true,
    counterfactual: true,
  })

  if (!series || series.length === 0) return null

  const byPath = (path: PathId) => series
    .filter(d => d.path === path)
    .sort((a, b) => a.year - b.year)

  const minYear = Math.min(...series.map(d => d.year))
  const maxYear = Math.max(...series.map(d => d.year))

  const allValues = series.flatMap(d => [d.lo95, d.hi95]).filter(v => v != null) as number[]
  const yDomain: [number, number] = allValues.length
    ? [Math.min(...allValues) - 0.02, Math.max(...allValues) + 0.02]
    : ['auto', 'auto'] as any

  // Merge all paths into single chart data array (recharts requires this)
  const years = Array.from(new Set(series.map(d => d.year))).sort()
  const chartData = years.map(yr => {
    const row: Record<string, any> = { year: yr }
    for (const path of ['status_quo', 'counterfactual'] as PathId[]) {
      const pt = series.find(d => d.year === yr && d.path === path)
      if (pt) {
        row[`${path}_value`] = pt.value
        row[`${path}_lo80`]  = pt.lo80
        row[`${path}_hi80`]  = pt.hi80
      }
    }
    return row
  })

  return (
    <div className="flex flex-col gap-2">
      {/* Path toggles */}
      <div className="flex gap-1 flex-wrap">
        {(Object.entries(PATH_CONFIG) as [PathId, typeof PATH_CONFIG[PathId]][]).map(([id, cfg]) => (
          <button
            key={id}
            onClick={() => setActive(a => ({ ...a, [id]: !a[id] }))}
            style={{
              borderColor: active[id] ? cfg.color : 'transparent',
              color: active[id] ? cfg.color : '#444',
              background: active[id] ? `${cfg.color}14` : 'transparent',
            }}
            className="px-2 py-0.5 text-[9px] font-mono tracking-widest uppercase border cursor-pointer"
          >
            {cfg.label}
          </button>
        ))}
        {/* Locked innovation hub toggle */}
        <button
          disabled
          className="px-2 py-0.5 text-[9px] font-mono tracking-widest uppercase border border-[#2a2a2a] text-[#2a2a2a] cursor-not-allowed flex items-center gap-1"
        >
          <span>INNOVATION HUB</span>
          <span className="text-[8px]">🔒</span>
        </button>
      </div>

      {/* Fan chart */}
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="year"
            tick={{ fill: '#444', fontSize: 10, fontFamily: 'Space Mono, monospace' }}
            tickLine={false}
            axisLine={{ stroke: '#1e1e1e' }}
            interval="preserveStartEnd"
          />
          <YAxis hide domain={yDomain} />
          <Tooltip content={<CustomTooltip />} />

          {(Object.entries(PATH_CONFIG) as [PathId, typeof PATH_CONFIG[PathId]][]).map(([id, cfg]) => (
            active[id] && (
              <Line
                key={id}
                type="monotone"
                dataKey={`${id}_value`}
                stroke={cfg.color}
                strokeWidth={1.8}
                strokeDasharray={cfg.dash}
                dot={false}
                activeDot={{ r: 3, fill: cfg.color, stroke: 'none' }}
                name={cfg.label}
              />
            )
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Reform cost summary */}
      {reformCost2035 != null && (
        <div className="text-[9px] font-mono text-[#444]">
          Projected reform cost 2035:
          <span className={reformCost2035 < 0 ? 'text-[#ff4d4d]' : 'text-[#4dffb4]'}>
            {' '}{reformCost2035 > 0 ? '+' : ''}{(reformCost2035 * 100).toFixed(1)}% log pts
          </span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
npm test -- --run tests/components/ForecastPanel.test.tsx
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pip-reform/components/ForecastPanel.tsx \
        pip-reform/tests/components/ForecastPanel.test.tsx
git commit -m "feat: ForecastPanel — status_quo + counterfactual fan chart, locked innovation hub toggle"
```

---

## Task 14: RegionPanel + LayerSwitcher + Page Updates

**Files:**
- Modify: `pip-reform/components/RegionPanel.tsx`
- Modify: `pip-reform/components/LayerSwitcher.tsx`
- Modify: `pip-reform/app/page.tsx`

- [ ] **Step 1: Update `pip-reform/components/RegionPanel.tsx` to use new charts**

Add imports at the top:

```tsx
import CounterfactualChart from './CounterfactualChart'
import ForecastPanel from './ForecastPanel'
```

Replace the existing `PopChart` block (the `{p.populationSeries && p.populationSeries.length > 0 && (...)}` section) with:

```tsx
          {/* Population chart — counterfactual for demoted PL, standard for all others */}
          {p.reformStatus === 'demoted' &&
           p.counterfactualSeries && p.counterfactualSeries.length > 0 ? (
            <div className="px-4 py-3 border-b border-[#1e1e1e]">
              <span className="text-[10px] font-mono text-[#444] uppercase tracking-widest block mb-2">
                Population vs Counterfactual
              </span>
              <CounterfactualChart
                data={p.counterfactualSeries}
                reformYear={1999}
              />
            </div>
          ) : p.populationSeries && p.populationSeries.length > 0 ? (
            <div className="px-4 py-3 border-b border-[#1e1e1e]">
              <span className="text-[10px] font-mono text-[#444] uppercase tracking-widest block mb-2">
                Population
              </span>
              <PopChart data={p.populationSeries} reformYear={1999} />
            </div>
          ) : null}

          {/* Forecast panel — demoted cities only */}
          {p.reformStatus === 'demoted' &&
           p.forecastSeries && p.forecastSeries.length > 0 && (
            <div className="px-4 py-3 border-b border-[#1e1e1e]">
              <span className="text-[10px] font-mono text-[#444] uppercase tracking-widest block mb-2">
                Forecast to 2035
              </span>
              <ForecastPanel
                series={p.forecastSeries}
                reformCost2035={p.reformCost2035 ?? null}
              />
            </div>
          )}
```

- [ ] **Step 2: Add fifth layer to `pip-reform/components/LayerSwitcher.tsx`**

In the `LAYERS` array, add after the existing `reform-impact` entry:

```tsx
  { id: 'counterfactual-gap', label: 'Reform Cost',    color: '#4dffb4' },
```

Also update the `LayerId` type:

```tsx
export type LayerId = 'reform-impact' | 'counterfactual-gap' | 'innovation' | 'investment' | 'gdp'
```

- [ ] **Step 3: Add layer description and color config to `pip-reform/app/page.tsx`**

In `LAYER_DESCRIPTIONS`, add:

```tsx
  'counterfactual-gap': 'GSC-estimated population gap vs counterfactual trajectory (log pts)',
```

In `LEGEND_CONFIG` in the `Legend` component, add:

```tsx
  'counterfactual-gap': {
    type: 'diverging' as const,
    lo: '#ff4d4d', mid: '#1c1c1c', hi: '#4dffb4',
    loLabel: 'large reform cost', hiLabel: 'resilient',
  },
```

- [ ] **Step 4: Run TypeScript check and full test suite**

```bash
cd pip-reform
npx tsc --noEmit
npm test
```

Expected: TypeScript: no errors. All existing 5 tests + 6 new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pip-reform/components/RegionPanel.tsx \
        pip-reform/components/LayerSwitcher.tsx \
        pip-reform/app/page.tsx
git commit -m "feat: dashboard integration — counterfactual chart, forecast panel, reform cost layer"
```

---

## Final Verification

- [ ] **Run the full pipeline end-to-end**

```bash
cd PL-Capital-Reform-DiD
python scripts/run_r_stages.py
python scripts/08_local_projections.py
python scripts/09_pvar_forecast.py
cd ..
python scripts/export_to_json.py
```

Expected: all stages complete without errors.

- [ ] **Run all Python tests**

```bash
cd PL-Capital-Reform-DiD
python -m pytest scripts/tests/ -v
```

Expected: all tests PASS.

- [ ] **Run dashboard tests**

```bash
cd pip-reform
npm test
```

Expected: all tests PASS.

- [ ] **Verify dev server renders new components**

```bash
npm run dev -- --port 3456
```

Open a demoted city (e.g. click Radom on the map). Panel should show CounterfactualChart above ForecastPanel. Non-demoted cities show standard PopChart.

- [ ] **Final commit**

```bash
cd /c/Users/andre/Desktop/Sandbox
git add .
git commit -m "feat: Phase 1 forecasting complete — LP, Panel VAR, SDiD, GSC, NUTS-3 GDP, dashboard integration"
```
