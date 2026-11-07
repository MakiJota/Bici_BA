"""Step 09 - Trip animation data across years (web "Animación" tab).

For every year in config.ANIM_YEARS the raw trip file of that year is read
(schemas differ by year, see `COLUMNS`), and for each month in ANIM_MONTHS and
weekday in ANIM_DOWS one TYPICAL date is chosen: not an Argentine public
holiday or bridge day, with the trip count closest to the median of that
weekday in that month. Each trip of the chosen dates is animated along its
RECONSTRUCTED route on the street network (step 05), traversed at constant
speed between the observed departure and arrival. Not GPS.

Stations are taken from each year's own records (they were added and moved
over time). 2014 publishes station names only, so its coordinates come from
the same names in neighbouring years. All years are routed on today's street
and bike-lane network: the ciclovías layer has no construction date, so the
"on a bike lane" share of early years is an upper bound.

Privacy: per trip only origin station, destination station and departure /
arrival minute are published - no user id, gender, age or bike model.

Outputs (web/data/anim/):
  days.json                    index: years -> files, chosen dates, trip counts
  network.bin.gz               Uint32 [K, NV]; Uint32 start[K+1]; Float32 xy[NV*2]; Uint8 infra[K]
  <year>/stations.json         [{i, id, name, lon, lat}]
  <year>/routes.bin.gz         Uint32 [nPairs, nRefsI, nRefsS]; Uint32 startI[nPairs+1], startS[nPairs+1];
                               Uint16 pairO[nPairs], pairD[nPairs]; Uint16 refsI[], refsS[]
                               (ref = k*2 + reversed, k = segment index in network.bin.gz;
                                "I" = infrastructure-preferred route, "S" = shortest)
  <year>/<date>.bin.gz         Uint32 nTrips; Uint32 tripPair[n]; Uint16 startMin[n], endMin[n]
                               (minutes since 00:00, trips sorted by departure; end may pass 1440)

Usage:  python pipeline/09_export_animation.py [year ...]
"""
import gzip
import importlib
import json
import re
import sys
import time
import unicodedata
import zipfile

import geopandas as gpd
import holidays
import numpy as np
import pandas as pd

from config import (ANIM_DOWS, ANIM_MONTHS, ANIM_YEARS, INTERIM, MAX_DURATION_S, MIN_DURATION_S,
                    PROCESSED, RAW, SOURCES, WEB_DATA, YEAR)

routing = importlib.import_module("06_routing")
OUT = WEB_DATA / "anim"
BBOX = (-58.56, -34.72, -58.33, -34.52)            # lon_min, lat_min, lon_max, lat_max (CABA + margin)
MIN_DAYS_IN_MONTH = 2                              # candidates needed to call a date "typical"
MIN_TRIPS_DAY = 20

# Column names used by the different yearly schemas (lower-cased).
COLUMNS = {
    "start": ["fecha_origen_recorrido", "origen_fecha"],
    "end": ["fecha_destino_recorrido", "destino_fecha"],
    "o_id": ["id_estacion_origen"], "d_id": ["id_estacion_destino"],
    "o_name": ["nombre_estacion_origen", "nombre_origen"],
    "d_name": ["nombre_estacion_destino", "destino_estacion"],
    "o_lon": ["long_estacion_origen"], "o_lat": ["lat_estacion_origen"],
    "d_lon": ["long_estacion_destino"], "d_lat": ["lat_estacion_destino"],
}


def raw_path(year: int):
    url = SOURCES["trips"] if year == YEAR else SOURCES[f"trips_{year}"]
    return RAW / url.rsplit("/", 1)[-1]


def open_csv(path):
    """Return (opener, encoding, separator, lower-cased header) for a csv or a zip holding one."""
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        name = max((i for i in z.infolist() if i.filename.lower().endswith(".csv")), key=lambda i: i.file_size).filename
        opener = lambda: z.open(name)  # noqa: E731
    else:
        opener = lambda: open(path, "rb")  # noqa: E731
    with opener() as f:
        head = f.read(1 << 20)
    head = head[: head.rfind(b"\n")]
    try:
        head.decode("utf-8")
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        enc = "latin-1"
    first = head.split(b"\n", 1)[0].decode(enc).strip()
    sep = ";" if first.count(";") > first.count(",") else ","
    return opener, enc, sep, [c.strip().strip('"').lower() for c in first.split(sep)]


def parse_dt(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, format="ISO8601", errors="coerce")
    bad = out.isna() & s.notna()
    if bad.any():                                  # e.g. 2011 arrivals as dd/mm/yyyy hh:mm
        out[bad] = pd.to_datetime(s[bad], format="mixed", dayfirst=True, errors="coerce")
    return out


def norm_name(x: str) -> str:
    x = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().upper()
    x = re.sub(r"^\s*\d+\s*-\s*", "", x)            # "146 - Hospital Francés" -> "HOSPITAL FRANCES"
    return re.sub(r"[^A-Z0-9]+", " ", x).strip()


def read_year(year: int):
    """Trips of the animation months and per-station coordinates for one year."""
    path = raw_path(year)
    opener, enc, sep, header = open_csv(path)
    col = {k: next((c for c in v if c in header), None) for k, v in COLUMNS.items()}
    has_id, has_xy = col["o_id"] is not None, col["o_lon"] is not None
    use = [c for c in col.values() if c]
    trips, coords, names = [], [], []
    with opener() as f:
        for ch in pd.read_csv(f, sep=sep, encoding=enc, usecols=lambda c: c.strip().strip('"').lower() in use,
                              dtype=str, chunksize=1_000_000, on_bad_lines="skip"):
            ch.columns = [c.strip().strip('"').lower() for c in ch.columns]
            st = parse_dt(ch[col["start"]])
            keep = (st.dt.year == year) & st.dt.month.isin(ANIM_MONTHS)
            ch, st = ch[keep], st[keep]
            if ch.empty:
                continue
            en = parse_dt(ch[col["end"]])
            if has_id:
                ko = ch[col["o_id"]].str.extract(r"^\s*(\d+)", expand=False)
                kd = ch[col["d_id"]].str.extract(r"^\s*(\d+)", expand=False)
            else:
                ko, kd = ch[col["o_name"]].map(norm_name), ch[col["d_name"]].map(norm_name)
            trips.append(pd.DataFrame({"o": ko.values, "d": kd.values, "start": st.values, "end": en.values}))
            for side in ("o", "d"):
                k = ko if side == "o" else kd
                nm = ch[col[f"{side}_name"]] if col[f"{side}_name"] else pd.Series("", index=ch.index)
                names.append(pd.DataFrame({"key": k.values, "name": nm.values}))
                if has_xy:
                    lon = pd.to_numeric(ch[col[f"{side}_lon"]], errors="coerce")
                    lat = pd.to_numeric(ch[col[f"{side}_lat"]], errors="coerce")
                    swap = lon > -45                    # some years swap the two columns
                    lon, lat = lon.where(~swap, lat), lat.where(~swap, lon)
                    coords.append(pd.DataFrame({"key": k.values, "lon": lon.round(5).values, "lat": lat.round(5).values}))
    t = pd.concat(trips, ignore_index=True)
    nm = pd.concat(names, ignore_index=True).dropna()
    nm = nm[nm.name.str.strip() != ""].groupby("key").name.agg(lambda s: s.mode().iat[0])
    if has_xy:
        c = pd.concat(coords, ignore_index=True).dropna()
        c = c[c.lon.between(BBOX[0], BBOX[2]) & c.lat.between(BBOX[1], BBOX[3])]
        xy = c.groupby(["key", "lon", "lat"]).size().reset_index(name="n").sort_values("n").drop_duplicates("key", keep="last")
        st = xy.set_index("key")[["lon", "lat"]]
    else:
        st = pd.DataFrame(columns=["lon", "lat"])
    st = st.join(nm.rename("name"), how="outer")
    st.index.name = "key"
    return t, st.reset_index(), has_xy


def typical_dates(t: pd.DataFrame, year: int):
    daily = t.groupby(t.start.dt.normalize()).size()
    hol = holidays.country_holidays("AR", years=year)
    chosen = []
    for m in ANIM_MONTHS:
        for dow in ANIM_DOWS:
            c = daily[(daily.index.month == m) & (daily.index.day_of_week == dow)]
            c = c[[d.date() not in hol for d in c.index]]
            c = c[c >= MIN_TRIPS_DAY]
            if len(c) < MIN_DAYS_IN_MONTH:
                continue
            med = c.median()
            d = (c - med).abs().sort_values(kind="stable").index[0]
            chosen.append({"date": d.strftime("%Y-%m-%d"), "month": m, "dow": dow, "trips": int(c[d]),
                           "median": float(med), "candidates": int(len(c))})
    return chosen


def write_gz(path, arrays) -> int:
    raw = b"".join(np.ascontiguousarray(a).tobytes() for a in arrays)
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", compresslevel=9, mtime=0, filename="") as f:
        f.write(raw)
    return path.stat().st_size


def export_network():
    seg = gpd.read_parquet(PROCESSED / "network_segments.parquet")
    seg = seg[seg.in_network].sort_values("seg_id").reset_index(drop=True)
    assert len(seg) * 2 < 65535
    lines = [list(g.coords) if g.geom_type == "LineString" else [p for part in g.geoms for p in part.coords] for g in seg.geometry]
    start = np.concatenate([[0], np.cumsum([len(c) for c in lines])]).astype(np.uint32)
    xy = np.array([p for c in lines for p in c], dtype=np.float64).round(5).astype(np.float32).ravel()
    size = write_gz(OUT / "network.bin.gz", [np.array([len(seg), start[-1]], np.uint32), start, xy,
                                            seg.infra.to_numpy(np.uint8)])
    print(f"network: {len(seg):,} segments, {start[-1]:,} vertices, {size / 1e6:.2f} MB")
    kmap = pd.Series(np.arange(len(seg)), index=seg.seg_id)
    edges = pd.read_parquet(INTERIM / "network_edges.parquet")
    k = kmap.reindex(edges.seg_id).to_numpy()
    ref = pd.Series(np.where(np.isnan(k), -1, k * 2 + (~edges.forward.to_numpy()).astype(int)).astype(np.int64),
                    index=edges.edge_id.to_numpy())
    return ref, edges


def main(years) -> None:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.bin.gz"):
        if old.name != "network.bin.gz":
            old.unlink()                                   # files of the earlier single-year layout
    ref_of_edge, edges = export_network()
    nodes = pd.read_parquet(INTERIM / "network_nodes.parquet")
    n_nodes = int(max(nodes.node.max(), edges.u.max(), edges.v.max())) + 1
    index_path = OUT / "days.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    by_year = {y["year"]: y for y in index.get("years", [])}

    loaded = {}
    for year in years:
        if not raw_path(year).exists():
            print(f"{year}: raw file missing ({raw_path(year).name}) - run pipeline/01_download.py")
            continue
        loaded[year] = read_year(year)
        print(f"{year}: read {len(loaded[year][0]):,} trips in the animation months ({time.time() - t0:.0f}s)")

    # names -> coordinates from every year with coordinates (for years publishing names only)
    lookup = {}
    for y in sorted(loaded, key=lambda y: -y):
        _, st, has_xy = loaded[y]
        if has_xy:
            for _, r in st.dropna(subset=["lon"]).iterrows():
                lookup.setdefault(norm_name(r["name"]), (r.lon, r.lat))
    for y in [y for y in ANIM_YEARS if y not in loaded and (OUT / str(y) / "stations.json").exists()]:
        for s in json.loads((OUT / str(y) / "stations.json").read_text(encoding="utf-8")):
            lookup.setdefault(norm_name(s["name"]), (s["lon"], s["lat"]))

    for year, (t, st, has_xy) in sorted(loaded.items()):
        if not has_xy:
            st["lon"] = st.key.map(lambda k: lookup.get(k, (np.nan, np.nan))[0])
            st["lat"] = st.key.map(lambda k: lookup.get(k, (np.nan, np.nan))[1])
            st["name"] = st["name"].fillna(st.key).str.title()
            print(f"{year}: {st.lon.notna().sum()}/{len(st)} stations located by name")
        st = st.dropna(subset=["lon", "lat"]).reset_index(drop=True)
        dur = (t.end - t.start).dt.total_seconds()
        t = t[t.o.isin(st.key) & t.d.isin(st.key) & dur.between(MIN_DURATION_S, MAX_DURATION_S)]
        days = typical_dates(t, year)
        if not days:
            print(f"{year}: no usable dates")
            continue
        t = t[t.start.dt.strftime("%Y-%m-%d").isin([d["date"] for d in days])]

        # stations actually used on the chosen dates, snapped to the network
        used = pd.unique(pd.concat([t.o, t.d]))
        st = st[st.key.isin(used)].sort_values("key", key=lambda s: pd.to_numeric(s, errors="coerce").fillna(1e9)).reset_index(drop=True)
        snap = routing.snap_stations(nodes, st.rename(columns={"key": "station_id"}))
        st["node"], st["snap_m"] = snap.node.values, snap.snap_m.values
        far = st.snap_m > routing.MAX_SNAP_M
        st = st[~far].reset_index(drop=True)
        sidx = pd.Series(np.arange(len(st)), index=st.key)
        t = t[t.o.isin(st.key) & t.d.isin(st.key)].copy()
        t["oi"], t["di"] = sidx.loc[t.o].to_numpy(), sidx.loc[t.d].to_numpy()

        pairs = t[["oi", "di"]].drop_duplicates().sort_values(["oi", "di"]).reset_index(drop=True)
        pairs["o_node"], pairs["d_node"] = st.node.to_numpy()[pairs.oi], st.node.to_numpy()[pairs.di]
        refs, starts = {}, {}
        for tag, weight in (("I", "cost_infra"), ("S", "length_m")):
            r = routing.route_all(edges, n_nodes, weight, pairs[pairs.oi != pairs.di])
            seqs = []
            for o, d, on, dn in zip(pairs.oi, pairs.di, pairs.o_node, pairs.d_node):
                e = None if o == d else r.get((on, dn))
                seqs.append([] if not e else [int(x) for x in ref_of_edge.loc[e].to_numpy() if x >= 0])
            starts[tag] = np.concatenate([[0], np.cumsum([len(s) for s in seqs])]).astype(np.uint32)
            refs[tag] = np.array([x for s in seqs for x in s], dtype=np.uint16)
        ydir = OUT / str(year)
        ydir.mkdir(exist_ok=True)
        for old in ydir.glob("*.bin.gz"):
            old.unlink()
        rsize = write_gz(ydir / "routes.bin.gz", [np.array([len(pairs), len(refs["I"]), len(refs["S"])], np.uint32),
                                                 starts["I"], starts["S"], pairs.oi.to_numpy(np.uint16), pairs.di.to_numpy(np.uint16),
                                                 refs["I"], refs["S"]])
        (ydir / "stations.json").write_text(json.dumps(
            [{"i": int(i), "id": str(r.key), "name": str(r["name"]) if pd.notna(r["name"]) else str(r.key),
              "lon": round(float(r.lon), 5), "lat": round(float(r.lat), 5)} for i, r in st.iterrows()],
            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        pid = pd.Series(np.arange(len(pairs)), index=pd.MultiIndex.from_frame(pairs[["oi", "di"]]))
        total = rsize
        for d in days:
            midnight = pd.Timestamp(d["date"])
            x = t[t.start.dt.normalize() == midnight].sort_values("start")
            sm = ((x.start - midnight).dt.total_seconds() // 60).astype(int).to_numpy()
            em = np.maximum(((x.end - midnight).dt.total_seconds() // 60).astype(int).to_numpy(), sm + 1)
            tp = pid.reindex(pd.MultiIndex.from_frame(x[["oi", "di"]])).to_numpy()
            d.update({"trips": int(len(x)), "round_trips": int((x.oi == x.di).sum()), "file": f"{year}/{d['date']}.bin.gz"})
            d["bytes"] = write_gz(OUT / d["file"], [np.array([len(x)], np.uint32), tp.astype(np.uint32),
                                                     sm.astype(np.uint16), em.astype(np.uint16)])
            total += d["bytes"]
        by_year[year] = {"year": year, "stations": f"{year}/stations.json", "routes": f"{year}/routes.bin.gz",
                         "n_stations": int(len(st)), "pairs": int(len(pairs)), "stations_dropped_far": int(far.sum()),
                         "days": days, "bytes": int(total)}
        print(f"{year}: {len(days)} dates, {len(st)} stations, {len(pairs):,} pairs, "
              f"{sum(d['trips'] for d in days):,} trips, {total / 1e6:.2f} MB ({time.time() - t0:.0f}s)")

    index = {"bin_s": 900, "network": "network.bin.gz", "months": ANIM_MONTHS, "dows": ANIM_DOWS,
             "years": [by_year[y] for y in sorted(by_year)],
             "note": "Departure and arrival observed (minute resolution); path = inferred route at constant speed on "
                     "today's network. Not GPS. One typical non-holiday date per year x month x weekday."}
    index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"total {sum(y['bytes'] for y in index['years']) / 1e6:.1f} MB for {len(index['years'])} years")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or list(ANIM_YEARS))
