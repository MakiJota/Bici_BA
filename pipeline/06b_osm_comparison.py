"""Step 06b - Compare official-network routes with OpenStreetMap bicycle routing.

Downloads the OSM `bike` network for the city (OSMnx / Overpass), routes the
500 busiest station pairs by distance and compares route length with the two
strategies of step 06. This mirrors the legacy R approach (dodgr + OSM
bicycle profile) and serves as an external plausibility check. It is optional:
if Overpass is unreachable the step records the failure and the pipeline
continues.

Outputs: data/processed/osm_comparison.json, data/processed/osm_comparison_pairs.parquet

Usage:  python pipeline/06b_osm_comparison.py
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from config import CRS_METRIC, INTERIM, PROCESSED, RAW

N_PAIRS = 500


def main() -> None:
    rep = {"n_pairs": N_PAIRS}
    try:
        import networkx as nx
        import osmnx as ox
        cache = INTERIM / "osm_bike.graphml"
        if cache.exists():
            G = ox.load_graphml(cache)
        else:
            city = gpd.read_file(RAW / "comunas.geojson").to_crs(4326).union_all()
            G = ox.graph_from_polygon(city.buffer(0.005), network_type="bike", simplify=True)
            ox.save_graphml(G, cache)
        rep["osm_retrieved"] = "Overpass API via OSMnx " + ox.__version__
        rep["osm_nodes"], rep["osm_edges"] = G.number_of_nodes(), G.number_of_edges()
        G = ox.project_graph(G, to_crs=CRS_METRIC)  # projected -> nearest-node search via scipy
        pr = pd.read_parquet(PROCESSED / "pair_routes.parquet").nlargest(N_PAIRS, "trips")
        st = pd.read_parquet(PROCESSED / "stations_geo.parquet").set_index("station_id")
        xy = gpd.GeoSeries(gpd.points_from_xy(st.lon, st.lat), index=st.index, crs=4326).to_crs(CRS_METRIC)
        on = ox.distance.nearest_nodes(G, xy.loc[pr.o].x.values, xy.loc[pr.o].y.values)
        dn = ox.distance.nearest_nodes(G, xy.loc[pr.d].x.values, xy.loc[pr.d].y.values)
        dist = []
        for a, b in zip(on, dn):
            try:
                dist.append(nx.shortest_path_length(G, a, b, weight="length"))
            except nx.NetworkXNoPath:
                dist.append(np.nan)
        pr["dist_osm_bike_m"] = dist
        pr.to_parquet(PROCESSED / "osm_comparison_pairs.parquet", index=False)
        ok = pr.dist_osm_bike_m.notna() & (pr.dist_shortest_m > 0)
        r1 = pr.loc[ok, "dist_osm_bike_m"] / pr.loc[ok, "dist_shortest_m"]
        r2 = pr.loc[ok, "dist_osm_bike_m"] / pr.loc[ok, "dist_infra_m"]
        rep.update({
            "status": "ok",
            "pairs_routed": int(ok.sum()),
            "median_ratio_osm_to_official_shortest": round(float(r1.median()), 3),
            "median_ratio_osm_to_official_infra": round(float(r2.median()), 3),
            "p10_p90_ratio_osm_to_shortest": [round(float(r1.quantile(.1)), 3), round(float(r1.quantile(.9)), 3)],
            "trip_weighted_dist_m": {
                "osm_bike": round(float(np.average(pr.loc[ok, "dist_osm_bike_m"], weights=pr.loc[ok, "trips"])), 1),
                "official_shortest": round(float(np.average(pr.loc[ok, "dist_shortest_m"], weights=pr.loc[ok, "trips"])), 1),
                "official_infra": round(float(np.average(pr.loc[ok, "dist_infra_m"], weights=pr.loc[ok, "trips"])), 1),
            },
        })
    except Exception as e:  # network unavailable, Overpass timeout, ...
        rep.update({"status": "failed", "error": repr(e)})
    (PROCESSED / "osm_comparison.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
