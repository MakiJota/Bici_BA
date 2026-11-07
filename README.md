# Bici BA · Explorador de movilidad en bicicleta

Interactive, bilingual (Spanish / English) platform that reconstructs and visualises how Buenos Aires moves on the public bicycle-sharing system (EcoBici), built from official open data for **2025** (3,148,375 valid trips, 403 stations).

> Origin–destination trips are **observed**. Street-level routes are **inferred**: they are plausible reconstructions on the official street network, **not GPS trajectories**.

The site has two sections, plus a methodology page:

- **Mapa de movilidad / Mobility map**: stations, directional OD arrows (station, barrio or comuna level; top 10/20/50), reconstructed routes, inferred street intensity, barrios, comunas and ciclovías. Click a station, street or territory for details.
- **Animación / Animation**: one day of trips moving along their reconstructed routes (deck.gl TripsLayer, in the style of the FlowSense viewer). Trails are white on ciclovías and grey on regular streets, the street network glows with traffic per 15 minutes, and you can switch the routing assumption, pick a **year** (every year with published trip data), a **month** (Feb, May, Sep, Nov) and a **weekday** (Tue, Wed, Fri, Sat, Sun) to see a typical non-holiday day, compare the same day across years, or focus on one station.
- **Informe de movilidad / Mobility report**: (A) overview KPIs, (B) territorial relationships (top flows, Sankey, OD heatmap), (C) temporal patterns and period comparison, (D) user characteristics, (E) distance, duration and speed, (F) station and street rankings.

Filters (months, day type, time bands, area, origin, destination, gender **or** age) are shared by the map and the report.

## Repository layout (in execution order)

| Folder | Purpose |
|---|---|
| [`pipeline/`](pipeline/) | Reproducible data pipeline, numbered in run order. Shared settings in `config.py`. |
| [`eda/`](eda/) | Exploratory analysis scripts, figures and findings ([eda/README.md](eda/README.md)). |
| [`web/`](web/) | The visualisation tool: static site (MapLibre + Plotly, no build step) with its optimised data in `web/data/`. |
| [`docs/`](docs/) | Technical and methodological documentation. |
| `data/` | `raw/` and `interim/` are git-ignored and re-created by the pipeline; `processed/` holds analytical tables. |
| [`.github/workflows/`](.github/workflows/) | GitHub Actions workflow that deploys `web/` to GitHub Pages. |

### Pipeline

| Step | Script | Output |
|---|---|---|
| 01 | `01_download.py` | Official resources and catalogue metadata, with size check and resume (`data/raw/`) |
| 02 | `02_inspect.py` | Schema, coverage and CRS of every file (`data/interim/inspection.json`) |
| 03 | `03_clean_trips.py` | Validated trips, stations, age join, [data quality report](docs/03_data_quality.md) |
| 04 | `04_geo_layers.py` | Barrios, comunas, population, station → barrio / comuna |
| 05 | `05_network.py` | Directed cycling network from `callejero` + `ciclovías` |
| 06 | `06_routing.py` | Routes for every OD pair (shortest vs infrastructure-preferred), street assignment |
| 06b | `06b_osm_comparison.py` | Independent check against OpenStreetMap bicycle routing (optional, needs internet) |
| 07 | `07_aggregate.py` | OD matrices (3 levels), territorial / station indicators, distance / duration / speed |
| 08 | `08_export_web.py` | Compact, privacy-safe data products for the browser (`web/data/`, ≈ 23 MB) |
| 09 | `09_export_animation.py` | Trip animation: one typical day per year × month × weekday, all yearly trip files (`web/data/anim/`) |

## Documentation

1. [00 · Legacy R project review](docs/00_legacy_review.md): what was reused from the 2022 attempt.
2. [01 · Data inventory and metadata](docs/01_data_inventory.md): sources, license, fields, coverage.
3. [02 · Methodology](docs/02_methodology.md): definitions, indicators, privacy safeguards, browser data model.
4. [03 · Data quality report](docs/03_data_quality.md): validation flags and exclusions (generated).
5. [04 · Network and routing](docs/04_routing.md): network rules, routing strategies, OSM comparison.

## Reproduce

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cd pipeline
python 01_download.py             # ~260 MB of official open data into data/raw
python 02_inspect.py
python 03_clean_trips.py          # ~2 min
python 04_geo_layers.py
python 05_network.py
python 06_routing.py              # ~3 min
python 06b_osm_comparison.py      # optional
python 07_aggregate.py
python 08_export_web.py
python 09_export_animation.py
cd ../eda && python 01_temporal.py && python 02_spatial.py && python 03_users_dds.py && python 04_routing_streets.py
```

Run the site locally (the browser cannot load `file://` modules):

```bash
cd web && python -m http.server 8000     # open http://localhost:8000
```

## Deployment (GitHub Pages)

1. Push to `main`. The workflow [`deploy.yml`](.github/workflows/deploy.yml) checks that the data products exist, syntax-checks the JavaScript, and publishes `web/`.
2. One-time setup: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. To refresh the data, re-run the pipeline locally (for example after changing `YEAR` in `pipeline/config.py`) and commit `web/data/`. Raw data never enters the repository.

## Data and license

Source: Gobierno de la Ciudad de Buenos Aires — [Buenos Aires Data](https://data.buenosaires.gob.ar), **CC-BY-2.5-AR** (bicicletas públicas, barrios, comunas, calles, ciclovías). Basemap © OpenStreetMap contributors © CARTO. OSM comparison data © OpenStreetMap contributors (ODbL).
