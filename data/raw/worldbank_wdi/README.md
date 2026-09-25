# World Bank — World Development Indicators (WDI)

## Purpose
National-level context variables for Poland only. No subnational variation — used as
time-varying macro controls (e.g., national GDP growth, inflation) in main powiat regressions.

## Source
World Bank DataBank
URL: https://databank.worldbank.org/source/world-development-indicators
Country: Poland (POL)
Time: 1990–2023, Annual

## Required Series

| File to save | Indicator code | Description |
|---|---|---|
| `wdi_poland.csv` | NY.GDP.MKTP.KD.ZG | GDP growth (annual %) |
| `wdi_poland.csv` | FP.CPI.TOTL.ZG | Inflation, consumer prices (annual %) |
| `wdi_poland.csv` | SL.UEM.TOTL.NE.ZS | Unemployment, total (% of national labour force) |
| `wdi_poland.csv` | NE.TRD.GNFS.ZS | Trade (% of GDP) |

Download all in a single CSV export from DataBank. Save as `wdi_poland.csv`.

## Expected CSV Format
World Bank DataBank export:
```
Series Name,Series Code,Country Name,Country Code,1990 [YR1990],...,2023 [YR2023]
GDP growth (annual %),...,Poland,POL,...
```

## Download Date
- wdi_poland.csv: [FILL IN DATE]

## Citation
World Bank. (2024). World Development Indicators [Dataset]. World Bank Group.
https://databank.worldbank.org/source/world-development-indicators. Accessed: [DATE].
BibTeX key: worldbank_wdi_2024
