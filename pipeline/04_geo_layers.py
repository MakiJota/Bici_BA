"""Step 04 - Geographic layers: barrios, comunas, population and station assignment.

Inputs : data/raw/barrios.geojson, comunas.geojson, caba_pob_barrios_2010.csv,
         data/processed/stations.parquet
Outputs: data/processed/stations_geo.parquet  stations + barrio + comuna
         data/processed/territories.parquet   barrio/comuna attributes (area, population)
         web/data/barrios.geojson, web/data/comunas.geojson  (simplified, ~5 m)
         data/processed/geo_report.json

Usage:  python pipeline/04_geo_layers.py
"""
import json
import unicodedata

import geopandas as gpd
import pandas as pd

from config import CRS_METRIC, CRS_WGS84, PROCESSED, RAW, WEB_DATA


def norm(s: str) -> str:
    """Accent- and case-insensitive key for matching barrio names across files."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace(".", " ").split())


def main() -> None:
    rep = {}
    barrios = gpd.read_file(RAW / "barrios.geojson").to_crs(CRS_WGS84)
    comunas = gpd.read_file(RAW / "comunas.geojson").to_crs(CRS_WGS84)
    pop = pd.read_csv(RAW / "caba_pob_barrios_2010.csv", encoding="utf-8-sig")

    barrios = barrios.rename(columns={"nombre": "barrio"})[["barrio", "comuna", "geometry"]]
    barrios["comuna"] = barrios.comuna.astype(int)
    barrios["key"] = barrios.barrio.map(norm)
    # Name differences between the two official files, resolved explicitly
    aliases = {"BOCA": "LA BOCA"}
    pop["key"] = pop.BARRIO.map(norm).replace(aliases)
    barrios = barrios.merge(pop[["key", "POBLACION"]].rename(columns={"POBLACION": "population_2010"}), on="key", how="left")
    rep["barrios_without_population"] = barrios.loc[barrios.population_2010.isna(), "barrio"].tolist()

    comunas = comunas[["comuna", "geometry"]].copy()
    comunas["comuna"] = comunas.comuna.astype(int)
    cpop = barrios.groupby("comuna").population_2010.sum(min_count=1)
    comunas = comunas.merge(cpop.rename("population_2010"), left_on="comuna", right_index=True, how="left")

    for g in (barrios, comunas):
        g["area_km2"] = g.to_crs(CRS_METRIC).area / 1e6

    # --- Assign stations -------------------------------------------------
    st = pd.read_parquet(PROCESSED / "stations.parquet")
    pts = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st.lon, st.lat), crs=CRS_WGS84)
    j = gpd.sjoin(pts, barrios[["barrio", "comuna", "geometry"]], how="left", predicate="within").drop(columns="index_right")
    miss = j.barrio.isna()
    rep["stations_outside_polygons"] = int(miss.sum())
    if miss.any():  # stations on the city edge / riverside: nearest barrio within 500 m
        near = gpd.sjoin_nearest(
            pts[miss].to_crs(CRS_METRIC), barrios[["barrio", "comuna", "geometry"]].to_crs(CRS_METRIC),
            how="left", max_distance=500, distance_col="dist_m").drop(columns="index_right")
        near = near[~near.index.duplicated()]
        j.loc[miss, ["barrio", "comuna"]] = near[["barrio", "comuna"]].values
        rep["stations_assigned_by_nearest"] = near[["station_id", "name", "dist_m"]].round(1).to_dict("records")
    rep["stations_unassigned"] = int(j.barrio.isna().sum())
    j["comuna"] = j.comuna.astype("Int8")
    rep["stations_per_comuna"] = {int(k): int(v) for k, v in j.comuna.value_counts().sort_index().items()}
    rep["barrios_with_stations"] = int(j.barrio.nunique())
    pd.DataFrame(j.drop(columns="geometry")).to_parquet(PROCESSED / "stations_geo.parquet", index=False)

    terr = pd.concat([
        pd.DataFrame({"level": "barrio", "unit": barrios.barrio, "comuna": barrios.comuna,
                      "area_km2": barrios.area_km2, "population_2010": barrios.population_2010}),
        pd.DataFrame({"level": "comuna", "unit": comunas.comuna.astype(str), "comuna": comunas.comuna,
                      "area_km2": comunas.area_km2, "population_2010": comunas.population_2010}),
    ])
    terr.to_parquet(PROCESSED / "territories.parquet", index=False)

    # --- Web layers: simplify in metres, round coordinates -----------------
    for name, g in (("barrios", barrios.drop(columns="key")), ("comunas", comunas)):
        w = g.to_crs(CRS_METRIC)
        w["geometry"] = w.simplify(5, preserve_topology=True)
        w = w.to_crs(CRS_WGS84)
        w["area_km2"] = w.area_km2.round(2)
        w.to_file(WEB_DATA / f"{name}.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    (PROCESSED / "geo_report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
