"""Step 09 - Trip animation data for selected days (web "Animación" tab).

Each trip is animated along its RECONSTRUCTED route: departure and arrival
times are observed, the path in between is the inferred route on the street
network (step 06), traversed at constant speed. Not GPS.

Privacy: this is the only row-level product published. It is limited to the
days in config.ANIM_DAYS and contains, per trip, only origin station,
destination station and departure / arrival time rounded down to the minute:
no user id, gender, age or bike model.

Output: web/data/anim/days.json and web/data/anim/<date>.bin.gz with layout
  Uint32 header[4]   nTrips, nPairs, nRefsI, nRefsS
  Uint32 refStartI[nPairs+1], refStartS[nPairs+1]
  Uint16 pairO[nPairs], pairD[nPairs]          station index (stations.json "i")
  Uint16 refsI[nRefsI], refsS[nRefsS]          segment ref = k*2 + reversed
                                               (k = feature index in segments.geojson)
  Uint16 tripPair[nTrips], startMin[nTrips], endMin[nTrips]   (minutes since 00:00, end may pass 1440)
Trips are sorted by departure. "I" = infrastructure-preferred route, "S" = shortest.

Usage:  python pipeline/09_export_animation.py
"""
import gzip
import json

import numpy as np
import pandas as pd

from config import ANIM_DAYS, INTERIM, PROCESSED, WEB_DATA

OUT = WEB_DATA / "anim"


def write_gz(path, arrays) -> int:
    raw = b"".join(np.ascontiguousarray(a).tobytes() for a in arrays)
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", compresslevel=9, mtime=0, filename="") as f:
        f.write(raw)
    return path.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.bin.gz"):
        old.unlink()

    st = pd.read_parquet(PROCESSED / "stations_geo.parquet").sort_values("station_id").reset_index(drop=True)
    sidx = pd.Series(np.arange(len(st)), index=st.station_id)

    # directed edge -> segment ref (k*2 + reversed), using the same k as web/data/segments.geojson
    flows = pd.read_parquet(PROCESSED / "segment_flows.parquet")
    flows = flows[(flows.trips > 0) | (flows.trips_shortest > 0)].reset_index(drop=True)
    kmap = pd.Series(np.arange(len(flows)), index=flows.seg_id)
    edges = pd.read_parquet(INTERIM / "network_edges.parquet").set_index("edge_id")
    k = kmap.reindex(edges.seg_id).to_numpy()
    ref_of_edge = np.where(np.isnan(k), -1, k * 2 + (~edges.forward.to_numpy()).astype(int)).astype(np.int64)
    assert ref_of_edge.max() < 65535

    routes = {}
    for tag, name in (("I", "infra"), ("S", "shortest")):
        r = pd.read_parquet(INTERIM / f"pair_edges_{name}.parquet")
        routes[tag] = {(o, d): e for o, d, e in zip(r.o, r.d, r.edges)}

    t = pd.read_parquet(PROCESSED / "trips_clean.parquet", columns=["o", "d", "start", "end", "valid"])
    t = t[t.valid]
    t["day"] = t.start.dt.strftime("%Y-%m-%d")
    t = t[t.day.isin(ANIM_DAYS)].copy()
    t["o"], t["d"] = t.o.astype(int), t.d.astype(int)

    index = []
    for day in ANIM_DAYS:
        x = t[t.day == day].sort_values("start")
        midnight = pd.Timestamp(day)
        start_min = ((x.start - midnight).dt.total_seconds() // 60).astype(int).to_numpy()
        end_min = ((x.end - midnight).dt.total_seconds() // 60).astype(int).to_numpy()
        end_min = np.maximum(end_min, start_min + 1)
        pairs = x[["o", "d"]].drop_duplicates().reset_index(drop=True)
        pid = pd.Series(np.arange(len(pairs)), index=pd.MultiIndex.from_frame(pairs))
        trip_pair = pid.reindex(pd.MultiIndex.from_frame(x[["o", "d"]])).to_numpy()

        refs, starts = {}, {}
        for tag in ("I", "S"):
            seqs = []
            for o, d in zip(pairs.o, pairs.d):
                e = routes[tag].get((o, d))
                seq = [] if o == d or e is None else [int(ref_of_edge[int(j)]) for j in e]
                seqs.append([s for s in seq if s >= 0])
            starts[tag] = np.concatenate([[0], np.cumsum([len(s) for s in seqs])]).astype(np.uint32)
            refs[tag] = np.array([s for q in seqs for s in q], dtype=np.uint16)

        header = np.array([len(x), len(pairs), len(refs["I"]), len(refs["S"])], dtype=np.uint32)
        size = write_gz(OUT / f"{day}.bin.gz", [
            header, starts["I"], starts["S"],
            sidx.loc[pairs.o].to_numpy(np.uint16), sidx.loc[pairs.d].to_numpy(np.uint16),
            refs["I"], refs["S"],
            trip_pair.astype(np.uint16), start_min.astype(np.uint16), end_min.astype(np.uint16)])
        round_trips = int((x.o == x.d).sum())
        index.append({"date": day, "dow": int(midnight.day_of_week), "trips": int(len(x)), "round_trips": round_trips,
                      "pairs": int(len(pairs)), "file": f"{day}.bin.gz", "bytes": size})
        print(f"{day}: {len(x):>6,} trips, {len(pairs):>6,} pairs, {size / 1e6:.2f} MB")

    meta = {"days": index, "bin_s": 900,
            "note": "Departure and arrival observed (minute resolution); path = inferred route at constant speed. Not GPS."}
    (OUT / "days.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"total {sum(d['bytes'] for d in index) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
