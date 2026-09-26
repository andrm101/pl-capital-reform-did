"""Estimate B input for Stage 13: a per-city MegaCampus ecosystem-type overlay
for the 8 showcase cities (the only cities Stage 13's innovation_hub path ever
covers). Mirrors RO-Administrative-Reform/scripts/build_nuts3_suitability.py's
approach, adapted per docs/superpowers/specs/2026-09-25-poland-megacampus-overlay-design.md:
no new GVA/NACE-employment data is fetched -- the vitality index uses
panel_powiat.parquet's existing wages_avg/migration_net/nat_change_rate columns
as a documented proxy, and the T4 (Cleantech) anchor uses vitality_rank
directly (matching Romania's own fallback for counties missing its
employment-share data), rather than a separate NACE B-E/TOTAL anchor.

Only the 8 showcase cities are scored -- building suitability for all 377
powiats is out of scope; no other city ever appears in Stage 13's output.

NOTE: as of 2026-09-26, none of the 8 cities' raw NUTS2 suitability scores
exceed ~0.58 on any type (max is Legnica's region at 0.576 on T8), so even the
full +/-20% vitality adjustment can't reach the 0.70 Tier-1 threshold -- every
city currently falls back to the flat T3 rate in Stage 13. This is confirmed
correct given the current MegaCampus scores, not a bug in this script; it
converts a previously-unverified assumption into a documented, tested fact,
and leaves the real per-city code path in place for future re-scoring.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress

ROOT = Path(__file__).parent.parent
SIBLING_ROOT = ROOT.parent

SHOWCASE_CITIES = [
    "Radom", "Czestochowa", "Lomza", "Kielce",
    "Slupsk", "Legnica", "Zamosc", "Plock",
]

# TERYT powiat code -> NUTS3 code. Copied from scripts/03_crosswalk_merge.py's
# hardcoded `partial` list (the 8 entries covering our showcase cities) rather
# than imported, to keep this script self-contained -- matches how Poland's
# own Stage 13 and Romania's Stage 13 already duplicate small constant tables
# instead of cross-importing between sibling scripts.
TERYT_TO_NUTS3 = {
    "0262": "PL516",  # Legnica
    "0664": "PL812",  # Zamosc
    "1462": "PL923",  # Plock
    "1463": "PL924",  # Radom
    "2062": "PL842",  # Lomza
    "2263": "PL636",  # Slupsk
    "2464": "PL224",  # Czestochowa
    "2661": "PL721",  # Kielce
}

SUIT_TYPES = [f"T{k}" for k in range(1, 9)]
TIER1_THRESHOLD = 0.70

SUITABILITY_PATH = SIBLING_ROOT / "EU-MegaCampus-Siting" / "data" / "gold" / "suitability_scores.parquet"
PANEL_PATH = ROOT / "data" / "processed" / "panel_powiat.parquet"
OUTPUT_PATH = ROOT / "data" / "processed" / "pl_powiat_suitability.parquet"


def _ols_slope(df: pd.DataFrame, value_col: str) -> float:
    """OLS slope of value_col on year. NaN if fewer than 3 valid points."""
    clean = df[["year", value_col]].dropna()
    if len(clean) < 3:
        return np.nan
    slope, *_ = linregress(clean["year"], clean[value_col])
    return slope


def compute_vitality_index(panel: pd.DataFrame, cities: list[str]) -> pd.DataFrame:
    """One row per city: vitality_wages_growth, vitality_migration_trend,
    vitality_nat_change (each z-scored across `cities`), and vitality_index
    (their mean, ignoring any NaN components -- so a city missing one
    component still gets a real vitality_index from the other two)."""
    rows = []
    for city in cities:
        city_panel = panel[panel["city_en"] == city].copy()

        wages_panel = city_panel[city_panel["wages_avg"] > 0]
        wages_slope = _ols_slope(wages_panel, "wages_avg")

        mig_panel = city_panel.dropna(subset=["migration_net", "population"]).copy()
        mig_panel = mig_panel[mig_panel["population"] > 0]
        mig_panel["migration_rate"] = mig_panel["migration_net"] / mig_panel["population"]
        mig_slope = _ols_slope(mig_panel, "migration_rate")

        nc_panel = city_panel.dropna(subset=["nat_change_rate"]).sort_values("year")
        nc_recent = nc_panel.tail(5)
        nat_change_mean = nc_recent["nat_change_rate"].mean() if len(nc_recent) else np.nan

        rows.append({
            "city_en": city,
            "vitality_wages_growth_raw": wages_slope,
            "vitality_migration_trend_raw": mig_slope,
            "vitality_nat_change_raw": nat_change_mean,
        })

    vit = pd.DataFrame(rows)

    for raw_col, z_col in [
        ("vitality_wages_growth_raw", "vitality_wages_growth"),
        ("vitality_migration_trend_raw", "vitality_migration_trend"),
        ("vitality_nat_change_raw", "vitality_nat_change"),
    ]:
        mu = vit[raw_col].mean(skipna=True)
        sd = vit[raw_col].std(ddof=1, skipna=True)
        vit[z_col] = (vit[raw_col] - mu) / sd

    vit["vitality_index"] = vit[
        ["vitality_wages_growth", "vitality_migration_trend", "vitality_nat_change"]
    ].mean(axis=1, skipna=True)

    return vit.drop(columns=[
        "vitality_wages_growth_raw", "vitality_migration_trend_raw", "vitality_nat_change_raw",
    ])


def redistribute_suitability(
    vitality: pd.DataFrame,
    teryt_to_nuts3: dict[str, str],
    suit_nuts2: pd.DataFrame,
) -> pd.DataFrame:
    """vitality: city_en, teryt_powiat, vitality_index (and the raw z-score
    columns, ignored here). Ranks vitality_index within each NUTS2 group (there
    is no meaningful within-region distinction for most of the 8 cities, since
    at most 2 share a NUTS2 region -- see module docstring note on Radom/Plock
    both under PL92), applies the +/-20% adjustment, and gates at 0.70.

    Raises ValueError naming the first NUTS2 code with no matching row in
    suit_nuts2 (do not silently produce NaN suitability for an unmapped city).
    """
    df = vitality.copy()
    df["nuts3_code"] = df["teryt_powiat"].map(teryt_to_nuts3)
    df["nuts2_code"] = df["nuts3_code"].str[:4]

    missing_nuts2 = sorted(set(df["nuts2_code"]) - set(suit_nuts2.index))
    if missing_nuts2:
        raise ValueError(
            f"nuts2_code(s) not found in suitability_scores.parquet: {missing_nuts2}"
        )

    def region_rank(grp: pd.DataFrame) -> pd.Series:
        n = len(grp)
        ranks = grp["vitality_index"].rank(method="average") - 1
        denom = max(1, n - 1)
        return ranks / denom

    df["vitality_rank_within_region"] = (
        df.groupby("nuts2_code", group_keys=False)
        .apply(lambda g: region_rank(g), include_groups=False)
    )

    suit_cols = [f"suitability_{t}" for t in SUIT_TYPES]
    joined = df.merge(suit_nuts2[suit_cols], left_on="nuts2_code", right_index=True, how="left")

    for col in suit_cols:
        joined[col] = (
            joined[col] * (1.0 + 0.4 * (joined["vitality_rank_within_region"] - 0.5))
        ).clip(0.0, 1.0)

    joined["tier1_gate"] = joined[suit_cols].ge(TIER1_THRESHOLD).any(axis=1)
    joined["tier1_types"] = joined[suit_cols].apply(
        lambda row: "|".join(t for t, v in zip(SUIT_TYPES, row) if v >= TIER1_THRESHOLD),
        axis=1,
    )

    return joined[
        ["teryt_powiat", "city_en", "nuts3_code", "nuts2_code", "vitality_rank_within_region"]
        + suit_cols + ["tier1_gate", "tier1_types"]
    ]


def main() -> None:
    panel = pd.read_parquet(PANEL_PATH)
    suit_nuts2 = pd.read_parquet(SUITABILITY_PATH)

    vitality = compute_vitality_index(panel, SHOWCASE_CITIES)

    teryt_by_city = (
        panel[panel["city_en"].isin(SHOWCASE_CITIES)]
        .drop_duplicates("city_en")
        .set_index("city_en")["teryt_powiat"]
        .to_dict()
    )
    vitality["teryt_powiat"] = vitality["city_en"].map(teryt_by_city)

    n_cities = len(vitality)
    if n_cities != len(SHOWCASE_CITIES):
        raise ValueError(
            f"Expected {len(SHOWCASE_CITIES)} showcase cities, found {n_cities} "
            f"in panel_powiat.parquet -- check SHOWCASE_CITIES spelling against city_en."
        )

    out = redistribute_suitability(vitality, TERYT_TO_NUTS3, suit_nuts2)
    out = out.merge(vitality[["city_en", "vitality_index"]], on="city_en", how="left")

    out.to_parquet(OUTPUT_PATH, index=False)
    print(f"Written: {OUTPUT_PATH} ({len(out)} rows)")
    print(out[["city_en", "nuts2_code", "vitality_rank_within_region", "tier1_gate", "tier1_types"]].to_string(index=False))


if __name__ == "__main__":
    main()
