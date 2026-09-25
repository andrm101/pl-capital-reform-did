"""Final probe: exact variable IDs + data sample verification."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def get(ep, p):
    r = requests.get(f"{BASE}{ep}", params=p, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()

def vars_in(sid):
    d = get("/Variables", {"lang": "pl", "subject-id": sid, "page-size": 100})
    return d.get("results", [])

def subs_of(sid):
    d = get("/Subjects", {"lang": "pl", "parent-id": sid, "page-size": 50})
    return d.get("results", [])

def sample(var_id):
    d = get(f"/data/by-variable/{var_id}",
            {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 2, "year": [1998, 2010, 2020]})
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    sample_vals = []
    if results:
        u = results[0]
        sample_vals = [(v["year"], v.get("val")) for v in u.get("values", [])[:3]]
    return total, sample_vals

# 1. Stopa bezrobocia: search directly in G12 variables (no sub-subject filter)
print("=== G12 direct variables (searching stopa) ===")
for v in vars_in("G12")[:30]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.7)

# Also check K4 directly for stopa bezrobocia
print("\n=== K4 direct variables ===")
for v in vars_in("K4")[:20]:
    if "stopa" in v.get("n1","").lower() or "%" in v.get("measureUnitName",""):
        print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.7)

# 2. REGON - G203 direct variables
print("\n=== G203 direct variables ===")
for v in vars_in("G203")[:20]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.7)
# also G203 sub-subjects
for s in subs_of("G203")[:3]:
    print(f"  sub {s['id']}: {s['name']}")
    for v in vars_in(s["id"])[:5]:
        if "ogó" in v.get("n1","").lower():
            print(f"    {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
    time.sleep(0.5)

# 3. Wages G403 direct
print("\n=== G403 direct variables ===")
for v in vars_in("G403")[:20]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.7)
for s in subs_of("G403")[:3]:
    print(f"  sub {s['id']}: {s['name']}")
    for v in vars_in(s["id"])[:5]:
        print(f"    {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
    time.sleep(0.5)

# 4. Net migration saldo: search P1350 and P3313 for saldo
print("\n=== P3313 variables (migration inter-powiat) ===")
for v in vars_in("P3313")[:20]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.5)

print("\n=== P1350 variables (migration stays/permits) ===")
for v in vars_in("P1350")[:20]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
time.sleep(0.5)

# 5. Verify population VAR 72305 and a candidate stopa var
print("\n=== Sample data verification ===")
for var_id, label in [
    (72305, "Population total (P2137 ogółem)"),
]:
    total, vals = sample(var_id)
    print(f"  VAR {var_id}: {label}")
    print(f"    powiat-level units: {total}")
    print(f"    sample values (first unit): {vals}")
    time.sleep(0.7)
