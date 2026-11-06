# Buenos Aires Bike Sharing Mobility Explorer

## Project objective

Develop a bilingual (Spanish/English), interactive urban mobility visualization platform for Buenos Aires, Argentina, using public bicycle-sharing data and official geographic datasets.

The primary objective is to reconstruct and visualize cycling movements between public bicycle-sharing stations, identify the main streets used by cyclists through inferred routing, and analyse mobility patterns across different geographical scales.

The application must combine an interactive map with a dedicated analytical report.

The default interface language is Spanish. English must be available through a language selector.

The visual identity must be minimalist, predominantly black and white, with a restrained monochromatic palette.

The final application must be deployable through GitHub Pages.

---

# 1. Specialist agents and workstreams

Organize the project into three coordinated specialist workstreams.

## Agent 1 — Data Engineer and Data Quality Specialist

Responsibilities:

- Inspect all original datasets and their metadata.
- Download and document available resources.
- Identify available fields, formats, temporal coverage and spatial reference systems.
- Investigate whether individual trips contain gender, age or other user attributes.
- Identify station identifiers and geographic coordinates.
- Validate origin and destination station identifiers.
- Validate timestamps and trip durations.
- Detect missing, duplicated and inconsistent records.
- Process official street geometries, barrios and comunas.
- Establish a reproducible data ingestion pipeline.
- Create optimized datasets for the frontend.

Deliverables:

- Data inventory and metadata report.
- Cleaned trip dataset.
- Station dataset.
- Official street network.
- Barrios and comunas geographic layers.
- Data quality report.
- Reproducible processing scripts.

Never assume that a field exists before inspecting the source data.

## Agent 2 — Urban Mobility and Network Analysis Specialist

Responsibilities:

- Perform exploratory data analysis.
- Reconstruct station-to-station journeys.
- Build a directed cycling network.
- Incorporate one-way restrictions and cycling infrastructure.
- Snap stations to appropriate network nodes.
- Calculate plausible routes.
- Assign reconstructed trips to street segments.
- Calculate spatial and temporal mobility indicators.
- Identify the main origin–destination relationships.
- Evaluate differences between user groups where supported by data.
- Produce analytical statistics for the report.

Evaluate NetworkX, OSMnx, OSRM and Valhalla as possible routing solutions.

Prefer the official Buenos Aires street network as the initial geographic reference, supplemented by OpenStreetMap when necessary.

Clearly distinguish observed origin–destination trips from inferred street-level routes. Do not describe reconstructed routes as actual GPS trajectories.

## Agent 3 — Frontend, UI/UX and Visualization Specialist

Responsibilities:

- Design the web application.
- Implement the interactive map.
- Implement the analytical report.
- Create temporal and geographical filters.
- Implement bilingual navigation.
- Create interactive flow diagrams.
- Develop responsive layouts.
- Optimize data delivery and map rendering.
- Implement GitHub Pages deployment.

The interface should be intuitive to both urban mobility researchers and members of the general public.

---

# 2. Original data sources

Use these official Buenos Aires Open Data resources:

1. Bicycle-sharing system:
   https://data.buenosaires.gob.ar/dataset/bicicletas-publicas

2. Neighborhood boundaries:
   https://data.buenosaires.gob.ar/dataset/barrios

3. Commune boundaries:
   https://data.buenosaires.gob.ar/dataset/comunas

4. Official street network:
   https://data.buenosaires.gob.ar/dataset/calles

Inspect all available downloadable resources before deciding which files to use.

The user will also provide additional street data if necessary.

Document the original source, license, date of retrieval, geographic coverage and temporal coverage of each dataset.

---

# 3. Application structure

The application must have two main sections.

## Section A — Mapa de movilidad / Mobility Map

An interactive city map displaying:

- All bicycle-sharing stations.
- Origin and destination relationships.
- Reconstructed cycling routes.
- Street-level cycling intensity.
- Barrios boundaries.
- Comunas boundaries.
- Optional cycling infrastructure.

### Map layers

Implement independent, switchable layers:

1. Estaciones — bicycle-sharing stations.
2. Viajes OD — origin–destination connections.
3. Rutas — reconstructed street-level routes.
4. Intensidad vial — aggregated trip frequency by street.
5. Barrios — neighborhood boundaries.
6. Comunas — commune boundaries.
7. Infraestructura ciclista — cycle lanes and cycling infrastructure, where available.

### Map interactions

Users must be able to:

- Zoom and pan.
- Select individual stations.
- View station names and usage statistics.
- Select origin and destination stations.
- Display connections between stations.
- Filter by date and time.
- Filter by weekday or weekend.
- Filter by gender or age, if available.
- Select a geographical aggregation level.
- Inspect incoming and outgoing flows.
- Compare different time periods.

### Station information

Each station popup should contain:

- Station name and identifier.
- Number of departures.
- Number of arrivals.
- Total number of associated trips.
- Net flow.
- Most frequent destinations.
- Most frequent origins.
- Temporal usage distribution.

### Street information

When selecting a street segment, display:

- Street name.
- Number of inferred trips.
- Share of total reconstructed trips.
- Cycling infrastructure characteristics, if available.
- Temporal distribution of cycling activity.

---

# 4. Geographical flow analysis

Implement three aggregation levels:

1. Estaciones / Stations.
2. Barrios / Neighborhoods.
3. Comunas / Communes.

The user must be able to switch between them without changing the overall analytical framework.

### Origin–destination flow matrix

Calculate a directed origin–destination matrix at each geographical level.

For every pair of geographical units, calculate:

- Number of trips from A to B.
- Number of trips from B to A.
- Total bidirectional trips.
- Net directional exchange.
- Percentage of total trips.
- Average duration, where available.
- Estimated distance, where available.

Avoid counting trips twice when calculating directional flows.

### Interactive geographical arrows

Implement an interactive flow visualization using arrows connecting geographic units.

Arrow characteristics:

- Direction represents travel direction.
- Thickness represents trip volume.
- Optional labels display trip counts.
- Hover displays detailed statistics.
- Clicking a geographical unit highlights its incoming and outgoing connections.

Allow users to select:

- All geographical units.
- One origin commune or neighborhood.
- One destination commune or neighborhood.
- A specific pair of territories.

Provide an option to display the strongest 10, 20 or 50 flows.

### Spatial indicators

Calculate:

- Top origin–destination pairs.
- Top outgoing territories.
- Top incoming territories.
- Net inflow/outflow.
- Internal trips within the same territory.
- Inter-territorial trips.
- Territorial cycling activity per area.
- Territorial cycling activity per population, if an appropriate population dataset is added.

---

# 5. Section B — Informe de movilidad / Mobility Report

Create a dedicated report section with interactive charts, statistical summaries and explanatory text.

The report must use actual calculated statistics from the cleaned dataset.

All figures must respond to the selected temporal and geographical filters wherever appropriate.

## A. Panorama general / General overview

Display key indicators:

- Total bicycle trips.
- Average daily trips.
- Number of active stations.
- Number of origin stations.
- Number of destination stations.
- Average trip duration.
- Median trip duration.
- Average estimated distance.
- Average estimated speed, if reliable.
- Share of trips within the same commune.
- Share of trips between different communes.

Show the selected period and sample size.

## B. Relaciones territoriales / Territorial relationships

Analyse the strongest relationships between:

- Comunas.
- Barrios.
- Stations.

Include:

- Top 20 directional origin–destination relationships.
- Directional flow comparisons.
- Incoming versus outgoing trips.
- Net territorial exchange.
- Internal versus external trips.

Visualizations:

- Interactive directional flow map.
- Sankey diagram.
- Origin–destination heatmap.
- Ranked horizontal bar charts.

Allow switching between commune, neighborhood and station levels.

## C. Distribución temporal / Temporal distribution

Analyse:

- Trips by hour of day.
- Trips by weekday.
- Weekday versus weekend.
- Monthly distribution.
- Seasonal variation, where temporal coverage permits.
- Morning and evening peak periods.

Visualizations:

- Hourly bar chart.
- Weekday bar chart.
- Month-by-month trend.
- Hour × weekday heatmap.
- Interactive comparison between periods.

Allow selection of specific days, hours and months.

## D. Características de los usuarios / User characteristics

First establish which user characteristics are actually present in the original data.

If available, investigate:

- Gender.
- Age.
- User category.
- Other relevant demographic fields.

Analyse gender differences where supported:

- Number and percentage of trips.
- Hourly travel patterns.
- Weekday/weekend differences.
- Trip duration.
- Estimated distance.
- Estimated speed.
- Origin–destination relationships.
- Station preferences.

For age, calculate distributions and compare travel patterns across age groups.

Do not infer missing demographic attributes or assume gender categories are exhaustive.

Apply minimum sample-size and privacy safeguards before publishing demographic breakdowns.

## E. Distancia, duración y velocidad / Distance, duration and speed

Calculate:

- Trip duration.
- Estimated network distance.
- Estimated average speed.
- Median distance and duration.
- 25th and 75th percentiles.
- Distance and duration distributions.

Compare these indicators across:

- Communes.
- Neighborhoods.
- Gender, if available.
- Age groups, if available.
- Weekdays and weekends.
- Different hours of the day.

Use reconstructed network distances rather than straight-line distances when reliable routing is available.

Estimated average speed must be calculated using estimated route distance and observed trip duration.

Flag implausible records and document the treatment of outliers.

These are estimated trip characteristics, not GPS-measured cycling speeds.

## F. Estaciones y calles / Stations and streets

Rank:

- Most-used stations.
- Highest departure stations.
- Highest arrival stations.
- Stations with the largest net inflows.
- Stations with the largest net outflows.
- Most frequently traversed street segments.
- Streets with the greatest inferred cycling intensity.

Provide interactive maps and ranked bar charts.

---

# 6. Temporal and geographical filtering

Filters should be shared between the map and report wherever possible.

Required filters:

- Date range.
- Month.
- Weekday.
- Weekend.
- Hour range.
- Commune.
- Neighborhood.
- Station.
- Origin.
- Destination.
- Gender, if available.
- Age group, if available.

Provide a clear reset-filters option.

Ensure charts and maps update consistently when filters change.

---

# 7. Routing and street-level reconstruction

Build a directed cycling network from the official street data.

The network should consider:

- Street geometry.
- Street direction.
- One-way restrictions.
- Cycling infrastructure.
- Cycle lanes.
- Connectivity.
- Street hierarchy.

Evaluate whether cycle-specific restrictions and access rules are sufficiently complete.

### Routing workflow

1. Validate station coordinates.
2. Snap each station to the closest suitable network node.
3. Construct the directed street graph.
4. Calculate candidate routes between origin and destination stations.
5. Assign reconstructed routes to street segments.
6. Aggregate trip counts by segment.
7. Generate optimized spatial outputs.

Compare alternative routing strategies where possible:

- Shortest-distance route.
- Cycling infrastructure-preferred route.
- Routing based on OpenStreetMap cycling profiles.

Document the assumptions used.

Where actual GPS trajectories are unavailable, explain that the street-level map represents plausible reconstructed routes rather than observed paths.

---

# 8. Visual identity and interface

The visual language must be minimalist and predominantly monochromatic.

### Design guidelines

- Black and white as primary colors.
- Grey variations for secondary information.
- High-contrast typography.
- Minimal decorative elements.
- Clean map backgrounds.
- Consistent chart styles.
- Clear legends.
- Responsive desktop and mobile layouts.

Use visual emphasis through line thickness, opacity, size and contrast.

Avoid excessive colors.

### Language

Spanish must be the default language.

English must be available through a language toggle.

Translate all:

- Navigation.
- Buttons.
- Tooltips.
- Chart labels.
- Legends.
- Filters.
- Report descriptions.
- Methodological explanations.

Do not translate original geographical names.

---

# 9. Technical architecture

Suggested architecture:

### Data processing

Python:

- Pandas.
- GeoPandas.
- Shapely.
- NetworkX.
- OSMnx.
- PyArrow / Parquet.

### Frontend

Evaluate:

- Leaflet or MapLibre GL JS.
- Plotly.
- JavaScript or TypeScript.
- A lightweight static application framework.

### Data storage

Use optimized static data products:

- Parquet for analytical tables.
- GeoJSON or vector tiles for geographic layers.
- Pre-aggregated origin–destination matrices.
- Aggregated temporal statistics.

Avoid sending the entire raw trip database to the browser.

### GitHub deployment

The final application must be hosted on GitHub Pages.

Repository should include:

- Source code.
- Data processing scripts.
- Documentation.
- Configuration.
- Optimized public datasets.
- GitHub Actions workflow.
- Deployment instructions.

Use GitHub Actions to automate the build and deployment.

Keep large raw datasets outside the GitHub repository when necessary. Publish only appropriately licensed, optimized and privacy-safe derived data.

The application must work without a permanently running backend server.

---

# 10. Statistical quality and validation

Before publishing the report:

- Validate trip counts against the original data.
- Validate origin and destination station matching.
- Inspect missing timestamps.
- Identify duplicate records.
- Check impossible or implausible durations.
- Validate station coordinates.
- Validate network connectivity.
- Inspect routing failures.
- Compare alternative routing assumptions.
- Check spatial aggregation consistency.
- Document all exclusions and assumptions.

For demographic comparisons, report sample sizes and avoid interpreting differences without considering sampling and data-quality limitations.

Do not invent statistics where the original data cannot support them.

---

# 11. Expected project deliverables

1. Complete data inventory.
2. Reproducible data ingestion pipeline.
3. Cleaned and validated datasets.
4. Reconstructed cycling network.
5. Origin–destination matrices.
6. Street-level inferred cycling intensity.
7. Temporal and demographic statistics, where available.
8. Interactive mobility map.
9. Interactive analytical report.
10. Spanish and English interface.
11. GitHub repository.
12. GitHub Pages deployment.
13. Technical documentation and methodological report.

---

# 12. Final objective

The final platform should allow residents, researchers and urban planners to understand how Buenos Aires moves by bicycle.

It should answer:

- Where do bicycle trips originate?
- Where do they go?
- Which communes and neighborhoods are most strongly connected?
- Which direction are the main flows moving?
- Which streets carry the highest inferred cycling volumes?
- When does cycling activity peak?
- Which stations are most frequently used?
- Do travel patterns differ across user groups?
- How far and how long do people travel?

The platform should turn individual bicycle-sharing transactions into a comprehensive picture of urban cycling mobility.

**The main objective is not simply to visualize bicycle stations, but to reconstruct and understand the spatial structure of bicycle mobility across Buenos Aires.**