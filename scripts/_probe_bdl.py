"""Temporary probe: discover BDL subject IDs and variable IDs needed for download."""
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


def browse_subjects(parent_id, indent=0):
    d = get("/Subjects", {"lang": "pl", "parent-id": parent_id, "page-size": 30})
    for s in d.get("results", []):
        print(" " * indent + f"{s['id']}: {s['name']}")


def find_variables(subject_id, name_filter=""):
    params = {"lang": "pl", "subject-id": subject_id, "page-size": 50}
    if name_filter:
        params["name"] = name_filter
    d = get("/Variables", params)
    return d.get("results", [])


def sample_data(var_id, n_units=3):
    """Fetch first page of data for a variable at powiat level."""
    d = get(
        f"/data/by-variable/{var_id}",
        {"lang": "pl", "unit-level": 4, "page": 0, "page-size": n_units},
    )
    return d


# Key top-level subjects: K3=LUDNOSC, K4=RYNEK PRACY, K25=PODMIOTY, K40=WYNAGRODZENIA
targets = {
    "K3": "LUDNOSC",
    "K4": "RYNEK PRACY",
    "K25": "PODMIOTY GOSPODARCZE",
    "K40": "WYNAGRODZENIA",
}

print("=== Browsing child subjects ===")
for kid, label in targets.items():
    print(f"\n--- {kid}: {label} ---")
    browse_subjects(kid, indent=2)
    time.sleep(0.5)

# Now drill into K3 to find population variable
print("\n\n=== Variables in K3 (LUDNOSC) ===")
browse_subjects("K3", indent=0)
time.sleep(0.5)
# Get sub-subjects of K3
d3 = get("/Subjects", {"lang": "pl", "parent-id": "K3", "page-size": 20})
for sub in d3.get("results", [])[:5]:
    sid = sub["id"]
    print(f"\n  Subject {sid}: {sub['name']}")
    vars_ = find_variables(sid)
    time.sleep(0.5)
    for v in vars_[:5]:
        print(f"    VAR {v['id']}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
