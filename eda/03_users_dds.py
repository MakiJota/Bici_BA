"""EDA 03 - Who rides and how far / long / fast? Gender, age, distance, duration, speed.

Demographic figures use only categories recorded in the source; groups with
fewer than MIN_CELL trips are not shown.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _style import INK, LIGHT, MID, PROCESSED, save, trips
from config import MAX_SPEED_KMH, MIN_CELL

t = trips(["o", "d", "duration_s", "hour", "weekend", "gender", "age_group", "round_trip"])
t["o"], t["d"] = t.o.astype(int), t.d.astype(int)
pr = pd.read_parquet(PROCESSED / "pair_routes.parquet", columns=["o", "d", "dist_infra_m"])
t = t.merge(pr, on=["o", "d"], how="left")
t.loc[t.round_trip, "dist_infra_m"] = np.nan
t["km"] = t.dist_infra_m / 1000
t["min"] = t.duration_s / 60
t["kmh"] = t.km / (t.duration_s / 3600)
r = t[t.km.notna() & (t.kmh <= MAX_SPEED_KMH)]

# Distributions
fig, axes = plt.subplots(1, 3, figsize=(11, 3))
for ax, s, lab, rng in ((axes[0], t["min"], "Duration (min)", (0, 90)), (axes[1], r.km, "Estimated network distance (km)", (0, 12)),
                        (axes[2], r.kmh, "Estimated speed (km/h)", (0, 30))):
    ax.hist(s.clip(*rng), bins=60, range=rng, color=INK)
    for q, ls in ((0.25, ":"), (0.5, "-"), (0.75, ":")):
        ax.axvline(s.quantile(q), color=MID, ls=ls, lw=1)
    ax.set(xlabel=lab, ylabel="Trips")
fig.suptitle("Distributions (lines: p25, median, p75). Distance and speed are estimates from inferred routes", fontsize=9)
save(fig, "03_distributions")

# Gender: hourly share profiles
g = t[t.gender.notna()].copy()
g["gender"] = g.gender.astype(str)
counts = g.gender.value_counts()
keep = counts[counts >= MIN_CELL].index
fig, ax = plt.subplots(figsize=(7, 3))
for gen, col, ls in zip(["MALE", "FEMALE", "OTHER"], [INK, INK, MID], ["-", "--", ":"]):
    if gen in keep:
        h = g[g.gender == gen].hour.value_counts(normalize=True).sort_index() * 100
        ax.plot(h.index, h.values, color=col, ls=ls, lw=1.5, label=f"{gen} (n={counts[gen]:,})")
ax.set(title="Hourly profile by recorded gender (% of each group's trips)", xlabel="Hour", ylabel="%", xticks=range(0, 24, 2))
ax.legend(frameon=False)
save(fig, "03_gender_hourly")

# Age groups: trips and median duration / distance
a = t[t.age_group.notna()]
ag = a.groupby("age_group", observed=True).agg(n=("min", "size"), dur=("min", "median"))
ag["km"] = r[r.age_group.notna()].groupby("age_group", observed=True).km.median()
ag = ag[ag.n >= MIN_CELL]
fig, axes = plt.subplots(1, 2, figsize=(9, 3))
axes[0].bar(ag.index.astype(str), ag.n, color=INK)
axes[0].set(title="Trips by age group (matched users only)", ylabel="Trips")
axes[1].plot(ag.index.astype(str), ag.dur, color=INK, marker="o", label="median duration (min)")
axes[1].plot(ag.index.astype(str), ag.km * 5, color=MID, marker="s", ls="--", label="median distance (km) × 5")
axes[1].set(title="Median duration and distance by age group")
axes[1].legend(frameon=False)
save(fig, "03_age_groups")

# Box-like summary by group
def q(df, col, by):
    return df.groupby(by, observed=True)[col].describe(percentiles=[.25, .5, .75])[["count", "25%", "50%", "75%"]]

print("duration by gender (min)\n", q(t.assign(gender=t.gender.astype(str)), "min", "gender").round(1))
print("speed by gender (km/h)\n", q(r.assign(gender=r.gender.astype(str)), "kmh", "gender").round(2))
print("distance weekday/weekend (km)\n", q(r, "km", "weekend").round(2))
print("speed weekday/weekend (km/h)\n", q(r, "kmh", "weekend").round(2))
print("implausible speed trips:", int((t.kmh > MAX_SPEED_KMH).sum()))
