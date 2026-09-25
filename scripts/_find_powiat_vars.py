"""
Test candidate variable IDs to find which ones return powiat-level (~380 units) data.
Tests /data endpoint only (lower rate limit than /Variables or /Subjects).
"""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def test_var(var_id, note=""):
    time.sleep(5)
    params = {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 5, "year": [2010]}
    r = requests.get(f"{BASE}/data/by-variable/{var_id}", params=params, headers=H, timeout=20)
    if r.status_code == 429:
        print(f"  VAR {var_id}: 429 rate limit")
        time.sleep(30)
        r = requests.get(f"{BASE}/data/by-variable/{var_id}", params=params, headers=H, timeout=20)
    if r.status_code != 200:
        print(f"  VAR {var_id}: HTTP {r.status_code}")
        return
    d = r.json()
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    uid = results[0].get("id", "") if results else ""
    val = results[0].get("values", [{}])[0].get("val") if results else None
    marker = "<< POWIAT LEVEL!" if total > 200 else ("NUTS-3" if total == 73 else f"N={total}")
    print(f"  VAR {var_id:>8}: total_units={total:>4}  unit_id_sample={uid:15s}  val={val}  [{note}]  {marker}")

# Candidates from P1336 (Ludnosc wg miejsca zamieszkania i plci w podziale na miasto i wies)
print("=== Candidates from P1336 ===")
for vid in [60606, 60608, 60609, 60612, 60614, 60615, 60616, 60618]:
    test_var(vid, "P1336")

# Candidates from P1342 (Ludnosc w wieku przedprodukcyjnym/produkcyjnym/poprodukcyjnym)
print("\n=== Candidates from P1342 ===")
for vid in [34038, 34039, 34040]:
    test_var(vid, "P1342")

# Candidates from P2914 (Ludnosc w gminach/miastach na prawach powiatu)
print("\n=== Candidates from P2914 ===")
for vid in [199186, 199194, 199202, 199203]:
    test_var(vid, "P2914")
