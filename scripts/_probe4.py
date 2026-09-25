"""Patient probe with 2s sleep between calls."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def get(ep, p):
    time.sleep(2)
    r = requests.get(f"{BASE}{ep}", params=p, headers=H, timeout=20)
    if r.status_code == 429:
        print("  429 rate limit — sleeping 10s")
        time.sleep(10)
        r = requests.get(f"{BASE}{ep}", params=p, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()

def vars_in(sid):
    return get("/Variables", {"lang": "pl", "subject-id": sid, "page-size": 50}).get("results", [])

def search_vars(name):
    return get("/Variables", {"lang": "pl", "name": name, "page-size": 20}).get("results", [])

def sample(var_id):
    d = get(f"/data/by-variable/{var_id}",
            {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 2, "year": [1998, 2010, 2020]})
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    if results:
        vals = [(v["year"], v.get("val")) for v in results[0].get("values", [])[:3]]
        unit_id = results[0].get("id","")
    else:
        vals, unit_id = [], ""
    return total, unit_id, vals

# 1. Search "stopa bezrobocia" by name directly
print("=== Search 'stopa bezrobocia' ===")
for v in search_vars("stopa bezrobocia"):
    print(f"  VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# 2. REGON total from G203 leaf subjects
print("\n=== G203 child subjects with vars ===")
subs = get("/Subjects", {"lang": "pl", "parent-id": "G203", "page-size": 30}).get("results", [])
for s in subs[:6]:
    print(f"  {s['id']}: {s['name']}")
    for v in vars_in(s["id"])[:6]:
        if "ogó" in v.get("n1","").lower():
            print(f"    VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# 3. Wages G403 child subjects
print("\n=== G403 child subjects ===")
subs = get("/Subjects", {"lang": "pl", "parent-id": "G403", "page-size": 20}).get("results", [])
for s in subs[:5]:
    print(f"  {s['id']}: {s['name']}")
    for v in vars_in(s["id"])[:5]:
        print(f"    VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# 4. Saldo migracji in P3313
print("\n=== P3313 vars (migration saldo) ===")
for v in vars_in("P3313"):
    if "saldo" in v.get("n1","").lower():
        print(f"  VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# 5. Verify population 72305
print("\n=== Sample verify VAR 72305 ===")
total, uid, vals = sample(72305)
print(f"  total units at level-4: {total}")
print(f"  first unit id: {uid}")
print(f"  sample values: {vals}")
