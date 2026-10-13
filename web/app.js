// Kantarellen: sannolikhetskartan, förklaring per ruta och privata fynd (bara i den här webbläsaren).
'use strict';

proj4.defs('EPSG:3006', '+proj=utm +zone=33 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs');
const TILL_SWEREF = proj4('EPSG:4326', 'EPSG:3006');
const FALT = ['poang', 'f_tradslag', 'f_alder', 'f_jordart', 'f_fukt', 'f_hojd',
  'gran', 'tall', 'bjork', 'tradhojd', 'ar_sedan_avverkning', 'jordart', 'fukt', 'hojd'];
const JORDARTER = { 1: 'morän', 2: 'sand', 3: 'grus', 4: 'silt', 5: 'lera', 6: 'torv', 7: 'berg i dagen', 8: 'annat' };
const FUKT = { 1: 'torr', 2: 'frisk', 3: 'fuktig', 4: 'blöt' };
const FAKTORNAMN = { tradslag: 'Trädslag', alder: 'Skogens ålder', jordart: 'Jordart', fukt: 'Markfuktighet', hojd: 'Höjd' };
const BEGRANSANDE = 0.15;  // samma som i kantarell/poang.py
const NYCKEL = 'kantarellen.fynd';

const $ = (id) => document.getElementById(id);
const visaStatus = (t) => { $('status').textContent = t; };
let meta, karta, minPosition = null;

// ---------- Fynden (localStorage) ----------
const lasFynd = () => { try { return JSON.parse(localStorage.getItem(NYCKEL) || '[]'); } catch { return []; } };
const sparaFynd = (f) => localStorage.setItem(NYCKEL, JSON.stringify(f));
function fyndSomGeojson() {
  return { type: 'FeatureCollection', features: lasFynd().map((f) => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: [f.lon, f.lat] }, properties: { tid: f.tid, mangd: f.mangd, not: f.not } })) };
}
function visaFynd() {
  $('antal').textContent = lasFynd().length;
  karta.getSource('fynd')?.setData(fyndSomGeojson());
}

// ---------- Rutans förklaring ----------
const blockCache = new Map();
async function rutaVid(lngLat) {
  const [x, y] = TILL_SWEREF.forward([lngLat.lng, lngLat.lat]);
  const n = meta.rutnat;
  const kol = Math.floor((x - n.x0) / n.ruta_m), rad = Math.floor((n.y0 - y) / n.ruta_m);
  if (kol < 0 || rad < 0 || kol >= n.bredd || rad >= n.hojd) return null;
  const bx = Math.floor(kol / n.block), by = Math.floor(rad / n.block);
  const nyckel = `${bx}_${by}`;
  if (!blockCache.has(nyckel)) {
    // Blocken är gzip-komprimerade filer (inte Content-Encoding), så de packas upp här
    blockCache.set(nyckel, fetch(`data/block/${nyckel}.bin.gz`)
      .then((r) => (r.ok ? new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer() : null))
      .catch(() => null));
  }
  const buf = await blockCache.get(nyckel);
  if (!buf) return null;
  const i = ((rad % n.block) * n.block + (kol % n.block)) * FALT.length;
  const b = new Uint8Array(buf, i, FALT.length);
  const v = {};
  FALT.forEach((f, k) => {
    const x = b[k];
    v[f] = x === 255 ? null : (f === 'poang' || f.startsWith('f_')) ? x / 250 : f === 'hojd' ? x * 5 : x;
  });
  return v;
}

const pct = (x) => `${Math.round(x * 100)} %`;
// Var rutan hamnar bland områdets skogsrutor; kartans färger går efter samma rangordning
function placering(p) {
  const s = meta.skala;
  if (!s?.poang?.length) return '';
  for (let i = s.poang.length - 1; i >= 0; i--) if (p >= s.poang[i]) return `<strong>Bland de ${100 - s.percentiler[i]} % bästa</strong> i ${meta.omrade}`;
  return `Under medel i ${meta.omrade}`;
}
function forklaring(v) {
  if (!v || v.poang === null) return '<div class="forklaring"><p>Ingen skog här, eller data saknas.</p></div>';
  const raa = {
    tradslag: v.gran === null ? '–' : `gran ${v.gran} %, tall ${v.tall ?? 0} %, björk ${v.bjork ?? 0} %`,
    alder: v.ar_sedan_avverkning !== null ? `avverkad för ${v.ar_sedan_avverkning} år sedan` : v.tradhojd !== null ? `träden ${v.tradhojd} m höga` : '–',
    jordart: v.jordart !== null ? JORDARTER[v.jordart] ?? '–' : '–',
    fukt: v.fukt !== null ? FUKT[v.fukt] ?? '–' : '–',
    hojd: v.hojd !== null ? `${v.hojd} m ö.h.` : '–',
  };
  const kanda = Object.keys(FAKTORNAMN).filter((k) => v[`f_${k}`] !== null);
  const lagst = kanda.reduce((a, k) => (a === null || v[`f_${k}`] < v[`f_${a}`] ? k : a), null);
  const begr = lagst && v[`f_${lagst}`] < BEGRANSANDE ? lagst : null;
  const rader = Object.entries(FAKTORNAMN).map(([k, namn]) => {
    const f = v[`f_${k}`];
    return `<tr${k === begr ? ' class="begr"' : ''}><td>${namn}<br><span class="dampad">${raa[k]}</span></td><td>${f === null ? 'saknas' : pct(f)}</td></tr>`;
  }).join('');
  return `<div class="forklaring"><div class="poang">${pct(v.poang)}</div>
    <div class="dampad">sannolikhet för kantareller${begr ? `, begränsas av ${FAKTORNAMN[begr].toLowerCase()}` : ''}</div>
    <div>${placering(v.poang)}</div>
    <table>${rader}</table><button data-fynd>Markera fynd här</button></div>`;
}

// ---------- Markera fynd ----------
function markera(lngLat) {
  $('fyndplats').textContent = `${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}`;
  const d = $('fyndform');
  d.returnValue = '';
  d.onclose = () => {
    if (d.returnValue !== 'spara') return;
    const form = d.querySelector('form');
    const fynd = lasFynd();
    fynd.push({ lat: lngLat.lat, lon: lngLat.lng, tid: new Date().toISOString(), mangd: form.mangd.value, not: form.not.value.trim() });
    sparaFynd(fynd);
    form.reset();
    visaFynd();
    visaStatus('Fyndet är sparat i den här webbläsaren');
  };
  d.showModal();
}

function visaLista() {
  const ol = $('fynd');
  const fynd = lasFynd();
  ol.innerHTML = fynd.length ? fynd.map((f) => `<li>${new Date(f.tid).toLocaleDateString('sv-SE')}: ${f.mangd}${f.not ? `, ${f.not}` : ''}<br><span class="dampad">${f.lat.toFixed(5)}, ${f.lon.toFixed(5)}</span></li>`).join('')
    : '<p class="dampad">Inga fynd än.</p>';
  $('fyndlista').showModal();
}

function exportera() {
  const blob = new Blob([JSON.stringify(fyndSomGeojson(), null, 1)], { type: 'application/geo+json' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `kantarellfynd-${new Date().toISOString().slice(0, 10)}.geojson` });
  a.click();
  URL.revokeObjectURL(a.href);
}

function omKartan() {
  const k = meta.kallor.map((s) => `<li><strong>${s.namn}</strong> (${s.vad}), ${s.datum}, licens: ${s.licens}${s.url ? `, <a href="${s.url}" target="_blank" rel="noopener">källa</a>` : ''}${s.not ? `<br><span class="dampad">${s.not}</span>` : ''}</li>`).join('');
  $('omtext').innerHTML = `<p>Sannolikheten är en poäng ur regler om var kantareller brukar växa: trädslag, skogens ålder (trädhöjd och avverkningar), jordart, markfuktighet och höjd. Färgerna går efter rangordning: guld är de 10 % bästa skogsrutorna i ${meta.omrade}. Tryck på kartan för att se varför ett område bedöms som det gör.</p>
    <p class="dampad">Beräknad ${meta.skapad}. ${meta.statistik.skogsrutor.toLocaleString('sv-SE')} skogsrutor om ${meta.rutnat.ruta_m} m.</p>
    <h3>Källor</h3><ul>${k}</ul>
    <p class="dampad">Dina fynd sparas bara i den här webbläsaren och skickas aldrig någonstans.</p>`;
  $('omkartan').showModal();
}

// ---------- Kartan ----------
async function start() {
  meta = await (await fetch('data/meta.json')).json();
  const t = meta.tiles;
  karta = new maplibregl.Map({
    container: 'karta',
    style: 'https://tiles.openfreemap.org/styles/liberty',   // OpenFreeMap: öppen bakgrundskarta utan nyckel
    bounds: [[t.bounds[0], t.bounds[1]], [t.bounds[2], t.bounds[3]]],
    fitBoundsOptions: { padding: 20 },
  });
  karta.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  const geo = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true });
  karta.addControl(geo, 'top-right');
  geo.on('geolocate', (e) => { minPosition = { lng: e.coords.longitude, lat: e.coords.latitude }; visaStatus(`Position ±${Math.round(e.coords.accuracy)} m`); });
  geo.on('error', () => visaStatus('Positionen kunde inte hämtas'));

  karta.on('load', () => {
    // Tiles till zoom 11; närmare förstoras de (rutorna är ändå 50 m)
    const bas = new URL('.', location.href).href;
    karta.addSource('poang', { type: 'raster', tiles: [bas + t.url], tileSize: 256, minzoom: t.minzoom, maxzoom: t.maxzoom, bounds: t.bounds });
    // Under vägar och ortnamn, så att kartan går att läsa genom poängen
    const forsta = karta.getStyle().layers.find((l) => l.type === 'symbol')?.id;
    karta.addLayer({ id: 'poang', type: 'raster', source: 'poang', paint: { 'raster-opacity': 0.7, 'raster-resampling': 'nearest' } }, forsta);
    karta.addSource('fynd', { type: 'geojson', data: fyndSomGeojson() });
    karta.addLayer({ id: 'fynd', type: 'circle', source: 'fynd', paint: { 'circle-radius': 7, 'circle-color': '#e6a91e', 'circle-stroke-color': '#2f3b25', 'circle-stroke-width': 2 } });
    visaFynd();
    visaStatus('Tryck på kartan för förklaring');
    geo.trigger();
  });

  karta.on('click', async (e) => {
    const v = await rutaVid(e.lngLat);
    const p = new maplibregl.Popup({ maxWidth: '300px' }).setLngLat(e.lngLat).setHTML(forklaring(v)).addTo(karta);
    p.getElement().querySelector('[data-fynd]')?.addEventListener('click', () => { p.remove(); markera(e.lngLat); });
  });

  $('markera').onclick = () => {
    if (minPosition) markera(minPosition);
    else { visaStatus('Ingen position än: tryck på kartan där du hittade svampen'); }
  };
  $('lista').onclick = visaLista;
  $('stang-lista').onclick = () => $('fyndlista').close();
  $('exportera').onclick = exportera;
  $('om').onclick = omKartan;
  $('stang-om').onclick = () => $('omkartan').close();
}

start().catch((e) => visaStatus(`Kartan kunde inte laddas: ${e.message}`));
