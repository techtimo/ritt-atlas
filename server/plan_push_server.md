# Implementierungsplan: Web-Push-Server (Go) für VDD Rittatlas

## Ziel

Ein in Go geschriebener Dienst auf **Fly.io** mit **scale-to-zero**. Er ist Subscription-Store +
Push-Versender **mit serverseitiger Filterung** nach Nutzer-Präferenzen. Die Event-Diff- und
Text-Logik liegt in der GitHub Action (`PLAN-github-action.md`); der Server bekommt fertige
Notifications **mit Zielangabe** (Kategorie + Event-ID) und entscheidet anhand der gespeicherten
Präferenzen, **welche** Subscription welche Notification erhält.

**Scope:** nur der Server. Frontend (Service Worker, Subscribe-UI, Favoriten-Auswahl) ist nicht
Teil dieses Plans; Schnittstellen sind am Ende dokumentiert.

---

## Präferenz-Modell (zentral)

Jede Subscription hat drei unabhängige Präferenzen:

- **`notify_new_events`** (Bool) — will Meldungen über **neue** Ritte.
- **`notify_all_changes`** (Bool) — will **jede** Änderung an **jedem** bestehenden Ritt
  (Favoriten dann irrelevant).
- **Favoriten** (Menge von Event-IDs) — will Änderungen **nur** an diesen Ritten.

Es gibt genau **zwei** Notification-Kategorien im Versand:
- `new_event` — ein neuer Ritt ist aufgetaucht.
- `event_change` — ein bestehender Ritt hat sich geändert (trägt die betroffene Event-ID).

### Versand-Entscheidung (pro Notification × Subscription)

```
notification.category == "new_event":
    sende an Sub, wenn  Sub.notify_new_events == true

notification.category == "event_change" (mit notification.event_id == X):
    sende an Sub, wenn  Sub.notify_all_changes == true
                    ODER X ∈ Sub.favorites
```

`notify_all_changes` ist die Obermenge: ist es gesetzt, werden Favoriten ignoriert. Ein neuer Ritt
kann nicht favorisiert sein (man kennt ihn noch nicht) → `new_event` läuft ausschließlich über
`notify_new_events`. Eine Änderung an einem Ritt, den niemand favorisiert hat und für den niemand
`notify_all_changes` gesetzt hat, geht an niemanden (gewollt).

---

## Designentscheidungen (verbindlich)

- **Sprache:** Go (1.22+).
- **Push-Library:** `github.com/SherClockHolmes/webpush-go`.
- **Persistenz:** SQLite auf Fly-Volume, Treiber `modernc.org/sqlite` (CGo-frei). **Nicht**
  `mattn/go-sqlite3`.
- **Kein Event-State im Server** (keine Snapshots). Diff passiert in der Action.
- **Keine Sammel-Notification** mehr — immer Einzel-Notifications (eine pro betroffenem Event).
- **TTL:** Default 24h (`PUSH_TTL`, Sekunden). Push-Dienste puffern offline bis max. 4 Wochen.
- **Collapse-Topic pro Event:** Server setzt den Web-Push-`Topic`-Header = `sanitize(event_id)`
  (base64url ≤32 Zeichen, deterministisch), damit offline gepufferte Updates desselben Ritts sich
  im Transit überschreiben. **Achtung Begriff:** Das ist *nicht* die Kategorie/Präferenz — nur ein
  technischer Collapse-Key.

---

## Architektur-Überblick

```
GitHub Action (stündlich)
   │  Diff alt/neu  ->  Liste Notifications, jede mit { category, event_id, title, body, url, tag }
   │  POST /notify  { "notifications":[...] }   (Header X-Notify-Token)
   ▼
Fly.io Go-Server (scale-to-zero)
   │  - lädt alle Subscriptions + deren Präferenzen + Favoriten
   │  - pro Notification: Zielmenge nach Versand-Entscheidung bestimmen
   │  - an die Zielmenge senden (TTL + Topic-Header)
   │  - tote Subs (404/410) entfernen
   ▼
Push-Dienste ──► Browser ──► Service Worker zeigt Notification

Frontend  ── POST /subscribe / POST /preferences / POST /unsubscribe ──►  Server (SQLite)
```

---

## Projektstruktur

```
push-server/
├── main.go
├── handlers.go      # /subscribe, /preferences, /unsubscribe, /notify, /health
├── store.go         # SQLite: subscriptions + subscription_favorites
├── push.go          # Versand + Cleanup + sanitizeTopic
├── target.go        # Versand-Entscheidung (welche Sub bekommt welche Notification)
├── model.go         # Structs
├── config.go
├── target_test.go   # Tests der Versand-Entscheidung (wichtig!)
├── push_test.go     # Tests sanitizeTopic / Payload / Cleanup
├── go.mod / go.sum
├── Dockerfile
├── fly.toml
└── cmd/genvapid/main.go
```

---

## Datenmodell

```go
type Subscription struct {
    Endpoint string `json:"endpoint"`
    Keys     struct {
        P256dh string `json:"p256dh"`
        Auth   string `json:"auth"`
    } `json:"keys"`
    NotifyNewEvents  bool     `json:"notify_new_events"`
    NotifyAllChanges bool     `json:"notify_all_changes"`
    Favorites        []string `json:"favorites"` // Event-IDs
}

type Notification struct {
    Category string `json:"category"`  // "new_event" | "event_change"
    EventID  string `json:"event_id"`  // betroffener Ritt; bei new_event die ID des neuen Ritts
    Title    string `json:"title"`
    Body     string `json:"body"`
    URL      string `json:"url"`
    Tag      string `json:"tag"`       // = event_id (clientseitiges Stapeln)
}

type NotifyRequest struct {
    Notifications []Notification `json:"notifications"`
}
```

> `topic` ist **kein** Feld mehr im Eingangs-Payload — der Server leitet den Collapse-Topic intern
> aus `event_id` ab (`sanitizeTopic`). Das vermeidet doppelte Sanitizing-Logik.

### SQLite-Schema

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
    endpoint           TEXT PRIMARY KEY,
    p256dh             TEXT NOT NULL,
    auth               TEXT NOT NULL,
    notify_new_events  INTEGER NOT NULL DEFAULT 0,  -- 0/1
    notify_all_changes INTEGER NOT NULL DEFAULT 0,  -- 0/1
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscription_favorites (
    endpoint  TEXT NOT NULL,
    event_id  TEXT NOT NULL,
    PRIMARY KEY (endpoint, event_id),
    FOREIGN KEY (endpoint) REFERENCES subscriptions(endpoint) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fav_event ON subscription_favorites(event_id);
```

> `PRAGMA foreign_keys = ON;` beim Öffnen setzen, damit ON DELETE CASCADE greift.

---

## HTTP-API

### `GET /health` → `200 {"status":"ok"}`. Kein Auth.

### `POST /subscribe`
Frontend ruft auf beim Aktivieren. Body = PushSubscription **plus** Präferenzen:
```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "keys": { "p256dh": "BNc...", "auth": "k9X..." },
  "notify_new_events": true,
  "notify_all_changes": false,
  "favorites": ["Frühjahrsdistanz am Meer 2026", "Herbstdistanz Eifel 2026"]
}
```
- Upsert nach `endpoint`: Subscription + Präferenzen schreiben, Favoriten-Tabelle für diesen
  Endpoint **ersetzen** (alle löschen, neue einfügen) in einer Transaktion.
- Fehlende Präferenzfelder: `notify_new_events` default `true`, `notify_all_changes` default
  `false`, `favorites` default leer.
- Antwort `201` (neu) / `200` (vorhanden). CORS für `ALLOWED_ORIGIN`, Preflight `204`.

### `POST /preferences`
Ändert Präferenzen/Favoriten einer bestehenden Subscription **ohne** Neu-Abo. Body:
```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "notify_new_events": true,
  "notify_all_changes": false,
  "favorites": ["Frühjahrsdistanz am Meer 2026"]
}
```
- Identifikation über `endpoint`. Existiert er nicht → `404`.
- Aktualisiert die drei Präferenzfelder und ersetzt die Favoritenliste (transaktional).
- `keys` sind hier **nicht** nötig (Subscription existiert schon). Antwort `200`. CORS wie oben.

> Optional, aber empfohlen: partielle Updates erlauben (nur mitgeschickte Felder ändern). Einfachste
> Variante: Client schickt immer den vollständigen Präferenz-Stand → Server überschreibt komplett.
> Im Plan: **vollständiges Überschreiben** (simpler, kein Merge-Edgecase).

### `POST /unsubscribe`
Body `{ "endpoint": "..." }`. Löscht Subscription (Favoriten via CASCADE mit). `200`. CORS.

### `POST /notify`
Von der Action. Header `X-Notify-Token` == `NOTIFY_TOKEN`, sonst `401`.
Body = `NotifyRequest`. Ablauf:
1. Token prüfen, Body parsen. Leere Liste → `200`.
2. Alle Subscriptions inkl. Präferenzen + Favoriten laden.
3. Pro Notification Zielmenge nach **Versand-Entscheidung** (siehe `target.go`) bestimmen.
4. An Zielmenge senden (Worker-Pool, begrenzte Parallelität; TTL + Topic = `sanitize(event_id)`).
5. Tote Subs (404/410) sammeln, **nach** dem Lauf löschen.
6. Antwort:
   ```json
   { "notifications": 3, "subscriptions": 12, "delivered": 18, "skipped_no_target": 1, "pruned": 0 }
   ```
- Push-Fehler ≠ Auth nur loggen.

---

## Versand-Entscheidung (`target.go`)

Reine Funktion, isoliert testbar:
```go
func shouldSend(n Notification, s Subscription) bool {
    switch n.Category {
    case "new_event":
        return s.NotifyNewEvents
    case "event_change":
        if s.NotifyAllChanges {
            return true
        }
        return contains(s.Favorites, n.EventID)
    default:
        return false // unbekannte Kategorie: nichts senden
    }
}
```

---

## Push-Versand (`push.go`)

- `webpush.SendNotification(payload, sub, opts)`. Payload = JSON `{title, body, url, tag}`.
- `opts`: VAPID-Keys, `Subscriber` (`mailto:...`), `TTL` aus Config, `Topic = sanitizeTopic(event_id)`.
- `sanitizeTopic`: SHA-256 von `event_id` → base64url → auf ≤32 Zeichen kürzen; deterministisch
  (gleiche ID ⇒ gleicher Topic über Läufe hinweg). In `push_test.go` testen.
- Cleanup: Status 404/410 → Sub löschen; andere Fehler nur loggen. Timeout 10s/Request.
- Nebenläufig mit Worker-Pool (z.B. 10), damit der Lauf kurz bleibt (scale-to-zero).

---

## Konfiguration (Env)

| Variable             | Zweck                                   | Quelle            |
|----------------------|-----------------------------------------|-------------------|
| `PORT`               | HTTP-Port (Default 8080)                | Fly               |
| `DB_PATH`            | `/data/push.db`                         | fly.toml / Volume |
| `VAPID_PUBLIC_KEY`   | öffentlicher VAPID-Key                  | Fly Secret        |
| `VAPID_PRIVATE_KEY`  | privater VAPID-Key                      | Fly Secret        |
| `VAPID_SUBSCRIBER`   | `mailto:...`                            | Fly Secret/Env    |
| `NOTIFY_TOKEN`       | Token für `/notify`                     | Fly Secret        |
| `ALLOWED_ORIGIN`     | CORS (`https://techtimo.github.io`)     | Env               |
| `PUSH_TTL`           | TTL Sekunden (Default 86400)            | Env               |

VAPID-Keys einmalig via `cmd/genvapid/main.go` oder `npx web-push generate-vapid-keys`.

---

## CORS

`/subscribe`, `/preferences`, `/unsubscribe` cross-origin → `ALLOWED_ORIGIN`,
`Allow-Methods: POST, OPTIONS`, `Allow-Headers: Content-Type`, Preflight `204`.
`/notify` server-to-server → kein CORS, nur Token.

---

## Dockerfile (CGo-frei)

```dockerfile
FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /push-server .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /push-server /push-server
EXPOSE 8080
ENTRYPOINT ["/push-server"]
```

## fly.toml (scale-to-zero + Volume)

```toml
app = "vdd-rittatlas-push"
primary_region = "fra"

[build]

[env]
  DB_PATH = "/data/push.db"
  ALLOWED_ORIGIN = "https://techtimo.github.io"
  PUSH_TTL = "86400"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

[[mounts]]
  source = "push_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

Setup: `fly launch --no-deploy`; `fly volumes create push_data --region fra --size 1`;
`fly secrets set VAPID_PUBLIC_KEY=... VAPID_PRIVATE_KEY=... VAPID_SUBSCRIBER=mailto:admin@timoe.de NOTIFY_TOKEN=...`;
`fly deploy`. **Genau eine Maschine** (Volume-Bindung).

---

## Robustheit & Edge Cases

- **Keine passende Zielmenge:** Notification, die niemand abonniert hat, wird übersprungen
  (`skipped_no_target` zählt mit). Kein Fehler.
- **`/preferences` für unbekannten Endpoint:** `404` (Client soll dann neu `/subscribe`-n).
- **Favoriten-Replace transaktional:** alte Favoriten löschen + neue einfügen in einer TX, damit
  bei Fehler kein halber Stand bleibt.
- **Doppelte `/notify`:** Server zustandslos bzgl. Events; Idempotenz liegt in der Action. Topic
  dämpft Duplikate für offline-Geräte.
- **Großer Favoriten-Index:** `idx_fav_event` macht „welche Subs haben Event X favorisiert"
  schnell; alternativ alle Subs in den Speicher laden (kleine Nutzerzahl → unkritisch).

---

## Tests

`target_test.go` (Kern!):
1. `new_event` + Sub mit `notify_new_events=true` → senden; mit `false` → nicht.
2. `event_change` X + Sub mit `notify_all_changes=true` → senden (egal ob Favorit).
3. `event_change` X + Sub mit X in Favoriten, `notify_all_changes=false` → senden.
4. `event_change` X + Sub ohne X in Favoriten, `notify_all_changes=false` → nicht senden.
5. unbekannte Kategorie → nie senden.

`push_test.go`:
6. `sanitizeTopic` deterministisch, ≤32 Zeichen, base64url, kollisionsarm.
7. Payload-Bau korrekt; leere `URL` → Fallback.
8. Cleanup: 410/404 → prune; 200/201 → behalten; 5xx → behalten.
9. `/notify` ohne/falsches Token → 401.

---

## Akzeptanzkriterien

- [ ] `CGO_ENABLED=0 go build` lauffähig.
- [ ] `/subscribe` speichert Präferenzen + Favoriten (transaktional), Defaults korrekt.
- [ ] `/preferences` überschreibt Präferenzen/Favoriten ohne Neu-Abo; unbekannt → 404.
- [ ] `/unsubscribe` löscht inkl. Favoriten (CASCADE).
- [ ] `/notify` ohne/falsches Token → 401.
- [ ] Versand-Entscheidung entspricht der Tabelle; alle `target_test.go`-Fälle grün.
- [ ] Notification ohne Zielmenge wird übersprungen, nicht gesendet.
- [ ] TTL + Topic-Header gesetzt; `sanitizeTopic` stabil ≤32 Zeichen.
- [ ] Tote Subs (404/410) entfernt.
- [ ] Fly-Deploy scale-to-zero + Volume, übersteht Stop/Start ohne Datenverlust.

---

## Schnittstellen fürs Frontend (nicht Teil dieses Plans)

- Beim Aktivieren: `POST /subscribe` mit PushSubscription + `notify_new_events`,
  `notify_all_changes`, `favorites`.
- UI „Einstellungen ändern" / Favoriten-Stern auf der Karte: `POST /preferences` mit
  vollständigem Präferenz-Stand (überschreibt). `endpoint` aus der aktiven PushSubscription holen.
- Service Worker liest `title`, `body`, `url`, `tag` aus dem Payload.
- `VAPID_PUBLIC_KEY` im Frontend hinterlegen.