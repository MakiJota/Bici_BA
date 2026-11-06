"""Step 08 - Export optimised, privacy-safe data products for the web app.

No row-level trip, user id, exact timestamp or demographic cell below
MIN_PUBLISH trips is written. Everything lands in web/data/.

Files (format contract with web/js/data.js):
  meta.json            KPIs, dictionaries, routing/quality reports, static report tables
  stations.json        [{i, id, name, address, barrio, comuna, lat, lon}]  (i = cube index)
  pairs.bin.gz         columnar Uint16: o[P] d[P] dist_infra_m[P] dist_shortest_m[P]
  od.bin.gz            columnar: Uint32 pair[R], Uint32 dur_s[R], Uint16 n[R], Uint8 key[R]
                       key = (month-1)*12 + weekend*6 + hour_band
  demo_gender.json, demo_age.json   comuna-level cubes: {oc, dc, key, cat, n, dur, dist}
                       cells < MIN_PUBLISH trips recoded to cat = "suppressed"
  calendar.json        {doy, hour, oc, n, dur}  (day of year x hour x origin comuna)
  segments.geojson     routed street segments: {k, name, infra, tipo, tot_i, tot_s}
  seg_flows.bin.gz     Uint32[K*144] trips per segment and key (primary strategy)
  edge_seg.bin.gz      Uint16 directed edge id -> segment k
  routes/<i>.bin.gz    route trees from origin station i (layout documented below)
  ciclovias.geojson    official cycling infrastructure (simplified)
  station_time.json    per station: departures / arrivals by hour (weekday, weekend) and month

Usage:  python pipeline/08_export_web.py
"""
import gzip
import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd

from config import (CRS_METRIC, CRS_WGS84, HOUR_BANDS, INTERIM, MIN_CELL,
                    MIN_PUBLISH, PROCESSED, RAW, WEB_DATA, YEAR)

GENDERS = ["MALE", "FEMALE", "OTHER", "UNKNOWN", "suppressed"]
AGES = ["16-24", "25-34", "35-44", "45-54", "55-64", "65+", "unknown", "suppressed"]


def hour_band(h: pd.Series) -> np.ndarray:
    edges = [b[0] for b in HOUR_BANDS[1:]]
    return np.searchsorted(edges, h.to_numpy(), side="right")


def write_bin(path, arrays) -> int:
    raw = b"".join(np.ascontiguousarray(a).tobytes() for a in arrays)
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(raw)
    return path.stat().st_size


def dump(name, obj) -> int:
    p = WEB_DATA / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=_default), encoding="utf-8")
    return p.stat().st_size


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else round(float(o), 4)
    raise TypeError(type(o))


def clean_records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records", double_precision=4))


def main() -> None:
    sizes = {}
    if (WEB_DATA / "routes").exists():
        shutil.rmtree(WEB_DATA / "routes")

    # --- Stations ---------------------------------------------------------
    st = pd.read_parquet(PROCESSED / "stations_geo.parquet").sort_values("station_id").reset_index(drop=True)
    st["i"] = np.arange(len(st))
    idx = st.set_index("station_id").i
    sizes["stations.json"] = dump("stations.json", [
        {"i": int(r.i), "id": int(r.station_id), "name": r["name"], "address": r.address,
         "barrio": r.barrio, "comuna": int(r.comuna), "lat": round(r.lat, 6), "lon": round(r.lon, 6)}
        for _, r in st.iterrows()])

    # --- Trips (valid) -> cubes --------------------------------------------
    t = pd.read_parquet(PROCESSED / "trips_clean.parquet",
                        columns=["o", "d", "valid", "start", "duration_s", "month", "weekend", "hour", "gender", "age_group"])
    t = t[t.valid].drop(columns="valid")
    t["oi"], t["di"] = t.o.astype(int).map(idx), t.d.astype(int).map(idx)
    t["oc"] = t.o.astype(int).map(st.set_index("station_id").comuna).astype(int)
    t["dc"] = t.d.astype(int).map(st.set_index("station_id").comuna).astype(int)
    t["key"] = ((t.month.astype(int) - 1) * 12 + t.weekend.astype(int) * 6 + hour_band(t.hour.astype(int))).astype(np.uint8)

    pr = pd.read_parquet(PROCESSED / "pair_routes.parquet")
    pairs = t.groupby(["oi", "di"]).size().rename("trips").reset_index()
    pairs["o"], pairs["d"] = st.station_id.to_numpy()[pairs.oi], st.station_id.to_numpy()[pairs.di]
    pairs = pairs.merge(pr[["o", "d", "dist_infra_m", "dist_shortest_m"]], on=["o", "d"], how="left").fillna(0)
    pairs["p"] = np.arange(len(pairs))
    sizes["pairs.bin.gz"] = write_bin(WEB_DATA / "pairs.bin.gz", [
        pairs.oi.to_numpy(np.uint16), pairs.di.to_numpy(np.uint16),
        pairs.dist_infra_m.round().clip(0, 65535).to_numpy(np.uint16),
        pairs.dist_shortest_m.round().clip(0, 65535).to_numpy(np.uint16)])
    pmap = pd.Series(pairs.p.to_numpy(), index=pd.MultiIndex.from_frame(pairs[["oi", "di"]]))
    t["p"] = pmap.reindex(pd.MultiIndex.from_frame(t[["oi", "di"]])).to_numpy()

    od = t.groupby(["p", "key"]).agg(n=("o", "size"), dur=("duration_s", "sum")).reset_index()
    assert od.n.max() < 65535 and od.dur.max() < 2**32
    sizes["od.bin.gz"] = write_bin(WEB_DATA / "od.bin.gz", [
        od.p.to_numpy(np.uint32), od.dur.to_numpy(np.uint32), od.n.to_numpy(np.uint16), od.key.to_numpy(np.uint8)])

    # distance per trip for demographic cubes
    dist = pairs.set_index("p").dist_infra_m
    t["dist"] = t.p.map(dist).to_numpy()

    def demo_cube(col, cats):
        x = t[["oc", "dc", "key", col, "duration_s", "dist"]].copy()
        x["cat"] = x[col].astype("string").fillna("UNKNOWN" if col == "gender" else "unknown")
        g = x.groupby(["oc", "dc", "key", "cat"]).agg(n=("duration_s", "size"),
                                                      dur=("duration_s", "sum"), dist=("dist", "sum")).reset_index()
        small = g.n < MIN_PUBLISH
        g.loc[small, "cat"] = "suppressed"
        g = g.groupby(["oc", "dc", "key", "cat"], as_index=False)[["n", "dur", "dist"]].sum()
        g["cat"] = g.cat.map({c: i for i, c in enumerate(cats)}).astype(int)
        rep = {"cells": int(len(g)), "suppressed_trips": int(g.loc[g.cat == cats.index("suppressed"), "n"].sum())}
        return {c: g[c].round().astype(int).tolist() for c in ["oc", "dc", "key", "cat", "n", "dur", "dist"]}, rep

    dg, rep_g = demo_cube("gender", GENDERS)
    da, rep_a = demo_cube("age_group", AGES)
    sizes["demo_gender.json"] = dump("demo_gender.json", dg)
    sizes["demo_age.json"] = dump("demo_age.json", da)

    t["doy"] = t.start.dt.day_of_year
    cal = t.groupby(["doy", "hour", "oc"]).agg(n=("o", "size"), dur=("duration_s", "sum")).reset_index()
    sizes["calendar.json"] = dump("calendar.json", {c: cal[c].astype(int).tolist() for c in cal.columns})

    # station temporal profiles (popups)
    stime = {}
    for side, col in (("dep", "oi"), ("arr", "di")):
        h = t.groupby([col, "weekend", "hour"]).size().unstack(fill_value=0).reindex(columns=range(24), fill_value=0)
        m = t.groupby([col, "month"]).size().unstack(fill_value=0).reindex(columns=range(1, 13), fill_value=0)
        for i in range(len(st)):
            e = stime.setdefault(i, {})
            e[f"{side}_wd"] = h.loc[(i, False)].tolist() if (i, False) in h.index else [0] * 24
            e[f"{side}_we"] = h.loc[(i, True)].tolist() if (i, True) in h.index else [0] * 24
            e[f"{side}_m"] = m.loc[i].tolist() if i in m.index else [0] * 12
    sizes["station_time.json"] = dump("station_time.json", [stime[i] for i in range(len(st))])

    # --- Streets ------------------------------------------------------------
    seg = gpd.read_parquet(PROCESSED / "network_segments.parquet")
    flows = pd.read_parquet(PROCESSED / "segment_flows.parquet")
    flows = flows[(flows.trips > 0) | (flows.trips_shortest > 0)].reset_index(drop=True)
    flows["k"] = np.arange(len(flows))
    kmap = flows.set_index("seg_id").k
    s = seg.merge(flows[["seg_id", "k", "trips", "trips_shortest"]], on="seg_id").sort_values("k")
    sm = s.to_crs(CRS_METRIC)
    sm["geometry"] = sm.simplify(2)
    s = sm.to_crs(CRS_WGS84)
    gj = gpd.GeoDataFrame({
        "k": s.k.astype(int), "name": s.nom_mapa.fillna(s.nomoficial), "infra": s.infra.astype(int),
        "tipo": s.tipo_c, "tot_i": s.trips.astype(int), "tot_s": s.trips_shortest.astype(int)}, geometry=s.geometry)
    gj.to_file(WEB_DATA / "segments.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    sizes["segments.geojson"] = (WEB_DATA / "segments.geojson").stat().st_size

    # segment x key matrix for the primary strategy, from pair incidence x pair-key counts
    from scipy import sparse
    edges = pd.read_parquet(INTERIM / "network_edges.parquet").set_index("edge_id").seg_id
    pk = t.groupby(["p", "key"]).size()
    PK = sparse.csr_matrix((pk.to_numpy(), (pk.index.get_level_values(0), pk.index.get_level_values(1))),
                           shape=(len(pairs), 144))
    routes_i = pd.read_parquet(INTERIM / "pair_edges_infra.parquet")
    routes_s = pd.read_parquet(INTERIM / "pair_edges_shortest.parquet")
    pid = pd.Series(pairs.p.to_numpy(), index=pd.MultiIndex.from_frame(pairs[["o", "d"]]))

    def seg_lists(routes):
        p = pid.reindex(pd.MultiIndex.from_frame(routes[["o", "d"]])).to_numpy()
        lists = [list(dict.fromkeys(kmap.reindex(edges.loc[list(e)]).dropna().astype(int).tolist())) if len(e) else []
                 for e in routes.edges]
        return p, lists

    p_i, l_i = seg_lists(routes_i)
    p_s, l_s = seg_lists(routes_s)
    ok = ~np.isnan(p_i)
    rows = np.repeat(p_i[ok].astype(int), [len(l) for l, k in zip(l_i, ok) if k])
    cols = np.concatenate([np.asarray(l, int) for l, k in zip(l_i, ok) if k and l])
    M = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(pairs), len(flows)))
    SK = (M.T @ PK).toarray().astype(np.uint32)
    sizes["seg_flows.bin.gz"] = write_bin(WEB_DATA / "seg_flows.bin.gz", [SK.ravel()])

    # Routes per origin station, stored as route trees. All routes from one
    # origin form a shortest-path tree, so each directed edge needs only its
    # parent edge. File routes/<i>.bin.gz, for strategy "i" then "s":
    #   Uint32 header [n_edges, n_dest]
    #   Uint16 edge[n] (directed edge id), Uint16 parent[n] (index into edge[], 65535 = root)
    #   Uint16 dest[m] (station index), Uint16 last[m] (index into edge[])
    # web/data/edge_seg.bin.gz maps directed edge id -> segment k (65535 = unused).
    all_edges = pd.read_parquet(INTERIM / "network_edges.parquet")
    edge_seg = kmap.reindex(all_edges.seg_id).fillna(65535).to_numpy(np.uint16)
    assert len(all_edges) < 65535
    sizes["edge_seg.bin.gz"] = write_bin(WEB_DATA / "edge_seg.bin.gz", [edge_seg])

    def tree(group):
        pos, edge, parent, dest, last = {}, [], [], [], []
        for d, e in zip(group.d, group.edges):
            if not len(e):
                continue
            prev = 65535
            for x in e:
                x = int(x)
                if x not in pos:
                    pos[x] = len(edge)
                    edge.append(x)
                    parent.append(prev)
                prev = pos[x]
            dest.append(int(idx[d]))
            last.append(prev)
        return [np.array([len(edge), len(dest)], np.uint32), np.array(edge, np.uint16), np.array(parent, np.uint16),
                np.array(dest, np.uint16), np.array(last, np.uint16)]

    (WEB_DATA / "routes").mkdir(exist_ok=True)
    gi, gs = dict(tuple(routes_i.groupby("o"))), dict(tuple(routes_s.groupby("o")))
    rsize = 0
    for o in sorted(set(gi) | set(gs)):
        empty = pd.DataFrame({"d": [], "edges": []})
        parts = tree(gi.get(o, empty)) + tree(gs.get(o, empty))
        rsize += write_bin(WEB_DATA / "routes" / f"{int(idx[o])}.bin.gz", parts)
    sizes["routes/*.bin.gz"] = rsize

    # cycling infrastructure layer
    cv = gpd.read_file(RAW / "ciclovias.geojson").to_crs(CRS_METRIC)
    cv["geometry"] = cv.simplify(2)
    cv = cv.to_crs(CRS_WGS84)[["nombre", "tipo", "geometry"]]
    cv["two_way"] = (~cv.tipo.str.contains("mano única", case=False)).astype(int)
    cv[["nombre", "two_way", "geometry"]].to_file(WEB_DATA / "ciclovias.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
    sizes["ciclovias.geojson"] = (WEB_DATA / "ciclovias.geojson").stat().st_size

    # --- Territories: labels / arrow anchors ----------------------------------
    anchors = {}
    for lvl, key in (("barrio", "barrio"), ("comuna", "comuna")):
        g = gpd.read_file(WEB_DATA / f"{lvl}s.geojson").to_crs(CRS_METRIC)
        pts = g.representative_point().to_crs(CRS_WGS84)
        anchors[lvl] = {str(k): [round(p.x, 5), round(p.y, 5)] for k, p in zip(g[key], pts)}

    # --- Meta ------------------------------------------------------------------
    rd = lambda n: json.loads((PROCESSED / n).read_text(encoding="utf-8"))
    terr = pd.read_parquet(PROCESSED / "territory_indicators.parquet")
    dds = pd.read_parquet(PROCESSED / "dds_stats.parquet")
    demo = pd.read_parquet(PROCESSED / "demographics.parquet")
    meta = {
        "year": YEAR,
        "summary": rd("summary.json"),
        "quality": {k: v for k, v in rd("quality_report.json").items() if k not in ("raw_columns",)},
        "network": rd("network_report.json"),
        "routing": rd("routing_report.json"),
        "osm": rd("osm_comparison.json"),
        "hour_bands": HOUR_BANDS,
        "genders": GENDERS, "ages": AGES,
        "min_cell": MIN_CELL, "min_publish": MIN_PUBLISH,
        "suppression": {"gender": rep_g, "age": rep_a},
        "counts": {"pairs": int(len(pairs)), "od_rows": int(len(od)), "segments": int(len(flows)), "keys": 144},
        "anchors": anchors,
        "territories": clean_records(terr),
        "dds": clean_records(dds),
        "demographics": clean_records(demo.drop(columns=[c for c in demo.columns if c.startswith("hour_")]).assign(
            hours=demo[[f"hour_{h}" for h in range(24)]].values.tolist())),
        "attribution": "Fuente: Gobierno de la Ciudad de Buenos Aires — data.buenosaires.gob.ar (CC-BY-2.5-AR)",
    }
    sizes["meta.json"] = dump("meta.json", meta)
    total = sum(sizes.values())
    for k, v in sizes.items():
        print(f"  {k:<22} {v / 1e6:7.2f} MB")
    print(f"  {'TOTAL':<22} {total / 1e6:7.2f} MB")
    print("suppression", rep_g, rep_a)


if __name__ == "__main__":
    main()
