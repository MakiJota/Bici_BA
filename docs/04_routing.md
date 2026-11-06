# 04 · Network and routing

> The street-level map shows **plausible reconstructed routes**, not observed GPS trajectories. EcoBici does not publish trajectories.

## Tools evaluated

| Option | Verdict |
|---|---|
| **NetworkX / SciPy on the official `callejero`** | **Chosen.** It uses the official network the brief prefers, gives full control over one-way rules and cycling infrastructure, and needs no server. SciPy's compiled Dijkstra routes all 94,736 observed pairs for two strategies in about 2.5 minutes. |
| **OSMnx (OpenStreetMap, `bike` profile)** | Used as an **independent check** (step 06b), as in the legacy R project (`dodgr` + OSM bicycle profile). |
| OSRM | Fast and production-grade, but it needs a server or Docker image and an OSM extract. That adds infrastructure without improving on the official network. |
| Valhalla | Has rich bicycle costing, but the same server requirement as OSRM; it would mostly re-encode OSM's view of the network. |

## Network construction (step 05)

| Item | Value |
|---|---:|
| Official street segments | 31,961 |
| Excluded: motorways and ramps (no bicycles allowed) | 306 |
| Excluded: private passages | 30 |
| Network length kept | 3,279 km |
| Directed edges | 41,400 |
| Contraflow edges added (two-way ciclovía on a one-way street) | 2,484 |
| Largest strongly connected component | 98.6 % of nodes |

**Direction.** `sentido` is defined relative to house numbering. The segments are digitised from low to high numbers (99.996 % have `alt_izqini < alt_izqfin`). Known one-way avenues confirm the rule: Av. Córdoba is `CRECIENTE` and its geometry runs west towards higher numbers, Av. Corrientes is `DECRECIENTE` and Callao is `CRECIENTE`. So `CRECIENTE` means travel along the geometry, `DECRECIENTE` against it, and `DOBLE` both ways.

**Cycling infrastructure.** The `bicisenda` field of the street network is filled for only 7 segments, so the official **Ciclovías** layer (2,764 lines, 306 km) is matched to the streets instead. A segment counts as a ciclovía when at least 50 % of its length lies within 10 m of a ciclovía line (3,066 segments, 317 km). **Completeness check:** the layer does not record cycle-specific access rules such as contraflow permissions outside ciclovías, bike-prohibited avenues or turn restrictions. The only cycle-specific rule applied is contraflow on two-way ciclovías.

**Pedestrian streets** stay in the network in both directions at 3× cost (walking the bike), so connectivity is preserved without favouring them.

## Routing (step 06)

1. Each station is **snapped** to the nearest node of the main component. Median distance 24 m, p90 51 m, maximum 305 m. Six stations are more than 100 m from a node because they sit next to large blocks without internal streets (Hipódromo de Palermo, Costanera Norte, Hospital Alvear, Torre Macro, Plaza Irlanda, Soldado de la Frontera).
2. One **Dijkstra** run per origin station gives routes to every observed destination.
3. Two strategies:
   - **Shortest**: minimum distance.
   - **Infrastructure-preferred (primary)**: cost = length × 0.6 on ciclovías, else × 1.0 / 1.15 / 1.3 / 1.5 by road hierarchy (local → trunk), × 3 on pedestrian streets.
4. Routes are assigned to street segments. A route that crosses a segment twice counts once.
5. Segment trips are aggregated by month × day type × time band for the browser.

Routing failures: **0** of 94,736 pairs for both strategies.

## Comparison of assumptions

| Trip-weighted | Shortest | Infrastructure-preferred |
|---|---:|---:|
| Mean route length | 2.71 km | 2.95 km (+8.9 %) |
| Share of length on ciclovías | 33.6 % | 73.9 % |

The two strategies share **44.6 %** of route length and **42 %** of their 200 busiest segments. The street map is therefore sensitive to the assumption, and the app lets users switch between them.

**External check (OpenStreetMap).** For the 500 busiest OD pairs, the OSMnx `bike` network (27,112 nodes, retrieved via Overpass) gives routes with a median length ratio of 0.995 to the primary strategy and 1.018 to the shortest. A routing engine designed for cyclists therefore produces route lengths very close to the primary assumption.

## Outputs

- `data/processed/pair_routes.parquet`: per OD pair, both distances, ciclovía shares and overlap.
- `data/processed/segment_flows.parquet`: trips per street segment (total, by hour, weekday, month and gender; shortest-strategy total).
- `web/data/routes/<i>.bin.gz`: route trees used by the map's *Rutas* layer.
