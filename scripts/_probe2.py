"""Targeted probe for exact variable IDs needed for download."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def get(ep, p):
    r = requests.get(f"{BASE}{ep}", params=p, headers=H, timeout=20)
    r.raise_for_status()
    return r.json()

def vars_in(sid):
    d = get("/Variables", {"lang": "pl", "subject-id": sid, "page-size": 50})
    return d.get("results", [])

def subs_of(sid):
    d = get("/Subjects", {"lang": "pl", "parent-id": sid, "page-size": 30})
    return d.get("results", [])

def sample(var_id, years=(2000, 2020)):
    d = get(f"/data/by-variable/{var_id}",
            {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 3,
             "year": list(years)})
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    return total, results

# ---- 1. Population: look for "ludność ogółem" in G7 sub-subjects ----
print("=== G7 full sub-subject tree ===")
for s in subs_of("G7"):
    print(f"  {s['id']}: {s['name']}")
time.sleep(0.5)

# Try P2137 (classic BDL population subject)
print("\n=== Variables in P2137 (if exists) ===")
try:
    for v in vars_in("P2137")[:10]:
        print(f"  {v['id']}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
except:
    print("  P2137 not found")
time.sleep(0.5)

# Stan ludności by sex in G7 sub-subject G533 or similar
print("\n=== Looking for Ludnosc ogołem sub-subject directly ===")
for s in subs_of("G7"):
    sid = s["id"]
    vs = vars_in(sid)
    time.sleep(0.4)
    # Find variable named just "ogołem" or "ludność"
    for v in vs:
        n = v.get("n1","").lower()
        if "ogó" in n and "osoba" in v.get("measureUnitName","").lower():
            print(f"  [{sid}] VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# ---- 2. Unemployment rate: browse G12 sub-subjects ----
print("\n=== G12 all sub-subjects ===")
for s in subs_of("G12"):
    print(f"  {s['id']}: {s['name']}")
    vs = vars_in(s["id"])
    time.sleep(0.4)
    for v in vs[:5]:
        if "stopa" in v.get("n1","").lower() or "%" in v.get("measureUnitName",""):
            print(f"    VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# ---- 3. REGON total: G203 ----
print("\n=== G203 sub-subjects and vars ===")
for s in subs_of("G203"):
    print(f"  {s['id']}: {s['name']}")
    vs = vars_in(s["id"])
    time.sleep(0.4)
    for v in vs[:8]:
        print(f"    VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# ---- 4. Net migration saldo: G8 ----
print("\n=== G8 direct vars (saldo) ===")
for s in subs_of("G8"):
    sid = s["id"]
    vs = vars_in(sid)
    time.sleep(0.4)
    for v in vs:
        if "saldo" in v.get("n1","").lower():
            print(f"  [{sid}] VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# ---- 5. Wages G403 ----
print("\n=== G403 WYNAGRODZENIA sub-subjects ===")
for s in subs_of("G403"):
    print(f"  {s['id']}: {s['name']}")
    vs = vars_in(s["id"])
    time.sleep(0.4)
    for v in vs[:6]:
        print(f"    VAR {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
