"""Probe specific BDL subjects for variable IDs, then verify powiat data sample."""
import requests
import time
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}


def get(endpoint, params):
    r = requests.get(f"{BASE}{endpoint}", params=params, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()


def list_vars(subject_id):
    d = get("/Variables", {"lang": "pl", "subject-id": subject_id, "page-size": 50})
    return d.get("results", [])


def sample_data(var_id):
    d = get(
        f"/data/by-variable/{var_id}",
        {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 2, "year": [2010, 2020]},
    )
    results = d.get("results", [])
    total = d.get("totalRecords", 0)
    return total, results[:1]


# Target subjects identified from probe:
# G7 = STAN LUDNOŚCI (population status)
# G8 = MIGRACJE WEWNĘTRZNE I ZAGRANICZNE
# G12 = BEZROBOCIE REJESTROWANE
# G203 = PODMIOTY GOSP. WPISANE DO REJESTRU REGON
# G403 = WYNAGRODZENIA

probes = {
    "G7": "STAN LUDNOSCI (population)",
    "G8": "MIGRACJE",
    "G12": "BEZROBOCIE",
    "G203": "REGON PODMIOTY",
    "G403": "WYNAGRODZENIA",
}

for sid, label in probes.items():
    print(f"\n{'='*60}")
    print(f"Subject {sid}: {label}")
    vars_ = list_vars(sid)
    time.sleep(0.7)
    for v in vars_[:15]:
        print(f"  VAR {v['id']:>8}: {v.get('n1','')[:60]:60s} [{v.get('measureUnitName','')}]")

    # Also check sub-subjects
    subs = get("/Subjects", {"lang": "pl", "parent-id": sid, "page-size": 20})
    for sub in subs.get("results", [])[:5]:
        print(f"  -> sub-subject {sub['id']}: {sub['name']}")
        sub_vars = list_vars(sub["id"])
        time.sleep(0.5)
        for v in sub_vars[:8]:
            print(f"     VAR {v['id']:>8}: {v.get('n1','')[:60]:60s} [{v.get('measureUnitName','')}]")

print("\n\n=== Verify sample data for candidate variables ===")
# Test a few likely candidates
candidates = []  # will fill after seeing output above
