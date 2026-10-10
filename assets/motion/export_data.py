"""
export_data.py — every number the explainer video shows, read from the
project's own outputs (data/dashboard/*.json, figures/t04_robustness_summary.csv).

    python assets/motion/export_data.py      → assets/motion/data.json
"""
from __future__ import annotations

import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DASH = os.path.join(ROOT, "data", "dashboard")


def load(name):
    with open(os.path.join(DASH, name), encoding="utf-8") as fh:
        return json.load(fh)


def r(x, n=4):
    return None if x is None else round(float(x), n)


def main():
    summary = load("summary.json")
    sdid = load("sdid_estimates.json")
    lp = [x for x in load("lp_irfs.json") if x["outcome"] == "ln_population"]
    regions = load("regions.json")

    # synthetic DiD on ln population (the headline estimate)
    sd = next(e for e in sdid if e["outcome"] == "ln_population" and e["estimator"] == "SDiD")
    estimators = [{"name": "Synthetic DiD", "coef": r(sd["att"]), "se": r(sd["se"])},
                  {"name": "Generalized synth. control", "coef": r(summary["gsc_avg_att_ln_pop"]), "se": None}]
    with open(os.path.join(ROOT, "figures", "t04_robustness_summary.csv"), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = {"Baseline TWFE": "Two-way fixed effects",
                    "R1: Matched DiD (PSM)": "Matched DiD (PSM)",
                    "R4: Exclude co-capitals from control": "Excl. co-capitals"}[row["spec"]]
            estimators.append({"name": name, "coef": r(row["coef"]), "se": r(row["se"])})

    # one city's actual vs synthetic path, in thousands of residents
    radom = next(c for c in regions if c["city_en"] == "Radom")
    path = [{"year": p["year"], "actual": r(math.exp(p["actual"]) / 1e3, 1),
             "synthetic": r(math.exp(p["counterfactual"]) / 1e3, 1)} for p in radom["counterfactualSeries"]]

    cities = sorted(({"city": c["city_en"], "att_pct": r(c["gsc_att_avg_pct"], 2)}
                     for c in regions if c["treated"] and c.get("gsc_att_avg_pct") is not None),
                    key=lambda c: c["att_pct"])

    data = {
        "n_treated": summary["n_demoted_cities"], "n_control": summary["n_control_cities"],
        "years": summary["panel_years"], "reform_year": summary["reform_year"],
        "sdid_pct": r(summary["sdid_pop_loss_pct"], 1),
        "radom": {"att_pct": radom["gsc_att_avg_pct"], "path": path},
        "irf": [{"h": x["horizon"], "b": r(x["coef"]), "lo": r(x["ci_lo_95"]), "hi": r(x["ci_hi_95"])} for x in lp],
        "estimators": estimators,
        "cities": cities,
    }
    out = os.path.join(HERE, "data.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"wrote {os.path.relpath(out, ROOT)}")
    print({k: data[k] for k in ("n_treated", "n_control", "sdid_pct", "estimators")})
    print(len(cities), "cities;", sum(c["att_pct"] < 0 for c in cities), "negative")


if __name__ == "__main__":
    main()
