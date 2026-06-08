# VDD Rittatlas

**Live: https://techtimo.github.io/vdd-rittatlas/**

![Last data update](https://img.shields.io/github/last-commit/techtimo/vdd-rittatlas?label=data+updated)

Alle Distanzritte des VDD haben einen Standort – dieses Tool zeigt sie alle auf einer Karte. Filtern nach Region, Distanz, Typ oder eigenem Standort.

## Idee

Die VDD veröffentlicht ihre Veranstaltungsdaten im öffentlichen MediaWiki auf vdd-aktuell.de. Diese Daten sind dort tabellarisch, aber nicht räumlich durchsuchbar. Der Rittatlas lädt alle Ritte, ergänzt fehlende Koordinaten über Nominatim (OpenStreetMap) und macht sie als interaktive Karte erkundbar.

## Wie es funktioniert

```
vdd_scrape.py  →  data.json + data.min.json  →  index.html
                                              →  notify_diff.py  →  Push-Server  →  Browser
```

1. **`vdd_scrape.py`** fragt die SMW-API des VDD-Wikis ab, geocodiert Orte ohne Wiki-Koordinaten und schreibt zwei Dateien: `data.json` (pretty-printed, für lesbare Git-Diffs) und `data.min.json` (minifiziert, für den Browser).
2. Beide Dateien werden im Repo gespeichert und per GitHub Actions stündlich aktualisiert.
3. **`index.html`** lädt `data.min.json` per `fetch()` und baut daraus Karte (MapLibre) und Tabelle (Tabulator).
4. **`notify_diff.py`** vergleicht alten und neuen Datenstand und schickt Web-Push-Benachrichtigungen an einen Go-Server auf Fly.io, der die Abonnenten informiert.

## Push-Benachrichtigungen

Nutzer können sich für Web-Push-Benachrichtigungen anmelden. Der Dienst unterscheidet zwei Kategorien:

- **Neue Ritte** (`new_event`) — ein bisher unbekannter Ritt taucht in den Daten auf.
- **Änderungen an Favoriten** (`event_change`) — Status, Termin, Dokumente, Ort oder Distanzen eines abonnierten Ritts haben sich geändert.

Rittvorrat-Einträge erzeugen grundsätzlich keine Benachrichtigungen.

### Architektur

```
GitHub Action (stündlich)
   │  notify_diff.py berechnet Diff (alt vs. neu)
   │  POST /notify  →  { notifications: [...] }
   ▼
Push-Server (Go, Fly.io, scale-to-zero)
   │  filtert nach Nutzer-Präferenzen (neue Ritte / alle Änderungen / Favoriten)
   │  sendet via Web Push API (VAPID)
   ▼
Browser / installierte PWA
```

Der Push-Server liegt unter [`server/`](server/) und ist ein schlanker Go-Dienst mit SQLite-Persistenz auf einem Fly-Volume.

### Secrets (GitHub Actions)

| Secret | Zweck |
| --- | --- |
| `NOTIFY_TOKEN` | Authentifiziert die Action gegenüber dem Push-Server |
| `PUSH_SERVER_URL` | URL des Fly.io-Servers, z. B. `https://vdd-rittatlas-push.fly.dev` |

### Push-Server lokal testen

```bash
cd server
go test ./...
```

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
