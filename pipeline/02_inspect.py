"""Step 02 - Inspect every downloaded resource before any assumption is made.

Prints and saves (data/interim/inspection.json) for each file:
columns, dtypes, row counts, null counts, sample rows, value ranges and,
for geographic layers, CRS, geometry types and bounds.

The facts gathered here are the basis of docs/01_data_inventory.md.

Usage:  python pipeline/02_inspect.py
"""
import io
import json
import zipfile

import geopandas as gpd
import pandas as pd

from config import INTERIM, RAW, SOURCES


def fname(key: str) -> str:
    return SOURCES[key].rsplit("/", 1)[-1]


def describe_df(df: pd.DataFrame) -> dict:
    out = {
        "rows": int(len(df)),
        "columns": {c: str(t) for c, t in df.dtypes.items()},
        "nulls": {c: int(n) for c, n in df.isna().sum().items()},
        "sample": df.head(3).astype(str).to_dict(orient="records"),
        "n_unique": {c: int(df[c].nunique()) for c in df.columns if c != "geometry"},
    }
    return out


def inspect_trips() -> dict:
    zpath = RAW / fname("trips")
    with zipfile.ZipFile(zpath) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        info = {"zip_members": [(m.filename, m.file_size) for m in members]}
        csv = next(m for m in members if m.filename.lower().endswith(".csv"))
        with z.open(csv) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), low_memory=False)
    info.update(describe_df(df))
    # Value ranges for anything that looks like a date or a numeric column
    ranges = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            ranges[c] = [str(s.min()), str(s.max())]
        elif "fecha" in c.lower() or "date" in c.lower():
            d = pd.to_datetime(s, errors="coerce")
            ranges[c] = [str(d.min()), str(d.max()), f"unparsed={int(d.isna().sum())}"]
        elif s.nunique() <= 12:
            ranges[c] = s.value_counts(dropna=False).astype(int).to_dict()
    info["ranges"] = {k: {str(a): b for a, b in v.items()} if isinstance(v, dict) else v for k, v in ranges.items()}
    return info


def inspect_users() -> dict:
    df = pd.read_csv(RAW / fname("users"), low_memory=False, encoding_errors="replace")
    info = describe_df(df)
    info["value_counts"] = {
        c: df[c].value_counts(dropna=False).head(15).astype(int).rename(str).to_dict()
        for c in df.columns if df[c].nunique() <= 15
    }
    return info


def inspect_geo(key: str) -> dict:
    g = gpd.read_file(RAW / fname(key))
    info = describe_df(g.drop(columns="geometry"))
    info["crs"] = str(g.crs)
    info["geom_types"] = g.geom_type.value_counts().astype(int).to_dict()
    info["bounds"] = [round(float(b), 5) for b in g.total_bounds]
    return info


def main() -> None:
    report = {
        "trips": inspect_trips(),
        "users": inspect_users(),
        "barrios": inspect_geo("barrios"),
        "comunas": inspect_geo("comunas"),
        "calles": inspect_geo("calles"),
        "barrios_poblacion": describe_df(pd.read_csv(RAW / fname("barrios_poblacion"), encoding_errors="replace")),
    }
    (INTERIM / "inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    for k, v in report.items():
        print(f"\n===== {k}: {v['rows']:,} rows")
        for c, t in v["columns"].items():
            print(f"  {c:<32} {t:<10} nulls={v['nulls'][c]:<8} unique={v['n_unique'].get(c, '-')}")
        for extra in ("crs", "geom_types", "bounds", "ranges", "value_counts", "zip_members"):
            if extra in v:
                print(f"  {extra}: {v[extra]}")
        print("  sample:", v["sample"][0])


if __name__ == "__main__":
    main()
