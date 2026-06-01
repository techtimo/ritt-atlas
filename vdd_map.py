import sqlite3
import json

DB_PATH = "vdd_events.db"
OUT_PATH = "vdd_map.html"
WIKI_FILE_BASE = "https://vdd-aktuell.de/mediawiki/index.php?title=Datei:"


def clean(text):
    if not text:
        return None
    return " · ".join(p.strip() for p in text.split("\n") if p.strip()) or None


def load_events():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT
            id, wiki_title, wiki_url, vdd_url, name, subtitle,
            start_date, end_date, multi_day,
            region, country, venue, lat, lon, geocoded,
            organizer, contact, patron,
            event_types, efr, kdr, mdr, ldr, mtr, cei,
            announcement_pdf, announcement_updated,
            results_pdf, registration_pdf,
            status, first_edition_year, website, rittvorrat
        FROM events
        ORDER BY start_date, name
    """).fetchall()
    scraped_at = con.execute("SELECT MAX(fetched_at) FROM events").fetchone()[0] or ""
    con.close()

    events = []
    for r in rows:
        e = dict(r)
        e["venue"]     = clean(e["venue"])
        e["organizer"] = clean(e["organizer"])
        e["contact"]   = clean(e["contact"])
        events.append(e)
    return events, scraped_at


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VDD Distanzwettbewerbe Inland 2026</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; font-family: system-ui, sans-serif; font-size: 13px; color: #222; background: #f5f5f5; }

/* ── top bar ── */
#header { background: #9D3230; color: #fff; padding: 10px 14px; flex-shrink: 0; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
#header h1 { font-size: 16px; font-weight: 600; }
#scraped-at { font-size: 11px; opacity: .7; }
#vorrat-toggle { font-size: 12px; margin-left: auto; display: flex; align-items: center; gap: 5px; cursor: pointer; user-select: none; white-space: nowrap; }
#vorrat-toggle input { cursor: pointer; width: 14px; height: 14px; accent-color: #ffcdd2; }

/* ── main split ── */
#app { display: flex; flex-direction: column; height: 100vh; }
#split { display: flex; flex: 1; overflow: hidden; }

/* left pane: table */
#left-pane {
    display: flex; flex-direction: column;
    width: 58%; border-right: 2px solid #ccc;
    overflow: hidden;
}

/* right pane: map */
#right-pane { flex: 1; position: relative; }
#map { position: absolute; inset: 0; }

/* ── search bar ── */
#controls {
    display: flex; gap: 8px; align-items: center;
    padding: 7px 10px; background: #fff;
    border-bottom: 1px solid #ddd; flex-shrink: 0;
}
#search { flex: 1; padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
#count  { font-size: 11px; color: #666; white-space: nowrap; }

/* ── table ── */
#table-scroll { overflow: auto; flex: 1; }
table { border-collapse: collapse; background: #fff; }

thead th {
    position: sticky; top: 0; z-index: 2;
    background: #eaeaea; border-bottom: 2px solid #bbb;
    padding: 6px 7px; text-align: left; font-size: 11px; font-weight: 600;
    cursor: pointer; user-select: none; white-space: nowrap;
}
thead th:first-child { left: 0; z-index: 3; }
thead th:hover { background: #ddd; }
thead th.sorted-asc::after  { content: " \25b2"; }
thead th.sorted-desc::after { content: " \25bc"; }

tbody tr { border-bottom: 1px solid #eee; cursor: pointer; }
tbody tr:hover         { background: #fff8e1; }
tbody tr.active        { background: #ffe082; }
tbody tr.no-coords     { opacity: .6; }
tbody tr.vorrat        { background: #ffebee; }
tbody tr.vorrat:hover  { background: #ffcdd2; }
tbody tr.vorrat.active { background: #ffe082; }
td { padding: 5px 7px; vertical-align: top; font-size: 12px; }
td.date  { white-space: nowrap; }
td.dist  { font-size: 11px; white-space: nowrap; color: #444; }
td.trunc { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* sticky name column */
td:first-child, th:first-child { position: sticky; left: 0; }
td:first-child {
    background: #fff;
    box-shadow: 2px 0 4px -2px rgba(0,0,0,.15);
    white-space: nowrap;
}
tbody tr:hover         td:first-child { background: #fff8e1; }
tbody tr.active        td:first-child { background: #ffe082; }
tbody tr.no-coords     td:first-child { background: #fafafa; }
tbody tr.vorrat        td:first-child { background: #ffebee; }
tbody tr.vorrat:hover  td:first-child { background: #ffcdd2; }
tbody tr.vorrat.active td:first-child { background: #ffe082; }
.tbl-doc {
    display: inline-block; padding: 2px 6px; background: #1565c0; color: #fff;
    border-radius: 3px; font-size: 10px; text-decoration: none; white-space: nowrap;
}
.tbl-doc:hover { background: #0d47a1; }
.tbl-doc.updated::after { content: " *"; }

.status-fest  { color: #2e7d32; font-weight: 600; }
.status-vorl  { color: #e65100; }
.status-abges { color: #b71c1c; text-decoration: line-through; }

.no-map-badge {
    font-size: 10px; padding: 1px 4px; background: #eee;
    border-radius: 3px; color: #888; margin-left: 4px;
}

/* ── popup ── */
.popup-name  { font-weight: 700; font-size: 14px; margin-bottom: 5px; }
.popup-row   { margin: 2px 0; font-size: 12px; }
.popup-label { color: #777; }
.popup-docs  { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; }
.popup-doc   {
    display: inline-block; padding: 3px 8px;
    background: #1565c0; color: #fff !important; border-radius: 3px;
    font-size: 11px; text-decoration: none !important; font-weight: 600;
}
.popup-doc:hover { background: #0d47a1; color: #fff !important; }
.popup-doc.updated::after { content: " \2605"; opacity: .9; }
.popup-link  { display: inline-block; margin-top: 8px; font-size: 11px; color: #1565c0; }

/* ── location / radius ── */
#loc-controls { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
#btn-locate {
  padding: 4px 9px; border: 1px solid #bbb; border-radius: 4px;
  background: #fff; font-size: 12px; cursor: pointer; white-space: nowrap; line-height: 1.4;
}
#btn-locate:hover { background: #e8f0fe; }
#btn-locate.active { background: #1565c0; color: #fff; border-color: #1565c0; }
#radius-input {
  width: 62px; padding: 4px 6px; border: 1px solid #ccc;
  border-radius: 4px; font-size: 13px; text-align: right;
}
#radius-label { font-size: 12px; color: #555; white-space: nowrap; }
#btn-clear-loc {
  padding: 2px 7px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; font-size: 11px; cursor: pointer; color: #666;
  display: none; line-height: 1.6;
}
#btn-clear-loc:hover { background: #fee; color: #c00; border-color: #fcc; }
</style>
</head>
<body>

<div id="app">
  <div id="header">
    <h1>VDD Distanzwettbewerbe Inland 2026</h1>
    <span id="scraped-at"></span>
    <label id="vorrat-toggle">
      <input type="checkbox" id="show-vorrat"> Rittvorrat anzeigen
    </label>
  </div>

  <div id="split">
    <!-- left: table -->
    <div id="left-pane">
      <div id="controls">
        <input id="search" type="search" placeholder="Suchen (Name, Region, Ort …)">
        <div id="loc-controls">
          <button id="btn-locate">&#x1F4CD; Standort</button>
          <input id="radius-input" type="number" min="10" max="3000" value="300">
          <span id="radius-label">km Radius</span>
          <button id="btn-clear-loc">&#x2715;</button>
        </div>
        <span id="count"></span>
      </div>
      <div id="table-scroll">
        <table id="evt-table">
          <thead>
            <tr>
              <th data-col="name">Name</th>
              <th data-col="start_date">Datum</th>
              <th data-col="region">Region</th>
              <th data-col="venue">Veranstaltungsort</th>
              <th data-col="organizer">Veranstalter</th>
              <th data-col="event_types">Art</th>
              <th data-col="efr">EFR</th>
              <th data-col="kdr">KDR</th>
              <th data-col="mdr">MDR</th>
              <th data-col="ldr">LDR</th>
              <th data-col="mtr">MTR</th>
              <th data-col="cei">CEI</th>
              <th data-col="status">Status</th>
              <th data-col="first_edition_year">Seit</th>
              <th data-col="announcement_pdf">Ausschreibung</th>
              <th data-col="results_pdf">Ergebnisliste</th>
              <th data-col="registration_pdf">Nennformular</th>
              <th data-col="website">Website</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- right: map -->
    <div id="right-pane">
      <div id="map"></div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const EVENTS = JSON_DATA_PLACEHOLDER;
const SCRAPED_AT = "SCRAPED_AT_PLACEHOLDER";
const WIKI_FILE = "https://vdd-aktuell.de/mediawiki/index.php?title=Datei:";

document.getElementById('scraped-at').textContent = 'Stand: ' + SCRAPED_AT.slice(0, 16);

let showVorrat = false;

// ── map ────────────────────────────────────────────────────────────────────
const map = L.map('map').setView([51.2, 10.4], 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
  maxZoom: 18
}).addTo(map);

function markerColor(ev) {
  if (ev.rittvorrat) return '#c62828';
  const s = (ev.status || '').toLowerCase();
  if (s.includes('abgesagt')) return '#f9a825';
  if (s.includes('vorl'))    return '#e65100';
  return '#2e7d32';
}

function makeIcon(color) {
  return L.divIcon({
    className: '',
    html: `<svg width="22" height="33" viewBox="0 0 24 36" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 9 12 24 12 24s12-15 12-24C24 5.37 18.63 0 12 0z"
            fill="${color}" stroke="#fff" stroke-width="1.5"/>
      <circle cx="12" cy="12" r="4.5" fill="#fff" opacity=".85"/>
    </svg>`,
    iconSize: [22, 33], iconAnchor: [11, 33], popupAnchor: [0, -33]
  });
}

const markers = {}, rowEls = {};

function dateRange(ev) {
  if (!ev.start_date) return '–';
  if (!ev.end_date || ev.start_date === ev.end_date) return ev.start_date;
  return ev.start_date + ' – ' + ev.end_date;
}

function pdfLink(filename, label, updated) {
  if (!filename) return '';
  const url = WIKI_FILE + encodeURIComponent(filename);
  const cls = updated ? 'popup-doc updated' : 'popup-doc';
  return `<a class="${cls}" href="${url}" target="_blank">${label}</a>`;
}

function popupHtml(ev) {
  const distParts = [
    ev.efr && `EFR ${ev.efr}`, ev.kdr && `KDR ${ev.kdr}`,
    ev.mdr && `MDR ${ev.mdr}`, ev.ldr && `LDR ${ev.ldr}`,
    ev.mtr && `MTR ${ev.mtr}`, ev.cei && `CEI ${ev.cei}`,
  ].filter(Boolean).join(' | ');

  let h = `<div class="popup-name">${ev.name || ev.wiki_title}`;
  if (ev.subtitle) h += ` <small style="font-weight:400">${ev.subtitle}</small>`;
  h += `</div>`;

  const rows = [
    ['Datum',        dateRange(ev)],
    ['Region',       ev.region],
    ['Ort',          ev.venue],
    ['Veranstalter', ev.organizer],
    ['Art',          ev.event_types],
    ['Distanzen',    distParts],
    ['Status',       ev.status],
    ['Seit',         ev.first_edition_year],
  ];
  for (const [label, val] of rows) {
    if (val) h += `<div class="popup-row"><span class="popup-label">${label}: </span>${val}</div>`;
  }

  const docs = [
    pdfLink(ev.announcement_pdf, 'Ausschreibung', ev.announcement_updated),
    pdfLink(ev.results_pdf,      'Ergebnisliste', false),
    pdfLink(ev.registration_pdf, 'Nennformular',  false),
  ].filter(Boolean).join('');

  if (docs) h += `<div class="popup-docs">${docs}</div>`;

  if (ev.website) h += `<div class="popup-row" style="margin-top:4px"><a href="${ev.website}" target="_blank">Website</a></div>`;
  const link = ev.vdd_url || ev.wiki_url;
  if (link) h += `<a class="popup-link" href="${link}" target="_blank">VDD-Seite &rarr;</a>`;

  return h;
}

EVENTS.forEach(ev => {
  if (ev.lat && ev.lon) {
    const m = L.marker([ev.lat, ev.lon], { icon: makeIcon(markerColor(ev)) })
      .bindPopup(popupHtml(ev), { maxWidth: 340 })
      .addTo(map);
    m.on('click', () => highlightRow(ev.id));
    markers[ev.id] = m;
  }
});

// ── table ──────────────────────────────────────────────────────────────────
let sortCol = 'start_date', sortDir = 1;
let filterText = '';
let userLat = null, userLon = null;
let radiusKm = 300;
let userMarker = null, radiusCircle = null;

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

function eventVisible(ev) {
  if (ev.rittvorrat && !showVorrat) return false;
  if (filterText) {
    const q = filterText.toLowerCase();
    return [ev.wiki_title, ev.name, ev.subtitle, ev.region, ev.venue,
            ev.event_types, ev.organizer, ev.status]
      .some(v => v && v.toLowerCase().includes(q));
  }
  if (userLat !== null) {
    if (!ev.lat || !ev.lon) return false;
    return haversineKm(userLat, userLon, ev.lat, ev.lon) <= radiusKm;
  }
  return true;
}

function syncAllMarkers() {
  EVENTS.forEach(ev => {
    if (!markers[ev.id]) return;
    eventVisible(ev) ? markers[ev.id].addTo(map) : markers[ev.id].remove();
  });
}

function applyAll() {
  syncAllMarkers();
  renderTable();
}

function statusClass(s) {
  if (!s) return '';
  const l = s.toLowerCase();
  if (l.includes('abgesagt')) return 'status-abges';
  if (l.includes('vorl'))    return 'status-vorl';
  return 'status-fest';
}

function renderTable() {
  const filtered = EVENTS.filter(eventVisible).sort((a, b) => {
    const av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
    return av < bv ? -sortDir : av > bv ? sortDir : 0;
  });

  document.getElementById('count').textContent =
    `${filtered.length} / ${EVENTS.length}`;

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  Object.keys(rowEls).forEach(k => delete rowEls[k]);

  filtered.forEach(ev => {
    const tr = document.createElement('tr');
    if (!ev.lat)       tr.classList.add('no-coords');
    if (ev.rittvorrat) tr.classList.add('vorrat');

    const link = ev.vdd_url || ev.wiki_url;
    const nameHtml = link
      ? `<a href="${link}" target="_blank" onclick="event.stopPropagation()">${ev.name || ev.wiki_title}</a>`
      : (ev.name || ev.wiki_title);

    const docCell = (pdf, updated) => pdf
      ? `<a class="tbl-doc${updated ? ' updated' : ''}" href="${WIKI_FILE}${encodeURIComponent(pdf)}" target="_blank" onclick="event.stopPropagation()">PDF</a>`
      : '';

    tr.innerHTML = `
      <td>${nameHtml}${!ev.lat ? '<span class="no-map-badge">kein GPS</span>' : ''}</td>
      <td class="date">${dateRange(ev)}</td>
      <td>${ev.region || '–'}</td>
      <td class="trunc" title="${ev.venue || ''}">${ev.venue || '–'}</td>
      <td class="trunc" title="${ev.organizer || ''}">${ev.organizer || '–'}</td>
      <td class="trunc">${ev.event_types || '–'}</td>
      <td class="dist">${ev.efr || ''}</td>
      <td class="dist">${ev.kdr || ''}</td>
      <td class="dist">${ev.mdr || ''}</td>
      <td class="dist">${ev.ldr || ''}</td>
      <td class="dist">${ev.mtr || ''}</td>
      <td class="dist">${ev.cei || ''}</td>
      <td class="${statusClass(ev.status)}">${ev.status || '–'}</td>
      <td class="dist">${ev.first_edition_year || ''}</td>
      <td>${docCell(ev.announcement_pdf, ev.announcement_updated)}</td>
      <td>${docCell(ev.results_pdf, false)}</td>
      <td>${docCell(ev.registration_pdf, false)}</td>
      <td>${ev.website ? `<a href="${ev.website}" target="_blank" onclick="event.stopPropagation()">Link</a>` : ''}</td>
    `;
    tr.addEventListener('click', () => focusEvent(ev));
    tbody.appendChild(tr);
    rowEls[ev.id] = tr;
  });

  if (activeId && rowEls[activeId]) rowEls[activeId].classList.add('active');
}

// ── interaction ────────────────────────────────────────────────────────────
let activeId = null;

function highlightRow(id) {
  if (activeId && rowEls[activeId]) rowEls[activeId].classList.remove('active');
  activeId = id;
  if (rowEls[id]) {
    rowEls[id].classList.add('active');
    rowEls[id].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

function focusEvent(ev) {
  highlightRow(ev.id);
  if (markers[ev.id]) {
    map.setView([ev.lat, ev.lon], Math.max(map.getZoom(), 10), { animate: true });
    markers[ev.id].openPopup();
  }
}

// ── sort ───────────────────────────────────────────────────────────────────
document.querySelectorAll('thead th').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    sortDir = sortCol === col ? -sortDir : 1;
    sortCol = col;
    document.querySelectorAll('thead th').forEach(h =>
      h.classList.remove('sorted-asc', 'sorted-desc'));
    th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
    renderTable();
  });
});

// ── Rittvorrat toggle ──────────────────────────────────────────────────────
document.getElementById('show-vorrat').addEventListener('change', e => {
  showVorrat = e.target.checked;
  applyAll();
});

// ── search ─────────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  filterText = e.target.value;
  if (filterText) clearRadius();
  applyAll();
});

// ── location & radius ──────────────────────────────────────────────────────
function clearRadius() {
  userLat = null; userLon = null;
  if (userMarker)   { userMarker.remove();   userMarker = null; }
  if (radiusCircle) { radiusCircle.remove(); radiusCircle = null; }
  document.getElementById('btn-locate').classList.remove('active');
  document.getElementById('btn-clear-loc').style.display = 'none';
}

document.getElementById('btn-locate').addEventListener('click', () => {
  if (!navigator.geolocation) { alert('Geolocation nicht verfügbar'); return; }
  navigator.geolocation.getCurrentPosition(pos => {
    userLat = pos.coords.latitude;
    userLon = pos.coords.longitude;
    filterText = '';
    document.getElementById('search').value = '';

    if (userMarker)   { userMarker.remove();   userMarker = null; }
    if (radiusCircle) { radiusCircle.remove(); radiusCircle = null; }

    userMarker = L.marker([userLat, userLon], {
      icon: L.divIcon({
        className: '',
        html: '<div style="width:14px;height:14px;border-radius:50%;background:#1565c0;border:3px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5)"></div>',
        iconSize: [14, 14], iconAnchor: [7, 7]
      }),
      zIndexOffset: 1000
    }).addTo(map).bindPopup('Mein Standort');

    radiusKm = Math.max(10, +document.getElementById('radius-input').value || 300);
    radiusCircle = L.circle([userLat, userLon], {
      radius: radiusKm * 1000,
      color: '#1565c0', weight: 2,
      fillColor: '#1565c0', fillOpacity: 0.07
    }).addTo(map);

    map.fitBounds(radiusCircle.getBounds());
    document.getElementById('btn-locate').classList.add('active');
    document.getElementById('btn-clear-loc').style.display = '';

    applyAll();
  }, () => alert('Standort konnte nicht ermittelt werden.'));
});

document.getElementById('radius-input').addEventListener('input', e => {
  radiusKm = Math.max(10, +e.target.value || 300);
  if (radiusCircle) {
    radiusCircle.setRadius(radiusKm * 1000);
    if (userLat !== null) map.fitBounds(radiusCircle.getBounds());
    applyAll();
  }
});

document.getElementById('btn-clear-loc').addEventListener('click', () => {
  clearRadius();
  applyAll();
});

applyAll();
</script>
</body>
</html>
"""


def main():
    events, scraped_at = load_events()
    html = HTML_TEMPLATE \
        .replace("JSON_DATA_PLACEHOLDER", json.dumps(events, ensure_ascii=False)) \
        .replace("SCRAPED_AT_PLACEHOLDER", scraped_at)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    active = sum(1 for e in events if not e["rittvorrat"])
    vorrat = sum(1 for e in events if e["rittvorrat"])
    pins   = sum(1 for e in events if e["lat"])
    print(f"Generated {OUT_PATH}: {active} active + {vorrat} Rittvorrat = {len(events)} events ({pins} with pins)")


if __name__ == "__main__":
    main()
