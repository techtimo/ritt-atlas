let EVENTS = [];
const WIKI_FILE = "https://vdd-aktuell.de/mediawiki/index.php?title=Special:Redirect/file/";

function safeUrl(url) {
  return url && /^https?:\/\//i.test(url) ? url : '';
}
function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
const imgCache = {};
function preloadImg(ev) {
  if (ev.ritt_bild && !imgCache[ev.id]) {
    const img = new Image();
    img.src = WIKI_FILE + encodeURIComponent(ev.ritt_bild);
    imgCache[ev.id] = img;
  }
}

let showVorrat = document.getElementById('show-vorrat').checked;
let showVergangene = document.getElementById('show-vergangene').checked;
const TODAY = new Date().toISOString().slice(0, 10);

// ── map ────────────────────────────────────────────────────────────────────
const BASEMAP_STYLE = 'https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/styles/bm_web_top.json';
const BLANK_STYLE = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f8f8f8' } }] };

const map = new maplibregl.Map({
  container: 'map',
  style: navigator.onLine ? BASEMAP_STYLE : BLANK_STYLE,
  bounds: [[6.0259, 47.5733], [14.5152, 54.4286]],
  fitBoundsOptions: { padding: 25 },
  attributionControl: { compact: true },
  pitchWithRotate: false,
  maxPitch: 0,
  dragRotate: false,
});
map.touchZoomRotate.disableRotation();
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
map.on('click', () => { if (openPopup) openPopup.remove(); });
window.addEventListener('offline', () => map.setStyle(BLANK_STYLE));
window.addEventListener('online',  () => map.setStyle(BASEMAP_STYLE));

function markerColor(ev) {
  if (ev.rittvorrat) return '#c62828';
  const s = (ev.status || '').toLowerCase();
  if (s.includes('abgesagt')) return '#f9a825';
  if (s.includes('vorl'))    return '#e65100';
  return '#2e7d32';
}

const _markerElCache = {};
function makeMarkerEl(color) {
  if (!_markerElCache[color]) {
    const el = document.createElement('div');
    el.style.cssText = 'width:22px;height:33px;cursor:pointer';
    el.innerHTML = `<svg width="22" height="33" viewBox="0 0 24 36" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 9 12 24 12 24s12-15 12-24C24 5.37 18.63 0 12 0z"
          fill="${color}" stroke="#fff" stroke-width="1.5"/>
    <circle cx="12" cy="12" r="4.5" fill="#fff" opacity=".85"/>
  </svg>`;
    _markerElCache[color] = el;
  }
  return _markerElCache[color].cloneNode(true);
}

function kmOffsets(lat, km) {
  const dLat = km / 111.32;
  return { dLat, dLon: km / (111.32 * Math.cos(lat * Math.PI / 180)) };
}

function circlePolygon(lat, lon, km, n = 64) {
  const { dLat, dLon } = kmOffsets(lat, km);
  const coords = Array.from({ length: n + 1 }, (_, i) => {
    const a = (i / n) * 2 * Math.PI;
    return [lon + dLon * Math.sin(a), lat + dLat * Math.cos(a)];
  });
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } };
}

const INIT_BOUNDS = [[6.0259, 47.5733], [14.5152, 54.4286]];

function radiusBounds(lat, lon, km) {
  const { dLat, dLon } = kmOffsets(lat, km);
  return [
    [Math.max(lon - dLon, INIT_BOUNDS[0][0]), Math.max(lat - dLat, INIT_BOUNDS[0][1])],
    [Math.min(lon + dLon, INIT_BOUNDS[1][0]), Math.min(lat + dLat, INIT_BOUNDS[1][1])],
  ];
}

function showRadiusCircle(lat, lon, km) {
  const data = circlePolygon(lat, lon, km);
  const src = map.getSource('radius-circle');
  if (src) {
    src.setData(data);
  } else {
    map.addSource('radius-circle', { type: 'geojson', data });
    map.addLayer({ id: 'radius-fill', type: 'fill', source: 'radius-circle',
      paint: { 'fill-color': '#2ea3f2', 'fill-opacity': 0.07 } });
    map.addLayer({ id: 'radius-stroke', type: 'line', source: 'radius-circle',
      paint: { 'line-color': '#2ea3f2', 'line-width': 2 } });
  }
}

function removeRadiusCircle() {
  if (map.getSource('radius-circle')) {
    map.removeLayer('radius-fill');
    map.removeLayer('radius-stroke');
    map.removeSource('radius-circle');
  }
}

const markers = {};

let openPopup = null;

function showEventPopup(ev) {
  const prev = openPopup;
  openPopup = null;
  if (prev) prev.remove();
  openPopup = new maplibregl.Popup({ maxWidth: '340px', closeButton: false, anchor: 'bottom', offset: [0, -38], focusAfterOpen: false })
    .setLngLat([ev.lon, ev.lat])
    .setHTML(popupHtml(ev))
    .addTo(map);
  const _pc = openPopup.getElement()?.querySelector('.maplibregl-popup-content');
  if (_pc) _pc.scrollTop = 0;
  openPopup.on('close', () => {
    if (!openPopup) return;
    if (window.location.hash.slice(1) === encodeURIComponent(ev.id)) clearUrlHash();
    openPopup = null;
    if (activeId === ev.id) {
      activeId = null;
      const r = tbl.getRow(ev.id);
      if (r) r.reformat();
    }
  });
}

function fmtDateDe(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y.slice(2)}`;
}

function dateRange(ev) {
  if (!ev.start_date) return '–';
  if (!ev.end_date || ev.start_date === ev.end_date) return fmtDateDe(ev.start_date);
  const [sy, sm, sd] = ev.start_date.split('-');
  const [ey, em, ed] = ev.end_date.split('-');
  if (sy === ey) return `${sd}.${sm} – ${ed}.${em}.${ey.slice(2)}`;
  return `${fmtDateDe(ev.start_date)} – ${fmtDateDe(ev.end_date)}`;
}

function pdfLink(filename, label, updated) {
  if (!filename) return '';
  const url = WIKI_FILE + encodeURIComponent(filename);
  return `<a class="popup-doc${updated ? ' updated' : ''}" href="${url}" target="_blank">${label}</a>`;
}

function icsDownload(ev) {
  if (!ev.start_date) return;
  const pad = s => String(s).padStart(2, '0');
  const toDate = str => str.replace(/-/g, '');
  // RFC 5545 TEXT escaping: backslash first, then real newlines → \n, then ; and ,
  const esc = s => String(s).replace(/\\/g, '\\\\').replace(/\r\n|\r|\n/g, '\\n').replace(/;/g, '\\;').replace(/,/g, '\\,');
  // LOCATION escaping: newlines become ", " — Google rejects multi-line LOCATION with \n
  const locEsc = s => String(s).replace(/\\/g, '\\\\').replace(/\r\n|\r|\n/g, ', ').replace(/;/g, '\\;');
  // RFC 5545 line folding: max 75 octets per line, continuation lines start with a space
  const fold = line => {
    const enc = new TextEncoder();
    if (enc.encode(line).length <= 75) return line;
    const parts = [];
    let i = 0;
    while (i < line.length) {
      // find largest slice that fits within the byte budget (75 first, 74 for continuations due to leading space)
      const budget = i === 0 ? 75 : 74;
      let j = i + budget;
      if (j > line.length) j = line.length;
      // don't split inside a surrogate pair or multi-byte char
      while (j > i && enc.encode(line.slice(i, j)).length > budget) j--;
      parts.push((i === 0 ? '' : ' ') + line.slice(i, j));
      i = j;
    }
    return parts.join('\r\n');
  };
  const umlaut = s => s.replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue')
    .replace(/Ä/g,'Ae').replace(/Ö/g,'Oe').replace(/Ü/g,'Ue').replace(/ß/g,'ss');
  // UID must be ASCII-only per RFC 5545
  const asciiId = umlaut(ev.id || ev.wiki_title).replace(/[^a-zA-Z0-9_-]/g, '-');
  // DTEND for all-day events is exclusive — add one day
  const endExcl = d => {
    const [y, m, day] = d.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1, day + 1));
    return `${dt.getUTCFullYear()}${pad(dt.getUTCMonth()+1)}${pad(dt.getUTCDate())}`;
  };
  // DTSTAMP: current UTC timestamp (required by RFC 5545)
  const now = new Date();
  const dtstamp = `${now.getUTCFullYear()}${pad(now.getUTCMonth()+1)}${pad(now.getUTCDate())}T${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}Z`;
  const end = ev.end_date && ev.end_date !== ev.start_date ? ev.end_date : ev.start_date;
  const distParts = ['efr','kdr','mdr','ldr','mtr','cei'].map(k => ev[k] && `${k.toUpperCase()} ${ev[k]}`).filter(Boolean).join(', ');
  const descParts = [
    distParts      && `Distanzen: ${distParts}`,
    ev.organizer   && `Veranstalter: ${ev.organizer}`,
    ev.event_types && `Art: ${ev.event_types}`,
    ev.vdd_url,
  ].filter(Boolean).map(esc).join('\\n');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//VDD Viewer//DE',
    'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:vdd-${asciiId}@vdd-aktuell.de`,
    `DTSTAMP:${dtstamp}`,
    `DTSTART;VALUE=DATE:${toDate(ev.start_date)}`,
    `DTEND;VALUE=DATE:${endExcl(end)}`,
    `SUMMARY:${esc(ev.name || ev.wiki_title)}`,
    ev.venue    ? `LOCATION:${locEsc(ev.venue)}` : '',
    descParts   ? `DESCRIPTION:${descParts}` : '',
    ev.vdd_url  ? `URL:${ev.vdd_url}` : '',
    'END:VEVENT', 'END:VCALENDAR',
  ].filter(l => l !== '').map(fold).join('\r\n') + '\r\n';
  const blob = new Blob([lines], { type: 'text/calendar;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${umlaut(ev.name || ev.wiki_title).replace(/[^a-zA-Z0-9_-]/g, '_')}.ics`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function popupBodyHtml(ev) {
  const distParts = [
    ev.efr && `EFR ${ev.efr}`, ev.kdr && `KDR ${ev.kdr}`,
    ev.mdr && `MDR ${ev.mdr}`, ev.ldr && `LDR ${ev.ldr}`,
    ev.mtr && `MTR ${ev.mtr}`, ev.cei && `CEI ${ev.cei}`,
  ].filter(Boolean).join(' | ');

  let h = '';
  if (ev.ritt_bild) h += `<div class="popup-img" style="background-image:url(${WIKI_FILE}${encodeURIComponent(ev.ritt_bild)})"></div>`;

  const status = ev.status && ev.status !== 'steht fest' ? ev.status : null;
  for (const [label, val] of [
    ['Datum', dateRange(ev)], ['Status', status], ['Distanzen', distParts],
    ['Region', ev.region], ['Ort', ev.venue],
    ['Veranstalter', ev.organizer], ['Art', ev.event_types], ['Seit', ev.first_edition_year],
  ]) {
    if (val) h += `<div class="popup-row"><span class="popup-label">${label}: </span>${val}</div>`;
  }

  const siteUrl = safeUrl(ev.website);
  if (siteUrl) {
    const siteLabel = siteUrl.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
    h += `<div class="popup-row"><span class="popup-label">Website: </span><a href="${siteUrl}" target="_blank" rel="noopener noreferrer">${escHtml(siteLabel)}</a></div>`;
  }
  const link = ev.vdd_url || ev.wiki_url;
  if (link) {
    h += `<div style="margin-top:8px"><a class="popup-link" style="margin:0" href="${link}" target="_blank">VDD-Seite &rarr;</a></div>`;
  }
  if (ev.bemerkung) h += `<div class="popup-note"><span class="popup-label">Bemerkung: </span>${escHtml(ev.bemerkung)}</div>`;
  return h;
}

function popupDocsHtml(ev) {
  return [
    pdfLink(ev.announcement_pdf, 'Ausschreibung', ev.announcement_updated),
    pdfLink(ev.results_pdf,      'Ergebnisse',    false),
    pdfLink(ev.registration_pdf, 'Nennung',        false),
    ev.start_date ? `<a class="popup-doc popup-doc-ics" href="javascript:void(0)" data-ics-id="${escHtml(ev.id)}">Kalender</a>` : '',
  ].filter(Boolean).join('');
}

const SHARE_ICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>`;
document.getElementById('popup-modal-share').innerHTML = SHARE_ICON;

function popupHtml(ev) {
  const name = escHtml(ev.name || ev.wiki_title);
  const title = ev.subtitle ? `${name} <small style="font-weight:400;opacity:.85">${escHtml(ev.subtitle)}</small>` : name;
  const docs = popupDocsHtml(ev);
  const footer = docs ? `<div class="popup-footer">${docs}</div>` : '';
  return `<div class="popup-header"><span class="popup-header-title">${title}</span><button class="popup-header-close" onclick="shareCurrentUrl(this)" title="Link teilen" data-copied="✓">${SHARE_ICON}</button><button class="popup-header-close" onclick="if(openPopup)openPopup.remove()" title="Schließen">✕</button></div><div class="popup-body">${popupBodyHtml(ev)}</div>${footer}`;
}

// ── filter logic ───────────────────────────────────────────────────────────
let filterText = '';
let userLat = null, userLon = null, radiusKm = 250;
let userMarker = null;
let selectedRegion = '';
let selectedEventTypes = new Set();
let selectedDistances = new Set();

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function eventVisible(ev) {
  if (ev.rittvorrat && !showVorrat) return false;
  if (!showVergangene && (ev.end_date || ev.start_date) < TODAY) return false;
  if (selectedRegion && ev.region !== selectedRegion) return false;
  if (selectedEventTypes.size > 0) {
    if (!ev.event_types_arr.some(t => selectedEventTypes.has(t))) return false;
  }
  if (selectedDistances.size > 0) {
    let distMatch = false;
    for (const d of selectedDistances) { if (ev[d]) { distMatch = true; break; } }
    if (!distMatch) return false;
  }
  if (filterText) {
    const q = filterText.toLowerCase();
    return [ev.wiki_title, ev.name, ev.subtitle, ev.region, ev.venue,
            ev.event_types, ev.organizer, ev.status]
      .some(v => v && v.toLowerCase().includes(q));
  } else if (userLat !== null) {
    if (!ev.lat || !ev.lon) return false;
    return haversineKm(userLat, userLon, ev.lat, ev.lon) <= radiusKm;
  }
  return true;
}

function applyFilters() {
  tbl.setFilter(eventVisible);
}

function statusClass(s) {
  if (!s) return '';
  const l = s.toLowerCase();
  if (l.includes('abgesagt')) return 'status-abges';
  if (l.includes('vorl'))    return 'status-vorl';
  return 'status-fest';
}

// ── column formatters ───────────────────────────────────────────────────────
function fmtName(cell) {
  const ev = cell.getRow().getData();
  const name = ev.name || ev.wiki_title;
  let html = name;
  if (!ev.lat) html += '<span class="no-map-badge">kein GPS</span>';
  return html;
}

function fmtDate(cell) { return dateRange(cell.getRow().getData()); }

function fmtStatus(cell) {
  const s = cell.getValue() || '–';
  return `<span class="${statusClass(s)}">${s}</span>`;
}

function fmtPdf(pdfField, updatedField) {
  return function(cell) {
    const ev = cell.getRow().getData();
    const pdf = ev[pdfField];
    if (!pdf) return '';
    const updated = updatedField ? ev[updatedField] : false;
    return `<a class="tbl-doc${updated ? ' updated' : ''}" href="${WIKI_FILE}${encodeURIComponent(pdf)}" target="_blank" onclick="event.stopPropagation()">PDF</a>`;
  };
}

function fmtIcs(cell) {
  const ev = cell.getRow().getData();
  if (!ev.start_date) return '';
  return `<a class="tbl-doc tbl-doc-ics" href="javascript:void(0)" onclick="event.stopPropagation();icsDownload(EVENTS.find(e=>e.id==='${ev.id}'))">ICS</a>`;
}

function fmtLink(cell) {
  const url = safeUrl(cell.getValue());
  if (!url) return '';
  const label = url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
  return `<a href="${url}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${escHtml(label)}</a>`;
}

// ── MiniTable — lightweight table ──────────────────────────────────────────
// API: setFilter, getRow, scrollToRow, on(tableBuilt|rowClick|rowMouseEnter|dataFiltered)
class MiniTable {
  #data; #idx; #cols; #rowFmt; #filterFn = null;
  #sortField; #sortDir; #container;
  #tbody; #headerCells = [];
  #rowMap = new Map(); // id → { tr, data }
  #listeners = {};

  constructor(selector, { data, index, columns, rowFormatter, initialSort }) {
    this.#data     = data;
    this.#idx      = index;
    this.#cols     = columns;
    this.#rowFmt   = rowFormatter;
    this.#sortField = initialSort?.[0]?.column ?? null;
    this.#sortDir   = initialSort?.[0]?.dir     ?? 'asc';
    this.#container = document.querySelector(selector);
    this.#build();
  }

  #build() {
    const wrap = document.createElement('div');
    wrap.className = 'mtbl-wrap';
    this.#container.appendChild(wrap);

    const table = document.createElement('table');
    table.className = 'mtbl';

    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    let frozenPx = 0;
    this.#cols.forEach(col => {
      const th = document.createElement('th');
      if (col.width)         th.style.cssText += `width:${col.width}px;max-width:${col.width}px;`;
      if (col.frozen)       { th.classList.add('fr'); th.style.left = frozenPx + 'px'; frozenPx += col.width || 160; }
      if (col.headerTooltip) th.title = col.headerTooltip;
      const canSort = col.headerSort !== false && col.sorter !== false;
      th.innerHTML = escHtml(col.title) + (canSort ? '<span class="sa"></span>' : '');
      if (!canSort) th.classList.add('ns');
      else th.addEventListener('click', () => this.#toggleSort(col.field));
      this.#headerCells.push({ th, col });
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    this.#tbody = document.createElement('tbody');
    table.appendChild(this.#tbody);
    wrap.appendChild(table);

    const frag = document.createDocumentFragment();
    this.#getSorted(this.#data).forEach(d => this.#appendRow(d, frag));
    this.#tbody.appendChild(frag);
    this.#updateArrows();
    setTimeout(() => this.#emit('tableBuilt'), 0);
  }

  #getSorted(arr) {
    if (!this.#sortField) return arr;
    const col = this.#cols.find(c => c.field === this.#sortField);
    const num = col?.sorter === 'number';
    return [...arr].sort((a, b) => {
      let av = a[this.#sortField], bv = b[this.#sortField];
      if (num) { av = +av || 0; bv = +bv || 0; }
      else     { av = av ?? ''; bv = bv ?? ''; }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return this.#sortDir === 'asc' ? cmp : -cmp;
    });
  }

  #toggleSort(field) {
    this.#sortDir   = this.#sortField === field && this.#sortDir === 'asc' ? 'desc' : 'asc';
    this.#sortField = field;
    this.#updateArrows();
    this.#reapply();
  }

  #updateArrows() {
    this.#headerCells.forEach(({ th, col }) => {
      th.classList.toggle('asc',  col.field === this.#sortField && this.#sortDir === 'asc');
      th.classList.toggle('desc', col.field === this.#sortField && this.#sortDir === 'desc');
    });
  }

  #rowProxy(tr, d) {
    return {
      getData:    () => d,
      getElement: () => tr,
      reformat:   () => { if (this.#rowFmt) this.#rowFmt(this.#rowProxy(tr, d)); },
    };
  }

  #appendRow(d, container = this.#tbody) {
    const tr = document.createElement('tr');
    let frozenPx = 0;
    this.#cols.forEach(col => {
      const td = document.createElement('td');
      if (col.width)  td.style.cssText = `width:${col.width}px;max-width:${col.width}px;`;
      if (col.frozen) { td.classList.add('fr'); td.style.left = frozenPx + 'px'; frozenPx += col.width || 160; }
      const rp = this.#rowProxy(tr, d);
      const cp = { getRow: () => rp, getValue: () => d[col.field], getData: () => d };
      td.innerHTML = col.formatter ? (col.formatter(cp) ?? '') : escHtml(String(d[col.field] ?? ''));
      if (col.tooltip === true)               td.title = String(d[col.field] ?? '');
      else if (typeof col.tooltip === 'function') td.title = col.tooltip(null, cp) || '';
      tr.appendChild(td);
    });
    tr.addEventListener('click',      e => this.#emit('rowClick',      e, this.#rowProxy(tr, d)));
    tr.addEventListener('mouseenter', e => this.#emit('rowMouseEnter', e, this.#rowProxy(tr, d)));
    this.#rowMap.set(d[this.#idx], { tr, data: d });
    if (this.#rowFmt) this.#rowFmt(this.#rowProxy(tr, d));
    container.appendChild(tr);
  }

  #reapply() {
    const filtered = this.#filterFn ? this.#data.filter(this.#filterFn) : this.#data;
    const sorted   = this.#getSorted(filtered);
    this.#rowMap.forEach(({ tr }) => { tr.style.display = 'none'; });
    sorted.forEach(d => {
      const e = this.#rowMap.get(d[this.#idx]);
      if (e) { e.tr.style.display = ''; this.#tbody.appendChild(e.tr); }
    });
    this.#emit('dataFiltered', [],
      sorted.map(d => { const e = this.#rowMap.get(d[this.#idx]); return e ? this.#rowProxy(e.tr, e.data) : null; }).filter(Boolean));
  }

  setFilter(fn)   { this.#filterFn = fn; this.#reapply(); }
  getRow(id)      { const e = this.#rowMap.get(id); return e ? this.#rowProxy(e.tr, e.data) : null; }
  scrollToRow(id) { this.#rowMap.get(id)?.tr.scrollIntoView({ block: 'nearest', behavior: 'instant' }); return Promise.resolve(); }
  on(ev, fn)      { (this.#listeners[ev] ??= []).push(fn); return this; }
  #emit(ev, ...a) { (this.#listeners[ev] || []).forEach(fn => fn(...a)); }
}

let tbl;
let activeId = null;

function initTable(data) {
  tbl = new MiniTable("#grid", {
    data,
    index: "id",
    initialSort: [{ column: "start_date", dir: "asc" }],
    columns: [
      { title: "Name",              field: "name",               formatter: fmtName,                                          frozen: true, width: window.innerWidth <= 768 ? 115 : 160, tooltip: (e, cell) => cell.getData().name },
      { title: "Datum",             field: "start_date",         formatter: fmtDate,          width: 95 },
      { title: "EFR",               field: "efr",                width: 37, headerSort: false, headerTooltip: "Einführungsritt (25–40 km)",          tooltip: true },
      { title: "KDR",               field: "kdr",                width: 37, headerSort: false, headerTooltip: "Kurzdistanzritt (41–60 km)",           tooltip: true },
      { title: "MDR",               field: "mdr",                width: 37, headerSort: false, headerTooltip: "Mitteldistanzritt (61–80 km)",          tooltip: true },
      { title: "LDR",               field: "ldr",                width: 40, headerSort: false, headerTooltip: "Langdistanzritt (81–160 km)",           tooltip: true },
      { title: "MTR",               field: "mtr",                width: 40, headerSort: false, headerTooltip: "Mehrtagesritt",                         tooltip: true },
      { title: "CEI",               field: "cei",                width: 20, headerSort: false, headerTooltip: "Concours d'Endurance International",    tooltip: true },
      { title: "Ausschreibung",     field: "announcement_pdf",   formatter: fmtPdf("announcement_pdf", "announcement_updated"), sorter: false, width: 40, headerTooltip: "Ausschreibung (PDF)" },
      { title: "Ergebnisliste",     field: "results_pdf",        formatter: fmtPdf("results_pdf", null),                      sorter: false, width: 40, headerTooltip: "Ergebnisliste (PDF)" },
      { title: "Nennformular",      field: "registration_pdf",   formatter: fmtPdf("registration_pdf", null),                 sorter: false, width: 40, headerTooltip: "Nennformular (PDF)" },
      { title: "Kalender",          field: "start_date",         formatter: fmtIcs,                                           sorter: false, width: 40, headerTooltip: "Termin als ICS-Datei herunterladen", headerSort: false },
      { title: "Geändert",          field: "wiki_touched",       formatter: cell => fmtDateDe(cell.getValue()),               width: 80,     headerTooltip: "Letzte Änderung auf der VDD-Wiki-Seite" },
      { title: "Seit",              field: "first_edition_year", sorter: "number",            width: 50 },
      { title: "Website",           field: "website",            formatter: fmtLink,                                          sorter: false, width: 160 },
      { title: "Art",               field: "event_types",        width: 100, tooltip: true },
      { title: "Status",            field: "status",             formatter: fmtStatus,                                        width: 110, tooltip: true },
      { title: "Region",            field: "region",             width: 100, tooltip: true },
      { title: "Veranstaltungsort", field: "venue",              width: 150, tooltip: true },
      { title: "Veranstalter",      field: "organizer",          width: 150, tooltip: true },
    ],
    rowFormatter(row) {
      const d = row.getData();
      const el = row.getElement();
      el.classList.toggle('vorrat',      !!d.rittvorrat);
      el.classList.toggle('no-coords',   !d.lat);
      el.classList.toggle('row-active',  d.id === activeId);
      el.classList.toggle('row-abgesagt', (d.status || '').toLowerCase().includes('abgesagt'));
    },
  });

  tbl.on("tableBuilt", () => {
    applyFilters();
    requestAnimationFrame(() => { map.resize(); fitVisibleMarkers(); });
    const hash = window.location.hash.slice(1);
    if (hash) {
      const ev = EVENTS.find(e => e.id === decodeURIComponent(hash));
      if (ev) focusEvent(ev);
    }
  });

  tbl.on("rowClick",      (_e, row) => focusEvent(row.getData()));
  tbl.on("rowMouseEnter", (_e, row) => { preloadImg(row.getData()); });

  tbl.on("dataFiltered", (_filters, rows) => {
    const visibleIds = new Set(rows.map(r => r.getData().id));
    EVENTS.forEach(ev => {
      if (!markers[ev.id]) return;
      visibleIds.has(ev.id) ? markers[ev.id].addTo(map) : markers[ev.id].remove();
    });
    document.getElementById('count').textContent = `${rows.length} / ${EVENTS.length}`;
  });
}

// ── interaction ────────────────────────────────────────────────────────────
function isMobileViewport() {
  return window.matchMedia('(max-width: 860px)').matches;
}

function showModalPopup(ev) {
  const modal = document.getElementById('popup-modal');
  const title = document.getElementById('popup-modal-title');
  const body  = document.getElementById('popup-modal-body');
  title.textContent = ev.name || ev.wiki_title;
  body.innerHTML = popupBodyHtml(ev);
  const docs = popupDocsHtml(ev);
  const footer = document.getElementById('popup-modal-footer');
  footer.innerHTML = docs;
  footer.style.display = docs ? '' : 'none';
  modal.classList.add('show');
}

function clearUrlHash() {
  history.replaceState(null, '', window.location.pathname + window.location.search);
}

function hideModalPopup() {
  document.getElementById('popup-modal').classList.remove('show');
  clearUrlHash();
}

document.getElementById('popup-modal-close').addEventListener('click', hideModalPopup);

function shareCurrentUrl(feedbackEl) {
  const url = window.location.origin + window.location.pathname + window.location.hash;
  if (navigator.share) {
    navigator.share({ url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(url).then(() => {
      if (feedbackEl) {
        const orig = feedbackEl.dataset.label || feedbackEl.innerHTML;
        feedbackEl.innerHTML = feedbackEl.dataset.copied || '✓ Link kopiert';
        setTimeout(() => { feedbackEl.innerHTML = orig; }, 1500);
      }
    });
  }
}

document.getElementById('popup-modal-share').addEventListener('click', e => {
  shareCurrentUrl(e.currentTarget);
});

document.getElementById('popup-modal').addEventListener('click', e => {
  if (e.target.id === 'popup-modal') hideModalPopup();
});

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-ics-id]');
  if (btn) icsDownload(EVENTS.find(ev => ev.id === btn.dataset.icsId));
});

function highlightRow(id) {
  const prevId = activeId;
  activeId = id;
  if (prevId) { const r = tbl.getRow(prevId); if (r) r.reformat(); }
  const row = tbl.getRow(id);
  if (row) { row.reformat(); tbl.scrollToRow(id); }
}

function focusEvent(ev) {
  history.replaceState(null, '', '#' + encodeURIComponent(ev.id));
  highlightRow(ev.id);
  if (markers[ev.id]) {
    if (isMobileViewport()) {
      showModalPopup(ev);
    } else {
      requestAnimationFrame(() => {
        showEventPopup(ev);
        requestAnimationFrame(() => {
          const _mapH    = map.getContainer().clientHeight;
          const _popupEl = openPopup?.getElement();
          const _popupH  = _popupEl ? _popupEl.getBoundingClientRect().height : 250;
          const _needed  = 15 + _popupH + 38;
          const _topPad  = Math.max(15, Math.min(2 * _needed - _mapH, _mapH - 50));
          map.flyTo({ center: [ev.lon, ev.lat], zoom: map.getZoom(), padding: { top: _topPad } });
        });
      });
    }
  }
}

// ── filter bar ─────────────────────────────────────────────────────────────
function updateClearFiltersBtn() {
  const active = selectedRegion || selectedEventTypes.size || selectedDistances.size;
  document.getElementById('btn-clear-filters').style.display = active ? '' : 'none';
}

document.getElementById('region-select').addEventListener('change', e => {
  selectedRegion = e.target.value;
  updateClearFiltersBtn();
  applyFilters();
});

document.querySelectorAll('[data-dist]').forEach(btn => {
  btn.addEventListener('click', () => {
    const d = btn.dataset.dist;
    btn.classList.toggle('active');
    btn.classList.contains('active') ? selectedDistances.add(d) : selectedDistances.delete(d);
    updateClearFiltersBtn();
    applyFilters();
  });
});

document.getElementById('btn-clear-filters').addEventListener('click', () => {
  selectedRegion = ''; selectedEventTypes.clear(); selectedDistances.clear();
  document.getElementById('region-select').value = '';
  document.querySelectorAll('.tog.active').forEach(b => b.classList.remove('active'));
  updateClearFiltersBtn();
  applyFilters();
});

// ── controls ───────────────────────────────────────────────────────────────
document.getElementById('show-vorrat').addEventListener('change', e => {
  showVorrat = e.target.checked;
  applyFilters();
  if (showVorrat) {
    const modal = document.getElementById('popup-modal');
    document.getElementById('popup-modal-title').textContent = 'Hinweis: Rittvorrat';
    document.getElementById('popup-modal-body').innerHTML =
      '<p style="margin:0 0 10px;line-height:1.5">Der <strong>Rittvorrat</strong> enthält ältere Einträge, ' +
      'bei denen die aufgeführten Ritte teilweise seit <strong>Jahren nicht mehr stattgefunden</strong> haben. ' +
      'Diese Daten sind möglicherweise veraltet und spiegeln nicht den aktuellen Stand wieder.</p>' +
      '<p style="margin:0;line-height:1.5">Vermisst du einen dieser Ritte? ' +
      'Vielleicht kannst du dabei helfen, einen Ritt wieder aufleben zu lassen. ' +
      'Möglicherweise kannst du dich mit dem Veranstalter in Verbindung setzen.</p>';
    modal.classList.add('show');
  }
});

document.getElementById('show-vergangene').addEventListener('change', e => {
  showVergangene = e.target.checked;
  applyFilters();
});

const searchEl      = document.getElementById('search');
const searchClearBtn = document.getElementById('search-clear');

function syncSearchToUrl(q) {
  const url = new URL(window.location.href);
  if (q) url.searchParams.set('q', q);
  else   url.searchParams.delete('q');
  history.replaceState(null, '', url.pathname + (url.search || '') + url.hash);
}

searchEl.addEventListener('input', e => {
  filterText = e.target.value;
  searchClearBtn.style.display = filterText ? 'block' : 'none';
  if (filterText) clearRadius();
  syncSearchToUrl(filterText);
  applyFilters();
});

searchClearBtn.addEventListener('click', () => {
  searchEl.value = '';
  filterText = '';
  searchClearBtn.style.display = 'none';
  syncSearchToUrl('');
  applyFilters();
  searchEl.focus();
});

function fitVisibleMarkers() {
  const evs = EVENTS.filter(e => e.lat && e.lon);
  if (!evs.length) return;
  const lons = evs.map(e => e.lon), lats = evs.map(e => e.lat);
  map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 25 });
}

function clearRadius() {
  userLat = null; userLon = null;
  if (userMarker) { userMarker.remove(); userMarker = null; }
  removeRadiusCircle();
  const btn = document.getElementById('btn-locate');
  btn.classList.remove('active');
  btn.textContent = '📍 Standort';
  fitVisibleMarkers();
}

document.getElementById('btn-locate').addEventListener('click', () => {
  if (userLat !== null) { clearRadius(); applyFilters(); return; }
  if (!navigator.geolocation) { alert('Geolocation nicht verfügbar'); return; }
  const btn = document.getElementById('btn-locate');
  btn.textContent = '⏳ …';
  btn.disabled = true;
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude, longitude, accuracy } = pos.coords;
    userLat = latitude;
    userLon = longitude;
    filterText = '';
    document.getElementById('search').value = '';
    document.getElementById('search-clear').style.display = 'none';
    if (userMarker) { userMarker.remove(); userMarker = null; }
    removeRadiusCircle();

    const userEl = document.createElement('div');
    userEl.style.cssText = 'width:14px;height:14px;border-radius:50%;background:#2ea3f2;border:3px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5);cursor:default';
    const userPopup = new maplibregl.Popup({ offset: 7 })
      .setHTML(`Mein Standort<br><small>Genauigkeit: ±${Math.round(accuracy)} m</small>`);
    userMarker = new maplibregl.Marker({ element: userEl })
      .setLngLat([userLon, userLat])
      .setPopup(userPopup)
      .addTo(map);

    radiusKm = +document.getElementById('radius-slider').value || 250;
    showRadiusCircle(userLat, userLon, radiusKm);
    map.resize();
    map.fitBounds(radiusBounds(userLat, userLon, radiusKm), { padding: 25 });
    btn.textContent = '✕ Löschen';
    btn.disabled = false;
    btn.classList.add('active');
    applyFilters();
  }, err => {
    btn.textContent = '📍 Standort';
    btn.disabled = false;
    alert('Standort konnte nicht ermittelt werden: ' + err.message);
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
});

document.getElementById('radius-slider').addEventListener('input', e => {
  radiusKm = +e.target.value;
  document.getElementById('radius-label').textContent = radiusKm + ' km';
  if (userLat !== null) {
    showRadiusCircle(userLat, userLon, radiusKm);
    map.fitBounds(radiusBounds(userLat, userLon, radiusKm), { padding: 25 });
    applyFilters();
  }
});

// ── data caching ───────────────────────────────────────────────────────────
async function loadVddData() {
  const KEY = 'vdd_d', TS = 'vdd_t', SA = 'vdd_sa';
  const MAX_AGE = 7 * 24 * 60 * 60 * 1000;
  const now = Date.now();
  let cached = null, ts = 0, cachedScrapedAt = null;
  try {
    cached = localStorage.getItem(KEY);
    ts = parseInt(localStorage.getItem(TS) || '0', 10);
    cachedScrapedAt = localStorage.getItem(SA);
    const offline = !navigator.onLine;
    if (cached && (offline || (now - ts) < MAX_AGE)) {
      return { data: JSON.parse(cached), fromCache: true, cacheTs: ts, cachedScrapedAt };
    }
  } catch(e) {
    try { localStorage.removeItem(KEY); localStorage.removeItem(TS); localStorage.removeItem(SA); } catch(_) {}
    cached = null;
  }
  try {
    const data = await fetch('data.min.json').then(r => r.json());
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
      localStorage.setItem(TS, String(now));
      localStorage.setItem(SA, data.scraped_at || '');
    } catch(_) {}
    return { data, fromCache: false, cacheTs: now, cachedScrapedAt: data.scraped_at || null };
  } catch(fetchErr) {
    if (cached) return { data: JSON.parse(cached), fromCache: true, cacheTs: ts, cachedScrapedAt };
    throw fetchErr;
  }
}

// ── load data ──────────────────────────────────────────────────────────────
(async function () {
  const initialQ = new URL(window.location.href).searchParams.get('q');
  if (initialQ) {
    filterText = initialQ;
    searchEl.value = initialQ;
    document.getElementById('search-clear').style.display = 'block';
  }

  let _vd, fromCache, cacheTs, cachedScrapedAt;
  try {
    ({ data: _vd, fromCache, cacheTs, cachedScrapedAt } = await loadVddData());
  } catch(e) {
    document.getElementById('grid').innerHTML =
      `<p style="padding:1.5rem;color:#c00">Daten konnten nicht geladen werden.<br>${e.message}</p>`;
    console.error(e);
    return;
  }
  const { events, scraped_at } = _vd;
  EVENTS = events.map((ev, i) => {
    const strip = f => ev[f] ? String(ev[f]).replace(/\s+/g, '') : ev[f];
    return { ...ev, id: ev.id ?? ev.wiki_title ?? String(i), event_types_arr: (ev.event_types || '').split(',').map(s => s.trim()).filter(Boolean), efr: strip('efr'), kdr: strip('kdr'), mdr: strip('mdr'), ldr: strip('ldr'), mtr: strip('mtr'), cei: strip('cei') };
  });

  const lastChanged = EVENTS.filter(e => e.wiki_touched).sort((a, b) => b.wiki_touched.localeCompare(a.wiki_touched))[0];
  if (lastChanged) {
    const a = document.createElement('a');
    a.href = '#' + encodeURIComponent(lastChanged.id);
    a.textContent = lastChanged.name || lastChanged.wiki_title;
    a.addEventListener('click', e => {
      e.preventDefault();
      window.location.hash = encodeURIComponent(lastChanged.id);
      document.getElementById('info-modal').classList.remove('show');
      focusEvent(lastChanged);
    });
    const cell = document.getElementById('info-last-changed');
    cell.textContent = '';
    cell.appendChild(a);
    cell.appendChild(document.createTextNode(` (${fmtDateDe(lastChanged.wiki_touched)})`));
  }

  fetch('https://api.github.com/repos/techtimo/vdd-rittatlas/actions/workflows/update.yml/runs?per_page=1')
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      const run = d?.workflow_runs?.[0];
      if (!run) return;
      const mins = Math.round((Date.now() - new Date(run.updated_at)) / 60000);
      let ago;
      if (mins < 2)        ago = 'gerade eben';
      else if (mins < 60)  ago = `vor ${mins} Min.`;
      else if (mins < 120) ago = 'vor 1 Std.';
      else                 ago = `vor ${Math.round(mins / 60)} Std.`;
      document.getElementById('info-geprueft').textContent = ago;
      if (fromCache && new Date(run.updated_at).getTime() > cacheTs) {
        fetch('data.min.json', { cache: 'no-store' })
          .then(r => r.json())
          .then(fresh => {
            if (fresh.scraped_at === cachedScrapedAt) return;
            try {
              localStorage.setItem('vdd_d', JSON.stringify(fresh));
              localStorage.setItem('vdd_t', String(Date.now()));
              localStorage.setItem('vdd_sa', fresh.scraped_at || '');
            } catch(_) {}
          })
          .catch(() => {});
      }
    })
    .catch(() => {});

  document.getElementById('btn-info').addEventListener('click', () =>
    document.getElementById('info-modal').classList.add('show')
  );
  document.getElementById('info-modal-close').addEventListener('click', () =>
    document.getElementById('info-modal').classList.remove('show')
  );
  document.getElementById('info-modal').addEventListener('click', e => {
    if (e.target.id === 'info-modal') document.getElementById('info-modal').classList.remove('show');
  });

  // populate region dropdown
  const regionSel = document.getElementById('region-select');
  [...new Set(EVENTS.map(e => e.region).filter(Boolean))].sort().forEach(r => {
    const o = document.createElement('option'); o.value = r; o.textContent = r;
    regionSel.appendChild(o);
  });

  // populate event-type toggles
  const allTypes = new Set();
  EVENTS.forEach(e => e.event_types_arr.forEach(t => allTypes.add(t)));
  const typeRow = document.getElementById('type-toggles');
  [...allTypes].sort().forEach(type => {
    const btn = document.createElement('button');
    btn.className = 'tog'; btn.textContent = type; btn.dataset.type = type;
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
      btn.classList.contains('active') ? selectedEventTypes.add(type) : selectedEventTypes.delete(type);
      updateClearFiltersBtn();
      applyFilters();
    });
    typeRow.appendChild(btn);
  });

  EVENTS.forEach(ev => {
    if (ev.lat && ev.lon) {
      const el = makeMarkerEl(markerColor(ev));
      el.addEventListener('mouseover', () => preloadImg(ev));
      el.addEventListener('click', () => focusEvent(ev));
      markers[ev.id] = new maplibregl.Marker({ element: el, anchor: 'bottom' })
        .setLngLat([ev.lon, ev.lat]);
    }
  });

  // Yield to let the map paint before building the table.
  await new Promise(r => setTimeout(r, 0));
  initTable(EVENTS);
})();
