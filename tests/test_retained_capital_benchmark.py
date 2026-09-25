import pandas as pd
import pytest
from analysis.retained_capital_benchmark import compute_benchmark


def _panel(city, start_pop, end_pop, year_start=1999, year_end=2023):
    return pd.DataFrame({
        "city_en": [city, city],
        "year": [year_start, year_end],
        "population": [start_pop, end_pop],
        "retained_capital": [True, True],
    })


def test_compute_benchmark_single_city_growth_rate():
    panel = _panel("Krakow", 100_000, 121_000, 1999, 2023)
    out = compute_benchmark(panel, cities=["Krakow"], year_start=1999, year_end=2023)
    row = out[out["city_en"] == "Krakow"].iloc[0]
    # ln(121000/100000) / 24 years ~= 0.00792/yr
    assert row["annual_growth_ln"] == pytest.approx(0.00792, abs=1e-4)


def test_compute_benchmark_multiple_cities_includes_average_row():
    panel = pd.concat([
        _panel("Krakow", 100_000, 121_000),
        _panel("Wroclaw", 200_000, 221_000),
    ], ignore_index=True)
    out = compute_benchmark(panel, cities=["Krakow", "Wroclaw"], year_start=1999, year_end=2023)
    assert set(out["city_en"]) == {"Krakow", "Wroclaw", "AVERAGE"}
    avg_row = out[out["city_en"] == "AVERAGE"].iloc[0]
    per_city_mean = out[out["city_en"] != "AVERAGE"]["annual_growth_ln"].mean()
    assert avg_row["annual_growth_ln"] == pytest.approx(per_city_mean, abs=1e-9)


def test_compute_benchmark_raises_on_missing_city():
    panel = _panel("Krakow", 100_000, 121_000)
    with pytest.raises(ValueError, match="Gdansk"):
        compute_benchmark(panel, cities=["Krakow", "Gdansk"], year_start=1999, year_end=2023)
