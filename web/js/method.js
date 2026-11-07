// Methodology page (bilingual). All numbers come from meta.json (pipeline reports).
import { D } from "./data.js";
import { fmt, getLang, pct } from "./i18n.js";

export function renderMethod() {
  const m = D.meta, q = m.quality, n = m.network, r = m.routing, o = m.osm, s = m.summary;
  const es = getLang() === "es";
  const osmLine = o.status === "ok"
    ? (es ? `En los ${fmt(o.pairs_routed)} pares OD con más viajes, la ruta en bicicleta de OpenStreetMap (OSMnx) difiere en una mediana de ${pct(o.median_ratio_osm_to_official_infra - 1)} respecto de la ruta principal sobre la red oficial.`
          : `For the ${fmt(o.pairs_routed)} busiest OD pairs, the OpenStreetMap bicycle route (OSMnx) differs by a median of ${pct(o.median_ratio_osm_to_official_infra - 1)} from the primary route on the official network.`)
    : (es ? "La comparación con OpenStreetMap no pudo ejecutarse." : "The OpenStreetMap comparison could not be run.");
  const html = es ? `
  <h2>Metodología</h2>
  <p>Esta plataforma transforma los viajes individuales del sistema de bicicletas públicas (EcoBici) de ${m.year} en una lectura agregada de la movilidad en bicicleta en la Ciudad de Buenos Aires. Todo el procesamiento es reproducible con los scripts de <code>pipeline/</code> del repositorio.</p>
  <h2>Fuentes</h2>
  <ul>
    <li><b>Bicicletas públicas</b>: recorridos realizados ${m.year} (${fmt(q.raw_rows)} registros) y archivos anuales de usuarios 2015–${m.year}.</li>
    <li><b>Barrios</b> y <b>Comunas</b>: límites oficiales; población por barrio del censo 2010 (dato desactualizado, usado solo como referencia).</li>
    <li><b>Calles</b>: callejero oficial (red vial con sentido de circulación) y <b>Ciclovías</b> oficiales.</li>
  </ul>
  <p>${m.attribution}.</p>
  <h2>Limpieza y validación</h2>
  <p>Se conservan ${fmt(q.valid_trips)} viajes válidos (${pct(q.valid_trips / q.raw_rows, 2)}). Se excluyen viajes de más de 4 horas (${fmt(q.flags.too_long)}), con estación desconocida o sin destino (${fmt(q.flags.unknown_station + q.flags.missing_dest)}) y con duración inconsistente (${fmt(q.flags.duration_mismatch)}). No se encontraron duplicados. Los viajes circulares (misma estación de origen y destino, ${pct(s.round_trip_share)}) son válidos pero no tienen ruta ni distancia.</p>
  <h2>Viajes observados y rutas inferidas</h2>
  <p><b>Los pares origen–destino son observados.</b> Las <b>rutas por calle son inferidas</b>: el sistema no publica trayectorias GPS. Para cada par de estaciones se calcula una ruta plausible sobre una red dirigida construida con el callejero oficial (${fmt(n.network_km)} km; ${fmt(n.directed_edges)} arcos dirigidos), que respeta el sentido de circulación, excluye autopistas, penaliza calles peatonales y agrega contramano solo donde hay ciclovía bidireccional (${fmt(n.contraflow_edges_added)} arcos). La red conserva el componente fuertemente conexo principal (${pct(n.largest_scc_share_nodes)} de los nodos).</p>
  <p>Se comparan dos supuestos: <b>ruta más corta</b> y <b>ruta que prioriza ciclovías</b> (principal), que pondera cada metro por 0,6 en ciclovía y entre 1,0 y 1,5 según la jerarquía vial. La ruta principal es en promedio ${pct(r.detour_infra_vs_shortest)} más larga y recorre ${pct(r.trip_weighted.infra_share_infra)} de su longitud sobre ciclovías (frente a ${pct(r.trip_weighted.infra_share_shortest)} en la más corta). Ambas rutas comparten solo ${pct(r.trip_weighted.overlap_infra_vs_shortest)} de su longitud: <b>la intensidad por calle depende del supuesto</b>. ${osmLine}</p>
  <p>Las estaciones se asignan al nodo más cercano de la red (mediana ${fmt(r.snap_m["50%"], 0)} m; máximo ${fmt(r.snap_m.max, 0)} m en estaciones junto a grandes predios).</p>
  <h2>Distancia, duración y velocidad</h2>
  <p>La duración es observada. La distancia es la longitud de la ruta inferida principal. La velocidad estimada es distancia estimada / duración observada; incluye paradas y desvíos, por lo que no es una velocidad de pedaleo. ${fmt(s.speed_implausible_trips)} viajes con velocidad estimada mayor a ${s.max_speed_kmh} km/h se excluyen de las estadísticas de distancia y velocidad.</p>
  <h2>Usuarios y privacidad</h2>
  <p>El género figura en cada viaje tal como fue registrado (categorías no exhaustivas). La edad no figura en los viajes; se obtiene de los archivos de usuarios para ${pct(q.age_available_share)} de los viajes y se estima como edad al registrarse más los años transcurridos. No se infieren atributos faltantes. Los datos demográficos se publican solo a nivel de comuna; las celdas con menos de ${m.min_publish} viajes se recodifican como «suprimido» y cualquier cifra con menos de ${m.min_cell} viajes no se muestra. Los filtros de género y edad no se combinan. No se publican identificadores de usuario. La única excepción a la publicación agregada es la <b>animación</b>: para 9 días seleccionados se publica cada viaje solo con estación de origen, estación de destino y minuto de salida y llegada (sin usuario, género ni edad); el recorrido animado es la ruta inferida a velocidad constante, no una trayectoria GPS.</p>
  <h2>Datos para el navegador</h2>
  <p>El navegador recibe solo agregados: un cubo de ${fmt(m.counts.od_rows)} celdas (par de estaciones × mes × tipo de día × franja horaria), cubos demográficos por comuna, un calendario día × hora × comuna, la intensidad por tramo y árboles de rutas por estación de origen. Los filtros de tiempo usan meses y seis franjas horarias.</p>
  <h2>Limitaciones</h2>
  <ul>
    <li>Las rutas son plausibles, no observadas; el comportamiento real puede diferir (atajos, parques, preferencias personales).</li>
    <li>La población por barrio es del censo 2010.</li>
    <li>Las diferencias entre grupos de usuarios son descriptivas: no controlan por distancia, propósito ni muestreo.</li>
    <li>Algunos días con actividad muy baja (p. ej., 17/5) no tienen causa verificada.</li>
  </ul>` : `
  <h2>Methodology</h2>
  <p>This platform turns individual trips of the public bike-sharing system (EcoBici) in ${m.year} into an aggregated picture of cycling mobility in the City of Buenos Aires. All processing is reproducible with the scripts in the repository's <code>pipeline/</code> folder.</p>
  <h2>Sources</h2>
  <ul>
    <li><b>Public bicycles</b>: trips ${m.year} (${fmt(q.raw_rows)} records) and yearly user files 2015–${m.year}.</li>
    <li><b>Barrios</b> and <b>Comunas</b>: official boundaries; neighborhood population from the 2010 census (dated, used only as a reference).</li>
    <li><b>Streets</b>: official street network (callejero, with traffic direction) and official <b>Ciclovías</b>.</li>
  </ul>
  <p>${m.attribution}.</p>
  <h2>Cleaning and validation</h2>
  <p>${fmt(q.valid_trips)} valid trips are kept (${pct(q.valid_trips / q.raw_rows, 2)}). Excluded: trips over 4 hours (${fmt(q.flags.too_long)}), unknown or missing stations (${fmt(q.flags.unknown_station + q.flags.missing_dest)}) and inconsistent durations (${fmt(q.flags.duration_mismatch)}). No duplicates were found. Round trips (same origin and destination station, ${pct(s.round_trip_share)}) are valid but have no route or distance.</p>
  <h2>Observed trips and inferred routes</h2>
  <p><b>Origin–destination pairs are observed.</b> <b>Street-level routes are inferred</b>: the system does not publish GPS tracks. For each station pair a plausible route is computed on a directed network built from the official street map (${fmt(n.network_km)} km; ${fmt(n.directed_edges)} directed edges). It respects one-way rules, excludes motorways, penalises pedestrian streets and allows contraflow only where a two-way bike lane exists (${fmt(n.contraflow_edges_added)} edges). The network keeps the main strongly connected component (${pct(n.largest_scc_share_nodes)} of nodes).</p>
  <p>Two assumptions are compared: <b>shortest route</b> and <b>bike-lane-preferring route</b> (primary), which weights each metre by 0.6 on bike lanes and 1.0–1.5 by road hierarchy. The primary route is on average ${pct(r.detour_infra_vs_shortest)} longer and runs ${pct(r.trip_weighted.infra_share_infra)} of its length on bike lanes (vs ${pct(r.trip_weighted.infra_share_shortest)} for the shortest). The two share only ${pct(r.trip_weighted.overlap_infra_vs_shortest)} of their length: <b>street intensity depends on the assumption</b>. ${osmLine}</p>
  <p>Stations are snapped to the nearest network node (median ${fmt(r.snap_m["50%"], 0)} m; maximum ${fmt(r.snap_m.max, 0)} m next to large blocks).</p>
  <h2>Distance, duration and speed</h2>
  <p>Duration is observed. Distance is the length of the primary inferred route. Estimated speed is estimated distance / observed duration; it includes stops and detours, so it is not a riding speed. ${fmt(s.speed_implausible_trips)} trips above ${s.max_speed_kmh} km/h are excluded from distance and speed statistics.</p>
  <h2>Users and privacy</h2>
  <p>Gender is recorded on each trip as provided (categories are not exhaustive). Age is not in the trip data; it comes from the user files for ${pct(q.age_available_share)} of trips, estimated as age at registration plus elapsed years. Missing attributes are not inferred. Demographic data is published only at commune level; cells with fewer than ${m.min_publish} trips are recoded as "suppressed" and any figure based on fewer than ${m.min_cell} trips is not shown. Gender and age filters are not combined. No user identifiers are published. The one exception to aggregate-only publication is the <b>animation</b>: for 9 selected days each trip is published with only origin station, destination station and departure / arrival minute (no user, gender or age). The animated path is the inferred route at constant speed, not a GPS trajectory.</p>
  <h2>Browser data</h2>
  <p>The browser only receives aggregates: a cube of ${fmt(m.counts.od_rows)} cells (station pair × month × day type × time band), commune-level demographic cubes, a day × hour × commune calendar, segment intensity, and route trees per origin station. Time filters use months and six time bands.</p>
  <h2>Limitations</h2>
  <ul>
    <li>Routes are plausible, not observed; actual behaviour may differ (shortcuts, parks, personal preferences).</li>
    <li>Neighborhood population is from the 2010 census.</li>
    <li>Differences between user groups are descriptive: they do not control for distance, purpose or sampling.</li>
    <li>Some days with very low activity (e.g. 17 May) have no verified cause.</li>
  </ul>`;
  document.getElementById("methodBody").innerHTML = html;
}
