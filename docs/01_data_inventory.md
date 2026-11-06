# 01 · Data inventory and metadata

All sources were inspected with `pipeline/02_inspect.py` before use; the full machine-readable inspection is written to `data/interim/inspection.json` and the CKAN catalogue records to `data/raw/catalog_*.json`.

**Retrieved:** 2026-11-06 (UTC timestamps per file in `data/raw/download_log.json`).
**Publisher:** Gobierno de la Ciudad de Buenos Aires — Buenos Aires Data (data.buenosaires.gob.ar).
**License:** Creative Commons Attribution 2.5 Argentina (CC-BY-2.5-AR) for every dataset below. Attribution: *Fuente: Gobierno de la Ciudad de Buenos Aires — data.buenosaires.gob.ar*.

## Datasets used

| Dataset | Resource | Format | Size | Records | CRS | Coverage |
|---|---|---|---:|---:|---|---|
| [Bicicletas públicas](https://data.buenosaires.gob.ar/dataset/bicicletas-publicas) | `recorridos-realizados-2025.zip` → `Trips.csv` | CSV in ZIP | 208 MB (832 MB unzipped) | 3,156,182 trips | WGS84 lon/lat columns | 2025-01-01 → 2025-12-31 (some trips end 2026-01) |
| Bicicletas públicas | `usuarios[_-]ecobici_<year>.csv`, 2015–2025 | CSV | 1–8 MB each | 1,098,439 users | — | registrations 2015–2025 |
| [Barrios](https://data.buenosaires.gob.ar/dataset/barrios) | `barrios.geojson` | GeoJSON | 0.8 MB | 48 polygons | EPSG:4326 | City of Buenos Aires |
| Barrios | `caba_pob_barrios_2010.csv` | CSV | <1 KB | 48 | — | Census 2010 population |
| [Comunas](https://data.buenosaires.gob.ar/dataset/comunas) | `comunas.geojson` | GeoJSON | 0.6 MB | 15 (14 Polygon, 1 MultiPolygon) | EPSG:4326 | City of Buenos Aires |
| [Calles](https://data.buenosaires.gob.ar/dataset/calles) | `callejero.geojson` | GeoJSON | 23.9 MB | 31,961 LineStrings | EPSG:4326 | City of Buenos Aires |
| [Ciclovías](https://data.buenosaires.gob.ar/dataset/ciclovias) | `ciclovias.geojson` | GeoJSON | 1.0 MB | 2,764 LineStrings | EPSG:4326 | City of Buenos Aires |

Other resources inspected but not used: XLSX/SHP/CSV duplicates of the same layers, trip archives for 2010–2024 and the partial 2026 file, and `avenida_rivadavia.geojson`. **2025 is the analysis year** because it is the latest complete calendar year.

## Trips (`Trips.csv`)

| Field | Type in source | Notes |
|---|---|---|
| `Id_recorrido` | text, `"<n>BAEcobici"` | unique for all rows |
| `duracion_recorrido` | text, seconds with thousands separator (`"1,058"`) | equals end − start |
| `fecha_origen_recorrido`, `fecha_destino_recorrido` | `YYYY-MM-DD HH:MM:SS` local time | no missing values |
| `id_estacion_origen` / `_destino` | text, `"<n>BAEcobici"` | 403 stations; 1 missing destination |
| `nombre_estacion_*`, `direccion_estacion_*` | text | names prefixed with the station number |
| `long_estacion_*`, `lat_estacion_*` | float | some missing and some `0,0` destination coordinates |
| `id_usuario` | text, `"<n>BAEcobici"` | 286,322 distinct users; links to user files |
| `modelo_bicicleta` | `FIT` / `ICONIC` | bike model |
| `género` | `MALE` / `FEMALE` / `OTHER` / empty | **gender is on the trip record**; 8,601 empty |

**No age or other demographic field is present in the trip file.**

## Users (`usuarios_ecobici_<year>.csv`)

| Field | Notes |
|---|---|
| user id | named `id_usuario` (2015–18, 2024), `ID_usuario` (2019–23), `ID Cliente` (2025) |
| `genero_usuario` | `M/F/O` up to 2018, `MALE/FEMALE/OTHER` afterwards |
| `edad_usuario` | age **at registration**; contains implausible values (e.g. `-41`, `1,021`) |
| `fecha_alta`, `hora_alta` | registration date (`dd-mm-yy` up to 2018, ISO afterwards) |
| `Customer Has Dni` | 2020–2023, 2025 only; not used |

## Geographic layers

- **Barrios:** `nombre`, `comuna`, `perimetro_`, `area_metro`. 48 barrios.
- **Comunas:** `comuna`, `barrios` (list), `perimetro`, `area`. 15 comunas.
- **Callejero:** official street centrelines split at intersections. Key fields:
  - `nomoficial`, `nom_mapa` — street names.
  - `sentido` — `CRECIENTE` (12,518), `DECRECIENTE` (12,122), `DOBLE` (6,134), `PEATONAL` (1,156), `PJE. PRIVADO` (30). One-way direction is expressed **relative to house-number order** (`alt_*ini` → `alt_*fin`).
  - `tipo_c` — CALLE, AVENIDA, PASAJE, SENDERO, AUTOPISTA and ramps, …
  - `red_jerarq` — VÍA LOCAL / DISTRIBUIDORA COMPLEMENTARIA / DISTRIBUIDORA PRINCIPAL / TRONCAL.
  - `bicisenda` — populated on only **7** of 31,961 segments, so it is not usable; the official *Ciclovías* layer is used instead.
- **Ciclovías:** `nombre`, `tipo` (`Ciclovías` 2,469 = two-way; `Ciclovías mano única` 295 = one-way), `comuna`, `barrio`, `longitud_m`.

## Population

`caba_pob_barrios_2010.csv` (2010 census) is the only population table published with the barrios dataset. It is used for activity-per-resident indicators and is flagged as dated in the report.
