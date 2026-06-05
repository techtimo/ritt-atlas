# VDD Rittatlas

**Live: https://techtimo.github.io/vdd-rittatlas/**

Alle Distanzritte des VDD haben einen Standort – dieses Tool zeigt sie alle auf einer Karte. Filtern nach Region, Distanz, Typ oder eigenem Standort.

## Idee

Die VDD veröffentlicht ihre Veranstaltungsdaten im öffentlichen MediaWiki auf vdd-aktuell.de. Diese Daten sind dort tabellarisch, aber nicht räumlich durchsuchbar. Der Rittatlas lädt alle Ritte, ergänzt fehlende Koordinaten über Nominatim (OpenStreetMap) und macht sie als interaktive Karte erkundbar.

## Wie es funktioniert

```
vdd_scrape.py  →  data.js  →  index.html
```

1. **`vdd_scrape.py`** fragt die SMW-API des VDD-Wikis ab, geocodiert Orte ohne Wiki-Koordinaten und schreibt das Ergebnis als `data.js`.
2. **`data.js`** enthält alle Veranstaltungen als JSON und wird im Repo gespeichert ( per GitHub Actions stündlich aktualisiert).
3. **`index.html`** lädt `data.js` als `<script>`-Tag und baut daraus Karte (Leaflet) und Tabelle (Tabulator) – kein Build-Schritt, kein Server nötig.

## Lokal ausführen

```bash
pip install -r requirements.txt
python vdd_scrape.py   # aktualisiert data.js
# index.html direkt im Browser öffnen
```

## Datenquelle

[VDD MediaWiki](https://vdd-aktuell.de/mediawiki) – Verein Deutscher Distanzreiter und -fahrer e.V.
