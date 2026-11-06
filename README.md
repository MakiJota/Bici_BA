# Bici BA · Explorador de movilidad en bicicleta

Interactive, bilingual (Spanish / English) platform that reconstructs and visualises how Buenos Aires moves on the public bicycle-sharing system (EcoBici), from official open data.

> Origin–destination trips are **observed**. Street-level routes are **inferred** (plausible reconstructions on the street network), **not GPS trajectories**.

## Repository layout (in execution order)

| Folder | Purpose |
|---|---|
| [`pipeline/`](pipeline/) | Reproducible data pipeline, numbered in run order (`01_download.py` → `08_export_web.py`). Shared settings in `config.py`. |
| [`eda/`](eda/) | Exploratory data-analysis scripts and the figures they produce (`eda/figures/`). |
| [`web/`](web/) | The visualisation tool: static site (map + report) served by GitHub Pages. Optimised data in `web/data/`. |
| [`docs/`](docs/) | Data inventory, data-quality report, methodology and routing notes. |
| `data/` | `raw/` and `interim/` are git-ignored (re-created by the pipeline); `processed/` holds analytical tables. |
| `.github/workflows/` | GitHub Actions workflow that deploys `web/` to GitHub Pages. |

## Documentation

1. [00 · Legacy R project review](docs/00_legacy_review.md)
2. [01 · Data inventory and metadata](docs/01_data_inventory.md)
3. [03 · Data quality report](docs/03_data_quality.md)

## Reproduce

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cd pipeline
python 01_download.py           # ~230 MB of official open data into data/raw
python 02_inspect.py            # schema, coverage and CRS of every file
python 03_clean_trips.py        # validated trips, stations, data-quality report
```

## Data and license

Source: Gobierno de la Ciudad de Buenos Aires — [Buenos Aires Data](https://data.buenosaires.gob.ar), CC-BY-2.5-AR. Analysis year: 2025.
