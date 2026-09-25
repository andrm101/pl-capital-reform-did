"""Minimal probe after rate-limit cooldown. 4s sleep per call."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

def get(ep, p):
    time.sleep(4)
    for attempt in range(4):
        r = requests.get(f"{BASE}{ep}", params=p, headers=H, timeout=30)
        if r.status_code == 429:
            wait = 20 * (attempt + 1)
            print(f"  429 — sleeping {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Exhausted retries")

def vars_in(sid):
    return get("/Variables", {"lang": "pl", "subject-id": sid, "page-size": 50}).get("results", [])

def subs_of(sid):
    return get("/Subjects", {"lang": "pl", "parent-id": sid, "page-size": 50}).get("results", [])

def sample(var_id, note=""):
    d = get(f"/data/by-variable/{var_id}",
            {"lang": "pl", "unit-level": 4, "page": 0, "page-size": 2, "year": [1998, 2005, 2015]})
    total = d.get("totalRecords", 0)
    results = d.get("results", [])
    vals, uid = [], ""
    if results:
        uid = results[0].get("id", "")
        vals = [(v["year"], v.get("val")) for v in results[0].get("values", [])[:3]]
    print(f"  VAR {var_id} [{note}]: units={total}, first_id={uid}, vals={vals}")
    return total

# --- stopa bezrobocia in P1364 ---
print("=== P1364 variables ===")
for v in vars_in("P1364"):
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# --- Look specifically for stopa in sub-subjects of G12 not yet probed ---
print("\n=== Search stopa in P2826, P1946 ===")
for sid in ["P2826", "P1946", "P3967"]:
    try:
        vs = vars_in(sid)
        for v in vs[:10]:
            if "stopa" in v.get("n1","").lower() or "%" in v.get("measureUnitName","").lower():
                print(f"  [{sid}] {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
    except Exception as e:
        print(f"  [{sid}] error: {e}")

# Check P2138 directly (known BDL subject for unemployment indicators)
print("\n=== P2138 variables ===")
try:
    for v in vars_in("P2138")[:15]:
        print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")
except Exception as e:
    print(f"  error: {e}")

# --- REGON: G203 first sub-subject ---
print("\n=== G203 first leaf sub-subject ===")
subs = subs_of("G203")
if subs:
    s = subs[0]
    print(f"  Using {s['id']}: {s['name']}")
    for v in vars_in(s["id"])[:8]:
        print(f"    {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# --- Wages: G403 first sub-subject ---
print("\n=== G403 first leaf sub-subject ===")
subs2 = subs_of("G403")
if subs2:
    for s in subs2[:3]:
        print(f"  {s['id']}: {s['name']}")
        for v in vars_in(s["id"])[:5]:
            print(f"    {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# --- Net migration: P1350 ===
print("\n=== P1350 variables ===")
for v in vars_in("P1350")[:20]:
    print(f"  {v['id']:>8}: {v.get('n1','')} [{v.get('measureUnitName','')}]")

# --- Confirm VAR 72305 population sample ---
print("\n=== VAR 72305 population sample ===")
sample(72305, "population")
