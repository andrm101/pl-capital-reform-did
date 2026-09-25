"""Estimate C: observed growth of Polish cities that retained/gained capital
status, used as the optimistic anchor for Stage 13's innovation-premium
bracket (both in this repo and in RO-Administrative-Reform's Stage 13, which
reads the CSV this script writes).

NOTE (data-reality substitution, see docs/superpowers/specs/
2026-09-25-stage13-innovation-roi-design.md Global Constraints): the design
named Krakow/Wroclaw/Trojmiasto as benchmark cities, but Trojmiasto is a
three-city metro area, not a single powiat in panel_powiat.parquet's
retained_capital flag. Gdansk (the largest Trojmiasto constituent, itself a
flagged retained-capital powiat) substitutes for it here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_CITIES = ["Krakow", "Wroclaw", "Gdansk"]
DEFAULT_YEAR_START = 1999
DEFAULT_YEAR_END = 2023


def compute_benchmark(
    panel: pd.DataFrame,
    cities: list[str],
    year_start: int,
    year_end: int,
) -> pd.DataFrame:
    """Annualized ln-population growth for each named retained-capital city
    over [year_start, year_end], plus an AVERAGE row.

    Raises ValueError naming the first missing city if any requested city
    has no matching row at both year_start and year_end.
    """
    rows = []
    for city in cities:
        city_panel = panel[panel["city_en"] == city]
        start_row = city_panel[city_panel["year"] == year_start]
        end_row = city_panel[city_panel["year"] == year_end]
        if start_row.empty or end_row.empty:
            raise ValueError(
                f"{city}: missing population data for {year_start} or {year_end} "
                f"in panel_powiat.parquet"
            )
        pop_start = start_row["population"].iloc[0]
        pop_end = end_row["population"].iloc[0]
        n_years = year_end - year_start
        annual_growth_ln = float(np.log(pop_end / pop_start) / n_years)
        rows.append({"city_en": city, "annual_growth_ln": annual_growth_ln})

    out = pd.DataFrame(rows)
    avg_row = pd.DataFrame([{
        "city_en": "AVERAGE",
        "annual_growth_ln": out["annual_growth_ln"].mean(),
    }])
    return pd.concat([out, avg_row], ignore_index=True)


def main() -> None:
    panel = pd.read_parquet(ROOT / "data" / "processed" / "panel_powiat.parquet")
    out = compute_benchmark(panel, DEFAULT_CITIES, DEFAULT_YEAR_START, DEFAULT_YEAR_END)
    out_path = ROOT / "analysis" / "retained_capital_benchmark.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
