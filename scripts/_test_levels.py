"""Test which unit-level value corresponds to powiat (~380 units)."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def test(var_id, level, note=""):
    time.sleep(5)
    r = requests.get(f"{BASE}/data/by-variable/{var_id}",
        params={"lang":"pl","unit-level":level,"page":0,"page-size":5,"year":[2010]},
        headers=H, timeout=20)
    if r.status_code == 429:
        print(f"  429 — waiting 30s"); time.sleep(30)
        r = requests.get(f"{BASE}/data/by-variable/{var_id}",
            params={"lang":"pl","unit-level":level,"page":0,"page-size":5,"year":[2010]},
            headers=H, timeout=20)
    if r.status_code != 200:
        print(f"  VAR {var_id} level {level}: HTTP {r.status_code}"); return
    d = r.json()
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    uid = results[0].get("id","") if results else ""
    print(f"  VAR {var_id} level={level}: total_units={total:>5}  sample_id={uid}  note={note}")

var = 72305  # population
for lvl in [2, 3, 4, 5, 6]:
    test(var, lvl, f"level-{lvl}")
