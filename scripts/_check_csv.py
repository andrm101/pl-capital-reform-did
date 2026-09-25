import sys, csv
sys.stdout.reconfigure(encoding="utf-8")
with open("data/raw/gus_bdl/bdl_population.csv", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f, delimiter=";"))
print(f"Rows: {len(rows)}")
name_col = "Jednostka terytorialna"
code_col = "Kod"
for r in rows[:5]:
    print(f"  {r[name_col][:45]:45s}  {r[code_col]}")
print("...")
for r in rows[-3:]:
    print(f"  {r[name_col][:45]:45s}  {r[code_col]}")
# Check column (year) count
cols = list(rows[0].keys())
year_cols = [c for c in cols if c.isdigit()]
print(f"\nYear columns: {year_cols[0]} to {year_cols[-1]} ({len(year_cols)} years)")
print(f"\nSample 2000 value for first row: {rows[0].get('2000','N/A')}")
print(f"Sample 2010 value for first row: {rows[0].get('2010','N/A')}")
