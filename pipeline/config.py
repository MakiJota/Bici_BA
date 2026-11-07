"""Shared configuration for the Bici BA data pipeline.

All paths are relative to the repository root so the pipeline is reproducible
on any machine. Raw downloads live in data/raw (git-ignored); intermediate
artefacts in data/interim (git-ignored); analytical outputs in data/processed;
and the small, privacy-safe products served to the browser in web/data.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
WEB_DATA = ROOT / "web" / "data"
DOCS = ROOT / "docs"

for _p in (RAW, INTERIM, PROCESSED, WEB_DATA, DOCS):
    _p.mkdir(parents=True, exist_ok=True)

# Analysis year. 2025 is the most recent complete calendar year published.
YEAR = 2025

CKAN_API = "https://data.buenosaires.gob.ar/api/3/action/package_show?id={}"
CKAN_DATASETS = ["bicicletas-publicas", "barrios", "comunas", "calles", "ciclovias"]
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (bici-ba-pipeline)"}

CDN = "https://cdn.buenosaires.gob.ar/datosabiertos/datasets"
SOURCES = {
    "trips": f"{CDN}/transporte-y-obras-publicas/bicicletas-publicas/recorridos-realizados-{YEAR}.zip",
    "users": f"{CDN}/transporte-y-obras-publicas/bicicletas-publicas/usuarios_ecobici_{YEAR}.csv",
    "barrios": f"{CDN}/innovacion-transformacion-digital/barrios/barrios.geojson",
    "comunas": f"{CDN}/innovacion-transformacion-digital/comunas/comunas.geojson",
    "calles": f"{CDN}/jefatura-de-gabinete-de-ministros/calles/callejero.geojson",
    "barrios_poblacion": f"{CDN}/barrios/caba_pob_barrios_2010.csv",
    # Official cycling infrastructure. The street network's own `bicisenda`
    # field is populated on only 7 of 31,961 segments, so this layer is needed.
    "ciclovias": f"{CDN}/transporte-y-obras-publicas/ciclovias/ciclovias.geojson",
}

# Each yearly user file lists only the users who *registered* that year, so a
# 2025 trip by someone who joined in 2019 needs the 2019 file to recover age.
# (Lesson taken from the legacy R project, which merged all yearly files.)
USER_YEARS = range(2015, YEAR + 1)
for _y in USER_YEARS:
    _sep = "-" if _y <= 2018 else "_"
    SOURCES[f"users_{_y}"] = f"{CDN}/transporte-y-obras-publicas/bicicletas-publicas/usuarios{_sep}ecobici{_sep}{_y}.csv"
del SOURCES["users"]  # superseded by users_<year>

# Projected CRS for metric operations: POSGAR 2007 / Argentina 5 is a common
# choice; for a city-scale analysis UTM 21S (EPSG:32721) is simpler and exact enough.
CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:32721"

# Cleaning thresholds (documented in docs/03_data_quality.md)
MIN_DURATION_S = 60            # under 1 minute: dock tests / immediate returns
MAX_DURATION_S = 4 * 3600      # over 4 hours: lost bikes / unreturned
MAX_SPEED_KMH = 35             # estimated route speed above this is implausible

# Privacy safeguards for demographic data
#  * MIN_PUBLISH: in published demographic cubes, a cell with fewer trips is
#    recoded to the category "suppressed" (totals stay correct).
#  * MIN_CELL: any demographic figure shown in the report or computed in the
#    browser from fewer trips is displayed as "n < MIN_CELL".
MIN_PUBLISH = 10
MIN_CELL = 30

# Trip animation (web "Animación" tab, step 09). For every year with trip data,
# four months and five weekdays; for each (year, month, weekday) one TYPICAL
# date is published: not a public holiday or bridge day (Argentine calendar,
# `holidays` package), with the trip count closest to the median of that
# weekday in that month. Older years are routed on today's street and
# bike-lane network (the ciclovías layer has no construction date).
ANIM_YEARS = range(2011, YEAR + 1)
ANIM_MONTHS = [2, 5, 9, 11]          # Feb, May, Sep, Nov
ANIM_DOWS = [1, 2, 4, 5, 6]          # Tue, Wed, Fri, Sat, Sun (Monday = 0)
for _y in ANIM_YEARS:
    if _y != YEAR:
        _ext = "csv" if _y <= 2013 else "zip"
        SOURCES[f"trips_{_y}"] = f"{CDN}/transporte-y-obras-publicas/bicicletas-publicas/recorridos-realizados-{_y}.{_ext}"

# Hour bands used by the browser cubes: [start, end)
HOUR_BANDS = [(0, 7), (7, 10), (10, 14), (14, 17), (17, 20), (20, 24)]
