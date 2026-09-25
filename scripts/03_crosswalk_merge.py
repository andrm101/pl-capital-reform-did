"""
Stage 03 — Crosswalk and merge.
Merges treatment panel with GUS BDL powiat outcomes.
Builds NUTS-3 GDP track separately.
Outputs:
  data/processed/panel_powiat.parquet   — main analysis panel (powiat × year)
  data/processed/panel_nuts3_gdp.parquet — GDP panel (NUTS-3 × year)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"

# Outcomes kept in main panel
POWIAT_OUTCOMES = [
    "population", "migration_net",
    "unemployment",                  # registered unemployment rate (%)
    "regon_firms",                   # total REGON-registered entities
    "wages_avg",                     # avg monthly gross wage (PLN)
    "births",                        # live births
    "deaths",                        # deaths
]

# Log-transform these (add 1 to handle zeros before log)
LOG_VARS = ["population", "regon_firms", "wages_avg", "births", "deaths"]


def load_nuts3_teryt_crosswalk() -> pd.DataFrame:
    """
    Load TERYT powiat → NUTS-3 correspondence.
    Expected file: data/raw/eurostat_regio/teryt_nuts3_crosswalk.csv
    Columns: teryt_powiat (4-char), nuts3 (5-char e.g. PL113)

    If file does not exist, fall back to a hardcoded partial crosswalk covering
    only the 49 old capital city-powiats. This is sufficient for the main DiD
    but GDP analysis will be limited to those units.
    """
    crosswalk_path = ROOT / "data" / "raw" / "eurostat_regio" / "teryt_nuts3_crosswalk.csv"
    if crosswalk_path.exists():
        cw = pd.read_csv(crosswalk_path, dtype=str)
        cw["teryt_powiat"] = cw["teryt_powiat"].str.strip().str.zfill(4)
        cw["nuts3"] = cw["nuts3"].str.strip()
        return cw

    print("[WARN] teryt_nuts3_crosswalk.csv not found. Using hardcoded partial crosswalk.")
    print("       Download full crosswalk from GUS NUTS correspondence tables for complete analysis.")

    # Partial crosswalk: 49 old voivodeship capitals → NUTS-3 pod-region
    # NUTS-3 codes reflect 2021 classification. Verify for pre-2018 data.
    partial = [
        # Dolnośląskie NUTS-3
        ("0261", "PL515"),  # Jelenia Góra → Jeleniogórski
        ("0262", "PL516"),  # Legnica → Legnicko-Głogowski
        ("0264", "PL514"),  # Wrocław → Miasto Wrocław
        ("0265", "PL517"),  # Wałbrzych → Wałbrzyski
        # Kujawsko-Pomorskie
        ("0461", "PL613"),  # Bydgoszcz → Bydgosko-Toruński
        ("0463", "PL613"),  # Toruń → Bydgosko-Toruński (same NUTS-3)
        ("0464", "PL616"),  # Włocławek → Włocławski
        # Lubelskie
        ("0661", "PL811"),  # Biała Podlaska → Bialski
        ("0662", "PL812"),  # Chełm → Chełmsko-Zamojski
        ("0663", "PL814"),  # Lublin → Lubelski
        ("0664", "PL812"),  # Zamość → Chełmsko-Zamojski
        # Lubuskie
        ("0861", "PL431"),  # Gorzów Wlkp → Gorzowski
        ("0862", "PL432"),  # Zielona Góra → Zielonogórski
        # Łódzkie
        ("1061", "PL711"),  # Łódź → Miasto Łódź
        ("1062", "PL713"),  # Piotrków Trybunalski → Piotrkowski
        ("1063", "PL715"),  # Skierniewice → Skierniewicki
        # Małopolskie
        ("1261", "PL213"),  # Kraków → Miasto Kraków
        ("1262", "PL218"),  # Nowy Sącz → Nowosądecki
        ("1263", "PL217"),  # Tarnów → Tarnowski
        # Mazowieckie
        ("1461", "PL921"),  # Ostrołęka → Ostrołęcki (post-2018: PL922)
        ("1462", "PL923"),  # Płock → Płocki
        ("1463", "PL924"),  # Radom → Radomski
        ("1464", "PL925"),  # Siedlce → Siedlecki
        ("1465", "PL911"),  # Warszawa → Miasto Warszawa
        # Opolskie
        ("1661", "PL524"),  # Opole → Opolski
        # Podkarpackie
        ("1861", "PL821"),  # Krosno → Krośnieński
        ("1862", "PL822"),  # Przemyśl → Przemyski
        ("1863", "PL823"),  # Rzeszów → Rzeszowski
        ("1864", "PL824"),  # Tarnobrzeg → Tarnobrzeski
        # Podlaskie
        ("2061", "PL841"),  # Białystok → Białostocki
        ("2062", "PL842"),  # Łomża → Łomżyński
        ("2063", "PL843"),  # Suwałki → Suwalski
        # Pomorskie
        ("2261", "PL633"),  # Gdańsk → Trójmiejski
        ("2263", "PL636"),  # Słupsk → Słupski
        # Śląskie
        ("2461", "PL225"),  # Bielsko-Biała → Bielsko-Bialski
        ("2464", "PL224"),  # Częstochowa → Częstochowski
        ("2467", "PL22A"),  # Katowice → Katowicki
        # Świętokrzyskie
        ("2661", "PL721"),  # Kielce → Kielecki
        # Warmińsko-Mazurskie
        ("2861", "PL621"),  # Elbląg → Elbląski
        ("2862", "PL622"),  # Olsztyn → Olsztyński
        # Wielkopolskie
        ("3061", "PL416"),  # Kalisz → Kaliski
        ("3062", "PL414"),  # Konin → Koniński
        ("3063", "PL417"),  # Leszno → Leszczyński
        ("3064", "PL411"),  # Piła → Pilski
        ("3065", "PL415"),  # Poznań → Miasto Poznań
        # Zachodniopomorskie
        ("3261", "PL426"),  # Koszalin → Koszaliński
        ("3262", "PL424"),  # Szczecin → Miasto Szczecin
    ]
    cw = pd.DataFrame(partial, columns=["teryt_powiat", "nuts3"])
    cw["teryt_powiat"] = cw["teryt_powiat"].str.zfill(4)
    return cw


def build_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Construct log transforms and per-capita variables."""
    for var in LOG_VARS:
        if var in df.columns:
            df[f"ln_{var}"] = np.log1p(df[var])

    # Firms per capita (natural unit for agglomeration)
    if "regon_firms" in df.columns and "population" in df.columns:
        df["firms_per_1k"] = 1000 * df["regon_firms"] / df["population"].replace(0, np.nan)

    # Population growth rate (within-unit YoY)
    if "population" in df.columns:
        df["pop_growth"] = df.groupby("teryt_powiat")["population"].pct_change()

    # Natural population change (births − deaths) and crude rates per 1,000
    if "births" in df.columns and "deaths" in df.columns:
        df["natural_change"] = df["births"] - df["deaths"]
        if "population" in df.columns:
            pop_safe = df["population"].replace(0, np.nan)
            df["birth_rate"]   = 1000 * df["births"]  / pop_safe
            df["death_rate"]   = 1000 * df["deaths"]  / pop_safe
            df["nat_change_rate"] = 1000 * df["natural_change"] / pop_safe

    # Real wages proxy: wages_avg / national CPI handled downstream (WDI deflator in stage 03)
    # Log wages already computed via LOG_VARS above

    return df


def main() -> None:
    print("=== Stage 03: Crosswalk & Merge ===\n")

    # Load treatment panel
    tp = pd.read_parquet(PROCESSED / "treatment_panel.parquet")

    # Load BDL outcomes if available
    bdl_path = PROCESSED / "bdl_interim.parquet"
    if not bdl_path.exists():
        print("[WARN] bdl_interim.parquet not found — run Stage 01 after downloading BDL data.")
        print("       Saving treatment-only panel for structure validation.")
        tp.to_parquet(PROCESSED / "panel_powiat.parquet", index=False)
        return

    bdl = pd.read_parquet(bdl_path)
    bdl["teryt_powiat"] = bdl["teryt_powiat"].str.zfill(4)

    # Merge treatment panel with BDL outcomes
    panel = tp.merge(
        bdl[["teryt_powiat", "year"] + [c for c in POWIAT_OUTCOMES if c in bdl.columns]],
        on=["teryt_powiat", "year"],
        how="left",
    )

    panel = build_derived_features(panel)

    # Merge national WDI controls
    wdi_path = PROCESSED / "wdi_poland.parquet"
    if wdi_path.exists():
        wdi = pd.read_parquet(wdi_path)
        panel = panel.merge(wdi, on="year", how="left")

    panel.to_parquet(PROCESSED / "panel_powiat.parquet", index=False)
    print(f"Saved → data/processed/panel_powiat.parquet  shape={panel.shape}")

    # --- NUTS-3 GDP track ---
    estat_path = PROCESSED / "eurostat_interim.parquet"
    if estat_path.exists():
        estat = pd.read_parquet(estat_path)
        cw = load_nuts3_teryt_crosswalk()

        # Attach treatment status via crosswalk: if a NUTS-3 contains a treated city,
        # compute share of treated city-powiats in that NUTS-3 (for heterogeneity).
        treatment_by_nuts3 = (
            tp[tp["year"] == 1999][["teryt_powiat", "treated", "retained_capital"]]
            .merge(cw, on="teryt_powiat")
            .groupby("nuts3")
            .agg(
                n_demoted=("treated", "sum"),
                n_retained=("retained_capital", "sum"),
                n_old_capitals=("teryt_powiat", "count"),
            )
            .reset_index()
        )
        treatment_by_nuts3["any_demoted"] = (treatment_by_nuts3["n_demoted"] > 0).astype(int)
        treatment_by_nuts3["any_retained"] = (treatment_by_nuts3["n_retained"] > 0).astype(int)

        nuts3_panel = estat.merge(treatment_by_nuts3, on="nuts3", how="left")
        nuts3_panel["post"] = (nuts3_panel["year"] >= 1999).astype(int)
        nuts3_panel["event_time"] = nuts3_panel["year"] - 1999

        if "gdp_mio_eur" in nuts3_panel.columns and "pop_nuts3" in nuts3_panel.columns:
            nuts3_panel["gdp_per_cap_eur"] = (
                1e6 * nuts3_panel["gdp_mio_eur"] / nuts3_panel["pop_nuts3"].replace(0, np.nan)
            )
            nuts3_panel["ln_gdp_per_cap"] = np.log(nuts3_panel["gdp_per_cap_eur"].replace(0, np.nan))

        nuts3_panel.to_parquet(PROCESSED / "panel_nuts3_gdp.parquet", index=False)
        print(f"Saved → data/processed/panel_nuts3_gdp.parquet  shape={nuts3_panel.shape}")
    else:
        print("[SKIP] eurostat_interim.parquet not found — NUTS-3 GDP panel not built.")

    print("\n=== Stage 03 complete ===")


if __name__ == "__main__":
    main()
