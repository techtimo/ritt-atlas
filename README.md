# VDD Rittatlas

**Live: https://techtimo.github.io/vdd-rittatlas/**

![Last data update](https://img.shields.io/github/last-commit/techtimo/vdd-rittatlas?label=data+updated)

Alle Distanzritte des VDD haben einen Standort – dieses Tool zeigt sie alle auf einer Karte. Filtern nach Region, Distanz, Typ oder eigenem Standort.

## Idee

Die VDD veröffentlicht ihre Veranstaltungsdaten im öffentlichen MediaWiki auf vdd-aktuell.de. Diese Daten sind dort tabellarisch, aber nicht räumlich durchsuchbar. Der Rittatlas lädt alle Ritte, ergänzt fehlende Koordinaten über Nominatim (OpenStreetMap) und macht sie als interaktive Karte erkundbar.

## Wie es funktioniert

```
vdd_scrape.py  →  data.json + data.min.json  →  index.html
```

1. **`vdd_scrape.py`** fragt die SMW-API des VDD-Wikis ab, geocodiert Orte ohne Wiki-Koordinaten und schreibt zwei Dateien: `data.json` (pretty-printed, für lesbare Git-Diffs) und `data.min.json` (minifiziert, für den Browser).
2. Beide Dateien werden im Repo gespeichert und per GitHub Actions stündlich aktualisiert.
3. **`index.html`** lädt `data.min.json` per `fetch()` und baut daraus Karte (MapLibre) und Tabelle (Tabulator).

## Lokal ausführen

```bash
pip install -r requirements.txt
python vdd_scrape.py   # aktualisiert data.json und data.min.json

npx serve .            # lokaler HTTP-Server (fetch() benötigt HTTP, nicht file://)
```

Dann [http://localhost:3000](http://localhost:3000) im Browser öffnen.

Mit `Ctrl+C` im Terminal beenden.

## Datenquelle

[VDD MediaWiki](https://vdd-aktuell.de/mediawiki) – Verein Deutscher Distanzreiter und -fahrer e.V.
