"""EDA 02 - Where do trips go? Station usage, net flows, comuna OD matrix, top relations."""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _style import INK, LIGHT, MID, PROCESSED, RAW, save

st = pd.read_parquet(PROCESSED / "station_stats.parquet")
comunas = gpd.read_file(RAW / "comunas.geojson")
barrios = gpd.read_file(RAW / "barrios.geojson")

# Station usage map (size = total trips) and net flow (fill = arrivals - departures)
fig, axes = plt.subplots(1, 2, figsize=(10, 5))
for ax in axes:
    barrios.boundary.plot(ax=ax, color=LIGHT, lw=0.4)
    comunas.boundary.plot(ax=ax, color=MID, lw=0.7)
    ax.set_axis_off()
axes[0].scatter(st.lon, st.lat, s=st.total / st.total.max() * 120, color=INK, alpha=0.6, lw=0)
axes[0].set_title("Station activity (departures + arrivals)")
size = np.abs(st.net_flow) / np.abs(st.net_flow).max() * 160 + 3
pos = st.net_flow > 0
axes[1].scatter(st.lon[pos], st.lat[pos], s=size[pos], color=INK, lw=0, label="net inflow (more arrivals)")
axes[1].scatter(st.lon[~pos], st.lat[~pos], s=size[~pos], facecolor="white", edgecolor=INK, lw=0.7, label="net outflow (more departures)")
axes[1].set_title("Net flow (arrivals - departures), size = magnitude")
axes[1].legend(frameon=False, loc="lower left", fontsize=7)
save(fig, "02_station_activity_netflow")

# Ranked stations
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
top = st.nlargest(15, "total").iloc[::-1]
axes[0].barh(top.name.str.slice(0, 28), top.total, color=INK)
axes[0].set_title("Most used stations")
nf = pd.concat([st.nsmallest(8, "net_flow"), st.nlargest(8, "net_flow")]).sort_values("net_flow")
axes[1].barh(nf.name.str.slice(0, 28), nf.net_flow, color=np.where(nf.net_flow > 0, INK, LIGHT), edgecolor=MID)
axes[1].set_title("Largest net inflow (+) and outflow (-)")
save(fig, "02_station_rankings")

# Comuna OD matrix (share of all trips, %)
od = pd.read_parquet(PROCESSED / "od_comuna.parquet")
mat = od.pivot_table(index="from", columns="to", values="pct_of_trips", fill_value=0)
fig, ax = plt.subplots(figsize=(6, 5))
im = ax.imshow(mat.values, cmap="Greys")
ax.set(xticks=range(15), xticklabels=mat.columns, yticks=range(15), yticklabels=mat.index,
       xlabel="Destination comuna", ylabel="Origin comuna", title="Origin-destination matrix by comuna (% of trips)")
ax.grid(False)
fig.colorbar(im, ax=ax, shrink=0.8)
save(fig, "02_od_comuna_heatmap")

# Top inter-comuna and inter-barrio relations
for level in ("comuna", "barrio"):
    o = pd.read_parquet(PROCESSED / f"od_{level}.parquet")
    o = o[~o.internal].nlargest(20, "trips").iloc[::-1]
    fig, ax = plt.subplots(figsize=(6, 5))
    lab = o["from"].astype(str) + " → " + o["to"].astype(str)
    ax.barh(lab, o.trips, color=INK, label="A → B")
    ax.barh(lab, -o.trips_reverse, color=LIGHT, edgecolor=MID, label="B → A")
    ax.set_title(f"Top 20 directional relations between {level}s")
    ax.legend(frameon=False, loc="lower right")
    save(fig, f"02_top_relations_{level}")

ti = pd.read_parquet(PROCESSED / "territory_indicators.parquet")
c = ti[ti.level == "comuna"].sort_values("activity_per_1000_residents", ascending=False)
print(c[["unit", "outgoing", "incoming", "net_flow", "internal_share", "activity_per_km2", "activity_per_1000_residents"]]
      .round(2).to_string(index=False))
