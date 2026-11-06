"""Step 06 - Route reconstruction and street-level assignment.

For every observed station pair (origin != destination) two plausible routes
are computed on the directed network of step 05:

* `shortest`  - minimum distance.
* `infra`     - infrastructure-preferred: distance weighted by cycling
                infrastructure (x0.6) and road hierarchy (x1.0-1.5).  PRIMARY.

The primary strategy provides the "estimated network distance" used for
speed and for street intensity. These are inferred routes, NOT GPS tracks.

Inputs : data/processed/trips_clean.parquet, stations_geo.parquet,
         data/interim/network_edges.parquet, network_nodes.parquet
Outputs: data/processed/pair_routes.parquet     o, d, trips, distances per strategy, overlap
         data/interim/pair_edges_<strategy>.parquet  edge sequence per pair
         data/processed/segment_flows.parquet   trips per street segment (+ hour / dow / month / gender)
         data/processed/station_snap.parquet    station -> node, snap distance
         data/processed/routing_report.json

Usage:  python pipeline/06_routing.py
"""
import json
import time

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from config import INTERIM, PROCESSED

PRIMARY = "infra"
STRATEGIES = {"shortest": "length_m", "infra": "cost_infra"}
MAX_SNAP_M = 150


def snap_stations(nodes: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    import geopandas as gpd
    from config import CRS_METRIC
    p = gpd.GeoSeries(gpd.points_from_xy(st.lon, st.lat), crs="EPSG:4326").to_crs(CRS_METRIC)
    tree = cKDTree(nodes[["x", "y"]].to_numpy())
    dist, idx = tree.query(np.c_[p.x, p.y])
    return pd.DataFrame({"station_id": st.station_id.values, "node": nodes.node.to_numpy()[idx],
                         "snap_m": dist.round(1)})


def route_all(edges: pd.DataFrame, n_nodes: int, weight: str, pairs: pd.DataFrame):
    """Return {(o_node, d_node): [edge_id, ...]} using one Dijkstra per origin node."""
    best = edges.sort_values(weight).drop_duplicates(["u", "v"])          # cheapest parallel edge
    W = sparse.csr_matrix((best[weight].to_numpy(), (best.u.to_numpy(), best.v.to_numpy())), shape=(n_nodes, n_nodes))
    eid = {(u, v): e for u, v, e in zip(best.u, best.v, best.edge_id)}
    origins = np.unique(pairs.o_node.to_numpy())
    _, pred = dijkstra(W, directed=True, indices=origins, return_predecessors=True)
    row = {o: i for i, o in enumerate(origins)}
    out = {}
    for o, d in zip(pairs.o_node, pairs.d_node):
        if (o, d) in out:
            continue
        pr = pred[row[o]]
        path, cur = [], d
        while cur != o and cur >= 0:
            prev = pr[cur]
            if prev < 0:
                path = None
                break
            path.append(eid[(prev, cur)])
            cur = prev
        out[(o, d)] = None if path is None else path[::-1]
    return out


def main() -> None:
    t0 = time.time()
    rep: dict = {}
    edges = pd.read_parquet(INTERIM / "network_edges.parquet")
    nodes = pd.read_parquet(INTERIM / "network_nodes.parquet")
    n_nodes = int(max(nodes.node.max(), edges.u.max(), edges.v.max())) + 1
    st = pd.read_parquet(PROCESSED / "stations_geo.parquet")

    snap = snap_stations(nodes, st)
    snap.to_parquet(PROCESSED / "station_snap.parquet", index=False)
    rep["snap_m"] = {k: float(v) for k, v in snap.snap_m.describe(percentiles=[.5, .9, .99]).round(1).items()}
    rep["stations_snap_over_limit"] = snap.loc[snap.snap_m > MAX_SNAP_M, "station_id"].tolist()
    node_of = snap.set_index("station_id").node

    t = pd.read_parquet(PROCESSED / "trips_clean.parquet",
                        columns=["o", "d", "valid", "round_trip", "hour", "dow", "month", "gender"])
    t = t[t.valid & ~t.round_trip].drop(columns=["valid", "round_trip"])
    t["o"], t["d"] = t.o.astype(int), t.d.astype(int)
    pairs = t.groupby(["o", "d"]).size().rename("trips").reset_index()
    pairs["o_node"] = pairs.o.map(node_of)
    pairs["d_node"] = pairs.d.map(node_of)
    rep["routable_trips"] = int(len(t))
    rep["od_pairs"] = int(len(pairs))
    same = pairs.o_node == pairs.d_node
    rep["pairs_same_node"] = int(same.sum())

    length = edges.set_index("edge_id").length_m
    infra = edges.set_index("edge_id").infra
    routes = {}
    for name, w in STRATEGIES.items():
        r = route_all(edges, n_nodes, w, pairs[~same])
        routes[name] = r
        paths = [r.get((a, b)) if a != b else [] for a, b in zip(pairs.o_node, pairs.d_node)]
        pairs[f"ok_{name}"] = [p is not None for p in paths]
        pairs[f"dist_{name}_m"] = [length.loc[p].sum() if p else (0.0 if p == [] else np.nan) for p in paths]
        pairs[f"infra_share_{name}"] = [float((length.loc[p] * infra.loc[p]).sum() / length.loc[p].sum()) if p else np.nan for p in paths]
        pd.DataFrame({"o": pairs.o, "d": pairs.d, "edges": [p if p else [] for p in paths]}).to_parquet(
            INTERIM / f"pair_edges_{name}.parquet", index=False)
        rep[f"routing_failures_{name}"] = int((~pairs[f"ok_{name}"]).sum())
        print(f"{name}: routed {len(r):,} pairs in {time.time() - t0:.0f}s")

    # overlap between strategies (share of primary route length also in shortest route)
    ov = []
    for a, b in zip(pairs.o_node, pairs.d_node):
        p1, p2 = routes["infra"].get((a, b)), routes["shortest"].get((a, b))
        if not p1 or not p2:
            ov.append(np.nan)
            continue
        common = set(p1) & set(p2)
        ov.append(float(length.loc[list(common)].sum() / length.loc[p1].sum()))
    pairs["overlap_infra_vs_shortest"] = ov
    pairs.drop(columns=["o_node", "d_node"]).to_parquet(PROCESSED / "pair_routes.parquet", index=False)

    w = pairs.trips
    def wmean(c):
        m = pairs[c].notna()
        return round(float(np.average(pairs.loc[m, c], weights=w[m])), 4)
    rep["trip_weighted"] = {
        "dist_shortest_m": wmean("dist_shortest_m"), "dist_infra_m": wmean("dist_infra_m"),
        "infra_share_shortest": wmean("infra_share_shortest"), "infra_share_infra": wmean("infra_share_infra"),
        "overlap_infra_vs_shortest": wmean("overlap_infra_vs_shortest"),
    }
    rep["detour_infra_vs_shortest"] = round(rep["trip_weighted"]["dist_infra_m"] / rep["trip_weighted"]["dist_shortest_m"] - 1, 4)

    # --- Street-level assignment (primary + shortest totals) ---------------
    seg_of = edges.set_index("edge_id").seg_id
    pair_idx = pd.MultiIndex.from_frame(pairs[["o", "d"]])
    t_idx = pd.MultiIndex.from_frame(t[["o", "d"]])
    t["pair"] = pair_idx.get_indexer(t_idx)

    def incidence(name):
        pe = pd.read_parquet(INTERIM / f"pair_edges_{name}.parquet")
        rows = np.repeat(np.arange(len(pe)), pe.edges.map(len))
        cols = np.concatenate([np.asarray(e, dtype=np.int64) for e in pe.edges if len(e)]) if len(rows) else np.array([], int)
        segs = seg_of.loc[cols].to_numpy()
        seg_ids, seg_col = np.unique(segs, return_inverse=True)
        M = sparse.csr_matrix((np.ones(len(rows)), (rows, seg_col)), shape=(len(pe), len(seg_ids)))
        M.data[:] = 1  # a route crossing a segment twice counts once
        return M, seg_ids

    def by(dim, n, offset=0):
        X = sparse.csr_matrix((np.ones(len(t)), (t.pair.to_numpy(), t[dim].astype(int).to_numpy() - offset)),
                              shape=(len(pairs), n))
        return X

    M, seg_ids = incidence(PRIMARY)
    flows = pd.DataFrame({"seg_id": seg_ids})
    flows["trips"] = np.asarray(M.T @ pairs.trips.to_numpy()).ravel()
    for dim, n, off in (("hour", 24, 0), ("dow", 7, 0), ("month", 12, 1)):
        A = (M.T @ by(dim, n, off)).toarray().astype(np.int32)
        for k in range(n):
            flows[f"{dim}_{k + off}"] = A[:, k]
    g = t.gender.astype(str).map({"MALE": 0, "FEMALE": 1, "OTHER": 2}).fillna(3).astype(int)
    G = sparse.csr_matrix((np.ones(len(t)), (t.pair.to_numpy(), g.to_numpy())), shape=(len(pairs), 4))
    A = (M.T @ G).toarray().astype(np.int32)
    for k, lab in enumerate(["male", "female", "other", "unknown"]):
        flows[f"gender_{lab}"] = A[:, k]

    Ms, seg_s = incidence("shortest")
    sh = pd.Series(np.asarray(Ms.T @ pairs.trips.to_numpy()).ravel(), index=seg_s, name="trips_shortest")
    flows = flows.merge(sh, left_on="seg_id", right_index=True, how="outer").fillna(0)
    flows["share"] = flows.trips / rep["routable_trips"]
    flows = flows.sort_values("trips", ascending=False)
    flows.to_parquet(PROCESSED / "segment_flows.parquet", index=False)
    rep["segments_with_flow"] = int((flows.trips > 0).sum())
    top = flows.head(200)
    rep["top200_segments_rank_overlap_with_shortest"] = round(
        len(set(top.seg_id) & set(flows.nlargest(200, "trips_shortest").seg_id)) / 200, 3)
    rep["runtime_s"] = round(time.time() - t0)
    (PROCESSED / "routing_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
