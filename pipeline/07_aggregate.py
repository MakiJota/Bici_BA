"""Step 07 - Analytical aggregates: OD matrices, territorial and station indicators,
temporal, demographic and distance / duration / speed statistics.

Inputs : data/processed/trips_clean.parquet, stations_geo.parquet, territories.parquet,
         pair_routes.parquet
Outputs: data/processed/
    od_station.parquet, od_barrio.parquet, od_comuna.parquet
    territory_indicators.parquet   per barrio / comuna
    station_stats.parquet
    dds_stats.parquet              distance / duration / speed by group (mean, p25, median, p75)
    demographics.parquet           gender and age group profiles (suppressed below MIN_CELL)
    summary.json                   overview KPIs and every number quoted in the report

Conventions
* A trip has one origin and one destination; directional flows A->B and B->A
  are stored once each, so no trip is counted twice. The "pair" view adds
  them only for the undirected total.
* Distances are estimated network distances of the PRIMARY routing strategy
  (infrastructure-preferred). Round trips (same station) have no distance.
* Estimated speed = estimated route distance / observed duration. Trips above
  MAX_SPEED_KMH are implausible for the inferred route and excluded from speed
  and distance statistics (documented in summary.json).

Usage:  python pipeline/07_aggregate.py
"""
import json

import numpy as np
import pandas as pd

from config import MAX_SPEED_KMH, MIN_CELL, PROCESSED

LEVELS = {"station": ("o", "d"), "barrio": ("ob", "db"), "comuna": ("oc", "dc")}


def load() -> pd.DataFrame:
    t = pd.read_parquet(PROCESSED / "trips_clean.parquet")
    t = t[t.valid].copy()
    t["o"], t["d"] = t.o.astype(int), t.d.astype(int)
    st = pd.read_parquet(PROCESSED / "stations_geo.parquet").set_index("station_id")
    t["ob"], t["db"] = t.o.map(st.barrio), t.d.map(st.barrio)
    t["oc"], t["dc"] = t.o.map(st.comuna).astype(int), t.d.map(st.comuna).astype(int)
    pr = pd.read_parquet(PROCESSED / "pair_routes.parquet", columns=["o", "d", "dist_infra_m", "dist_shortest_m"])
    t = t.merge(pr, on=["o", "d"], how="left")
    t.loc[t.round_trip, ["dist_infra_m", "dist_shortest_m"]] = np.nan
    t["dist_km"] = t.dist_infra_m / 1000
    t["dur_min"] = t.duration_s / 60
    t["speed_kmh"] = t.dist_km / (t.duration_s / 3600)
    t["speed_implausible"] = t.speed_kmh > MAX_SPEED_KMH
    t["gender"] = t.gender.astype("string").fillna("UNKNOWN")
    return t


def od_matrix(t: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    g = t.groupby([a, b]).agg(trips=("o", "size"), dur_mean_min=("dur_min", "mean"),
                              dist_mean_km=("dist_km", "mean")).reset_index()
    g.columns = ["from", "to", "trips", "dur_mean_min", "dist_mean_km"]
    rev = g[["from", "to", "trips"]].rename(columns={"from": "to", "to": "from", "trips": "trips_reverse"})
    g = g.merge(rev, on=["from", "to"], how="left").fillna({"trips_reverse": 0})
    g["trips_reverse"] = g.trips_reverse.astype(int)
    g["internal"] = g["from"] == g["to"]
    g["total_bidirectional"] = np.where(g.internal, g.trips, g.trips + g.trips_reverse)
    g["net_exchange"] = g.trips - g.trips_reverse            # >0: more A->B than B->A
    g["pct_of_trips"] = g.trips / len(t) * 100
    return g.sort_values("trips", ascending=False).reset_index(drop=True)


def territory_indicators(t: pd.DataFrame, terr: pd.DataFrame) -> pd.DataFrame:
    out = []
    for level, (a, b) in (("barrio", ("ob", "db")), ("comuna", ("oc", "dc"))):
        dep = t.groupby(a).size().rename("outgoing")
        arr = t.groupby(b).size().rename("incoming")
        internal = t[t[a] == t[b]].groupby(a).size().rename("internal")
        df = pd.concat([dep, arr, internal], axis=1).fillna(0).astype(int)
        df.index = df.index.astype(str)
        df["net_flow"] = df.incoming - df.outgoing
        df["inter_out"] = df.outgoing - df.internal
        df["inter_in"] = df.incoming - df.internal
        df["internal_share"] = df.internal / df.outgoing
        tt = terr[terr.level == level].set_index("unit")
        df = df.join(tt[["area_km2", "population_2010"]])
        df["activity"] = df.outgoing + df.incoming - df.internal  # trips touching the unit, counted once
        df["activity_per_km2"] = df.activity / df.area_km2
        df["activity_per_1000_residents"] = df.activity / df.population_2010 * 1000
        df.insert(0, "level", level)
        out.append(df.reset_index(names="unit"))
    return pd.concat(out, ignore_index=True)


def station_stats(t: pd.DataFrame) -> pd.DataFrame:
    st = pd.read_parquet(PROCESSED / "stations_geo.parquet").set_index("station_id")
    dep = t.groupby("o").size().rename("departures")
    arr = t.groupby("d").size().rename("arrivals")
    df = pd.concat([dep, arr], axis=1).fillna(0).astype(int)
    df["total"] = df.departures + df.arrivals
    df["net_flow"] = df.arrivals - df.departures
    df["round_trips"] = t[t.round_trip].groupby("o").size().reindex(df.index).fillna(0).astype(int)

    def top(col_from, col_to):
        g = t[~t.round_trip].groupby([col_from, col_to]).size().rename("n").reset_index()
        g = g.sort_values("n", ascending=False).groupby(col_from).head(5)
        return g.groupby(col_from).apply(lambda x: [[int(a), int(b)] for a, b in zip(x[col_to], x.n)], include_groups=False)

    df["top_destinations"] = top("o", "d")
    df["top_origins"] = top("d", "o")
    df = df.join(st[["name", "address", "barrio", "comuna", "lat", "lon"]])
    return df.reset_index(names="station_id").sort_values("total", ascending=False)


def pct(s: pd.Series, q: float) -> float:
    return float(s.quantile(q)) if len(s) else np.nan


def dds_stats(t: pd.DataFrame) -> pd.DataFrame:
    """Distance, duration and speed by group. Duration uses all valid trips;
    distance and speed use routable trips with plausible speed."""
    t = t.copy()
    t["daytype"] = np.where(t.weekend, "weekend", "weekday")
    t["all"] = "all"
    groups = {"all": "all", "comuna": "oc", "barrio": "ob", "gender": "gender",
              "age_group": "age_group", "daytype": "daytype", "hour": "hour", "bike_model": "bike_model"}
    rows = []
    for gname, col in groups.items():
        for key, x in t.groupby(col, observed=True):
            r = x[x.dist_km.notna() & ~x.speed_implausible]
            row = {"group": gname, "value": str(key), "n_trips": len(x), "n_routed": len(r)}
            for var, s in (("duration_min", x.dur_min), ("distance_km", r.dist_km), ("speed_kmh", r.speed_kmh)):
                row.update({f"{var}_mean": s.mean(), f"{var}_p25": pct(s, .25),
                            f"{var}_median": pct(s, .5), f"{var}_p75": pct(s, .75)})
            row["suppressed"] = gname in ("gender", "age_group") and len(x) < MIN_CELL
            rows.append(row)
    df = pd.DataFrame(rows)
    num = df.select_dtypes("number").columns.difference(["n_trips", "n_routed"])
    df[num] = df[num].round(3)
    df.loc[df.suppressed, num] = np.nan
    return df


def demographics(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for attr in ("gender", "age_group"):
        x = t[t[attr].notna()]
        for key, g in x.groupby(attr, observed=True):
            n = len(g)
            r = {"attribute": attr, "value": str(key), "trips": n, "share": n / len(x),
                 "weekend_share": g.weekend.mean(),
                 "peak_am_share": g.hour.between(7, 9).mean(), "peak_pm_share": g.hour.between(17, 19).mean()}
            r.update({f"hour_{h}": int(v) for h, v in g.hour.value_counts().reindex(range(24), fill_value=0).items()})
            top = g[~g.round_trip].groupby(["oc", "dc"]).size().nlargest(5)
            r["top_comuna_pairs"] = json.dumps([[int(a), int(b), int(v)] for (a, b), v in top.items() if v >= MIN_CELL])
            topst = g.groupby("o").size().nlargest(5)
            r["top_origin_stations"] = json.dumps([[int(k), int(v)] for k, v in topst.items() if v >= MIN_CELL])
            r["suppressed"] = n < MIN_CELL
            rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    t = load()
    terr = pd.read_parquet(PROCESSED / "territories.parquet")
    for level, (a, b) in LEVELS.items():
        od_matrix(t, a, b).to_parquet(PROCESSED / f"od_{level}.parquet", index=False)
    territory_indicators(t, terr).to_parquet(PROCESSED / "territory_indicators.parquet", index=False)
    station_stats(t).to_parquet(PROCESSED / "station_stats.parquet", index=False)
    dds = dds_stats(t)
    dds.to_parquet(PROCESSED / "dds_stats.parquet", index=False)
    demographics(t).to_parquet(PROCESSED / "demographics.parquet", index=False)

    days = t.start.dt.date.nunique()
    routed = t[t.dist_km.notna()]
    plaus = routed[~routed.speed_implausible]
    allrow = dds[dds.group == "all"].iloc[0]
    hourly = t.groupby("hour").size()
    wk = t[~t.weekend].groupby("hour").size() / t[~t.weekend].start.dt.date.nunique()
    summary = {
        "period": [str(t.start.min().date()), str(t.start.max().date())],
        "total_trips": int(len(t)),
        "days": int(days),
        "avg_daily_trips": round(len(t) / days, 1),
        "active_stations": int(pd.concat([t.o, t.d]).nunique()),
        "origin_stations": int(t.o.nunique()),
        "destination_stations": int(t.d.nunique()),
        "duration_mean_min": round(float(t.dur_min.mean()), 2),
        "duration_median_min": round(float(t.dur_min.median()), 2),
        "distance_mean_km": round(float(plaus.dist_km.mean()), 3),
        "distance_median_km": round(float(plaus.dist_km.median()), 3),
        "speed_mean_kmh": round(float(allrow.speed_kmh_mean), 2),
        "speed_median_kmh": round(float(allrow.speed_kmh_median), 2),
        "round_trips": int(t.round_trip.sum()),
        "round_trip_share": round(float(t.round_trip.mean()), 4),
        "routed_trips": int(len(routed)),
        "speed_implausible_trips": int(routed.speed_implausible.sum()),
        "speed_below_3kmh_share": round(float((plaus.speed_kmh < 3).mean()), 4),
        "same_comuna_share": round(float((t.oc == t.dc).mean()), 4),
        "different_comuna_share": round(float((t.oc != t.dc).mean()), 4),
        "same_barrio_share": round(float((t.ob == t.db).mean()), 4),
        "peak_hour": int(hourly.idxmax()),
        "weekday_am_peak_hour": int(wk.loc[5:11].idxmax()),
        "weekday_pm_peak_hour": int(wk.loc[15:21].idxmax()),
        "weekend_share": round(float(t.weekend.mean()), 4),
        "busiest_month": int(t.groupby("month").size().idxmax()),
        "quietest_month": int(t.groupby("month").size().idxmin()),
        "gender_share": {k: round(float(v), 4) for k, v in t.gender.value_counts(normalize=True).items()},
        "age_known_share": round(float(t.age_group.notna().mean()), 4),
        "min_cell": MIN_CELL,
        "max_speed_kmh": MAX_SPEED_KMH,
    }
    (PROCESSED / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
