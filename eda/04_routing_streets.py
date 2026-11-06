"""EDA 04 - Routing assumptions and street-level intensity.

Street maps show INFERRED routes (plausible reconstructions), not GPS tracks.
"""
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _style import INK, LIGHT, MID, PROCESSED, RAW, save

seg = gpd.read_parquet(PROCESSED / "network_segments.parquet")
flows = pd.read_parquet(PROCESSED / "segment_flows.parquet")
s = seg.merge(flows[["seg_id", "trips", "trips_shortest"]], on="seg_id", how="left").fillna({"trips": 0, "trips_shortest": 0})
comunas = gpd.read_file(RAW / "comunas.geojson")

fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
for ax, col, title in ((axes[0], "trips", "Infrastructure-preferred (primary)"), (axes[1], "trips_shortest", "Shortest distance")):
    comunas.boundary.plot(ax=ax, color=LIGHT, lw=0.5)
    x = s[s[col] > 0].sort_values(col)
    w = 0.15 + 2.6 * (x[col] / s[col].max()) ** 0.6
    x.plot(ax=ax, color=INK, linewidth=w, alpha=0.85)
    ax.set_title(f"Inferred street intensity — {title}")
    ax.set_axis_off()
save(fig, "04_street_intensity_strategies")

# Cycling infrastructure overlay
cv = gpd.read_file(RAW / "ciclovias.geojson")
fig, ax = plt.subplots(figsize=(6, 6))
comunas.boundary.plot(ax=ax, color=LIGHT, lw=0.5)
cv.plot(ax=ax, color=INK, lw=0.6)
ax.set_title("Official cycling infrastructure (ciclovías)")
ax.set_axis_off()
save(fig, "04_ciclovias")

# Strategy comparison per OD pair
pr = pd.read_parquet(PROCESSED / "pair_routes.parquet")
pr = pr[pr.dist_shortest_m > 0]
fig, axes = plt.subplots(1, 3, figsize=(11, 3))
det = (pr.dist_infra_m / pr.dist_shortest_m - 1) * 100
axes[0].hist(det.clip(0, 40), bins=40, weights=pr.trips, color=INK)
axes[0].set(title="Detour of primary vs shortest (%)", xlabel="%", ylabel="Trips")
axes[1].hist(pr.infra_share_shortest, bins=40, weights=pr.trips, color=LIGHT, edgecolor=MID, label="shortest")
axes[1].hist(pr.infra_share_infra, bins=40, weights=pr.trips, color=INK, alpha=0.7, label="primary")
axes[1].set(title="Share of route on ciclovías", xlabel="share")
axes[1].legend(frameon=False)
axes[2].hist(pr.overlap_infra_vs_shortest, bins=40, weights=pr.trips, color=INK)
axes[2].set(title="Route overlap (primary ∩ shortest)", xlabel="share of primary length")
save(fig, "04_strategy_comparison")

osm = json.loads((PROCESSED / "osm_comparison.json").read_text())
if osm.get("status") == "ok":
    o = pd.read_parquet(PROCESSED / "osm_comparison_pairs.parquet").dropna(subset=["dist_osm_bike_m"])
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(o.dist_infra_m / 1000, o.dist_osm_bike_m / 1000, s=np.sqrt(o.trips), color=INK, alpha=0.5, lw=0)
    m = max(o.dist_infra_m.max(), o.dist_osm_bike_m.max()) / 1000
    ax.plot([0, m], [0, m], color=MID, ls="--", lw=1)
    ax.set(xlabel="Official network, primary (km)", ylabel="OSM bicycle profile (km)",
           title=f"Top {len(o)} OD pairs: route length")
    save(fig, "04_osm_vs_official")

snap = pd.read_parquet(PROCESSED / "station_snap.parquet")
top = s.nlargest(15, "trips")[["nomoficial", "trips", "infra"]]
print(top.to_string(index=False))
print("snap distance p50/p90/max (m):", snap.snap_m.quantile([.5, .9, 1]).round(1).tolist())
print("trips on ciclovía segments share of segment-trips:", round(float((s.trips * s.infra).sum() / s.trips.sum()), 3))
