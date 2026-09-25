"""Decode BDL 12-char unit IDs to TERYT powiat codes."""
import requests, time, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://bdl.stat.gov.pl/api/v1"
H = {"Accept": "application/json"}

time.sleep(5)
r = requests.get(f"{BASE}/data/by-variable/72305",
    params={"lang":"pl","unit-level":5,"page":0,"page-size":10,"year":[2010]},
    headers=H, timeout=20)
if r.status_code == 429:
    time.sleep(30)
    r = requests.get(f"{BASE}/data/by-variable/72305",
        params={"lang":"pl","unit-level":5,"page":0,"page-size":10,"year":[2010]},
        headers=H, timeout=20)
d = r.json()
print(f"total: {d.get('totalRecords')}")
for u in d.get("results",[])[:15]:
    uid = u.get("id","")
    name = u.get("name","")
    val = u.get("values",[{}])[0].get("val","")
    # Decode: BDL 12-char = TERYT 7-char (powiat) = first 7? or different slice?
    # 011212001000 -> chars 2-5 = 1212? or 2-6?
    print(f"  id={uid}  name={name[:40]:40s}  2010pop={val}")
    print(f"     chars[2:6]={uid[2:6]}  chars[2:7]={uid[2:7]}  chars[3:7]={uid[3:7]}")
