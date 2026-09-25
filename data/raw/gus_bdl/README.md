# GUS BDL — Local Data Bank (Bank Danych Lokalnych)

## Source
Statistics Poland (Główny Urząd Statystyczny)
Portal: https://bdl.stat.gov.pl/bdl/start
Bulk CSV download: https://bdl.stat.gov.pl/bdl/dane/podgrup/temat

## Required Datasets (download manually, save here, do NOT rename)
For each dataset: navigate to subject → select variable → choose powiaty level → all years → CSV export.

| File to save | Subject path in BDL | Variable | Notes |
|---|---|---|---|
| `bdl_population.csv` | Ludność → Stan i struktura → Ludność ogółem | Population total | Powiat, annual 1995–2023 |
| `bdl_migration_net.csv` | Ruch naturalny → Migracje → Saldo migracji | Net migration | Powiat, annual |
| `bdl_unemployment_rate.csv` | Rynek pracy → Bezrobocie rejestrowane → Stopa bezrobocia | Registered unemployment rate | Powiat, annual |
| `bdl_regon_firms.csv` | Podmioty gospodarcze → REGON → Jednostki wpisane do rejestru | REGON-registered entities | Powiat, annual |
| `bdl_wages_avg.csv` | Wynagrodzenia → Przeciętne wynagrodzenie | Average monthly gross wage | Powiat, annual (coverage may start 2002) |

## Expected CSV Format
GUS BDL CSVs are typically wide format:
```
Jednostka terytorialna;Kod;1995;1996;...;2023
Polska;0000000;...
Dolnośląskie;0200000;...
Bolesławiec;0201011;...
```
Column separator: semicolon (;)
Decimal separator: comma (,)
Encoding: UTF-8 or CP1250 — check carefully.

## Download Date
Record download date for each file:
- bdl_population.csv: [FILL IN DATE]
- bdl_migration_net.csv: [FILL IN DATE]
- bdl_unemployment_rate.csv: [FILL IN DATE]
- bdl_regon_firms.csv: [FILL IN DATE]
- bdl_wages_avg.csv: [FILL IN DATE]

## Citation
Główny Urząd Statystyczny (GUS). (2024). Bank Danych Lokalnych [Local Data Bank].
Statistics Poland. https://bdl.stat.gov.pl/bdl/start. Accessed: [DATE].
BibTeX key: gus_bdl_2024
