# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A single-page map/table viewer for German endurance riding events (Distanzritte), scraped weekly from the VDD MediaWiki. There is no build step, no npm, no bundler. The entire frontend is one HTML file; all dependencies are loaded from CDN.

## Files

- **`index.html`** — the entire frontend: CSS, HTML, and JS in one file (~700 lines)
- **`data.js`** — generated weekly by the scraper; exports `const VDD_DATA = { scraped_at, events: [...] }`
- **`vdd_scrape.py`** — Python scraper; fetches events from the VDD MediaWiki SMW API, geocodes missing coordinates via Nominatim, writes `data.js`
- **`.github/workflows/update.yml`** — runs the scraper every Monday 05:00 UTC and commits `data.js` if changed

## Running the scraper locally

```bash
pip install requests
python vdd_scrape.py
```

The scraper makes two SMW `ask` queries (active events + Rittvorrat), then one batch `query&prop=info` call per 50 pages for `touched` timestamps, then Nominatim geocoding for any events missing wiki coordinates. It overwrites `data.js` in place.

## Viewing the app locally

Open `index.html` directly in a browser — no server needed. The page loads `data.js` as a script tag.

## Architecture

**Data flow:** `vdd_scrape.py` → `data.js` (committed to git) → `index.html` loads it as a `<script>` tag, reads `window.VDD_DATA`.

**Frontend libraries (CDN, no local copies):**

- Leaflet 1.9.4 — map with OpenStreetMap raster tiles
- Tabulator 6.3.1 — the sortable/filterable event table
- Google Fonts (Open Sans)

**Key JS globals in index.html:**

- `EVENTS` — flat array of all event objects (enriched from `VDD_DATA.events` with `id` and `event_types_arr`)
- `tbl` — the Tabulator instance (`#grid`)
- `markers` — `{ [id]: L.Marker }` map for all Leaflet markers
- `activeId` — currently highlighted event id

**Filter state** is held in module-level `let` variables (`filterText`, `userLat/userLon/radiusKm`, `selectedRegion`, `selectedEventTypes`, `selectedDistances`). All filtering goes through `applyFilters()` → `tbl.setFilter(eventVisible)`. Map markers are shown/hidden in the `dataFiltered` Tabulator event.

**Event focus** (`focusEvent`): highlights the table row, opens a Leaflet popup on desktop, or a fullscreen modal (`#popup-modal`) on mobile (≤860px breakpoint).

## data.js schema (per event)

Key fields: `id`, `wiki_title`, `vdd_url`, `name`, `subtitle`, `start_date`, `end_date`, `region`, `venue`, `lat`, `lon`, `organizer`, `event_types` (comma-separated string), `event_types_arr` (array, added at runtime), `efr/kdr/mdr/ldr/mtr/cei` (distance strings), `announcement_pdf`, `announcement_updated` (bool), `results_pdf`, `registration_pdf`, `status`, `first_edition_year`, `website`, `bemerkung` (free-text notes, ~44% of events), `ritt_bild` (photo filename, ~36% of events), `rittvorrat` (0/1), `wiki_touched` (YYYY-MM-DD of last wiki edit).

PDF and image URLs share the same base: `https://vdd-aktuell.de/mediawiki/index.php?title=Special:Redirect/file/<encoded_filename>`.

PDF links are constructed as `https://vdd-aktuell.de/mediawiki/index.php?title=Special:Redirect/file/<encoded_filename>`.

## CI

The GitHub Actions workflow commits only `data.js`. It uses `git diff --cached --quiet` to skip the commit if the scraper produced no changes.
