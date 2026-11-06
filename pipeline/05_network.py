"""Step 05 - Directed cycling network from the official street centrelines.

Inputs : data/raw/callejero.geojson, data/raw/ciclovias.geojson
Outputs: data/interim/network_edges.parquet   directed edges (u, v, length, weights, attributes)
         data/interim/network_nodes.parquet   node id -> x, y (EPSG:32721) and lon, lat
         data/processed/network_segments.parquet  one row per street segment (geometry WKB, attributes)
         data/processed/network_report.json

Rules (see docs/04_routing.md):
* Direction. Segments are digitised from low to high house numbers (verified:
  99.996% have alt_ini < alt_fin; known one-way avenues match). CRECIENTE ->
  along the geometry, DECRECIENTE -> against it, DOBLE -> both ways.
* Excluded: AUTOPISTA and its ramps (bicycles are not allowed), private passages.
* PEATONAL / pedestrian streets: kept in both directions with a 3x cost
  (walking the bike), so the graph stays connected without favouring them.
* Cycling infrastructure: a segment is a ciclovía when at least half of its
  length lies within 10 m of an official ciclovía line. A two-way ciclovía on
  a one-way street adds the contraflow edge for bicycles.

Usage:  python pipeline/05_network.py
"""
import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd

from config import CRS_METRIC, CRS_WGS84, INTERIM, PROCESSED, RAW

EXCLUDED_TYPES = {"AUTOPISTA", "BAJADA AUTOPISTA", "SUBIDA AUTOPISTA", "ENLACE AUTOPISTA"}
EXCLUDED_SENTIDO = {"PJE. PRIVADO"}
PEDESTRIAN_TYPES = {"CALLE PEATONAL", "PASAJE PEATONAL"}
INFRA_BUFFER_M = 10
INFRA_MIN_SHARE = 0.5
SNAP_GRID_M = 1.0          # endpoints closer than this are the same node

# Cost factors for the "infrastructure-preferred" strategy (multiplied by length)
COST_INFRA = 0.6           # a metre of ciclovía "feels" like 0.6 m of street
COST_HIERARCHY = {         # mixed traffic on busier roads is less attractive
    "VÍA LOCAL": 1.0,
    "VÍA DISTRIBUIDORA COMPLEMENTARIA": 1.15,
    "VÍA DISTRIBUIDORA PRINCIPAL": 1.3,
    "VÍA TRONCAL": 1.5,
}
COST_PEDESTRIAN = 3.0


def main() -> None:
    rep: dict = {}
    s = gpd.read_file(RAW / "callejero.geojson").to_crs(CRS_METRIC)
    rep["segments_raw"] = int(len(s))
    s["tipo_c"] = s.tipo_c.fillna("")
    s["sentido"] = s.sentido.fillna("DOBLE")
    drop = s.tipo_c.isin(EXCLUDED_TYPES) | s.sentido.isin(EXCLUDED_SENTIDO) | s.geometry.is_empty
    rep["segments_excluded"] = {
        "autopista_and_ramps": int(s.tipo_c.isin(EXCLUDED_TYPES).sum()),
        "private_passage": int(s.sentido.isin(EXCLUDED_SENTIDO).sum()),
    }
    s = s[~drop].copy()
    s["seg_id"] = s["id"].astype(int)
    s["length_m"] = s.length
    s["pedestrian"] = (s.sentido == "PEATONAL") | s.tipo_c.isin(PEDESTRIAN_TYPES)

    # --- Cycling infrastructure ------------------------------------------
    cv = gpd.read_file(RAW / "ciclovias.geojson").to_crs(CRS_METRIC)
    cv["two_way"] = cv.tipo.str.contains("mano única", case=False).map({True: False, False: True})
    buf = cv[["two_way", "geometry"]].copy()
    buf["geometry"] = buf.buffer(INFRA_BUFFER_M)
    inter = gpd.overlay(s[["seg_id", "geometry"]], buf, how="intersection", keep_geom_type=True)
    inter["ilen"] = inter.length
    share = inter.groupby("seg_id").ilen.sum() / s.set_index("seg_id").length_m
    two_way = inter.groupby("seg_id").two_way.any()
    s["infra"] = s.seg_id.map(share.clip(upper=1)).fillna(0) >= INFRA_MIN_SHARE
    s["infra_two_way"] = s.infra & s.seg_id.map(two_way).fillna(False).astype(bool)
    rep["ciclovia_lines"] = int(len(cv))
    rep["ciclovia_km_official"] = round(float(cv.length.sum() / 1000), 1)
    rep["segments_with_infra"] = int(s.infra.sum())
    rep["street_km_with_infra"] = round(float(s.loc[s.infra, "length_m"].sum() / 1000), 1)

    # --- Nodes: snap endpoints to a 1 m grid --------------------------------
    first = s.geometry.apply(lambda g: g.coords[0])
    last = s.geometry.apply(lambda g: g.coords[-1])
    key = lambda c: (round(c[0] / SNAP_GRID_M), round(c[1] / SNAP_GRID_M))
    keys = pd.Index(pd.unique(pd.concat([first.map(key), last.map(key)])))
    node_of = {k: i for i, k in enumerate(keys)}
    s["a"] = first.map(key).map(node_of)
    s["b"] = last.map(key).map(node_of)
    # house numbers decreasing along the geometry: swap meaning of direction
    flipped = (s.alt_izqini > s.alt_izqfin) & (s.alt_izqfin > 0)
    rep["segments_digitised_against_numbering"] = int(flipped.sum())

    hier = s.red_jerarq.map(COST_HIERARCHY).fillna(1.0)
    cost = s.length_m * np.where(s.infra, COST_INFRA, hier) * np.where(s.pedestrian, COST_PEDESTRIAN, 1.0)
    s["cost_infra"] = cost

    fwd_ok = s.sentido.isin(["DOBLE", "PEATONAL"]) | ((s.sentido == "CRECIENTE") ^ flipped) | (s.sentido == "")
    bwd_ok = s.sentido.isin(["DOBLE", "PEATONAL"]) | ((s.sentido == "DECRECIENTE") ^ flipped)
    contra_f = ~fwd_ok & s.infra_two_way
    contra_b = ~bwd_ok & s.infra_two_way
    rep["contraflow_edges_added"] = int(contra_f.sum() + contra_b.sum())

    cols = ["seg_id", "length_m", "cost_infra", "infra", "pedestrian"]
    e_f = s.loc[fwd_ok | contra_f, cols + ["a", "b"]].rename(columns={"a": "u", "b": "v"})
    e_f["contraflow"] = contra_f[fwd_ok | contra_f].values
    e_b = s.loc[bwd_ok | contra_b, cols + ["a", "b"]].rename(columns={"b": "u", "a": "v"})
    e_b["contraflow"] = contra_b[bwd_ok | contra_b].values
    e_f["forward"], e_b["forward"] = True, False
    edges = pd.concat([e_f, e_b], ignore_index=True)
    edges = edges[edges.u != edges.v]
    rep["directed_edges"] = int(len(edges))
    rep["nodes"] = int(len(keys))

    # --- Connectivity: keep the largest strongly connected component ---------
    G = nx.DiGraph()
    G.add_edges_from(zip(edges.u, edges.v))
    sccs = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    main_cc = sccs[0]
    rep["scc_count"] = len(sccs)
    rep["largest_scc_nodes"] = len(main_cc)
    rep["largest_scc_share_nodes"] = round(len(main_cc) / G.number_of_nodes(), 4)
    keep = edges.u.isin(main_cc) & edges.v.isin(main_cc)
    rep["edges_outside_largest_scc"] = int((~keep).sum())
    edges = edges[keep].reset_index(drop=True)
    edges["edge_id"] = np.arange(len(edges), dtype=np.int32)

    nodes = pd.DataFrame(list(keys), columns=["gx", "gy"])
    nodes["node"] = np.arange(len(nodes))
    nodes["x"], nodes["y"] = nodes.gx * SNAP_GRID_M, nodes.gy * SNAP_GRID_M
    nodes = nodes[nodes.node.isin(main_cc)]
    ll = gpd.GeoSeries(gpd.points_from_xy(nodes.x, nodes.y), crs=CRS_METRIC).to_crs(CRS_WGS84)
    nodes["lon"], nodes["lat"] = ll.x.values, ll.y.values
    nodes[["node", "x", "y", "lon", "lat"]].to_parquet(INTERIM / "network_nodes.parquet", index=False)
    edges.to_parquet(INTERIM / "network_edges.parquet", index=False)

    seg = s[["seg_id", "nomoficial", "nom_mapa", "tipo_c", "sentido", "red_jerarq", "comuna", "barrio",
             "length_m", "infra", "infra_two_way", "pedestrian", "geometry"]].to_crs(CRS_WGS84)
    seg["in_network"] = seg.seg_id.isin(edges.seg_id)
    seg.to_parquet(PROCESSED / "network_segments.parquet", index=False)

    rep["network_km"] = round(float(s.loc[s.seg_id.isin(edges.seg_id), "length_m"].sum() / 1000), 1)
    rep["cost_factors"] = {"infra": COST_INFRA, "hierarchy": COST_HIERARCHY, "pedestrian": COST_PEDESTRIAN}
    (PROCESSED / "network_report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
