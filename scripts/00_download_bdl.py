"""
Stage 00 — Download GUS BDL data via public REST API.
Saves wide-format CSVs to data/raw/gus_bdl/ matching the format
expected by 01_ingest.py (semicolon-delimited, Polish headers, 7-digit TERYT).

GUS BDL API: https://bdl.stat.gov.pl/api/v1/
No authentication required for public indicators.
Rate limit: ~1 request/second recommended.

Run once; commit outputs to data/raw/gus_bdl/ as immutable raw data.
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "raw" / "gus_bdl"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://bdl.stat.gov.pl/api/v1"
HEADERS = {"Accept": "application/json"}
POWIAT_LEVEL = 5       # BDL unit-level for powiaty (confirmed: level 5 = 379 units)
PAGE_SIZE = 100        # max per BDL API page
SLEEP_SEC = 3.0        # polite rate limit — BDL throttles ~20 req/min
YEARS = list(range(1995, 2025))

# ---------------------------------------------------------------------------
# Variable IDs — all confirmed via API probe scripts (_probe*.py)
# All download via /data/by-variable/{id} at unit-level=5 (powiaty, N≈379)
# ---------------------------------------------------------------------------
VARIABLE_MAP: list[dict] = [
    # --- Demography ---
    {
        "filename": "bdl_population.csv",
        "var_id":   72305,
        "subject":  "P2137",
        "label":    "Ludność ogółem (total population)",
        "unit":     "osoba",
        "note":     "1995-2024. Used as primary outcome.",
    },
    {
        "filename": "bdl_migration_in.csv",
        "var_id":   396240,
        "subject":  "P3313",
        "label":    "Zameldowania z innych powiatów (arrivals)",
        "unit":     "osoba",
        "note":     "Inter-powiat arrivals for permanent stay.",
    },
    {
        "filename": "bdl_migration_out.csv",
        "var_id":   396241,
        "subject":  "P3313",
        "label":    "Wymeldowania do innych powiatów (departures)",
        "unit":     "osoba",
        "note":     "Inter-powiat departures; saldo computed in 03_crosswalk_merge.py.",
    },
    {
        "filename": "bdl_births.csv",
        "var_id":   59,
        "subject":  "P1873",
        "label":    "Urodzenia żywe ogółem (live births, both sexes)",
        "unit":     "osoba",
        "note":     "1995-2024. Numerator for birth rate; used for natural change analysis.",
    },
    {
        "filename": "bdl_deaths.csv",
        "var_id":   65,
        "subject":  "P1873",
        "label":    "Zgony ogółem (deaths, both sexes)",
        "unit":     "osoba",
        "note":     "1995-2024. Denominator complement for natural increase.",
    },
    # --- Labour market ---
    {
        "filename": "bdl_unemployment_rate.csv",
        "var_id":   60270,
        "subject":  "P2392",
        "label":    "Stopa bezrobocia rejestrowanego ogółem (%)",
        "unit":     "%",
        "note":     "2004-2025. Registered unemployment rate. Pre-2004 gap; use event times k≥5.",
    },
    # --- Enterprise activity ---
    {
        "filename": "bdl_regon_firms.csv",
        "var_id":   58903,
        "subject":  "P2315",
        "label":    "Podmioty wg klas wielkości — ogółem (REGON entities, all sizes)",
        "unit":     "-",
        "note":     "2002-2025. Total registered economic entities in REGON. Pre-2002 gap.",
    },
    # --- Income ---
    {
        "filename": "bdl_wages_avg.csv",
        "var_id":   64428,
        "subject":  "P2497",
        "label":    "Przeciętne miesięczne wynagrodzenie brutto (avg gross wage, PLN)",
        "unit":     "zł",
        "note":     "2002-2024. Nominal PLN; deflate with WDI CPI for real wages.",
    },
]

# Monthly series — BDL P3559 encodes each month as a *separate variable* with annual data.
# 12 variables × ~16 years = ~192 monthly columns when merged.
# Variable IDs confirmed via API probe: 461680–461691 = Jan–Dec stopa bezrobocia rejestrowanego.
MONTHLY_VARIABLE_MAP: list[dict] = [
    {
        "filename": "bdl_unemployment_monthly.csv",
        "var_ids": {
            "01": 461680,  # styczeń
            "02": 461681,  # luty
            "03": 461682,  # marzec
            "04": 461683,  # kwiecień
            "05": 461684,  # maj
            "06": 461685,  # czerwiec
            "07": 461686,  # lipiec
            "08": 461687,  # sierpień
            "09": 461688,  # wrzesień
            "10": 461689,  # październik
            "11": 461690,  # listopad
            "12": 461691,  # grudzień
        },
        "subject":  "P3559",
        "label":    "Stopa bezrobocia rejestrowanego (miesięczna, %)",
        "unit":     "%",
        "note":     "Monthly 2011-2026. BDL encodes each calendar-month as a separate variable. "
                    "Merged to wide format with columns YYYYMNN. ~192 monthly columns per unit. "
                    "Used for ARIMA robustness in Stage 09.",
    },
]


MANUAL_DOWNLOAD_INSTRUCTIONS = """
All variables now auto-downloaded via BDL API.
No manual portal downloads required.

1. STOPA BEZROBOCIA (unemployment rate %)
   Path: RYNEK PRACY / BEZROBOCIE REJESTROWANE / Stopa bezrobocia
   Level: POWIATY, Annual, typically 1999-2023
   Save as: data/raw/gus_bdl/bdl_unemployment_rate.csv

2. PODMIOTY REGON (firms registered in REGON)
   Path: PODMIOTY GOSPODARCZE / WPISANE DO REJESTRU REGON / ogołem
   Level: POWIATY, Annual, 1995-2023
   Save as: data/raw/gus_bdl/bdl_regon_firms.csv

3. PRZECIETNE WYNAGRODZENIE (average gross wages PLN)
   Path: WYNAGRODZENIA / WYNAGRODZENIA / Przecietne miesięczne wynagrodzenie brutto
   Level: POWIATY, Annual, available from ~2002
   Save as: data/raw/gus_bdl/bdl_wages_avg.csv

CSV format: semicolon (;) delimiter, comma (,) decimal separator.
Expected header: Jednostka terytorialna;Kod;1999;2000;...;2023
"""


def get_json(url: str, params: dict) -> dict:
    """GET with retry on transient errors and 429 backoff."""
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  429 rate limit — sleeping {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if attempt == 3:
                raise
            print(f"  HTTP error {e} — retry {attempt+1}/4")
            time.sleep(10)
    return {}


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------

def download_variable_all_pages(variable_id: int) -> list[dict]:
    """Download all units for a variable across all pages. Returns flat list of unit dicts."""
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
        # Add year filters
        for y in YEARS:
            params.setdefault("year", [])
            if isinstance(params["year"], list):
                params["year"].append(y)

        # requests handles list params as repeated keys
        data = get_json(f"{BASE_URL}/data/by-variable/{variable_id}", params)
        time.sleep(SLEEP_SEC)

        results = data.get("results", [])
        all_results.extend(results)

        total = data.get("totalRecords", 0)
        fetched = (page + 1) * PAGE_SIZE
        print(f"    Page {page}: {len(results)} units  (total declared: {total})")

        if fetched >= total or not results:
            break
        page += 1

    return all_results


def results_to_wide_csv(results: list[dict], out_path: Path) -> None:
    """Convert API results to BDL-style wide CSV (semicolon-delimited)."""
    all_years: set[int] = set()
    for unit in results:
        for v in unit.get("values", []):
            all_years.add(v["year"])
    sorted_years = sorted(all_years)

    rows = []
    for unit in results:
        year_val = {v["year"]: v.get("val") for v in unit.get("values", [])}
        row = {
            "Jednostka terytorialna": unit.get("name", ""),
            "Kod": unit.get("id", ""),
        }
        for y in sorted_years:
            val = year_val.get(y)
            row[str(y)] = str(val).replace(".", ",") if val is not None else ""
        rows.append(row)

    if not rows:
        print(f"    [WARN] No rows to write for {out_path.name}")
        return

    fieldnames = ["Jednostka terytorialna", "Kod"] + [str(y) for y in sorted_years]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"    Saved {len(rows)} rows → {out_path.name}")


# ---------------------------------------------------------------------------
# Monthly download (P3559: 12 separate per-month variables → one merged CSV)
# ---------------------------------------------------------------------------

def _fetch_all_pages(var_id: int) -> list[dict]:
    """Fetch all pages for a single variable at powiat level (no year filter)."""
    all_results: list[dict] = []
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
        print(f"      Page {page}: {len(results)} units  (total declared: {total})")
        if fetched >= total or not results:
            break
        page += 1
    return all_results


def download_monthly(spec: dict, out_path: Path) -> None:
    """Download all 12 per-month BDL variables and merge into one wide CSV.

    BDL P3559 encodes each calendar-month as a separate variable (461680–461691).
    Each variable returns annual data where the 'year' field is the calendar year
    and the value is the unemployment rate for that month of that year.
    Columns in the output are formatted as YYYYMNN (e.g. 2011M01, 2011M02).
    """
    if out_path.exists():
        print(f"[SKIP] {out_path.name} already exists.")
        return

    var_ids: dict[str, int] = spec["var_ids"]  # {"01": 461680, ...}
    print(f"\n--- {out_path.name} (monthly, P3559, {len(var_ids)} month-variables) ---")

    # Collect per-unit data: unit_id -> {"name": str, "Kod": str, col -> value}
    unit_data: dict[str, dict] = {}
    all_cols: list[str] = []

    for month_code, var_id in sorted(var_ids.items()):
        print(f"    Fetching month {month_code} (VAR {var_id})...")
        results = _fetch_all_pages(var_id)
        if not results:
            raise RuntimeError(
                f"Month {month_code} (VAR {var_id}) returned no data. "
                "Check variable ID or BDL API availability."
            )
        for unit in results:
            uid = unit.get("id", "")
            if uid not in unit_data:
                unit_data[uid] = {
                    "Jednostka terytorialna": unit.get("name", ""),
                    "Kod": uid,
                }
            for v in unit.get("values", []):
                col = f"{v['year']}M{month_code}"
                unit_data[uid][col] = str(v["val"]).replace(".", ",") if v.get("val") is not None else ""
                if col not in all_cols:
                    all_cols.append(col)

    if not unit_data:
        print(f"    [WARN] No data returned for monthly unemployment")
        return

    # Sort columns chronologically: YYYYMNN
    all_cols_sorted = sorted(set(all_cols))
    fieldnames = ["Jednostka terytorialna", "Kod"] + all_cols_sorted

    rows = []
    for uid, row in sorted(unit_data.items(), key=lambda x: x[0]):
        # Fill any missing month-columns with empty string
        full_row = {col: row.get(col, "") for col in fieldnames}
        rows.append(full_row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    n_months = len(all_cols_sorted)
    print(f"    Saved {len(rows)} units × {n_months} monthly columns → {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Stage 00: Download GUS BDL Data (API) ===\n")
    print(f"Output: {OUT_DIR}\n")

    n_downloaded = 0
    for spec in VARIABLE_MAP:
        filename = spec["filename"]
        var_id = spec["var_id"]
        label = spec["label"]
        out_path = OUT_DIR / filename

        if out_path.exists():
            print(f"[SKIP] {filename} already exists.")
            continue

        print(f"\n--- {filename} (VAR {var_id}: {label}) ---")
        print(f"  Downloading powiat-level data, years {YEARS[0]}–{YEARS[-1]}...")

        units = download_variable_all_pages(var_id)
        if not units:
            print(f"  [FAIL] No data returned. Check variable ID or API availability.")
            continue

        print(f"  Total units returned: {len(units)}")
        results_to_wide_csv(units, out_path)
        n_downloaded += 1
        time.sleep(SLEEP_SEC)

    # Monthly unemployment (P3559 — 12 per-month variables merged into one file)
    monthly_spec = MONTHLY_VARIABLE_MAP[0]
    download_monthly(monthly_spec, OUT_DIR / monthly_spec["filename"])

    print(f"\n=== Stage 00 complete: {n_downloaded}/{len(VARIABLE_MAP)} variables downloaded via API ===")
    print("Download remaining 3 variables manually per instructions above.")
    print("Then run: python scripts/01_ingest.py")


if __name__ == "__main__":
    main()
