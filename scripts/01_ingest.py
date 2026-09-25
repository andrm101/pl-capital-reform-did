"""
Stage 01 — Raw data ingestion and validation.
Reads GUS BDL, Eurostat REGIO, World Bank WDI, and treatment CSV.
Outputs validated interim parquets to data/processed/.
"""
from __future__ import annotations

import gzip
import re
import urllib.request
from pathlib import Path
from typing import Any

import sys

import numpy as np
import pandas as pd

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
        try:
            urllib.request.urlretrieve(url, tmp)
            with gzip.open(tmp, "rb") as f_in, open(out, "wb") as f_out:
                f_out.write(f_in.read())
            print(f"  Saved -> {out.name}")
        except Exception as e:
            # Clean up partial files before re-raising
            if tmp.exists():
                tmp.unlink()
            if out.exists():
                out.unlink()
            raise RuntimeError(f"Failed to download {filename}: {e}") from e
        finally:
            if tmp.exists():
                tmp.unlink()

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# GUS BDL helpers
# ---------------------------------------------------------------------------

def load_bdl_wide(path: Path, value_name: str) -> pd.DataFrame:
    """Parse GUS BDL wide CSV (semicolon-delimited) into long panel."""
    raw = pd.read_csv(path, sep=";", decimal=",", encoding="utf-8", dtype=str)

    # Fallback to cp1250 if utf-8 fails
    if raw.shape[1] < 3:
        raw = pd.read_csv(path, sep=";", decimal=",", encoding="cp1250", dtype=str)

    # Standardise column names: strip whitespace
    raw.columns = [c.strip() for c in raw.columns]

    # Identify entity and code columns (BDL exports use Polish headers)
    name_col = raw.columns[0]   # e.g. "Jednostka terytorialna"
    code_col = raw.columns[1]   # e.g. "Kod"
    year_cols = [c for c in raw.columns[2:] if re.match(r"^\d{4}$", c.strip())]

    if not year_cols:
        raise ValueError(f"No year columns found in {path.name}. Check CSV format.")

    long = raw[[name_col, code_col] + year_cols].melt(
        id_vars=[name_col, code_col],
        var_name="year",
        value_name=value_name,
    )
    long = long.rename(columns={name_col: "unit_name", code_col: "teryt_raw"})
    long["year"] = long["year"].astype(int)
    long[value_name] = pd.to_numeric(long[value_name].str.replace(",", "."), errors="coerce")

    # TERYT extraction:
    # Web portal exports: 7-digit codes like "1200101" -> TERYT = first 4 chars "1200"
    # API downloads (00_download_bdl.py): 12-digit codes like "011212001000"
    #   -> TERYT = chars[2:4] (voivodeship WW) + chars[7:9] (powiat PP)
    def extract_teryt(code: str) -> str:
        c = str(code).strip()
        if len(c) == 12:  # API format
            return c[2:4] + c[7:9]
        return c[:4]      # web portal format

    long["teryt_powiat"] = long["teryt_raw"].map(extract_teryt)
    return long[["teryt_powiat", "unit_name", "year", value_name]]


def load_bdl_powiaty(path: Path, value_name: str) -> pd.DataFrame:
    """
    Filter BDL data to powiat-level records.
    Handles both web portal exports (7-digit TERYT, semicolon CSV) and
    API downloads (12-digit unit IDs, semicolon CSV from 00_download_bdl.py).
    """
    for enc in ["utf-8", "cp1250"]:
        try:
            raw = pd.read_csv(path, sep=";", decimal=",", encoding=enc, dtype=str)
            if raw.shape[1] >= 3:
                break
        except UnicodeDecodeError:
            continue

    raw.columns = [c.strip() for c in raw.columns]
    name_col = raw.columns[0]
    code_col = raw.columns[1]
    year_cols = [c for c in raw.columns[2:] if re.match(r"^\d{4}$", c.strip())]

    # Detect format by code length
    sample_code = raw[code_col].dropna().iloc[0].strip() if len(raw) > 0 else ""
    if len(sample_code) == 12:
        # API format: all rows are powiat-level (unit-level=5 download)
        powiat_mask = raw[code_col].str.strip().str.len() == 12
    else:
        # Web portal format: powiat records have 7-digit codes
        powiat_mask = raw[code_col].str.strip().str.len() == 7

    sub = raw.loc[powiat_mask, [name_col, code_col] + year_cols].melt(
        id_vars=[name_col, code_col], var_name="year", value_name=value_name
    )
    sub = sub.rename(columns={name_col: "unit_name", code_col: "teryt_raw"})
    sub["year"] = sub["year"].astype(int)
    sub[value_name] = pd.to_numeric(sub[value_name].str.replace(",", "."), errors="coerce")

    def extract_teryt(code: str) -> str:
        c = str(code).strip()
        if len(c) == 12:
            return c[2:4] + c[7:9]
        return c[:4]

    sub["teryt_powiat"] = sub["teryt_raw"].map(extract_teryt)
    return sub[["teryt_powiat", "unit_name", "year", value_name]]


# ---------------------------------------------------------------------------
# Eurostat REGIO helpers
# ---------------------------------------------------------------------------

def load_eurostat_tsv(path: Path, value_name: str, geo_filter: str = "PL") -> pd.DataFrame:
    """Parse Eurostat bulk TSV. Returns long panel filtered to Poland NUTS-3."""
    raw = pd.read_csv(path, sep="\t", dtype=str)
    raw.columns = [c.strip() for c in raw.columns]

    dim_col = raw.columns[0]          # e.g. "freq,unit,na_item,geo\TIME_PERIOD"
    year_cols = raw.columns[1:]

    # Split dimension column
    dims = dim_col.split("\\")[0].split(",")  # ['freq', 'unit', 'na_item', 'geo']
    dim_data = raw[dim_col].str.split(",", expand=True)
    dim_data.columns = dims + ["geo"] if len(dims) < dim_data.shape[1] else dims

    long = pd.concat([dim_data, raw[year_cols]], axis=1)

    # Filter to Poland NUTS-3 (PL + 5 chars = 7 total, e.g. PL113)
    long = long[long["geo"].str.startswith(geo_filter) & (long["geo"].str.len() == 5)]

    long = long.melt(
        id_vars=list(dim_data.columns),
        var_name="year_raw",
        value_name=value_name,
    )
    long["year"] = long["year_raw"].str.strip().astype(int, errors="ignore")
    long[value_name] = (
        long[value_name]
        .str.strip()
        .replace(":", np.nan)
        .str.split(" ", expand=True)[0]   # strip flags like "e", "p"
        .pipe(pd.to_numeric, errors="coerce")
    )
    long = long.rename(columns={"geo": "nuts3"})
    return long[["nuts3", "year", value_name]].dropna(subset=["year"])


# ---------------------------------------------------------------------------
# World Bank WDI helpers
# ---------------------------------------------------------------------------

def load_wdi(path: Path) -> pd.DataFrame:
    """Parse World Bank DataBank CSV export for Poland."""
    raw = pd.read_csv(path, dtype=str, skip_blank_lines=True)
    raw.columns = [c.strip() for c in raw.columns]

    # Identify year columns: pattern "YYYY [YRYYYY]"
    year_cols = {c: int(c[:4]) for c in raw.columns if re.match(r"^\d{4} \[YR\d{4}\]$", c.strip())}
    if not year_cols:
        # Fallback: plain 4-digit year headers
        year_cols = {c: int(c) for c in raw.columns if re.match(r"^\d{4}$", c.strip())}

    indicator_col = [c for c in raw.columns if "Series Code" in c][0]
    name_col = [c for c in raw.columns if "Series Name" in c][0]

    records = []
    for _, row in raw.iterrows():
        for col, yr in year_cols.items():
            records.append({
                "indicator_code": row[indicator_col].strip() if pd.notna(row[indicator_col]) else None,
                "indicator_name": row[name_col].strip() if pd.notna(row[name_col]) else None,
                "year": yr,
                "value": pd.to_numeric(row[col], errors="coerce"),
            })

    df = pd.DataFrame(records).dropna(subset=["indicator_code"])
    return df.pivot_table(index="year", columns="indicator_code", values="value").reset_index()


# ---------------------------------------------------------------------------
# Treatment CSV
# ---------------------------------------------------------------------------

def load_treatment() -> pd.DataFrame:
    path = RAW / "treatment" / "capital_status_1999.csv"
    df = pd.read_csv(path, dtype={"teryt_powiat": str})
    df["teryt_powiat"] = df["teryt_powiat"].str.zfill(4)
    assert df["city_pl"].nunique() == 49, "Expected 49 old voivodeship capitals"
    assert df["retained_capital"].sum() == 18, "Expected 18 retained capitals"
    return df


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_panel(df: pd.DataFrame, id_cols: list[str], value_col: str, label: str) -> None:
    n_units = df[id_cols[0]].nunique()
    n_years = df["year"].nunique()
    n_missing = df[value_col].isna().sum()
    pct_missing = 100 * n_missing / len(df)
    year_range = f"{df['year'].min()}–{df['year'].max()}"
    print(f"[{label}] units={n_units}, years={n_years} ({year_range}), "
          f"N={len(df)}, missing={n_missing} ({pct_missing:.1f}%)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    download_eurostat_if_missing(RAW)
    print("=== Stage 01: Ingest ===\n")

    # --- GUS BDL ---
    # Direct-download files (VAR IDs confirmed, downloaded by 00_download_bdl.py)
    bdl_files_direct = {
        "population":       RAW / "gus_bdl" / "bdl_population.csv",
        "unemployment":     RAW / "gus_bdl" / "bdl_unemployment_rate.csv",
        "regon_firms":      RAW / "gus_bdl" / "bdl_regon_firms.csv",
        "wages_avg":        RAW / "gus_bdl" / "bdl_wages_avg.csv",
        "births":           RAW / "gus_bdl" / "bdl_births.csv",
        "deaths":           RAW / "gus_bdl" / "bdl_deaths.csv",
    }
    # Migration: API downloads arrivals + departures separately; compute saldo here.
    # Fallback: if bdl_migration_net.csv exists (manual portal export), use directly.
    bdl_panels: dict[str, pd.DataFrame] = {}
    for name, path in bdl_files_direct.items():
        if not path.exists():
            print(f"[SKIP] {path.name} not found — see data/raw/gus_bdl/README.md")
            continue
        df = load_bdl_powiaty(path, name)
        validate_panel(df, ["teryt_powiat"], name, f"BDL:{name}")
        bdl_panels[name] = df

    # Compute migration saldo from arrivals/departures if direct saldo file absent
    mig_net_path = RAW / "gus_bdl" / "bdl_migration_net.csv"
    mig_in_path  = RAW / "gus_bdl" / "bdl_migration_in.csv"
    mig_out_path = RAW / "gus_bdl" / "bdl_migration_out.csv"
    if mig_net_path.exists():
        df = load_bdl_powiaty(mig_net_path, "migration_net")
        validate_panel(df, ["teryt_powiat"], "migration_net", "BDL:migration_net")
        bdl_panels["migration_net"] = df
    elif mig_in_path.exists() and mig_out_path.exists():
        df_in  = load_bdl_powiaty(mig_in_path,  "migration_in")
        df_out = load_bdl_powiaty(mig_out_path, "migration_out")
        mig = df_in.merge(df_out[["teryt_powiat", "year", "migration_out"]],
                          on=["teryt_powiat", "year"], how="outer")
        mig["migration_net"] = mig["migration_in"] - mig["migration_out"]
        validate_panel(mig, ["teryt_powiat"], "migration_net", "BDL:migration_net(computed)")
        bdl_panels["migration_net"] = mig[["teryt_powiat", "unit_name", "year", "migration_net"]]
    else:
        print("[SKIP] Migration data not found (bdl_migration_net.csv or bdl_migration_in/out.csv)")

    if bdl_panels:
        # Merge all BDL variables on teryt_powiat × year
        bdl_merged = list(bdl_panels.values())[0]
        for name, df in list(bdl_panels.items())[1:]:
            bdl_merged = bdl_merged.merge(df[["teryt_powiat", "year", name]],
                                          on=["teryt_powiat", "year"], how="outer")
        out_path = PROCESSED / "bdl_interim.parquet"
        bdl_merged.to_parquet(out_path, index=False)
        print(f"\nSaved -> {out_path.relative_to(ROOT)}")
    else:
        print("\n[WARNING] No BDL files found. Download required datasets first.")

    # --- Eurostat REGIO ---
    estat_files = {
        "gdp_mio_eur":  RAW / "eurostat_regio" / "nama_10r_3gdp.tsv",
        "area_km2":     RAW / "eurostat_regio" / "demo_r_d3area.tsv",
        "pop_nuts3":    RAW / "eurostat_regio" / "demo_r_pjangrp3.tsv",
    }
    estat_panels: list[pd.DataFrame] = []
    for name, path in estat_files.items():
        if not path.exists():
            print(f"[SKIP] {path.name} not found — download per data/raw/eurostat_regio/README.md")
            continue
        df = load_eurostat_tsv(path, name)
        validate_panel(df, ["nuts3"], name, f"ESTAT:{name}")
        estat_panels.append(df)

    if estat_panels:
        estat_merged = estat_panels[0]
        for df in estat_panels[1:]:
            non_key = [c for c in df.columns if c not in ["nuts3", "year"]]
            estat_merged = estat_merged.merge(df[["nuts3", "year"] + non_key],
                                              on=["nuts3", "year"], how="outer")
        out_path = PROCESSED / "eurostat_interim.parquet"
        estat_merged.to_parquet(out_path, index=False)
        print(f"Saved -> {out_path.relative_to(ROOT)}")
    else:
        print("[WARNING] No Eurostat files found.")

    # --- NUTS-3 panel: GDP per capita (PPS/HAB) direct from nama_10r_3gdp ---
    gdp_path = RAW / "eurostat_regio" / "nama_10r_3gdp.tsv"
    if gdp_path.exists():
        # Load raw TSV and extract PPS_HAB unit (GDP per inhabitant, PPS)
        raw_gdp = pd.read_csv(gdp_path, sep="\t", dtype=str)
        raw_gdp.columns = [c.strip() for c in raw_gdp.columns]

        dim_col = raw_gdp.columns[0]
        year_cols_gdp = [c for c in raw_gdp.columns[1:]
                         if re.match(r"^\s*\d{4}\s*$", c)]

        # First column encodes dims as comma-separated: freq,unit,na_item,geo
        parts = raw_gdp[dim_col].str.split(",", expand=True)
        # Find unit column (index 1 in typical Eurostat format: A,PPS_HAB,GDP,PL911)
        unit_idx = 1
        geo_idx  = parts.shape[1] - 1  # last column is geo code

        if parts.shape[1] < 3:
            print("[WARN] Unexpected TSV format: fewer than 3 dimension columns. Skipping nuts3_panel.")
        else:
            pps_mask = parts[unit_idx].str.strip() == "PPS_EU27_2020_HAB"
            pl_mask  = (
                parts[geo_idx].str.strip().str.startswith("PL") &
                (parts[geo_idx].str.strip().str.len() == 5)
            )

            sub_gdp = raw_gdp.loc[pps_mask & pl_mask, year_cols_gdp].copy()
            sub_gdp["nuts3"] = parts.loc[pps_mask & pl_mask, geo_idx].str.strip().values

            if sub_gdp.empty:
                print("[WARN] No PPS_HAB rows found in nama_10r_3gdp.tsv for PL NUTS-3.")
            else:
                gdp_long = sub_gdp.melt(
                    id_vars="nuts3", var_name="year_raw", value_name="gdp_pps_hab"
                )
                gdp_long["year"] = gdp_long["year_raw"].str.strip().str[:4].astype(int, errors="ignore")
                gdp_long["gdp_pps_hab"] = (
                    gdp_long["gdp_pps_hab"]
                    .str.strip()
                    .replace(":", np.nan)
                    .str.split(" ", expand=True)[0]
                    .pipe(pd.to_numeric, errors="coerce")
                )
                gdp_long = gdp_long[["nuts3", "year", "gdp_pps_hab"]].dropna(subset=["year"])
                gdp_long["ln_gdp_pps_hab"] = np.log(gdp_long["gdp_pps_hab"].replace(0, np.nan))

                # Attach treatment flags via TERYT->NUTS-3 crosswalk
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

                matched_nuts3 = nuts3_flags["nuts3"].nunique()
                print(f"  TERYT->NUTS-3 crosswalk: {len(cw)} mappings -> {matched_nuts3} unique NUTS-3 regions treated")

                nuts3 = gdp_long.merge(nuts3_flags, on="nuts3", how="left")
                nuts3["any_demoted"] = nuts3["any_demoted"].fillna(0).astype(int)
                nuts3["post"] = (nuts3["year"] >= 1999).astype(int)
                nuts3["event_time"] = nuts3["year"] - 1999

                unmatched = nuts3[nuts3["any_demoted"] == 0]["nuts3"].nunique()
                print(f"  NUTS-3 regions without crosswalk match (any_demoted=0 by default): {unmatched}")

                out_path = PROCESSED / "nuts3_panel.parquet"
                nuts3.to_parquet(out_path, index=False)
                print(f"Saved -> {out_path.relative_to(ROOT)}  shape={nuts3.shape}")

                # Verify coverage
                years_available = sorted(nuts3["year"].unique())
                print(f"  GDP per capita (PPS_HAB) coverage: {years_available[0]}-{years_available[-1]}")
                print(f"  any_demoted regions: {nuts3[nuts3['year']==2005]['any_demoted'].sum()} / {nuts3['nuts3'].nunique()}")
    else:
        print("[SKIP] nama_10r_3gdp.tsv not found -- nuts3_panel not built.")

    # --- World Bank WDI ---
    wdi_path = RAW / "worldbank_wdi" / "wdi_poland.csv"
    if wdi_path.exists():
        wdi = load_wdi(wdi_path)
        out_path = PROCESSED / "wdi_poland.parquet"
        wdi.to_parquet(out_path, index=False)
        print(f"Saved -> {out_path.relative_to(ROOT)}")
    else:
        print(f"[SKIP] wdi_poland.csv not found — download per data/raw/worldbank_wdi/README.md")

    # --- Treatment ---
    treat = load_treatment()
    out_path = PROCESSED / "treatment_cities.parquet"
    treat.to_parquet(out_path, index=False)
    print(f"Saved -> {out_path.relative_to(ROOT)}")
    print(f"\nTreatment: {treat['retained_capital'].sum()} retained, "
          f"{(treat['retained_capital']==0).sum()} demoted")

    print("\n=== Stage 01 complete ===")


if __name__ == "__main__":
    main()
