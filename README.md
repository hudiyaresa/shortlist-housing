# Shortlist housing

I collected about 2,200 house listings around Jakarta over two months and could not survey them all. This repo
filters them down with spatial SQL in DuckDB: price, land size, whether the house sits inside a housing complex,
car access, flood history, and how long it takes to drive to a toll gate that actually leads to my office in Senayan.

Result of the 15 November 2026 run (2,189 listings after merging duplicate ads): 14 houses pass every hard rule,
and 5 of them are in the areas we want.

Pages (in Indonesian, because the listings, addresses and flood reports are Indonesian):

- Shortlist and reasoning: https://hudiyaresa.github.io/shortlist-housing/
- Map: https://hudiyaresa.github.io/shortlist-housing/peta_shortlist.html
- Table of houses still in the running: https://hudiyaresa.github.io/shortlist-housing/kandidat.html

## What is in here

| Path | What it is |
|---|---|
| `index.html`, `shortlist_rumah.md` | The shortlist write-up |
| `peta_shortlist.html` | Leaflet map, one file. Dashed markers mean the location is only an area centroid |
| `kandidat.csv`, `kandidat.html` | Every listing with one column per rule |
| `foto/` | Small photos from the Threads posts, up to three per house. rumah123 and Pinhome photos load from their CDNs |
| `corong.csv` | How many listings drop out at each rule |
| `gerbang_tol.csv` | Toll gates that turned out to be entrances heading toward Senayan |
| `pipeline/` | Scripts, SQL and hand-made reference data |

## How it works

1. `01_muat` loads the listings and the Jakarta flood history per RT (BPBD, 2021 to 2024) into DuckDB with the
   spatial extension.
2. `02_ambil_osm` pulls toll roads, toll booths and rivers from OpenStreetMap through Overpass.
3. `03_gerbang` works out which toll booths are real entrances toward Senayan. OpenStreetMap mixes entrances,
   exits and mainline plazas from every direction. For each booth the script asks the public OSRM server for a
   route to the office, then checks that the route starts on the toll road and stays on it. 173 of 401 booths pass.
4. `04_kriteria_teks` reads price, land size, complex, car access and carport from the ad text with regular
   expressions. Manual corrections live in `data/koreksi_manual.csv`, each with a reason.
5. `05_waktu_tempuh` gets road travel time from each house to nearby gates from the OSRM table service. OSRM has no
   traffic, so times are multiplied by 2.4. That factor comes from 12 routes compared with Google Maps for a Monday
   06:30 departure (`data/kalibrasi_macet.csv`).
6. `06_banjir_luar_dki` adds the BNPB InaRISK flood hazard index and ground elevation for houses outside Jakarta,
   where there is no per-RT flood record.
6b. `06b_sekolah` adds primary, junior and senior high schools around each house (our school map plus the
   datawan-labs national school list), straight-line distance for school zoning and road distance to the best-ranked
   schools.
7. `07_spasial` and `08_kandidat` join everything in SQL: point in flood polygon, distance to the nearest toll road
   body, distance and height above the nearest river, fastest gate, and a named list of housing estates that made the
   news for flooding (`data/banjir_bernama.csv`).
8. `09_hasil` and `10_halaman` write the CSV files, the map and the pages. They also pick up to three photos per
   house. Photos whose OCR text contains a phone number are skipped, and brochure-style images go last.

Each rule has three values: yes, no, unclear. Only "no" removes a house. A house is listed as passing only when
nothing is unclear and its location is at least the complex, not an area centroid.

## Run it

The listing data itself is not in this repo. The scripts expect it in sibling folders of a private project, so
this code is here to be read and reused, not to be run as is. With your own listings in the same shape:

```
python pipeline/jalankan_semua.py
```

Python 3.11 with `duckdb`, `requests` and `Pillow`. Requests to public services are spaced out and cached in `cache/`.

## Limits

- Most listings only have an area centroid as location. Flood and travel time for those are estimates, and the
  map draws them with dashed markers.
- Flood data outside Jakarta is a hazard model plus news reports. A house that is not on the list can still flood.
- Travel times are free-flow times scaled by one factor. Single routes can be off by five minutes.
- Car access and carport come from ad text and photos, not from a visit.

This is a family discussion aid. It is not a property appraisal or financial advice.

## Data sources

OpenStreetMap (toll roads, rivers), OSRM public server (routing), BPBD DKI Jakarta (flood history per RT),
BNPB InaRISK (flood hazard index), Open-Meteo (elevation), public listings on rumah123, Pinhome (one snapshot, 22 November 2026) and Threads, and news
reports quoting BPBD Kota Bekasi (listed in `data/banjir_sumber.csv`).

Photos belong to the sellers and agents who posted the listings. They are shown here only so each house can be
recognised at a glance.
