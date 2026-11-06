"""EDA 01 - When do people ride? Hour, weekday, month, hour x weekday, daily series."""
import matplotlib.pyplot as plt
import numpy as np

from _style import DOW, INK, LIGHT, MID, MONTHS, save, trips

t = trips(["start", "hour", "dow", "month", "weekend"])
t["date"] = t.start.dt.normalize()
n_wd = t.loc[~t.weekend, "date"].nunique()
n_we = t.loc[t.weekend, "date"].nunique()

# Hourly profile per average day, weekday vs weekend
fig, ax = plt.subplots(figsize=(7, 3))
wd = t[~t.weekend].groupby("hour").size() / n_wd
we = t[t.weekend].groupby("hour").size() / n_we
ax.bar(wd.index - 0.2, wd.values, width=0.4, color=INK, label=f"Weekday (avg of {n_wd} days)")
ax.bar(we.index + 0.2, we.values, width=0.4, color=LIGHT, edgecolor=MID, label=f"Weekend (avg of {n_we} days)")
ax.set(title="Trips per hour, average day", xlabel="Hour of departure", ylabel="Trips", xticks=range(0, 24, 2))
ax.legend(frameon=False)
save(fig, "01_hourly_weekday_weekend")

# Weekday totals (average per day of that weekday)
fig, ax = plt.subplots(figsize=(5, 3))
per = t.groupby("dow").size() / t.groupby("dow").date.nunique()
ax.bar(DOW, per.values, color=[INK] * 5 + [MID] * 2)
ax.set(title="Average trips per day of the week", ylabel="Trips per day")
save(fig, "01_weekday")

# Monthly
fig, ax = plt.subplots(figsize=(6, 3))
m = t.groupby("month").size() / t.groupby("month").date.nunique()
ax.plot(MONTHS, m.values, color=INK, marker="o", lw=1.5)
ax.set(title="Average daily trips by month", ylabel="Trips per day", ylim=(0, m.max() * 1.15))
save(fig, "01_monthly")

# Hour x weekday heatmap
fig, ax = plt.subplots(figsize=(7, 2.8))
h = t.groupby(["dow", "hour"]).size().unstack(fill_value=0) / t.groupby("dow").date.nunique().to_numpy()[:, None]
im = ax.imshow(h.values, aspect="auto", cmap="Greys")
ax.set(yticks=range(7), yticklabels=DOW, xticks=range(0, 24, 2), xlabel="Hour", title="Average trips: hour x weekday")
ax.grid(False)
fig.colorbar(im, ax=ax, label="Trips per day-hour")
save(fig, "01_hour_weekday_heatmap")

# Daily series with 7-day mean
fig, ax = plt.subplots(figsize=(8, 2.8))
d = t.groupby("date").size()
ax.plot(d.index, d.values, color=LIGHT, lw=0.8, label="Daily")
ax.plot(d.index, d.rolling(7, center=True).mean(), color=INK, lw=1.4, label="7-day mean")
ax.set(title="Daily trips, 2025", ylabel="Trips")
ax.legend(frameon=False)
save(fig, "01_daily_series")

print("weekday AM peak:", int(wd.loc[5:11].idxmax()), "PM peak:", int(wd.loc[15:21].idxmax()))
print("weekday/weekend daily ratio:", round(float(wd.sum() / we.sum()), 2))
print("min / max day:", d.idxmin().date(), int(d.min()), "/", d.idxmax().date(), int(d.max()))
print("CV of monthly averages:", round(float(np.std(m) / np.mean(m)), 3))
