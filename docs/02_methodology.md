# 02 · Methodology

How 3.16 million bike-sharing transactions become the indicators shown in the map and the report. Numbers refer to 2025 and come from the reports written by the pipeline (`data/processed/*.json`).

## 1. Unit of analysis

A **trip** is one row of `Trips.csv`: undock at an origin station, dock at a destination station. Trips are **observed**. Routes on the street network are **inferred** (see [04 · Routing](04_routing.md)).

## 2. Cleaning (step 03)

Records are flagged, never silently dropped; `valid` marks trips used in the analysis. 3,148,375 of 3,156,182 trips are valid (99.75 %). The main exclusion is duration over 4 h (7,779 trips: lost or unreturned bikes). See [03 · Data quality](03_data_quality.md) for every rule and count.

Round trips (same origin and destination station, 8.7 %) are valid. They count in every trip total but have no route, distance or speed.

## 3. Geography (step 04)

Each station is assigned to the barrio polygon that contains it (one riverside station lies 4 m outside any polygon and is assigned to the nearest barrio), and through it to a comuna. All 403 stations and all 48 barrios are covered.

Territorial **activity** counts each trip touching a unit once: departures + arrivals − internal trips. It is normalised by area (km²) and by the 2010 census population (the only population table published with the barrios dataset, so it is dated).

## 4. Origin–destination matrices (step 07)

For each level (station, barrio, comuna) and each ordered pair (A, B):

| Field | Definition |
|---|---|
| `trips` | trips from A to B |
| `trips_reverse` | trips from B to A |
| `total_bidirectional` | A→B + B→A (A→A counted once) |
| `net_exchange` | A→B − B→A |
| `pct_of_trips` | A→B / all valid trips |
| `dur_mean_min` | mean observed duration of A→B trips |
| `dist_mean_km` | mean estimated network distance of A→B trips |

Every trip is assigned to exactly one ordered pair, so directional flows never double-count. The undirected total is derived only for display.

## 5. Distance, duration and speed

- **Duration**: observed (`duracion_recorrido`, equal to end − start).
- **Distance**: length of the primary inferred route (infrastructure-preferred) between the two stations' network nodes.
- **Speed**: estimated distance / observed duration. It includes stops, detours and leisure riding, so it is lower than riding speed. 665 trips above 35 km/h are implausible for the inferred route and are excluded from distance and speed statistics. In the browser, the mean speed is the ratio of total distance to total time (8.6 km/h); the median trip-level speed is 10.6 km/h.
- Percentiles (p25, median, p75) are computed per group in Python on trip-level data and published as static tables.

## 6. Users

- **Gender** is recorded on each trip (`MALE`, `FEMALE`, `OTHER`, or empty). The categories are reported as recorded; they are not exhaustive and are not inferred.
- **Age** is not in the trip file. Each yearly user file (2015–2025) lists users who *registered* that year with their age at registration. The union of all files matches 93.7 % of trips; age in 2025 = age at registration + (2025 − registration year). Ages outside 16–90 are set to missing. Age results describe the matched subset only.
- Demographic comparisons are **descriptive**: they do not control for trip purpose, distance or the composition of each group.

## 7. Privacy safeguards

| Safeguard | Rule |
|---|---|
| No row-level data published | the browser receives only aggregated cubes, **except** the animation days (below) |
| No identifiers | `id_usuario` is used only for the age join |
| Coarse demographic geography | gender and age cubes exist only at comuna × comuna level |
| Small-cell recoding | a demographic cell with < 10 trips is recoded to `suppressed` (totals preserved; 3.6 % of trips for gender, 7.3 % for age) |
| Display threshold | any demographic figure based on < 30 trips is shown as `n < 30` |
| No cross-tabulation | gender and age are never combined in one cube or filter |

**Animation exception (step 09).** To animate trips, the 9 days in `config.ANIM_DAYS` are published per trip with only origin station, destination station and departure / arrival minute. No user id, gender, age or bike model is included. Each trip moves along its inferred route at constant speed between the observed times; it is not a GPS trajectory.

## 8. Browser data model (step 08)

| Product | Content | Size |
|---|---|---:|
| `od.bin.gz` | 1.33 M cells: station pair × month × weekday/weekend × 6 time bands (count, duration sum) | 4.4 MB |
| `pairs.bin.gz` | station pair → origin, destination, distance (both strategies) | 0.4 MB |
| `calendar.json` | day of year × hour × origin comuna | 2.1 MB |
| `demo_gender.json`, `demo_age.json` | comuna pair × time key × category | 3.1 MB |
| `segments.geojson`, `seg_flows.bin.gz` | routed street segments and their trips per time key | 6.2 MB |
| `routes/<i>.bin.gz` | route trees per origin station (both strategies) | 5.8 MB |

Filters are evaluated in the browser in a single pass over the station cube. Barrio and comuna views are derived from it, so the three geographic levels share one analytical framework. Time bands: 00–07, 07–10, 10–14, 14–17, 17–20, 20–24 h.

## 9. Limitations

- Inferred routes are plausible, not observed; the street-intensity map depends on the routing assumption.
- Time filters in the station cube use months and six time bands. Hour-level and day-level detail comes from the calendar table, which supports only comuna-level spatial filtering.
- The 2010 population figures are dated.
- Several days have very low activity (e.g. 17 May 2025: 543 trips). The cause has not been verified, and the days are kept.
