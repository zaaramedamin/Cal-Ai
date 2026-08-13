# Food Data — extracted sources for the Maghreb diet app

Each source folder holds the same deliverables: a well-organized **JSON** (source of
truth), **CSV** exports (wide + tidy/long), and a **README**. All files are UTF-8;
CSVs use a BOM so Excel renders accents. Every value is **per 100 g**.

| # | Source | Folder | Foods | Nutrients | Quality |
|---|--------|--------|------:|----------:|---------|
| 1 | **INNTA** — Tunisian food composition table | `INNTA/` | 228 | 50 | OCR-derived; ~2% cells flagged, values verbatim |
| 2 | **Ciqual 2025** — French table (ANSES) | `Ciqual/` | 3,484 | 75 | Clean digital; full FA profile, INFOODS codes |
| 3 | **FoodData Central** — USDA Foundation Foods | `FoodDataCentral/` | 363 | 228 | Lab-measured; FA + amino-acid profiles, min/max/median |

## Which source for what
- **INNTA** — the only source with **Tunisian-specific** foods (pain tabouna/mlawi,
  chamia, rayeb, leben, smen, corète, figue de barbarie). Use it for local dishes;
  spot-check its OCR-flagged values.
- **Ciqual** — large, clean, French-language; best coverage of **composed dishes and
  everyday products** relevant to Maghreb diets.
- **FoodData Central** — most **analytically precise** for generic raw ingredients;
  richest micronutrient detail.

## Shared conventions (to make merging easy later)
- Consistent JSON shape: `metadata` (with a `nutrient_dictionary` data dictionary) →
  `categories` → `foods` → grouped `nutrients`.
- Nutrient cells are objects with an explicit value + status/quality info, never bare
  numbers, so "missing" is never confused with "zero".
- Cross-source keys: Ciqual carries **INFOODS** tags and FDC carries **USDA nutrient
  numbers/ids** — these let you align the same nutrient across all three.
