import numpy as np
import pandas as pd
import pytest
from build_powiat_suitability import compute_vitality_index, redistribute_suitability

CITIES = ["CityA", "CityB"]


def _panel_row(city, year, wages_avg, migration_net, population, nat_change_rate):
    return {
        "city_en": city, "year": year, "wages_avg": wages_avg,
        "migration_net": migration_net, "population": population,
        "nat_change_rate": nat_change_rate,
    }


def _synthetic_panel():
    rows = []
    for year in range(2000, 2024):
        t = year - 2000
        # CityA: wages growing fast, net inflow, positive nat change
        rows.append(_panel_row("CityA", year, 3000 + 100 * t, 50 + t, 100_000, 1.0))
        # CityB: wages flat, net outflow, negative nat change
        rows.append(_panel_row("CityB", year, 3000, -20 - t, 50_000, -2.0))
    return pd.DataFrame(rows)


def test_compute_vitality_index_returns_one_row_per_city():
    panel = _synthetic_panel()
    out = compute_vitality_index(panel, CITIES)
    assert sorted(out["city_en"]) == CITIES
    assert len(out) == 2


def test_compute_vitality_index_cityA_scores_higher_than_cityB():
    panel = _synthetic_panel()
    out = compute_vitality_index(panel, CITIES)
    a = out[out["city_en"] == "CityA"]["vitality_index"].iloc[0]
    b = out[out["city_en"] == "CityB"]["vitality_index"].iloc[0]
    assert a > b


def test_compute_vitality_index_ignores_zero_encoded_missing_wages():
    panel = _synthetic_panel()
    # Zero out the first 10 years of CityA's wages (simulating missing-as-zero)
    mask = (panel["city_en"] == "CityA") & (panel["year"] < 2010)
    panel.loc[mask, "wages_avg"] = 0.0
    out = compute_vitality_index(panel, CITIES)
    row = out[out["city_en"] == "CityA"].iloc[0]
    assert not pd.isna(row["vitality_wages_growth"])
    # Should still be positive -- the zero years are excluded, not treated as a crash
    assert row["vitality_wages_growth"] > 0


def test_compute_vitality_index_degrades_gracefully_with_too_few_wage_points():
    panel = _synthetic_panel()
    # Leave CityA with only 2 non-zero wage years -- below the OLS minimum of 3
    mask = (panel["city_en"] == "CityA") & (panel["year"] < 2022)
    panel.loc[mask, "wages_avg"] = 0.0
    out = compute_vitality_index(panel, CITIES)
    row = out[out["city_en"] == "CityA"].iloc[0]
    # vitality_wages_growth is NaN, but vitality_index itself must still be a real
    # number (averaged over the remaining 2 components), not NaN.
    assert pd.isna(row["vitality_wages_growth"])
    assert not pd.isna(row["vitality_index"])


def _suit_nuts2_frame():
    return pd.DataFrame(
        {f"suitability_{t}": [0.5, 0.9] for t in [f"T{k}" for k in range(1, 9)]},
        index=pd.Index(["PL51", "PL81"], name="nuts2_code"),
    )


def test_redistribute_suitability_joins_and_adjusts():
    vitality = pd.DataFrame({
        "city_en": ["CityA", "CityB"],
        "vitality_index": [1.0, -1.0],  # CityA above mean, CityB below
    })
    teryt_map = {"1111": "PL516", "2222": "PL812"}
    vitality = vitality.assign(teryt_powiat=["1111", "2222"])
    out = redistribute_suitability(vitality, teryt_map, _suit_nuts2_frame())
    assert set(out["city_en"]) == {"CityA", "CityB"}
    assert (out["suitability_T1"] <= 1.0).all()
    assert (out["suitability_T1"] >= 0.0).all()


def test_redistribute_suitability_applies_tier1_gate():
    vitality = pd.DataFrame({
        "city_en": ["CityA", "CityB"],
        "vitality_index": [1.0, -1.0],
        "teryt_powiat": ["1111", "2222"],
    })
    teryt_map = {"1111": "PL516", "2222": "PL812"}
    out = redistribute_suitability(vitality, teryt_map, _suit_nuts2_frame())
    city_b = out[out["city_en"] == "CityB"].iloc[0]
    # CityB's nuts2 (PL812) has a suitability of 0.9 on every type -- even
    # adjusted downward for below-median vitality, at least one type should
    # clear the 0.70 Tier-1 threshold
    assert city_b["tier1_gate"] == True
    assert len(city_b["tier1_types"]) > 0


def test_redistribute_suitability_raises_on_unknown_nuts2():
    vitality = pd.DataFrame({
        "city_en": ["CityC"],
        "vitality_index": [0.0],
        "teryt_powiat": ["9999"],
    })
    teryt_map = {"9999": "PL999"}  # nuts2_code "PL99" not present in _suit_nuts2_frame()
    with pytest.raises(ValueError, match="PL99"):
        redistribute_suitability(vitality, teryt_map, _suit_nuts2_frame())
