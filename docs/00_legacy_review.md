# 00 · Review of the legacy R project (2022–2023)

A previous attempt in R (`Eco_bici/`, kept locally and **excluded from git**: ~4.5 GB of raw CSVs and `.RData`) was reviewed before writing this pipeline.

## What it contained

| Area | Files | Approach |
|---|---|---|
| Trips 2014–2021 | `trips.R`, `recorridos/` | Parsed `"X days HH:MM:SS"` durations; hourly / weekday / monthly counts per station |
| Users 2015–2020 | `users.R`, `usuarios/` | Merged all yearly user files; harmonised gender codes (`M`/`MALE`, `F`/`FEMALE`, `O`/`OTRO`) and date formats |
| Stations | `stations.R`, `estaciones/` | Station list from the old `nuevas-estaciones-bicicletas-publicas` resource |
| Routing | `routing.R`, `routing_functoin.R`, `clean_routing.R` | `dodgr` on OpenStreetMap streets (`osmdata`) with the `bicycle` weighting profile; largest connected component only; CRS EPSG:5348 |
| Visual | `animate_routes.R`, `animation_shiny.R`, `time_in shiny.R`, `trips_route_data.R` | gganimate `transition_reveal` of a path; Shiny date slider with `animate = TRUE`; leaflet-timeline (features with start / end times); routes from one station (227) to five destinations |

## What was reused

1. **Age requires every yearly user file.** Each `usuarios_ecobici_<year>` file lists only users who *registered* that year.
   Joining 2025 trips to the 2025 user file alone matches 27 % of trips; joining the union of 2015–2025 files matches **93.7 %**.
   `pipeline/01_download.py` therefore fetches all yearly user files from the official portal (not from the legacy folder, for reproducibility).
2. **Schema drift handling.** Column names and formats change across years (`id_usuario` / `ID_usuario` / `ID Cliente`; `dd-mm-yy` vs `yyyy-mm-dd`; `M/F/O` vs `MALE/FEMALE/OTHER`). The same normalisation logic is implemented in `pipeline/03_clean_trips.py`.
3. **OSM bicycle-profile routing as a comparison.** The legacy `dodgr` + OSM `bicycle` profile is reproduced with OSMnx as the *alternative* routing strategy. The primary network is now the official `callejero`, as required.
4. **Keep only the main connected component** before routing.

5. **Trip animation.** The legacy prototypes (timeline of features with start and end, play slider, path reveal, routes from one station) are implemented together in the *Animación* tab: every trip has an observed start and end, follows its reconstructed route, and can be filtered to one station.

## What was not reused

- The 2022 station list (stations have since been added and relocated). Station coordinates now come from the 2025 trip records.
- Hard-coded `setwd()` paths and in-memory `.RData` state: replaced by a scripted, reproducible pipeline.
- Multi-colour palettes: the new visual identity is monochrome.
