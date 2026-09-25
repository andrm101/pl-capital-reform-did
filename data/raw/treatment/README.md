# Treatment: 1999 Polish Administrative Reform — Capital Status

## Source
Act of 24 July 1998 on the introduction of basic three-tier administrative division of the state
(Ustawa z dnia 24 lipca 1998 r. o wprowadzeniu zasadniczego trójstopniowego podziału terytorialnego państwa)
Dz.U. 1998 Nr 96 poz. 603
URL: https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU19980960603
Downloaded/coded: 2026-06

## Description
49 voivodeships (1975–1998) → 16 voivodeships effective 1999-01-01.
18 cities retained administrative capital functions; 31 lost them (treatment = "demoted").

## Columns
- city_pl: Polish name
- city_en: Anglicised name
- teryt_powiat: 4-digit GUS TERYT powiat code — **MUST VERIFY** against GUS TERYT register
  (https://eteryt.stat.gov.pl/) before running analysis. Codes marked verify_teryt are estimates.
- retained_capital: 1 = retained capital function after 1999, 0 = demoted
- capital_type: full / co-capital-main / co-capital-sejmik / co-capital-sejm / co-capital-marshal / demoted
- new_voivodeship: voivodeship the city is located in post-1999
- voivodeship_code: 2-digit TERYT voivodeship code
- pop_1998_approx_k: approximate 1998 population in thousands (GUS NSP 2002 intercensal estimate)
- notes: verification flags and structural breaks

## Critical Notes
1. **TERYT conflicts**: Ostrołęka and Ciechanów share teryt_powiat=1461 in this file — CONFLICT, must resolve.
2. **Wałbrzych structural break**: lost city-powiat status 2013, restored 2019. Exclude from main spec or use dummy.
3. **Ciechanów and Sieradz**: small population (~44k). May not have city-powiat (grodzki) status — may be powiaty
   ziemskie. Verify before inclusion. If ziemski, the unit of analysis shifts to powiat ziemski (different ID).
4. **Co-capitals (Bydgoszcz/Toruń, Gorzów/Zielona Góra)**: Both cities in each pair retained capital functions.
   For DiD, treat both as "retained" (retained_capital=1). Run sensitivity excluding co-capitals from treated/control.
5. **Verify all TERYT codes** against current GUS TERYT register before merging with BDL data.

## Citation (BibTeX: see references/references.bib key: sejm1998reform)
