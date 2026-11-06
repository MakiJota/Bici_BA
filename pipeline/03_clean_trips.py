"""Step 03 - Clean and validate trips, build the station table, join user age.

Inputs  (data/raw):  recorridos-realizados-<YEAR>.zip, usuarios*ecobici*<y>.csv
Outputs (data/processed):
    trips_clean.parquet   one row per trip, compact dtypes, quality flags
    stations.parquet      one row per station with validated coordinates
    quality_report.json   every count quoted in docs/03_data_quality.md
Also writes docs/03_data_quality.md from those numbers.

Design: records are *flagged*, never silently dropped. `valid` marks trips
used in analysis; every exclusion reason is counted in the report.

Usage:  python pipeline/03_clean_trips.py
"""
import json
import re
import zipfile

import numpy as np
import pandas as pd

from config import (DOCS, MAX_DURATION_S, MIN_DURATION_S, PROCESSED, RAW,
                    SOURCES, USER_YEARS, YEAR)

# Generous bounding box around CABA (official limits -58.53/-58.34, -34.71/-34.53)
BBOX = (-58.56, -34.72, -58.32, -34.51)
AGE_MIN, AGE_MAX = 16, 90
AGE_BINS = [16, 25, 35, 45, 55, 65, 91]
AGE_LABELS = ["16-24", "25-34", "35-44", "45-54", "55-64", "65+"]


def station_int(s: pd.Series) -> pd.Series:
    """'146BAEcobici' -> 146 (nullable Int32)."""
    return pd.to_numeric(s.str.extract(r"^(\d+)")[0], errors="coerce").astype("Int32")


def load_trips() -> pd.DataFrame:
    path = RAW / SOURCES["trips"].rsplit("/", 1)[-1]
    with zipfile.ZipFile(path) as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(z.open(member), dtype=str, encoding="utf-8")
    df.columns = [c.strip().lower() for c in df.columns]
    return df.rename(columns={"género": "genero"})


def build_stations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One coordinate per station: the most frequent valid pair across all trips."""
    parts = []
    for side in ("origen", "destino"):
        p = pd.DataFrame({
            "station_id": station_int(df[f"id_estacion_{side}"]),
            "name": df[f"nombre_estacion_{side}"],
            "address": df[f"direccion_estacion_{side}"],
            "lon": pd.to_numeric(df[f"long_estacion_{side}"], errors="coerce"),
            "lat": pd.to_numeric(df[f"lat_estacion_{side}"], errors="coerce"),
        })
        parts.append(p)
    s = pd.concat(parts, ignore_index=True).dropna(subset=["station_id"])
    in_box = s.lon.between(BBOX[0], BBOX[2]) & s.lat.between(BBOX[1], BBOX[3])
    stats = {"station_refs": int(len(s)), "station_refs_bad_coords": int((~in_box).sum())}
    s = s[in_box]

    def mode(x):
        return x.value_counts().index[0] if x.notna().any() else None

    coords = (s.groupby(["station_id", "lon", "lat"]).size().rename("n").reset_index()
                .sort_values("n", ascending=False))
    best = coords.drop_duplicates("station_id").set_index("station_id")[["lon", "lat"]]
    variants = coords.groupby("station_id").size().rename("coord_variants")
    # largest distance (m) between any recorded position and the chosen one
    c = coords.merge(best.add_suffix("_best"), left_on="station_id", right_index=True)
    c["moved_m"] = np.hypot((c.lon - c.lon_best) * 91_700, (c.lat - c.lat_best) * 111_000)
    moved = c.groupby("station_id").moved_m.max().round(0)

    names = s.groupby("station_id").name.agg(mode)
    addr = s.groupby("station_id").address.agg(mode)
    st = pd.concat([best, names, addr, variants, moved], axis=1).reset_index()
    # "146 - Hospital Francés" -> "Hospital Francés"
    st["name"] = st["name"].fillna("").str.replace(r"^\s*\d+\s*-\s*", "", regex=True).str.strip()
    st.loc[st.name == "", "name"] = "Estación " + st.station_id.astype(str)
    stats["stations"] = int(len(st))
    stats["stations_multiple_coords"] = int((st.coord_variants > 1).sum())
    stats["stations_moved_over_100m"] = int((st.moved_m > 100).sum())
    return st.sort_values("station_id").reset_index(drop=True), stats


def load_users() -> tuple[pd.DataFrame, dict]:
    """Union of all yearly user files -> user_id, gender at registration, age, year registered."""
    frames = []
    for y in USER_YEARS:
        f = RAW / SOURCES[f"users_{y}"].rsplit("/", 1)[-1]
        d = pd.read_csv(f, dtype=str, encoding="utf-8-sig", sep=None, engine="python")
        d.columns = [c.strip().lower() for c in d.columns]
        id_col = next(c for c in d.columns if "id" in c and ("usuario" in c or "cliente" in c))
        reg = pd.to_datetime(d["fecha_alta"], errors="coerce", format="%d-%m-%y" if y <= 2018 else "%Y-%m-%d")
        frames.append(pd.DataFrame({
            "user_id": pd.to_numeric(d[id_col], errors="coerce"),
            "age_at_reg": pd.to_numeric(d["edad_usuario"].str.replace(",", ""), errors="coerce"),
            "reg_year": reg.dt.year.fillna(y).astype(int),
            "file_year": y,
        }))
    u = pd.concat(frames, ignore_index=True).dropna(subset=["user_id"])
    u["user_id"] = u.user_id.astype("int64")
    stats = {"user_records": int(len(u)), "user_ids_in_several_files": int(u.user_id.duplicated().sum())}
    # If an ID appears in several files keep the earliest registration
    u = u.sort_values("reg_year").drop_duplicates("user_id")
    return u, stats


def main() -> None:
    q: dict = {"year": YEAR}
    raw = load_trips()
    q["raw_rows"] = int(len(raw))
    q["raw_columns"] = list(raw.columns)

    stations, st_stats = build_stations(raw)
    q.update(st_stats)

    t = pd.DataFrame({
        "trip_id": pd.to_numeric(raw.id_recorrido.str.extract(r"^(\d+)")[0], errors="coerce").astype("Int64"),
        "o": station_int(raw.id_estacion_origen),
        "d": station_int(raw.id_estacion_destino),
        "start": pd.to_datetime(raw.fecha_origen_recorrido, errors="coerce"),
        "end": pd.to_datetime(raw.fecha_destino_recorrido, errors="coerce"),
        "duration_s": pd.to_numeric(raw.duracion_recorrido.str.replace(",", ""), errors="coerce"),
        "user_id": pd.to_numeric(raw.id_usuario.str.extract(r"^(\d+)")[0], errors="coerce").astype("Int64"),
        "bike_model": raw.modelo_bicicleta.astype("category"),
        "gender": raw.genero.str.upper().astype("category"),
    })
    del raw

    # --- Validation flags -------------------------------------------------
    ts_dur = (t.end - t.start).dt.total_seconds()
    known = set(stations.station_id)
    f = pd.DataFrame(index=t.index)
    f["missing_origin"] = t.o.isna()
    f["missing_dest"] = t.d.isna()
    f["unknown_station"] = ~(t.o.isin(known) & t.d.isin(known)) & ~f.missing_origin & ~f.missing_dest
    f["missing_time"] = t.start.isna() | t.end.isna()
    f["end_before_start"] = ts_dur < 0
    f["duration_mismatch"] = (t.duration_s - ts_dur).abs() > 60
    f["too_short"] = t.duration_s < MIN_DURATION_S
    f["too_long"] = t.duration_s > MAX_DURATION_S
    f["outside_year"] = t.start.dt.year != YEAR
    f["duplicate_id"] = t.trip_id.duplicated(keep="first")
    f["duplicate_logical"] = t.duplicated(["user_id", "o", "start"], keep="first")
    t["round_trip"] = t.o == t.d  # kept as valid trips; not routable

    q["flags"] = {c: int(f[c].sum()) for c in f.columns}
    q["round_trips"] = int(t.round_trip.sum())
    t["valid"] = ~f.any(axis=1)
    q["valid_trips"] = int(t.valid.sum())
    q["excluded_trips"] = int((~t.valid).sum())
    q["duration_raw_summary_s"] = {k: float(v) for k, v in t.duration_s.describe(percentiles=[.01, .5, .99]).items()}

    # --- Gender (on the trip record itself) --------------------------------
    q["gender_counts"] = {str(k): int(v) for k, v in t.gender.value_counts(dropna=False).items()}

    # --- Age (joined from the union of yearly user files) -------------------
    users, u_stats = load_users()
    q.update(u_stats)
    t = t.merge(users[["user_id", "age_at_reg", "reg_year"]], on="user_id", how="left")
    age = t.age_at_reg + (YEAR - t.reg_year)
    q["age_join_rate"] = round(float(t.age_at_reg.notna().mean()), 4)
    q["age_implausible"] = int((age.notna() & ~age.between(AGE_MIN, AGE_MAX)).sum())
    age = age.where(age.between(AGE_MIN, AGE_MAX))
    t["age"] = age.astype("Int16")
    t["age_group"] = pd.cut(age, AGE_BINS, right=False, labels=AGE_LABELS)
    q["age_available_share"] = round(float(t.age.notna().mean()), 4)
    q["age_group_counts"] = {str(k): int(v) for k, v in t.age_group.value_counts(dropna=False).sort_index().items()}
    t = t.drop(columns=["age_at_reg"])

    # --- Derived time fields ---------------------------------------------
    t["date"] = t.start.dt.date
    t["month"] = t.start.dt.month.astype("Int8")
    t["dow"] = t.start.dt.day_of_week.astype("Int8")       # 0 = Monday
    t["hour"] = t.start.dt.hour.astype("Int8")
    t["weekend"] = t.dow >= 5
    v = t[t.valid]
    q["valid_period"] = [str(v.start.min()), str(v.start.max())]
    q["active_days"] = int(v.date.nunique())
    q["active_stations"] = int(pd.concat([v.o, v.d]).nunique())

    # --- Write -----------------------------------------------------------
    t["o"] = t.o.astype("Int16")
    t["d"] = t.d.astype("Int16")
    t["duration_s"] = t.duration_s.astype("Int32")
    t = t.drop(columns=["date"])
    t.to_parquet(PROCESSED / "trips_clean.parquet", index=False)
    stations.to_parquet(PROCESSED / "stations.parquet", index=False)
    (PROCESSED / "quality_report.json").write_text(json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8")
    write_doc(q)
    print(json.dumps(q, indent=2, ensure_ascii=False))


def write_doc(q: dict) -> None:
    fl = q["flags"]
    pct = lambda n: f"{100 * n / q['raw_rows']:.2f}%"
    rows = "\n".join(f"| `{k}` | {v:,} | {pct(v)} |" for k, v in fl.items())
    g = "\n".join(f"| {k} | {v:,} |" for k, v in q["gender_counts"].items())
    a = "\n".join(f"| {k} | {v:,} |" for k, v in q["age_group_counts"].items())
    doc = f"""# 03 · Data quality report — trips {q['year']}

*Generated by `pipeline/03_clean_trips.py`. Every number below is computed, not typed.*

## Summary

| Item | Value |
|---|---|
| Raw trip records | {q['raw_rows']:,} |
| Valid trips used in analysis | {q['valid_trips']:,} ({100 * q['valid_trips'] / q['raw_rows']:.2f}%) |
| Excluded trips | {q['excluded_trips']:,} |
| Round trips (same origin and destination; valid, not routable) | {q['round_trips']:,} |
| Period covered by valid trips | {q['valid_period'][0]} → {q['valid_period'][1]} |
| Days with activity | {q['active_days']} |
| Stations (distinct ids with valid coordinates) | {q['stations']} |
| Active stations in valid trips | {q['active_stations']} |

## Validation flags

A trip is **valid** when none of these flags is raised. Flags overlap, so they do not add up to the excluded total.

| Flag | Trips | Share of raw |
|---|---:|---:|
{rows}

Rules:

- `missing_origin` / `missing_dest`: station identifier empty.
- `unknown_station`: identifier never observed with a valid coordinate.
- `duration_mismatch`: reported `duracion_recorrido` differs from end − start by more than 60 s.
- `too_short`: under 60 s (dock tests, immediate re-docking). `too_long`: over 4 h (lost or unreturned bikes, not mobility).
- `outside_year`: trip starts outside {q['year']}. Trips that *end* in early {q['year'] + 1} are kept.
- `duplicate_id`: repeated `Id_recorrido`. `duplicate_logical`: same user, origin and start time.

Raw duration distribution (seconds): {', '.join(f"{k}={v:,.0f}" for k, v in q['duration_raw_summary_s'].items())}.
Durations in the source use a thousands separator (`"3,258"` = 3,258 s); they match the timestamps.
The shortest raw duration is {q['duration_raw_summary_s']['min']:.0f} s, which indicates that the publisher already removes sub-minute trips.

## Stations

- Station coordinates are taken from the trip records. {q['station_refs_bad_coords']:,} of {q['station_refs']:,} station references carried missing or `0,0` coordinates and were ignored.
- {q['stations_multiple_coords']} stations appear with more than one coordinate during the year; the most frequent position is used. {q['stations_moved_over_100m']} of them moved more than 100 m (relocations).
- Station names are normalised by removing the numeric prefix (`"146 - Hospital Francés"` → `"Hospital Francés"`).

## User attributes actually present

| Attribute | Source | Coverage |
|---|---|---|
| Gender | `género` field on every trip record | see below |
| Age | **not in the trip file**; joined via `id_usuario` from yearly user files {min(USER_YEARS)}–{max(USER_YEARS)} | {100 * q['age_available_share']:.1f}% of trips |
| Bike model | `modelo_bicicleta` (FIT / ICONIC) | all trips |

Gender categories as recorded (not exhaustive, not inferred):

| Gender | Trips |
|---|---:|
{g}

**Age caveats.** Each yearly user file lists the users who *registered* that year, with their age at registration.
Age in {q['year']} is estimated as age at registration + years since registration. {q['user_records']:,} user records were read;
{q['age_join_rate'] * 100:.1f}% of trips matched one. {q['age_implausible']:,} trips had an implausible estimated age
(outside {AGE_MIN}–{AGE_MAX}) and their age was set to missing. Users not found in any file (e.g. registered before
{min(USER_YEARS)} or absent from the publication) have no age. **Age results describe the matched subset only.**

| Age group | Trips |
|---|---:|
{a}

## Privacy safeguards

- User identifiers are used only for the age join and are **never** written to the web data.
- Published demographic breakdowns suppress any cell with fewer than `MIN_CELL` trips (see `pipeline/config.py`).
- Only aggregated tables are published; no row-level trip data leaves `data/processed/`.
"""
    (DOCS / "03_data_quality.md").write_text(doc, encoding="utf-8")


if __name__ == "__main__":
    main()
