"""
Stage 02 — Build treatment panel with expanded control group.

Treatment assignment:
  treated = 1  →  31 demoted old voivodeship capitals (lost capital status 1999)
  treated = 0  →  18 retained capitals  +  non-capital powiaty control pool

Control pool selection:
  - Source: all powiaty in bdl_population.csv (~379 units)
  - Exclude: the 49 old voivodeship capitals (treated + retained)
  - Filter:  1998 population ≥ MIN_CONTROL_POP (pragmatic lower bound)
  - Result:  ~200-280 "never-capital" comparison units

Outputs: data/processed/treatment_panel.parquet
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

REFORM_YEAR = 1999
YEAR_MIN = 1995
YEAR_MAX = 2024

# Wałbrzych lost city-powiat status 2013–2018 — flag for exclusion in robustness checks.
STRUCTURAL_BREAK_UNITS = {"0265"}

# Co-capitals (both retained double-capital function in reform)
CO_CAPITALS = {"0461", "0463", "0861", "0862"}

# Minimum 1998 population for non-capital control units (persons).
# Excludes very small rural powiaty that are structurally incomparable.
MIN_CONTROL_POP = 20_000


def extract_teryt(code: str) -> str:
    """Extract 4-digit TERYT powiat code from BDL unit ID."""
    c = str(code).strip()
    if len(c) == 12:         # API download format: e.g. "011212001000"
        return c[2:4] + c[7:9]
    return c[:4]             # web portal format: e.g. "1200101"


def load_population_1998() -> pd.DataFrame:
    """Return DataFrame of {teryt_powiat, pop_1998, unit_name} for all BDL powiaty."""
    pop_path = RAW / "gus_bdl" / "bdl_population.csv"
    if not pop_path.exists():
        return pd.DataFrame(columns=["teryt_powiat", "pop_1998", "unit_name"])

    raw = pd.read_csv(pop_path, sep=";", decimal=",", dtype=str, encoding="utf-8")
    if raw.shape[1] < 3:
        raw = pd.read_csv(pop_path, sep=";", decimal=",", dtype=str, encoding="cp1250")
    raw.columns = [c.strip() for c in raw.columns]

    name_col, code_col = raw.columns[0], raw.columns[1]
    raw["teryt_powiat"] = raw[code_col].map(extract_teryt)

    year_col = "1998"
    if year_col not in raw.columns:
        # Fallback to nearest available year
        year_cols = [c for c in raw.columns if re.match(r"^\d{4}$", c)]
        year_col = min(year_cols, key=lambda y: abs(int(y) - 1998)) if year_cols else None

    if year_col:
        raw["pop_1998"] = pd.to_numeric(
            raw[year_col].str.replace(",", "."), errors="coerce"
        )
    else:
        raw["pop_1998"] = None

    return raw[["teryt_powiat", name_col, "pop_1998"]].rename(columns={name_col: "unit_name"})


def build_treatment_panel() -> pd.DataFrame:
    """Build combined treatment + expanded control panel."""
    # --- 49 old capitals (treatment + retained) ---
    treat = pd.read_parquet(PROCESSED / "treatment_cities.parquet")
    treat["teryt_powiat"] = treat["teryt_powiat"].str.zfill(4)
    capital_teryts = set(treat["teryt_powiat"].unique())

    # --- All powiaty from BDL population data ---
    pop_all = load_population_1998()
    pop_all["teryt_powiat"] = pop_all["teryt_powiat"].str.zfill(4)
    # BDL occasionally returns voivodeship/national aggregates — drop 2-digit codes
    pop_all = pop_all[pop_all["teryt_powiat"].str.len() == 4]
    pop_all = pop_all.dropna(subset=["pop_1998"])

    # --- Non-capital control pool ---
    non_cap = (
        pop_all[
            ~pop_all["teryt_powiat"].isin(capital_teryts) &
            (pop_all["pop_1998"] >= MIN_CONTROL_POP)
        ]
        .copy()
    )
    non_cap["treated"] = 0
    non_cap["retained_capital"] = 0
    non_cap["control_type"] = "never_capital"
    non_cap["city_en"] = non_cap["unit_name"]
    non_cap["city_pl"] = non_cap["unit_name"]
    non_cap["new_voivodeship"] = ""          # not in source data; fill from teryt prefix
    non_cap["pop_1998_approx_k"] = (non_cap["pop_1998"] / 1000).round(1)
    non_cap["capital_type"] = "non_capital"
    non_cap["notes"] = ""
    non_cap["voivodeship_code"] = non_cap["teryt_powiat"].str[:2]
    non_cap["is_co_capital"] = 0
    non_cap["structural_break"] = 0

    # --- Old capitals: annotate with their BDL 1998 population ---
    treat_pop = treat.merge(
        pop_all[["teryt_powiat", "pop_1998"]],
        on="teryt_powiat", how="left"
    )
    treat_pop["treated"] = (treat_pop["retained_capital"] == 0).astype(int)
    treat_pop["control_type"] = treat_pop["retained_capital"].map(
        {1: "retained_capital", 0: "demoted_capital"}
    )
    treat_pop["is_co_capital"] = treat_pop["teryt_powiat"].isin(CO_CAPITALS).astype(int)
    treat_pop["structural_break"] = treat_pop["teryt_powiat"].isin(
        STRUCTURAL_BREAK_UNITS
    ).astype(int)
    treat_pop["voivodeship_code"] = treat_pop["teryt_powiat"].str[:2]

    # --- Align columns and stack ---
    keep_cols = [
        "teryt_powiat", "city_pl", "city_en",
        "treated", "retained_capital", "control_type",
        "voivodeship_code", "pop_1998_approx_k",
        "capital_type", "notes", "is_co_capital", "structural_break",
    ]
    for df in [treat_pop, non_cap]:
        for col in keep_cols:
            if col not in df.columns:
                df[col] = None

    units = pd.concat(
        [treat_pop[keep_cols], non_cap[keep_cols]],
        ignore_index=True,
    ).drop_duplicates(subset=["teryt_powiat"])

    # --- Expand to panel (unit × year) ---
    years = pd.DataFrame({"year": range(YEAR_MIN, YEAR_MAX + 1)})
    units["_key"] = 1
    years["_key"] = 1
    panel = units.merge(years, on="_key").drop(columns="_key")

    panel["post"] = (panel["year"] >= REFORM_YEAR).astype(int)
    panel["did"] = panel["treated"] * panel["post"]
    panel["event_time"] = panel["year"] - REFORM_YEAR

    # Summary
    n_demoted  = panel.loc[panel["year"] == REFORM_YEAR, "treated"].sum()
    n_retained = (panel.loc[panel["year"] == REFORM_YEAR, "control_type"] == "retained_capital").sum()
    n_never    = (panel.loc[panel["year"] == REFORM_YEAR, "control_type"] == "never_capital").sum()
    print(f"Control group: {n_demoted} demoted | {n_retained} retained | {n_never} never-capital")
    print(f"Event-time range: {panel['event_time'].min()} to {panel['event_time'].max()}")

    return panel


def main() -> None:
    print("=== Stage 02: Build Treatment Panel (expanded control group) ===\n")

    panel = build_treatment_panel()
    out = PROCESSED / "treatment_panel.parquet"
    panel.to_parquet(out, index=False)
    print(f"\nSaved → {out.relative_to(ROOT)}")
    print(f"Shape: {panel.shape}")
    print("\nSample (Radom, demoted):")
    sample = panel[(panel["city_en"].str.contains("Radom", na=False)) & (panel["year"].between(1997, 2003))]
    if not sample.empty:
        print(sample[["city_pl", "year", "treated", "post", "did", "event_time"]].to_string(index=False))

    print("\n=== Stage 02 complete ===")


if __name__ == "__main__":
    main()
