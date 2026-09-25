"""
Export pipeline — generates dashboard-ready JSON from all processed parquets.
Writes JSON files to data/dashboard/.

Outputs:
  regions.json          — per-city metadata + gsynth counterfactual series
  forecasts.json        — PVAR status_quo + counterfactual paths 2024-2035
  sdid_estimates.json   — three-estimator robustness table
  lp_irfs.json          — LP IRF coefficients per outcome
  nuts3_gdp.json        — NUTS-3 GDP counterfactual series
  summary.json          — aggregate stats for header cards
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "data" / "dashboard"
OUT.mkdir(parents=True, exist_ok=True)


def _safe(val):
    """Convert numpy scalars / NaN to JSON-safe Python types."""
    if val is None:
        return None
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    return val


def write_json(obj, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=_safe)
    kb = path.stat().st_size / 1024
    print(f"  {path.name:<35} {kb:>7.1f} KB")


# ── 1. regions.json ────────────────────────────────────────────────────────────

def export_regions() -> None:
    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)

    gaps = pd.read_parquet(PROCESSED / "gsynth_gaps.parquet")
    gaps["teryt_powiat"] = gaps["teryt_powiat"].astype(str).str.zfill(4)

    meta = (
        panel[["teryt_powiat", "city_en", "city_pl", "treated",
               "voivodeship_code", "pop_1998_approx_k"]]
        .drop_duplicates("teryt_powiat")
        .set_index("teryt_powiat")
    )

    # Last observed values (2023)
    obs23 = panel[panel["year"] == 2023].set_index("teryt_powiat")

    # GSC att_avg per demoted city
    att = (
        gaps[["teryt_powiat", "att_avg"]]
        .drop_duplicates("teryt_powiat")
        .set_index("teryt_powiat")["att_avg"]
        .to_dict()
    )

    regions = {}
    for teryt, row in meta.iterrows():
        city_gaps = (
            gaps[gaps["teryt_powiat"] == teryt]
            .sort_values("year")[
                ["year", "actual", "counterfactual", "gap"]
            ]
            .to_dict(orient="records")
        )
        obs = obs23.loc[teryt] if teryt in obs23.index else {}

        # Reform cost to 2023 (exp of gap in ln_population terms ≈ pop difference)
        att_val = att.get(teryt)
        reform_cost_pct = round(float(att_val) * 100, 2) if att_val is not None else None

        regions[teryt] = {
            "teryt_powiat":      teryt,
            "city_en":           row["city_en"],
            "city_pl":           row["city_pl"],
            "treated":           bool(row["treated"]),
            "voivodeship_code":  str(row["voivodeship_code"]) if pd.notna(row["voivodeship_code"]) else None,
            "pop_1998_k":        _safe(row["pop_1998_approx_k"]),
            "pop_2023":          _safe(obs.get("population")) if hasattr(obs, "get") else None,
            "unemployment_2023": _safe(obs.get("unemployment")) if hasattr(obs, "get") else None,
            "gsc_att_avg_pct":   reform_cost_pct,
            "counterfactualSeries": [
                {
                    "year":           int(r["year"]),
                    "actual":         _safe(r["actual"]),
                    "counterfactual": _safe(r["counterfactual"]),
                    "gap":            _safe(r["gap"]),
                }
                for r in city_gaps
            ],
            "innovationScenario": None,  # Stage 13 hook
        }

    write_json(list(regions.values()), OUT / "regions.json")


# ── 2. forecasts.json ──────────────────────────────────────────────────────────

def export_forecasts() -> None:
    pvar = pd.read_parquet(PROCESSED / "pvar_forecasts.parquet")

    out = {}
    for (teryt, city), grp in pvar.groupby(["teryt_powiat", "city_en"]):
        city_data = {}
        for (var, path), sub in grp.groupby(["variable", "path"]):
            sub = sub.sort_values("year")
            city_data.setdefault(var, {})[path] = [
                {
                    "year":  int(r["year"]),
                    "value": _safe(r["value"]),
                    "lo80":  _safe(r["lo80"]),
                    "hi80":  _safe(r["hi80"]),
                    "lo95":  _safe(r["lo95"]),
                    "hi95":  _safe(r["hi95"]),
                    # Stage 13 three-estimate bracket bounds; only populated on
                    # innovation_hub/ln_population rows, null elsewhere.
                    "valuePessimistic": _safe(r["value_pessimistic"]) if "value_pessimistic" in r else None,
                    "valueOptimistic":  _safe(r["value_optimistic"]) if "value_optimistic" in r else None,
                }
                for _, r in sub.iterrows()
            ]
        out[teryt] = {
            "teryt_powiat": teryt,
            "city_en":      city,
            "forecasts":    city_data,
        }

    write_json(list(out.values()), OUT / "forecasts.json")


# ── 3. sdid_estimates.json ────────────────────────────────────────────────────

def export_sdid() -> None:
    sdid = pd.read_parquet(PROCESSED / "sdid_estimates.parquet")

    # Load TWFE estimates from the event-study figures table if available
    twfe_path = ROOT / "figures" / "t03_twfe_eventstudy.csv"
    twfe_records = []
    if twfe_path.exists():
        twfe = pd.read_csv(twfe_path)
        # Aggregate to ATT (post-treatment mean)
        if "coef" in twfe.columns and "outcome" in twfe.columns:
            post = twfe[twfe.get("event_time", twfe.get("horizon", pd.Series(dtype=int))) >= 0] if "event_time" in twfe.columns else twfe
            for outcome, g in post.groupby("outcome"):
                att_twfe = g["coef"].mean() if "coef" in g.columns else None
                twfe_records.append({
                    "outcome":   outcome,
                    "estimator": "TWFE",
                    "att":       _safe(att_twfe),
                    "se":        None,
                    "ci_lo":     None,
                    "ci_hi":     None,
                })

    sdid_records = []
    for _, r in sdid.iterrows():
        se_val = r["se"]
        if isinstance(se_val, (np.ndarray, list)):
            se_val = float(se_val.flat[0]) if hasattr(se_val, "flat") else float(se_val[0])
        ci_lo = r["ci_lo"]
        ci_hi = r["ci_hi"]
        if isinstance(ci_lo, (np.ndarray, list)):
            ci_lo = float(ci_lo.flat[0]) if hasattr(ci_lo, "flat") else float(ci_lo[0])
        if isinstance(ci_hi, (np.ndarray, list)):
            ci_hi = float(ci_hi.flat[0]) if hasattr(ci_hi, "flat") else float(ci_hi[0])
        sdid_records.append({
            "outcome":   r["outcome"],
            "estimator": r["estimator"],
            "att":       _safe(r["att"]),
            "se":        _safe(se_val),
            "ci_lo":     _safe(ci_lo),
            "ci_hi":     _safe(ci_hi),
        })

    write_json(twfe_records + sdid_records, OUT / "sdid_estimates.json")


# ── 4. lp_irfs.json ───────────────────────────────────────────────────────────

def export_lp_irfs() -> None:
    lp = pd.read_parquet(PROCESSED / "lp_irfs.parquet")
    records = []
    for _, r in lp.iterrows():
        records.append({
            "outcome":  r["outcome"],
            "horizon":  int(r["horizon"]),
            "coef":     _safe(r["coef"]),
            "se":       _safe(r["se"]),
            "ci_lo_90": _safe(r["ci_lo_90"]),
            "ci_hi_90": _safe(r["ci_hi_90"]),
            "ci_lo_95": _safe(r["ci_lo_95"]),
            "ci_hi_95": _safe(r["ci_hi_95"]),
        })
    write_json(records, OUT / "lp_irfs.json")


# ── 5. nuts3_gdp.json ────────────────────────────────────────────────────────

def export_nuts3_gdp() -> None:
    gaps = pd.read_parquet(PROCESSED / "nuts3_gsynth_gaps.parquet")
    lp   = pd.read_parquet(PROCESSED / "nuts3_lp_irfs.parquet")

    gaps_records = []
    for _, r in gaps.iterrows():
        gaps_records.append({
            "nuts3":           r["nuts3"],
            "year":            int(r["year"]),
            "actual":          _safe(r["actual"]),
            "counterfactual":  _safe(r["counterfactual"]),
            "gap":             _safe(r["gap"]),
            "att_avg":         _safe(r.get("att_avg")),
        })

    lp_records = []
    for _, r in lp.iterrows():
        lp_records.append({
            "horizon":  int(r["horizon"]),
            "coef":     _safe(r["coef"]),
            "se":       _safe(r["se"]),
            "ci_lo_90": _safe(r["ci_lo_90"]),
            "ci_hi_90": _safe(r["ci_hi_90"]),
            "ci_lo_95": _safe(r["ci_lo_95"]),
            "ci_hi_95": _safe(r["ci_hi_95"]),
        })

    write_json({"gsc_gaps": gaps_records, "lp_irfs": lp_records}, OUT / "nuts3_gdp.json")


# ── 6. summary.json ───────────────────────────────────────────────────────────

def export_summary() -> None:
    panel = pd.read_parquet(PROCESSED / "panel_powiat.parquet")
    panel["teryt_powiat"] = panel["teryt_powiat"].astype(str).str.zfill(4)
    gaps  = pd.read_parquet(PROCESSED / "gsynth_gaps.parquet")
    sdid  = pd.read_parquet(PROCESSED / "sdid_estimates.parquet")

    treated = panel[panel["treated"] == 1]
    n_demoted = treated["teryt_powiat"].nunique()

    # Population loss estimate: avg ATT in ln_pop → % terms
    pop_att_row = sdid[sdid["outcome"] == "ln_population"]
    att_sdid = float(pop_att_row["att"].iloc[0]) if len(pop_att_row) else None
    pop_loss_pct = round(att_sdid * 100, 1) if att_sdid else None

    # Total population 2023 of demoted cities
    pop23 = panel[(panel["treated"] == 1) & (panel["year"] == 2023)]["population"].sum()

    # GSC avg ATT
    gsc_att = float(gaps["att_avg"].mean()) if "att_avg" in gaps.columns else None

    summary = {
        "n_demoted_cities":     n_demoted,
        "n_control_cities":     int(panel["teryt_powiat"].nunique()) - n_demoted,
        "panel_years":          [int(panel["year"].min()), int(panel["year"].max())],
        "reform_year":          1999,
        "sdid_att_ln_pop":      _safe(att_sdid),
        "sdid_pop_loss_pct":    pop_loss_pct,
        "gsc_avg_att_ln_pop":   _safe(gsc_att),
        "total_demoted_pop_2023": _safe(pop23),
        "data_note":            "SDiD ATT = log-point change in population. GSC avg over 29 cities with complete data.",
    }
    write_json(summary, OUT / "summary.json")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Export to JSON ===\n")
    print(f"Output directory: {OUT}\n")
    export_regions()
    export_forecasts()
    export_sdid()
    export_lp_irfs()
    export_nuts3_gdp()
    export_summary()
    print(f"\nAll JSON files written to data/dashboard/")


if __name__ == "__main__":
    main()
