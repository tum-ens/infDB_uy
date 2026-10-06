/* InfDB Uruguay – Data Explorer (vanilla JS + MapLibre). All figures are descriptive. */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (id) => document.getElementById(id);
const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf0 = new Intl.NumberFormat(LOCALES[LANG], { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat(LOCALES[LANG], { maximumFractionDigits: 1 });
const fmt = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "–" : nf0.format(n));
const fmt1 = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "–" : nf1.format(n));
const yr = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "–" : String(Math.round(Number(n))));
const mb = (b) => `${nf1.format(b / 1e6)} MB`;
const cssv = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const isDark = () => {
  const th = document.documentElement.dataset.theme;
  return th ? th === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
};

async function api(path, params) {
  const u = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, v);
  const r = await fetch(u);
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}
const geoCache = {};
const geo = (name) => (geoCache[name] ??= fetch(`/api/geo/${name}`).then((r) => (r.ok ? r.json() : null)));

const tip = $("tip");
function showTip(e, html) {
  tip.innerHTML = html; tip.classList.add("show");
  const w = tip.offsetWidth; let x = e.clientX + 14; if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  tip.style.left = Math.max(8, x) + "px"; tip.style.top = e.clientY + 14 + "px";
}
const hideTip = () => tip.classList.remove("show");

function bboxOf(fc) {
  let b = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => (typeof c[0] === "number" ? (b = [Math.min(b[0], c[0]), Math.min(b[1], c[1]), Math.max(b[2], c[0]), Math.max(b[3], c[1])]) : c.forEach(walk));
  fc.features.forEach((f) => f.geometry && walk(f.geometry.coordinates));
  return [[b[0], b[1]], [b[2], b[3]]];
}

// ------------------------------------------------------------------ theme
applyI18n();
$("lang").value = LANG;
$("lang").onchange = (e) => setLang(e.target.value);
const relLabel = (r) => (r ? t(`rel.${r}`) : "");
$("theme").onclick = () => {
  document.documentElement.dataset.theme = isDark() ? "light" : "dark";
  Object.values(maps).forEach(applyBasemap);
  if (cad.ready) cad.recolor();
  if (cen.ready) cen.recolor();
};

// ------------------------------------------------------------------ maps
const maps = {};
// Basemap: OpenStreetMap standard tiles (no API key), drawn in greyscale so data colours
// dominate; in dark mode the greyscale is inverted (brightness min/max swapped).
function basePaint() {
  return isDark()
    ? { "raster-saturation": -1, "raster-brightness-min": 0.92, "raster-brightness-max": 0.08, "raster-contrast": -0.1, "raster-opacity": 0.85 }
    : { "raster-saturation": -1, "raster-brightness-min": 0.08, "raster-brightness-max": 1, "raster-contrast": -0.25, "raster-opacity": 0.7 };
}
function baseStyle() {
  return {
    version: 8,
    sources: {
      osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19,
             attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": cssv("--bg") } },
      { id: "base", type: "raster", source: "osm", paint: basePaint() },
    ],
  };
}
function applyBasemap(m) {
  if (!m.isStyleLoaded()) return;
  m.setPaintProperty("bg", "background-color", cssv("--bg"));
  for (const [k, v] of Object.entries(basePaint())) m.setPaintProperty("base", k, v);
}
async function makeMap(id) {
  const scope = await geo("scope");
  const m = new maplibregl.Map({ container: id, style: baseStyle(), bounds: bboxOf(scope), fitBoundsOptions: { padding: 40 }, attributionControl: { compact: true } });
  m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  await new Promise((res) => m.on("load", res));
  m.addSource("scope", { type: "geojson", data: scope });
  maps[id] = m;
  return m;
}
function addScopeOutline(m) {
  m.addLayer({ id: "scope-line", type: "line", source: "scope", paint: { "line-color": cssv("--ink"), "line-width": 2, "line-dasharray": [3, 2] } });
}

// optional overlay layers shared by map tabs
const OVERLAYS = {
  zonas_censales_2023: { label: "ly.zones", kind: "line", color: "--c7" },
  segmentos_2023: { label: "ly.segments", kind: "line", color: "--c2", width: 2 },
  vias: { label: "ly.vias", kind: "line", color: "--ink-3" },
  manzanas: { label: "ly.manzanas", kind: "line", color: "--ink-3" },
  accesos_puerta: { label: "ly.doors", kind: "circle", color: "--c3" },
  permisos_construccion: { label: "ly.permits", kind: "circle", color: "--c2" },
  lidar_tiles: { label: "ly.lidar", kind: "line", color: "--c4", width: 2 },
};
function overlayControls(m, el, names, before) {
  el.innerHTML = `<details><summary style="cursor:pointer;font-weight:600">${h(t("layers"))}</summary><div class="layers" style="margin-top:4px">` + names.map((n) =>
    `<label><input type="checkbox" data-layer="${n}"> ${h(t(OVERLAYS[n].label))}</label>`).join("") + `</div></details>`;
  el.querySelectorAll("input").forEach((cb) => (cb.onchange = async () => {
    const n = cb.dataset.layer, o = OVERLAYS[n], id = `ov-${n}`;
    if (!m.getSource(id)) {
      const data = await geo(n);
      if (!data) { cb.checked = false; cb.disabled = true; return; }
      m.addSource(id, { type: "geojson", data });
      const paint = o.kind === "line"
        ? { "line-color": cssv(o.color), "line-width": o.width || 1, "line-opacity": 0.9 }
        : { "circle-color": cssv(o.color), "circle-radius": 3, "circle-stroke-color": cssv("--surface"), "circle-stroke-width": 1 };
      m.addLayer({ id, type: o.kind, source: id, paint }, before && m.getLayer(before) ? before : undefined);
      if (o.kind === "circle") {
        m.on("mousemove", id, (e) => { m.getCanvas().style.cursor = "pointer"; showTip(e.originalEvent, overlayTip(n, e.features[0].properties)); });
        m.on("mouseleave", id, () => { m.getCanvas().style.cursor = ""; hideTip(); });
      }
    }
    m.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none");
  }));
}
function overlayTip(n, p) {
  if (n === "accesos_puerta") return `<b>${h(p.nom_calle)} ${h(p.num_puerta)}${p.letra ? h(p.letra) : ""}</b><br>padrón <span class="m">${h(p.padron)}</span>`;
  if (n === "permisos_construccion") return `<b>${h(p.dsc_tipo_obra)}</b> · ${h(p.dsc_destino)}<br>${t("tip.approved")} <span class="m">${h(p.fecha_aprob)}</span> · ${fmt(p.area_edif)} m²<br>padrón <span class="m">${h(p.padron)}</span>`;
  return "";
}

// ------------------------------------------------------------------ charts
function hbar(el, rows, { selected = new Set(), onToggle, valueKey = "area_m2", unit = "m²", limit = 0, labelOf } = {}) {
  if (!rows.length) { el.innerHTML = `<p class="empty">${t("cad.nolines")}</p>`; return; }
  const max = Math.max(...rows.map((r) => r[valueKey] || 0), 1);
  const active = selected.size > 0;
  const shown = limit && !el._all ? rows.slice(0, limit) : rows;
  el.innerHTML = `<div class="hbar ${active ? "dim" : ""}">` + shown.map((r) => {
    const lab = labelOf ? labelOf(r) : r.label || r.code;
    return `<button class="row ${selected.has(String(r.code)) ? "on" : ""}" data-code="${h(r.code)}">
      <span class="lab" title="${h(lab)}">${h(lab)}</span>
      <span class="track"><div class="fill" style="width:${((r[valueKey] || 0) / max) * 100}%"></div></span>
      <span class="val">${fmt(r[valueKey])}</span></button>`;
  }).join("") + `</div>` + (limit && rows.length > limit ? `<button class="more">${el._all ? t("cad.showfewer") : t("cad.showall", { n: rows.length })}</button>` : "");
  el.querySelectorAll(".row").forEach((b) => {
    const r = rows.find((x) => String(x.code) === b.dataset.code);
    b.onclick = () => onToggle && onToggle(b.dataset.code);
    b.onmousemove = (e) => showTip(e, `<b>${h(labelOf ? labelOf(r) : r.label || r.code)}</b><br>${t("common.code")} <span class="m">${h(r.code)}</span><br><span class="m">${fmt(r.area_m2)}</span> m² · <span class="m">${fmt(r.lines)}</span> ${t("common.lines")}`);
    b.onmouseleave = hideTip;
  });
  const more = el.querySelector(".more");
  if (more) more.onclick = () => { el._all = !el._all; hbar(el, rows, { selected, onToggle, valueKey, unit, limit, labelOf }); };
}

function columns(el, bins, { isOn, onClick, tipOf, xlabels }) {
  const max = Math.max(...bins.map((b) => b.v), 1);
  const anyOn = bins.some(isOn);
  el.innerHTML = `<div class="cols ${anyOn ? "dim" : ""}">` + bins.map((b, i) =>
    `<button class="col ${isOn(b) ? "on" : ""}" data-i="${i}" aria-label="${h(b.label)}"><div class="fill" style="height:${(b.v / max) * 100}%;min-height:${b.v ? 1 : 0}px"></div></button>`
  ).join("") + `</div><div class="xl">${xlabels.map((x) => `<span>${h(x)}</span>`).join("")}</div>`;
  el.querySelectorAll(".col").forEach((c) => {
    const b = bins[+c.dataset.i];
    c.onclick = (e) => onClick(b, e);
    c.onmousemove = (e) => showTip(e, tipOf(b));
    c.onmouseleave = hideTip;
  });
}

// ------------------------------------------------------------------ tabs
const tabInit = {};
document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => openTab(b.dataset.tab)));
function openTab(name) {
  document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  document.querySelectorAll("section.tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${name}`));
  if (!tabInit[name]) tabInit[name] = ({ overview: renderOverview, cadastre: () => cad.init(), census: () => cen.init(), lidar: initLidar, data: initData }[name])();
  Object.values(maps).forEach((m) => m.resize());
  try { history.replaceState(null, "", `#${name}`); } catch (_) { /* ignore */ }
}

// ------------------------------------------------------------------ overview
let META;
async function renderOverview() {
  const el = $("overview");
  const [summary, anda] = await Promise.all([api("/api/cadastre/summary"), api("/api/anda")]);
  const qa = META.qa || {}, d = qa.dnc || {}, cs = qa.cross_source || {}, z = (qa.census || {}).im_zonas_2023 || {}, li = qa.lidar || {};
  const k = summary.kpis;
  const issues = (META.dnc?.tables?.["Líneas de Construccion"]?.conversion_or_label_issues) || {};
  const loc = META.dnc?.localidad_coverage || {};
  const docClasses = new Set(["1", "2", "3", "4", "5", "6", "9"]);
  const undocumented = Object.keys(li.classification_counts || {}).filter((c) => !docClasses.has(c));
  const flags = [
    [t("ov.f.year0.b", { n: fmt(k.lines_year_0) }), t("ov.f.year0")],
    [t("ov.f.area0.b", { n: fmt(k.lines_area_0) }), t("ov.f.area0")],
    [t("ov.f.aconstruir.b", { n: fmt(d.tipo_obra_counts?.["40"]) }), t("ov.f.aconstruir")],
    ...(d.lines_without_unit_of_same_regimen ? [[t("ov.f.regime.b", { n: fmt(d.lines_without_unit_of_same_regimen.lines) }),
      t("ov.f.regime", { a: fmt(d.lines_without_unit_of_same_regimen.area_m2), p: fmt(d.lines_without_unit_of_same_regimen.parcels) })]] : []),
    ...Object.entries(issues).filter(([key]) => key.endsWith("_without_label")).map(([key, v]) =>
      [key.replace("_codes_without_label", ""), t("ov.f.nolabel", { list: Object.entries(v).map(([c, n]) => `${c} (${fmt(n)})`).join(", ") })]),
    [t("ov.f.nopoly.b", { n: fmt(loc.csv_parcels_without_polygon) }), t("ov.f.nopoly", { m: fmt(loc.polygons_without_csv_record) })],
    [t("ov.f.zones.b", { n: fmt(z.by_scope_relation?.crosses_boundary) }), t("ov.f.zones", { p: fmt(z.POB_TOT_23_crossing) })],
    [t("ov.f.crs.b"), t("ov.f.crs", { a: h((li.crs || []).join(", ")), b: h(META.scope.crs) })],
    [t("ov.f.classes.b"), t("ov.f.classes", { list: undocumented.join(", ") || t("common.none") })],
  ];
  const sources = META.sources.map((s) => `<tr><td class="mono">${h(s.source)}</td><td>${h(s.hosts.join(", "))}</td><td class="n">${fmt(s.files)}</td><td class="n">${mb(s.bytes)}</td><td class="mono">${h((s.last_retrieved || "").slice(0, 16).replace("T", " "))}</td></tr>`).join("");
  const andaRows = anda.map((a) => `<tr><td class="mono">${h(a.idno)}</td><td>${h(a.metadata?.data_access_type || "–")}</td><td class="n">${fmt(a.metadata?.variables)}</td>
      <td>${a.files_present.length ? h(a.files_present.join(", ")) : `<span class="pill warn">${t("ov.anda.nofiles")}</span>`}</td><td>${a.scope_tables.length ? h(a.scope_tables.join(", ")) : "–"}</td></tr>`).join("");
  el.innerHTML = `
    <div>
      <h2 style="font-size:20px;margin-bottom:6px">${h(META.scope.values.join(", "))}, Montevideo</h2>
      <p class="lead">${t("ov.lead")}</p>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="l">${t("ov.k.parcels")}</div><div class="v">${fmt(META.build?.layers?.parcelas)}</div><div class="u">${t("ov.k.parcels.u")}</div></div>
      <div class="kpi"><div class="l">${t("ov.k.units")}</div><div class="v">${fmt(Object.values(d.units_by_regimen || {}).reduce((a, b) => a + b, 0))}</div><div class="u">${h(Object.entries(d.units_by_regimen || {}).map(([r, n]) => `${r} ${fmt(n)}`).join(" · "))}</div></div>
      <div class="kpi"><div class="l">${t("ov.k.lines")}</div><div class="v">${fmt(k.lines)}</div><div class="u">${t("ov.k.lines.u", { a: fmt(k.area_m2) })}</div></div>
      <div class="kpi"><div class="l">${t("ov.k.dwelling")}</div><div class="v">${fmt(k.area_vivienda_m2)}</div><div class="u">${t("ov.k.dwelling.u")}</div></div>
      <div class="kpi"><div class="l">${t("ov.k.pop")}</div><div class="v">${fmt(z.POB_TOT_23_within)}</div><div class="u">${t("ov.k.pop.u", { n: fmt(z.POB_TOT_23_crossing) })}</div></div>
      <div class="kpi"><div class="l">${t("ov.k.lidar")}</div><div class="v">${fmt1((li.points || 0) / 1e6)} M</div><div class="u">${t("ov.k.lidar.u", { n: fmt(li.tiles), s: mb(li.bytes || 0) })}</div></div>
    </div>
    <div class="grid2">
      <div class="card"><div class="card-h"><h2>${t("ov.qa.title")}</h2><span>${t("ov.qa.sub")}</span></div><div class="flags">${flags.map(([b, t]) => `<div class="flag"><b>${h(b)}</b><span>${t}</span></div>`).join("")}</div></div>
      <div class="card"><div class="card-h"><h2>${t("ov.where")}</h2></div>
        <div class="flags" style="gap:10px">
          <p><a href="#cadastre" data-go="cadastre">${t("tab.cadastre")}</a> – ${t("ov.where.cad")}</p>
          <p><a href="#census" data-go="census">${t("tab.census")}</a> – ${t("ov.where.cen")}</p>
          <p><a href="#lidar" data-go="lidar">${t("tab.lidar")}</a> – ${t("ov.where.lid")}</p>
          <p><a href="#data" data-go="data">${t("tab.data")}</a> – ${t("ov.where.data")}</p>
          <p class="note">${t("ov.where.api")} <a href="/api/docs" target="_blank" rel="noopener">/api/docs</a>.</p>
        </div></div>
    </div>
    <div class="card"><div class="card-h"><h2>${t("ov.prov")}</h2><span>${t("ov.prov.sub")}</span></div>
      <div class="tw"><table><thead><tr><th>${t("ov.prov.source")}</th><th>${t("ov.prov.host")}</th><th class="n">${t("ov.prov.files")}</th><th class="n">${t("ov.prov.size")}</th><th>${t("ov.prov.last")}</th></tr></thead><tbody>${sources}</tbody></table></div></div>
    <div class="card"><div class="card-h"><h2>${t("ov.anda")}</h2><span>${t("ov.anda.sub")}</span></div>
      <div class="tw"><table><thead><tr><th>${t("ov.anda.study")}</th><th>${t("ov.anda.access")}</th><th class="n">${t("ov.anda.vars")}</th><th>${t("ov.anda.files")}</th><th>${t("ov.anda.scope")}</th></tr></thead><tbody>${andaRows}</tbody></table></div></div>`;
  el.querySelectorAll("[data-go]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); openTab(a.dataset.go); }));
}

// ------------------------------------------------------------------ cadastre
const COLOR_BINS = {
  year_median_nonzero: { t: [1930, 1950, 1970, 1990, 2010], labels: [t("cad.l.before", { y: 1930 }), "1930–1949", "1950–1969", "1970–1989", "1990–2009", t("cad.l.after", { y: 2010 })] },
  nivel_max: { t: [1, 2, 3, 5, 10], labels: [t("cad.l.ground"), "1", "2", "3–4", "5–9", t("cad.l.ormore", { n: 10 })] },
  lines_area_m2: { t: [100, 250, 500, 1000, 2500], labels: [`< ${fmt(100)}`, `${fmt(100)}–${fmt(249)}`, `${fmt(250)}–${fmt(499)}`, `${fmt(500)}–${fmt(999)}`, `${fmt(1000)}–${fmt(2499)}`, `≥ ${fmt(2500)}`] },
  n_units: { t: [2, 3, 5, 10, 50], labels: ["1", "2", "3–4", "5–9", "10–49", "≥ 50"] },
  valor_total_sum: { t: [2e6, 4e6, 8e6, 16e6, 50e6], labels: ["< 2 M", "2–4 M", "4–8 M", "8–16 M", "16–50 M", "≥ 50 M"] },
};
const SEQ = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"];
const CAT = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6", "--c7", "--c8"];

const cad = {
  ready: false, map: null, parcels: null, matched: null, selectedKey: null,
  f: { destino: new Set(), categoria: new Set(), estado: new Set(), cubierta: new Set(), tipo_obra: new Set(), regimen: new Set(), unit_regimen_exists: new Set(), yearFrom: null, yearTo: null, year0: true, nivelFrom: null, nivelTo: null },

  async init() {
    this.map = await makeMap("cad-map");
    this.parcels = await geo("parcelas");
    const m = this.map;
    m.addSource("parcels", { type: "geojson", data: this.parcels, promoteId: "parcel_key" });
    m.addLayer({ id: "parcels-fill", type: "fill", source: "parcels", paint: { "fill-color": cssv("--mute"), "fill-opacity": ["case", ["boolean", ["feature-state", "out"], false], 0.12, 0.85] } });
    m.addLayer({ id: "parcels-line", type: "line", source: "parcels", paint: { "line-color": cssv("--surface"), "line-width": 0.4 } });
    m.addLayer({ id: "parcels-sel", type: "line", source: "parcels", paint: { "line-color": cssv("--ink"), "line-width": ["case", ["boolean", ["feature-state", "sel"], false], 2.5, 0] } });
    // 3D illustration (not data): extrusion of parcel outlines, see build.py / config dashboard.visual_storey_height_m
    m.addLayer({ id: "parcels-3d", type: "fill-extrusion", source: "parcels", layout: { visibility: "none" }, paint: {
      "fill-extrusion-color": cssv("--mute"),
      "fill-extrusion-height": ["case", ["boolean", ["feature-state", "out"], false], 0, ["coalesce", ["to-number", ["get", "vis_height_m"]], 0]],
      "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.9 } });
    addScopeOutline(m);
    $("cad-3d-text").textContent = t("cad.3d.text", { h: fmt1(META.build?.visual_storey_height_m ?? 3) });
    $("cad-3d").onchange = (e) => this.set3d(e.target.checked);
    overlayControls(m, $("cad-layers"), ["zonas_censales_2023", "segmentos_2023", "vias", "manzanas", "accesos_puerta", "permisos_construccion", "lidar_tiles"], "scope-line");
    m.on("mousemove", "parcels-fill", (e) => {
      m.getCanvas().style.cursor = "pointer";
      const p = e.features[0].properties;
      showTip(e.originalEvent, `<b>${h(p.address_lowest_door || t("cad.tip.nodoor"))}</b><br><span class="m">${h(p.parcel_key)}</span> · ${h(p.regimen_units || p.REGIMEN || "")}<br>${fmt(p.n_units)} ${t("cad.tip.units")} · ${fmt(p.lines_area_m2)} m² · ${t("cad.tip.median")} ${yr(p.year_median_nonzero)}`);
    });
    m.on("mouseleave", "parcels-fill", () => { m.getCanvas().style.cursor = ""; hideTip(); });
    m.on("click", "parcels-fill", (e) => this.openParcel(e.features[0].properties.parcel_key));
    $("cad-color").onchange = () => this.recolor();
    $("cad-year0").onchange = (e) => { this.f.year0 = e.target.checked; this.refresh(); };
    this.ready = true;
    this.recolor();
    await this.refresh();
  },

  params() {
    const j = (s) => [...s].join(",");
    const f = this.f;
    return { destino: j(f.destino), categoria: j(f.categoria), estado: j(f.estado), cubierta: j(f.cubierta), tipo_obra: j(f.tipo_obra), regimen: j(f.regimen), unit_regimen_exists: j(f.unit_regimen_exists),
      year_from: f.yearFrom, year_to: f.yearTo, include_year0: f.year0, nivel_from: f.nivelFrom, nivel_to: f.nivelTo };
  },

  async refresh() {
    const s = await api("/api/cadastre/summary", this.params());
    const k = s.kpis;
    $("cad-kpis").innerHTML = [[t("cad.k.parcels"), k.parcels], [t("cad.k.lines"), k.lines], [t("cad.k.built"), k.area_m2], [t("cad.k.dwelling"), k.area_vivienda_m2]].map(([l, v]) =>
      `<div class="kpi"><div class="l">${l}</div><div class="v">${fmt(v)}</div></div>`).join("");
    const toggle = (facet) => (code) => { const set = this.f[facet]; set.has(code) ? set.delete(code) : set.add(code); this.refresh(); };
    const lab = (r) => (r.label ? r.label : t("cad.nolabel", { c: r.code }));
    const yesno = (r) => (r.code === "true" ? t("cad.yes") : r.code === "false" ? t("cad.no") : r.code);
    for (const facet of ["destino", "categoria", "estado", "cubierta", "tipo_obra", "regimen", "unit_regimen_exists"]) {
      hbar($(`cad-${facet}`), s.by[facet], { selected: this.f[facet], onToggle: toggle(facet), limit: facet === "destino" ? 10 : 0,
        labelOf: facet === "unit_regimen_exists" ? yesno : lab });
    }
    this.decadeChart(s.by.decade);
    this.nivelChart(s.by.nivel);
    this.chips();
    this.matched = new Set(s.parcels);
    const filtered = this.anyFilter();
    for (const f of this.parcels.features) {
      this.map.setFeatureState({ source: "parcels", id: f.properties.parcel_key }, { out: filtered && !this.matched.has(f.properties.parcel_key) });
    }
  },

  anyFilter() {
    const f = this.f;
    return ["destino", "categoria", "estado", "cubierta", "tipo_obra", "regimen", "unit_regimen_exists"].some((k) => f[k].size) || f.yearFrom !== null || f.nivelFrom !== null || !f.year0;
  },

  decadeChart(rows) {
    const plaus = rows.filter((r) => r.decade >= 1800);
    const odd = rows.filter((r) => r.decade < 1800);
    const lo = Math.min(...plaus.map((r) => r.decade)), hi = Math.max(...plaus.map((r) => r.decade));
    const bins = [];
    for (let d = lo; d <= hi; d += 10) { const r = plaus.find((x) => x.decade === d); bins.push({ d, v: r ? r.area_m2 : 0, lines: r ? r.lines : 0, label: `${d}s` }); }
    const f = this.f;
    const el = $("cad-decade");
    columns(el, bins, {
      isOn: (b) => f.yearFrom !== null && b.d >= f.yearFrom && b.d + 9 <= f.yearTo,
      onClick: (b, e) => {
        if (e.shiftKey && f.yearFrom !== null) { f.yearFrom = Math.min(f.yearFrom, b.d); f.yearTo = Math.max(f.yearTo, b.d + 9); }
        else if (f.yearFrom === b.d && f.yearTo === b.d + 9) { f.yearFrom = f.yearTo = null; }
        else { f.yearFrom = b.d; f.yearTo = b.d + 9; }
        this.refresh();
      },
      tipOf: (b) => `<b>${b.d}–${b.d + 9}</b><br><span class="m">${fmt(b.v)}</span> m² · <span class="m">${fmt(b.lines)}</span> ${t("common.lines")}`,
      xlabels: [String(lo), String(Math.round((lo + hi) / 20) * 10), String(hi)],
    });
    const oddLines = odd.reduce((a, r) => a + r.lines, 0);
    el.insertAdjacentHTML("beforeend", `<p class="note">${t("cad.decade.note")} ${oddLines ? t("cad.decade.odd", { n: fmt(oddLines) }) : ""}</p>`);
  },

  nivelChart(rows) {
    const f = this.f;
    const bins = rows.map((r) => ({ n: r.nivel, v: r.area_m2, lines: r.lines, label: String(r.nivel) }));
    columns($("cad-nivel"), bins, {
      isOn: (b) => f.nivelFrom !== null && b.n >= f.nivelFrom && b.n <= f.nivelTo,
      onClick: (b, e) => {
        if (e.shiftKey && f.nivelFrom !== null) { f.nivelFrom = Math.min(f.nivelFrom, b.n); f.nivelTo = Math.max(f.nivelTo, b.n); }
        else if (f.nivelFrom === b.n && f.nivelTo === b.n) { f.nivelFrom = f.nivelTo = null; }
        else { f.nivelFrom = f.nivelTo = b.n; }
        this.refresh();
      },
      tipOf: (b) => `<b>nivel ${h(b.n)}</b><br><span class="m">${fmt(b.v)}</span> m² · <span class="m">${fmt(b.lines)}</span> ${t("common.lines")}`,
      xlabels: bins.length ? [String(bins[0].n), String(bins[bins.length - 1].n)] : [],
    });
  },

  chips() {
    const f = this.f, out = [];
    for (const k of ["destino", "categoria", "estado", "cubierta", "tipo_obra", "regimen", "unit_regimen_exists"]) for (const v of f[k]) out.push([`${k}: ${v}`, () => { f[k].delete(v); }]);
    if (f.yearFrom !== null) out.push([t("cad.chip.year", { a: f.yearFrom, b: f.yearTo }), () => { f.yearFrom = f.yearTo = null; }]);
    if (f.nivelFrom !== null) out.push([t("cad.chip.nivel", { a: f.nivelFrom, b: f.nivelTo }), () => { f.nivelFrom = f.nivelTo = null; }]);
    const el = $("cad-chips");
    el.innerHTML = out.map(([t], i) => `<button class="chip" data-i="${i}">${h(t)} ✕</button>`).join("") + (out.length ? `<button class="chip" data-all>${t("cad.clear")}</button>` : `<span class="note">${t("cad.nofilters")}</span>`);
    el.querySelectorAll("[data-i]").forEach((b) => (b.onclick = () => { out[+b.dataset.i][1](); this.refresh(); }));
    const all = el.querySelector("[data-all]");
    if (all) all.onclick = () => { for (const k of ["destino", "categoria", "estado", "cubierta", "tipo_obra", "regimen", "unit_regimen_exists"]) f[k].clear(); f.yearFrom = f.yearTo = f.nivelFrom = f.nivelTo = null; this.refresh(); };
  },

  set3d(on) {
    const m = this.map;
    m.setLayoutProperty("parcels-3d", "visibility", on ? "visible" : "none");
    for (const id of ["parcels-fill", "parcels-line"]) m.setLayoutProperty(id, "visibility", on ? "none" : "visible");
    $("cad-3d-banner").hidden = !on;
    m.easeTo({ pitch: on ? 55 : 0, bearing: on ? -20 : 0, duration: 800 });
  },

  recolor() {
    const m = this.map, key = $("cad-color").value, none = cssv("--surface-2");
    let expr, legend;
    if (COLOR_BINS[key]) {
      const { t: thr, labels } = COLOR_BINS[key];
      const cols = SEQ.map(cssv);
      const step = ["step", ["to-number", ["get", key]], cols[0]];
      thr.forEach((v, i) => step.push(v, cols[i + 1]));
      expr = ["case", ["==", ["get", key], null], none, step];
      legend = labels.map((l, i) => [cols[i], l]);
    } else if (key === "n_lines_year_0" || key === "n_lines_regimen_without_unit") {
      expr = ["case", ["==", ["get", key], null], none, [">", ["to-number", ["get", key]], 0], cssv("--warn"), cssv("--mute")];
      legend = [[cssv("--warn"), key === "n_lines_year_0" ? t("cad.l.year0") : t("cad.l.regnounit")], [cssv("--mute"), t("common.none")]];
    } else {
      const counts = {};
      this.parcels.features.forEach((f) => { const v = f.properties[key]; if (v) counts[v] = (counts[v] || 0) + 1; });
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([v]) => v);
      const match = ["match", ["get", key]];
      top.forEach((v, i) => match.push(v, cssv(CAT[i])));
      match.push(cssv("--mute"));
      expr = ["case", ["==", ["get", key], null], none, match];
      legend = top.map((v, i) => [cssv(CAT[i]), `${v} (${fmt(counts[v])})`]);
      if (Object.keys(counts).length > 7) legend.push([cssv("--mute"), t("common.other")]);
    }
    legend.push([none, t("cad.l.nolines")]);
    m.setPaintProperty("parcels-fill", "fill-color", expr);
    m.setPaintProperty("parcels-3d", "fill-extrusion-color", expr);
    m.setPaintProperty("parcels-line", "line-color", cssv("--surface"));
    m.setPaintProperty("parcels-sel", "line-color", cssv("--ink"));
    if (m.getLayer("scope-line")) m.setPaintProperty("scope-line", "line-color", cssv("--ink"));
    $("cad-legend").innerHTML = legend.map(([c, l]) => `<div class="li"><span class="sw" style="background:${c}"></span>${h(l)}</div>`).join("");
  },

  async openParcel(key) {
    const m = this.map;
    if (this.selectedKey) m.setFeatureState({ source: "parcels", id: this.selectedKey }, { sel: false });
    this.selectedKey = key;
    m.setFeatureState({ source: "parcels", id: key }, { sel: true });
    const dr = $("cad-drawer");
    dr.hidden = false; dr.innerHTML = `<p class="loading">${t("dr.loading", { k: h(key) })}</p>`;
    m.resize();
    let p;
    try { p = await api(`/api/cadastre/parcel/${encodeURIComponent(key)}`); }
    catch (e) { dr.innerHTML = `<button class="btn" id="dr-close">${t("common.close")}</button><p class="empty">${t("dr.norecord", { k: h(key), e: h(e.message) })}</p>`; $("dr-close").onclick = () => this.closeParcel(); return; }
    const feat = this.parcels.features.find((f) => f.properties.parcel_key === key)?.properties || {};
    const units = p.units, lines = p.lines;
    const sum = (arr, k) => arr.reduce((a, r) => a + (Number(r[k]) || 0), 0);
    const yr = (r) => (r.anio_construccion === 0 ? `<span class="pill warn">0</span>` : h(r.anio_construccion));
    const labelled = (r, c) => (r[`${c}_label`] ? h(r[`${c}_label`]) : `<i>${t("common.code")} ${h(r[c])}</i>`);
    const isPH = units.some((u) => u.regimen !== "CO");
    const lineRows = lines.map((r) => `<tr>${isPH ? `<td class="mono">${h([r.block, r.ep_ss, r.unidad].filter((x) => x !== "" && x !== null).join(" / "))}</td>` : ""}
      <td class="n">${h(r.nivel)}</td><td>${labelled(r, "destino")}</td><td>${labelled(r, "categoria")}</td><td>${labelled(r, "estado")}</td>
      <td>${labelled(r, "cubierta")}</td><td>${labelled(r, "tipo_obra")}</td><td class="n">${fmt(r.area_m2)}</td><td class="n">${yr(r)}</td><td class="n">${r.anio_remanente ? h(r.anio_remanente) : ""}</td></tr>`).join("");
    const unitRows = units.map((u) => `<tr><td class="mono">${h(u.regimen)}</td><td class="mono">${h([u.block, u.ep_ss, u.unidad].filter((x) => x !== "" && x !== null).join(" / "))}</td>
      <td class="n">${fmt(u.area_edificada_m2)}</td><td class="n">${fmt(u.valor_total)}</td><td class="mono">${h(u.fecha_djcu || "")}</td></tr>`).join("");
    const hist = [[t("dr.hist.release"), sum(units, "valor_total")], ...[1, 2, 3, 4].map((i) => [t("dr.hist.yr", { n: i }), sum(p.values, `valor_cat_y${i}`)])];
    const doors = [...new Set(p.doors.map((d) => `${(d.nom_calle || "").trim()} ${d.num_puerta ?? ""}${d.letra || ""}`))];
    dr.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
        <div><h2 style="font-size:15px">${h(feat.address_lowest_door || t("dr.nodoor"))}</h2>
          <span class="mono note">${h(key)}</span> <span class="pill">${h(feat.regimen_units || feat.REGIMEN || "")}</span> <span class="pill">${h(relLabel(feat.scope_relation))}</span></div>
        <button class="btn" id="dr-close">${t("common.close")}</button></div>
      <dl class="facts">
        <dt>${t("dr.units")}</dt><dd>${fmt(units.length)}</dd>
        <dt>${t("dr.parcelarea")}</dt><dd>${fmt(feat.area_predio_max_m2)} m²</dd>
        <dt>${t("dr.polyarea")}</dt><dd>${fmt(feat.AREA)} m²</dd>
        <dt>${t("dr.builtunits")}</dt><dd>${fmt(sum(units, "area_edificada_m2"))} m²</dd>
        <dt>${t("dr.builtlines")}</dt><dd>${fmt(sum(lines, "area_m2"))} m²</dd>
        <dt>${t("dr.value")}</dt><dd>${fmt(sum(units, "valor_total"))} UYU</dd>
        <dt>${t("dr.levels")}</dt><dd>${h(feat.nivel_min ?? "–")} … ${h(feat.nivel_max ?? "–")}</dd>
      </dl>
      <div><h3>${t("dr.lines", { n: fmt(lines.length) })}</h3>
        <div class="tw" style="max-height:340px"><table><thead><tr>${isPH ? `<th>${t("dr.th.unit")}</th>` : ""}<th class="n">${t("dr.th.nivel")}</th><th>${t("dr.th.use")}</th><th>${t("dr.th.cat")}</th><th>${t("dr.th.state")}</th><th>${t("dr.th.roof")}</th><th>${t("dr.th.works")}</th><th class="n">m²</th><th class="n">${t("dr.th.year")}</th><th class="n">${t("dr.th.orig")}</th></tr></thead><tbody>${lineRows || `<tr><td colspan="10" class="empty">${t("dr.nolines")}</td></tr>`}</tbody></table></div>
        <p class="note">${t("dr.orig.note")}</p></div>
      <div><h3>${t("dr.hist")}</h3>
        <div class="tw"><table><tbody>${hist.map(([l, v]) => `<tr><td>${l}</td><td class="n">${fmt(v)}</td></tr>`).join("")}</tbody></table></div>
        <p class="note">${t("dr.hist.note")}</p></div>
      ${units.length > 1 || isPH ? `<div><h3>${t("dr.unitstable", { n: fmt(units.length) })}</h3><div class="tw" style="max-height:240px"><table><thead><tr><th>${t("dr.th.regime")}</th><th>${t("dr.th.unit")}</th><th class="n">${t("dr.th.builtm2")}</th><th class="n">${t("dr.th.valueuyu")}</th><th>${t("dr.th.djcu")}</th></tr></thead><tbody>${unitRows}</tbody></table></div></div>` : ""}
      <div><h3>${t("dr.doors")}</h3><p>${doors.length ? doors.map(h).join("<br>") : `<span class="note">${t("common.none")}</span>`}</p></div>
      <div><h3>${t("dr.permits", { n: fmt(p.permits.length) })}</h3>${p.permits.length ? `<div class="tw"><table><thead><tr><th>${t("dr.th.approved")}</th><th>${t("dr.th.works")}</th><th>${t("dr.th.use")}</th><th>${t("dr.th.cat")}</th><th class="n">m²</th><th>${t("dr.th.file")}</th></tr></thead><tbody>${p.permits.map((x) => `<tr><td class="mono">${h(x.fecha_aprob)}</td><td>${h(x.dsc_tipo_obra)}</td><td>${h(x.dsc_destino)}</td><td>${h(x.dsc_categoria)}</td><td class="n">${fmt(x.area_edif)}</td><td class="mono">${h(x.expediente)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="note">${t("common.none")}</p>`}</div>
      ${p.mutations.length ? `<div><h3>${t("dr.mut")}</h3><div class="tw"><table><thead><tr><th>${t("dr.th.origin")}</th><th>${t("dr.th.date")}</th><th>${t("dr.th.originvalid")}</th></tr></thead><tbody>${p.mutations.map((x) => `<tr><td class="mono">${h(x.padron_origen)}</td><td class="mono">${h(x.fecha_vigencia)}</td><td>${h(x.vigencia_origen)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`;
    $("dr-close").onclick = () => this.closeParcel();
  },

  closeParcel() {
    if (this.selectedKey) this.map.setFeatureState({ source: "parcels", id: this.selectedKey }, { sel: false });
    this.selectedKey = null;
    $("cad-drawer").hidden = true;
    this.map.resize();
  },
};

// ------------------------------------------------------------------ census
const cen = {
  ready: false, map: null, zones: null, sort: { k: "POB_TOT_23", dir: -1 },
  async init() {
    this.map = await makeMap("cen-map");
    this.zones = await geo("zonas_censales_2023");
    this.zones.features.forEach((f, i) => {
      const p = f.properties; p._id = i;
      p.pop_ha = p.AREA_HA ? p.POB_TOT_23 / p.AREA_HA : null;
      p.viv_ha = p.AREA_HA ? p.VIV_TOT_23 / p.AREA_HA : null;
    });
    const m = this.map;
    m.addSource("zones", { type: "geojson", data: this.zones, promoteId: "_id" });
    m.addLayer({ id: "zones-fill", type: "fill", source: "zones", paint: { "fill-opacity": ["case", ["boolean", ["feature-state", "hl"], false], 1, 0.8] } });
    m.addLayer({ id: "zones-line", type: "line", source: "zones", paint: { "line-color": cssv("--surface"), "line-width": ["case", ["boolean", ["feature-state", "hl"], false], 3, 0.6] } });
    addScopeOutline(m);
    overlayControls(m, $("cen-layers"), ["segmentos_2023", "vias", "manzanas"], "scope-line");
    m.on("mousemove", "zones-fill", (e) => {
      m.getCanvas().style.cursor = "pointer";
      const p = e.features[0].properties;
      showTip(e.originalEvent, `<b>${t("cen.tip.zone")} <span class="m">${h(p.CODCOMP)}</span></b><br>${t("cen.tip.pop")} <span class="m">${fmt(p.POB_TOT_23)}</span> · ${t("cen.tip.viv")} <span class="m">${fmt(p.VIV_TOT_23)}</span><br>${fmt1(p.AREA_HA)} ha · ${h(relLabel(p.scope_relation))} (${t("cen.tip.inside", { p: fmt(p.scope_overlap_share * 100) })})`);
    });
    m.on("mouseleave", "zones-fill", () => { m.getCanvas().style.cursor = ""; hideTip(); });
    $("cen-metric").onchange = () => this.recolor();
    this.ready = true;
    this.recolor();
    await this.renderPanel();
  },

  recolor() {
    const key = $("cen-metric").value, cols = SEQ.map(cssv);
    const vals = this.zones.features.map((f) => f.properties[key]).filter((v) => v !== null && v !== undefined && !Number.isNaN(v)).sort((a, b) => a - b);
    const q = [1, 2, 3, 4, 5].map((i) => vals[Math.min(vals.length - 1, Math.floor((vals.length * i) / 6))]);
    const thr = [...new Set(q)];
    const step = ["step", ["to-number", ["get", key]], cols[0]];
    thr.forEach((v, i) => step.push(v, cols[i + 1]));
    this.map.setPaintProperty("zones-fill", "fill-color", ["case", ["==", ["get", key], null], cssv("--surface-2"), step]);
    this.map.setPaintProperty("zones-line", "line-color", cssv("--surface"));
    const f = (v) => (key === "scope_overlap_share" ? `${fmt(v * 100)} %` : v < 10 ? fmt1(v) : fmt(v));
    const edges = [vals[0], ...thr, vals[vals.length - 1]];
    $("cen-legend").innerHTML = edges.slice(0, -1).map((lo, i) => `<div class="li"><span class="sw" style="background:${cols[i]}"></span>${f(lo)} – ${f(edges[i + 1])}</div>`).join("") +
      `<p class="note" style="margin-top:4px">${t("cen.sextiles", { n: fmt(vals.length) })}</p>`;
  },

  async renderPanel() {
    const zs = this.zones.features.map((f) => f.properties);
    const tot = (rel, k) => zs.filter((p) => p.scope_relation === rel).reduce((a, p) => a + (p[k] || 0), 0);
    const anda = await api("/api/anda");
    const el = $("cen-panel");
    el.innerHTML = `
      <div><h3>${t("cen.title")}</h3>
        <div class="kpis small">
          <div class="kpi"><div class="l">${t("cen.k.within")}</div><div class="v">${fmt(zs.filter((p) => p.scope_relation === "within").length)}</div></div>
          <div class="kpi"><div class="l">${t("cen.k.crossing")}</div><div class="v">${fmt(zs.filter((p) => p.scope_relation !== "within").length)}</div></div>
          <div class="kpi"><div class="l">${t("cen.k.popwithin")}</div><div class="v">${fmt(tot("within", "POB_TOT_23"))}</div></div>
          <div class="kpi"><div class="l">${t("cen.k.incrossing")}</div><div class="v">${fmt(tot("crosses_boundary", "POB_TOT_23"))}</div></div>
          <div class="kpi"><div class="l">${t("cen.k.vivwithin")}</div><div class="v">${fmt(tot("within", "VIV_TOT_23"))}</div></div>
          <div class="kpi"><div class="l">${t("cen.k.incrossing")}</div><div class="v">${fmt(tot("crosses_boundary", "VIV_TOT_23"))}</div></div>
        </div>
        <p class="note" style="margin-top:6px">${t("cen.note")}</p></div>
      <details class="card fold" open><summary class="card-h"><h2>${t("cen.zones")}</h2><span>${fmt(zs.length)}</span></summary>
        <div class="tw" style="max-height:280px;margin-top:6px"><table id="cen-table"></table></div></details>
      <div id="anda"></div>`;
    this.table();
    this.renderAnda(anda);
  },

  table() {
    const cols = [["CODCOMP", t("cen.th.zone")], ["POB_TOT_23", t("cen.th.pop")], ["VIV_TOT_23", t("cen.th.viv")], ["AREA_HA", "ha"], ["scope_overlap_share", t("cen.th.inside")]];
    const s = this.sort;
    const rows = this.zones.features.map((f) => f.properties).sort((a, b) => ((a[s.k] > b[s.k]) - (a[s.k] < b[s.k])) * s.dir);
    const tbl = $("cen-table");
    tbl.innerHTML = `<thead><tr>${cols.map(([k, l]) => `<th class="${k === "CODCOMP" ? "" : "n"}" data-k="${k}" style="cursor:pointer">${l}${s.k === k ? (s.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((p) => `<tr class="click" data-id="${p._id}"><td class="mono">${h(p.CODCOMP)}</td><td class="n">${fmt(p.POB_TOT_23)}</td><td class="n">${fmt(p.VIV_TOT_23)}</td><td class="n">${fmt1(p.AREA_HA)}</td><td class="n">${fmt(p.scope_overlap_share * 100)} %</td></tr>`).join("")}</tbody>`;
    tbl.querySelectorAll("th").forEach((th) => (th.onclick = () => { this.sort = { k: th.dataset.k, dir: this.sort.k === th.dataset.k ? -this.sort.dir : -1 }; this.table(); }));
    tbl.querySelectorAll("tbody tr").forEach((tr) => {
      const id = +tr.dataset.id;
      tr.onmouseenter = () => this.map.setFeatureState({ source: "zones", id }, { hl: true });
      tr.onmouseleave = () => this.map.setFeatureState({ source: "zones", id }, { hl: false });
      tr.onclick = () => { const f = this.zones.features[id]; this.map.fitBounds(bboxOf({ features: [f] }), { padding: 120, maxZoom: 17 }); };
    });
  },

  renderAnda(studies) {
    const el = $("anda");
    el.innerHTML = `<h3>${t("anda.title")}</h3>` + studies.map((a, i) => `
      <details class="card fold" style="margin-bottom:10px">
        <summary class="card-h"><h2 class="mono" style="font-size:12px">${h(a.idno)}</h2>
          ${a.scope_tables.length ? `<span class="pill">${t("anda.ntables", { n: a.scope_tables.length })}</span>` : `<span class="pill warn">${t("anda.nofiles")}</span>`}</summary>
        <p style="font-size:12px;margin:6px 0">${h(a.metadata?.title || "")} <span class="note">· ${h(a.metadata?.data_access_type || "")}</span></p>
        ${a.scope_tables.length ? `<p class="note">${t("anda.ingested", { t: h(a.scope_tables.join(", ")) })}</p>` : `
        <div class="flag" style="margin-bottom:8px"><b>${t("anda.nofiles")}</b><span>${t("anda.howto", { link: `<a href="${h(a.download_page)}" target="_blank" rel="noopener">${t("anda.page")}</a>`, folder: `<span class="mono">${h(a.drop_folder)}</span>`, cmd: `<span class="mono">infdb-uy anda-ingest</span>` })}</span></div>`}
        ${a.scope_tables.length ? `<div class="toolbar" style="margin-top:8px">
            <select data-table="${i}">${a.scope_tables.map((name) => `<option>${h(name)}</option>`).join("")}</select>
            <input list="anda-vl-${i}" placeholder="${t("anda.var")}" data-var="${i}" style="width:170px" autocomplete="off">
            <input list="anda-wl-${i}" placeholder="${t("anda.weight")}" data-w="${i}" style="width:120px" autocomplete="off">
            <datalist id="anda-vl-${i}"></datalist><datalist id="anda-wl-${i}"></datalist>
            <label class="switch"><input type="checkbox" data-unit="${i}"> ${t("anda.perunit")}</label>
            <button class="btn primary" data-go="${i}" disabled>${t("anda.show")}</button></div>
          <p class="note" data-hint="${i}"></p>
          <div data-dist="${i}" style="margin-top:8px"></div>` : ""}
        <details class="fold sub" style="margin-top:8px"><summary>${t("anda.catalogue")} <span class="note" data-count="${i}"></span></summary>
          <div class="toolbar" style="margin-top:6px"><input type="search" placeholder="${t("anda.search")}" data-search="${i}"></div>
          <div class="tw" style="max-height:220px;margin-top:6px"><table data-vars="${i}"></table></div></details>
      </details>`).join("");
    studies.forEach(async (a, i) => {
      let vars = [];
      const tbl = el.querySelector(`[data-vars="${i}"]`), cnt = el.querySelector(`[data-count="${i}"]`);
      const sel = el.querySelector(`[data-table="${i}"]`), vIn = el.querySelector(`[data-var="${i}"]`), wIn = el.querySelector(`[data-w="${i}"]`);
      const go = el.querySelector(`[data-go="${i}"]`), hint = el.querySelector(`[data-hint="${i}"]`);
      let cols = [];
      // the dropdowns offer only columns that exist in the selected table
      const check = () => {
        if (!go) return;
        const names = new Set(cols.map((c) => c.name));
        const v = vIn.value.trim(), w = wIn.value.trim();
        const ok = names.has(v) && (!w || names.has(w));
        go.disabled = !ok;
        hint.textContent = !v ? t("anda.pick") : !names.has(v) ? t("anda.notcol", { c: v }) : w && !names.has(w) ? t("anda.notcol", { c: w }) : "";
      };
      const loadCols = async () => {
        if (!sel) return;
        try { cols = await api(`/api/anda/${encodeURIComponent(a.idno)}/columns`, { table: sel.value }); } catch (_) { cols = []; }
        const opt = (c) => `<option value="${h(c.name)}">${h(c.label || "")}</option>`;
        el.querySelector(`#anda-vl-${i}`).innerHTML = cols.map(opt).join("");
        // INE does not flag weights in its catalogue: likely weight columns are only listed first
        const isW = (c) => c.is_weight || /^(w|w_.*|peso.*|pond.*)$/i.test(c.name) || /expansor|ponderador/i.test(c.label || "");
        el.querySelector(`#anda-wl-${i}`).innerHTML = [...cols.filter(isW), ...cols.filter((c) => !isW(c))].map(opt).join("");
        check();
      };
      if (sel) {
        sel.onchange = loadCols;
        vIn.oninput = check;
        wIn.oninput = check;
        await loadCols();
      }
      try { vars = await api(`/api/anda/${encodeURIComponent(a.idno)}/variables`); } catch (_) { /* metadata missing */ }
      const draw = (s) => {
        const rows = vars.filter((v) => !s || `${v.name} ${v.label} ${v.file_name}`.toLowerCase().includes(s.toLowerCase()));
        cnt.textContent = `${fmt(rows.length)} ${t("common.of")} ${fmt(vars.length)}`;
        tbl.innerHTML = `<thead><tr><th>${t("anda.th.name")}</th><th>${t("anda.th.label")}</th><th>${t("anda.th.file")}</th><th class="n">${t("anda.th.cat")}</th></tr></thead><tbody>${rows.slice(0, 200).map((v) =>
          `<tr class="click" data-name="${h(v.name)}"><td class="mono">${h(v.name)}</td><td>${h(v.label)}</td><td class="mono">${h(v.file_id)}</td><td class="n">${fmt(v.n_categories)}</td></tr>`).join("")}</tbody>`;
        // clicking a catalogue row selects it (matched case-insensitively against the table's columns)
        if (vIn) tbl.querySelectorAll("tbody tr").forEach((tr) => (tr.onclick = () => {
          const c = cols.find((x) => x.name.toLowerCase() === tr.dataset.name.toLowerCase());
          vIn.value = c ? c.name : tr.dataset.name;
          check();
        }));
      };
      draw("");
      el.querySelector(`[data-search="${i}"]`).oninput = (e) => draw(e.target.value);
      if (go) go.onclick = async () => {
        const out = el.querySelector(`[data-dist="${i}"]`);
        out.innerHTML = `<p class="loading">${t("anda.computing")}</p>`;
        try {
          const rows = await api(`/api/anda/${encodeURIComponent(a.idno)}/distribution`, {
            table: sel.value, variable: vIn.value.trim(), weight: wIn.value.trim(), by_unit: el.querySelector(`[data-unit="${i}"]`).checked });
          out.innerHTML = `<div class="tw" style="max-height:300px"><table><thead><tr><th>${t("anda.th.unit")}</th><th>${t("anda.th.code")}</th><th>${t("anda.th.label")}</th><th class="n">${t("anda.th.records")}</th><th class="n">${t("anda.th.weighted")}</th></tr></thead><tbody>${rows.map((r) =>
            `<tr><td class="mono">${h(r.unit)}</td><td class="mono">${h(r.code)}</td><td>${r.label ? h(r.label) : `<i class="note">${t("anda.nolabel")}</i>`}</td><td class="n">${fmt(r.records)}</td><td class="n">${r.weighted === null ? "–" : fmt1(r.weighted)}</td></tr>`).join("")}</tbody></table></div>
            <p class="note">${t("anda.note")}</p>`;
        } catch (e) { out.innerHTML = `<p class="flag"><b>${t("common.error")}</b><span>${h(e.message)}</span></p>`; }
      };
    });
  },
};

// ------------------------------------------------------------------ lidar
const LIDAR_CLASSES = Object.fromEntries([1, 2, 3, 4, 5, 6, 9].map((c) => [c, t(`lid.class.${c}`)]));
async function initLidar() {
  const [tiles, m] = await Promise.all([api("/api/lidar"), makeMap("lid-map")]);
  const tg = await geo("lidar_tiles");
  if (tg) {
    m.addSource("tiles", { type: "geojson", data: tg, generateId: true });
    m.addLayer({ id: "tiles-fill", type: "fill", source: "tiles", paint: { "fill-color": cssv("--c4"), "fill-opacity": ["case", ["boolean", ["feature-state", "hl"], false], 0.45, 0.12] } });
    m.addLayer({ id: "tiles-line", type: "line", source: "tiles", paint: { "line-color": cssv("--c4"), "line-width": 1.5 } });
    m.on("mousemove", "tiles-fill", (e) => { const p = e.features[0].properties; showTip(e.originalEvent, `<b>${h(p.HOJA)}</b><br>${fmt(p.point_count)} ${t("lid.tip.points")} · ${mb(p.bytes || 0)}`); });
    m.on("mouseleave", "tiles-fill", hideTip);
    m.fitBounds(bboxOf(tg), { padding: 30, duration: 0 });
  }
  addScopeOutline(m);
  const total = {};
  tiles.forEach((tl) => Object.entries(tl.classification_counts).forEach(([c, n]) => (total[c] = (total[c] || 0) + n)));
  const all = Object.values(total).reduce((a, b) => a + b, 0);
  const classes = Object.keys(total).sort((a, b) => a - b);
  const main = ["1", "2", "5", "6"];
  const colOf = (c) => ({ 1: "--mute", 2: "--c4", 5: "--c3", 6: "--c1" }[c] || "--c7");
  const crs = [...new Set(tiles.map((tl) => tl.crs))];
  $("lid-panel").innerHTML = `
    <div><h3>${t("lid.title")}</h3>
      <div class="kpis small">
        <div class="kpi"><div class="l">${t("lid.tiles")}</div><div class="v">${fmt(tiles.length)}</div></div>
        <div class="kpi"><div class="l">${t("lid.points")}</div><div class="v">${fmt1(all / 1e6)} M</div></div>
        <div class="kpi"><div class="l">${t("lid.size")}</div><div class="v">${mb(tiles.reduce((a, tl) => a + tl.bytes, 0))}</div></div>
        <div class="kpi"><div class="l">${t("lid.format")}</div><div class="v">${h([...new Set(tiles.map((tl) => `${tl.las_version} / ${tl.point_format}`))].join(", "))}</div></div>
      </div></div>
    <div class="card" style="padding:10px 12px"><p style="font-size:13px">${t("lid.content")}</p></div>
    <div class="flag"><b>CRS</b><span>${t("lid.crs", { a: h(crs.join(", ")), b: h(META.scope.crs) })}</span></div>
    <div><h3>${t("lid.perclass")}</h3><div class="tw"><table><thead><tr><th class="n">${t("lid.th.class")}</th><th>${t("lid.th.meaning")}</th><th class="n">${t("lid.points")}</th><th class="n">${t("lid.th.share")}</th></tr></thead><tbody>${classes.map((c) =>
      `<tr><td class="n mono"><span class="sw" style="display:inline-block;vertical-align:-1px;background:${cssv(colOf(c))}"></span> ${h(c)}</td><td>${LIDAR_CLASSES[c] ? h(LIDAR_CLASSES[c]) : `<span class="pill warn">${t("lid.notdoc")}</span>`}</td><td class="n">${fmt(total[c])}</td><td class="n">${fmt1((total[c] / all) * 100)} %</td></tr>`).join("")}</tbody></table></div></div>
    <div><h3>${t("lid.tiles")}</h3><div class="tw"><table><thead><tr><th>${t("lid.th.sheet")}</th><th class="n">${t("lid.points")}</th><th class="n">MB</th><th>${t("lid.th.mix")}</th><th>${t("lid.th.scope")}</th></tr></thead><tbody>${tiles.map((tl, i) => {
      const n = tl.point_count, cc = tl.classification_counts;
      const segs = [...main.map((c) => [c, cc[c] || 0]), ["other", Object.entries(cc).filter(([c]) => !main.includes(c)).reduce((a, [, v]) => a + v, 0)]];
      return `<tr class="click" data-i="${i}"><td class="mono">${h(tl.sheet)}</td><td class="n">${fmt(n)}</td><td class="n">${fmt1(tl.bytes / 1e6)}</td>
        <td><div style="display:flex;height:10px;width:140px;border-radius:2px;overflow:hidden">${segs.map(([c, v]) => `<span title="${t("lid.classword")} ${c}: ${fmt(v)}" style="width:${(v / n) * 100}%;background:${cssv(c === "other" ? "--c7" : colOf(c))}"></span>`).join("")}</div></td>
        <td>${h(relLabel(tl.scope_relation))} (${fmt((tl.scope_overlap_share || 0) * 100)} %)</td></tr>`;
    }).join("")}</tbody></table></div>
    <p class="note" style="margin-top:6px">${t("lid.note")}</p></div>`;
  $("lid-panel").querySelectorAll("tr[data-i]").forEach((tr) => {
    const i = +tr.dataset.i;
    tr.onmouseenter = () => tg && m.setFeatureState({ source: "tiles", id: i }, { hl: true });
    tr.onmouseleave = () => tg && m.setFeatureState({ source: "tiles", id: i }, { hl: false });
  });
}

// ------------------------------------------------------------------ data browser
async function initData() {
  const list = await api("/api/datasets");
  const el = $("ds-list");
  el.innerHTML = list.map((d, i) => `<button data-i="${i}"><div class="id">${h(d.id.replace(/^prepared\//, ""))}</div><div class="meta">${t("data.rows", { n: fmt(d.rows) })} · ${t("data.columns", { n: fmt(d.columns.length) })}</div></button>`).join("");
  el.querySelectorAll("button").forEach((b) => (b.onclick = () => {
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("sel", x === b));
    showDataset(list[+b.dataset.i]);
  }));
}
async function showDataset(d) {
  const v = $("ds-view");
  let offset = 0, search = "";
  const limit = 100;
  v.innerHTML = `
    <div class="toolbar"><h2 class="mono" style="font-size:13px">${h(d.id)}</h2>
      <a class="btn" href="/api/datasets/download?id=${encodeURIComponent(d.id)}">${t("data.download")}</a></div>
    <details><summary class="note" style="cursor:pointer">${t("data.schema", { n: fmt(d.columns.length) })}</summary>
      <div class="tw" style="max-height:200px;margin-top:6px"><table><thead><tr><th>${t("data.th.column")}</th><th>${t("data.th.type")}</th></tr></thead><tbody>${d.columns.map((c) => `<tr><td class="mono">${h(c.column_name)}</td><td class="mono">${h(c.column_type)}</td></tr>`).join("")}</tbody></table></div></details>
    <div class="toolbar"><input type="search" id="ds-search" placeholder="${t("data.search")}"><button class="btn" id="ds-prev">◀</button><button class="btn" id="ds-next">▶</button><span class="note" id="ds-pos"></span></div>
    <div class="tw" id="ds-table"></div>`;
  const load = async () => {
    const r = await api("/api/datasets/rows", { id: d.id, offset, limit, search });
    const cols = r.rows.length ? Object.keys(r.rows[0]) : d.columns.map((c) => c.column_name);
    $("ds-table").innerHTML = `<table><thead><tr>${cols.map((c) => `<th>${h(c)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) =>
      `<tr>${cols.map((c) => { const x = row[c]; return typeof x === "number" ? `<td class="n">${h(x)}</td>` : `<td>${h(x ?? "")}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
    $("ds-pos").textContent = r.total ? `${fmt(offset + 1)}–${fmt(Math.min(offset + limit, r.total))} ${t("common.of")} ${fmt(r.total)}` : t("data.norows");
    $("ds-prev").disabled = offset === 0;
    $("ds-next").disabled = offset + limit >= r.total;
  };
  let timer;
  $("ds-search").oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { search = e.target.value; offset = 0; load(); }, 300); };
  $("ds-prev").onclick = () => { offset = Math.max(0, offset - limit); load(); };
  $("ds-next").onclick = () => { offset += limit; load(); };
  load();
}

// ------------------------------------------------------------------ boot
// Address under which other devices in the same network reach the dashboard (click = copy)
api("/api/network").then((net) => {
  const url = net.urls?.[0];
  if (!url) return;
  const b = $("net");
  b.textContent = `${t("net.label")} ${url.replace("http://", "")}`;
  b.title = `${t("net.title")}\n${net.urls.join("\n")}`;
  b.hidden = false;
  b.onclick = async () => {
    try { await navigator.clipboard.writeText(url); } catch (_) { prompt(t("net.title"), url); return; }
    b.textContent = t("net.copied");
    setTimeout(() => (b.textContent = `${t("net.label")} ${url.replace("http://", "")}`), 1500);
  };
}).catch(() => { /* not shown */ });

(async () => {
  try {
    META = await api("/api/meta");
    const area = META.qa?.scope?.area_ha;
    $("subtitle").textContent = `${META.scope.values.join(", ")} · ${area ? fmt1(area) + " ha · " : ""}${t("sub.release", { r: (META.dnc?.release_zip || "").replace(/\D/g, "").replace(/(\d{4})(\d{2})/, "$1-$2") })}`;
    const start = (location.hash || "#overview").slice(1);
    openTab(["overview", "cadastre", "census", "lidar", "data"].includes(start) ? start : "overview");
  } catch (e) {
    $("overview").innerHTML = `<div class="flag"><b>${t("boot.nodata")}</b><span>${h(e.message)}. ${t("boot.run")} <span class="mono">infdb-uy all</span>.</span></div>`;
  }
})();
