Claude finished the response

wie kann eine websiete eien benachrichtigung senden? passiert das immer vom server aus? oder kann z.b. eine statische websiete im hintergrund neue Infos vom server abfragen und wenn es neue Infos gibt diese dann per benachrichtigung teilen?
11:18

Kurz: Beides geht. Benachrichtigungen kommen nicht zwingend vom Server.

Zwei grundsätzliche Wege

Eine echte Push-Benachrichtigung (Web Push, erscheint auch wenn der Tab/Browser zu ist) läuft über einen Service Worker und einen Push-Dienst (FCM bei Chrome, Mozilla bei Firefox usw.). Hier muss der Server aktiv etwas an den Push-Dienst schicken – das ist serverinitiiert.

Eine "lokale" Notification, die der JavaScript-Code im Tab selbst auslöst (new Notification(...)), funktioniert ohne Server-Push. Hier kann eine auch rein statisch gehostete Seite selbst im Hintergrund pollen und bei neuen Infos eine Benachrichtigung anzeigen.

Dein Szenario (statische Seite fragt selbst ab)

Ja, das geht – mit Einschränkungen:

    Solange der Tab offen ist, kann JS per setInterval + fetch() regelmäßig einen Endpoint abfragen und bei Änderungen new Notification() aufrufen. Reicht für „Seite ist offen, melde mir Neues".
    Ein Service Worker kann das auch bei geschlossenem Tab versuchen, aber Periodic Background Sync ist nur in Chromium, an strenge Bedingungen geknüpft (installierte PWA, „Site Engagement"), und das Intervall bestimmt der Browser, nicht du. Unzuverlässig.
    Für echtes „Browser/Tab zu, trotzdem zuverlässig benachrichtigt" führt kein Weg an Web Push vorbei – und dafür brauchst du einen Server, der die Push-Nachricht absetzt (VAPID-Keys, Push-Dienst). „Statisch" reicht dann nicht mehr.

Voraussetzungen in jedem Fall

    HTTPS (außer localhost)
    Nutzer muss die Berechtigung erteilen (Notification.requestPermission())
    iOS/Safari: Web Push nur, wenn die Seite als PWA zum Homescreen hinzugefügt wurde

Fazit: Polling + lokale Notification von einer statischen Seite ist machbar, funktioniert aber nur zuverlässig bei offenem Tab. Sobald es „auch wenn alles zu ist" sein soll, brauchst du serverseitiges Web Push.

Soll ich dir ein minimales Code-Beispiel für die Polling-Variante zeigen?

ich habe diese komplett statische webseite github.com/techtimo/vdd-rittatlas 
und will dass wenn data.min.json aktualisert wurde eine benachrichtigung kommt
11:20
Fetched: GitHub - techtimo/vdd-rittatlas: VDD Distanzreiten – interaktive Wettbewerbskarte

Ok, dein Setup: statische Seite auf GitHub Pages, data.min.json wird stündlich per GitHub Actions aktualisiert, index.html lädt es per fetch(). MapLibre + Tabulator.

Für „Benachrichtigung wenn data.min.json aktualisiert wurde" hast du zwei realistische Optionen.

Option A — Polling + lokale Notification (passt zu deinem statischen Setup)

Die Seite fragt regelmäßig, ob sich die Datei geändert hat, und zeigt bei Änderung new Notification(). Funktioniert nur solange ein Tab offen ist (oder als installierte PWA, eingeschränkt). Kein Server nötig.

Statt die ganze JSON neu zu laden, fragst du nur den ETag/Last-Modified-Header per HEAD ab – GitHub Pages liefert beides. Das ist sparsam:
js

let lastEtag = null;

async function checkForUpdate() {
  try {
    const res = await fetch('data.min.json', { method: 'HEAD', cache: 'no-store' });
    const etag = res.headers.get('ETag') || res.headers.get('Last-Modified');
    if (lastEtag && etag && etag !== lastEtag) {
      notifyUpdate();
      // optional: Daten neu laden und Karte/Tabelle aktualisieren
    }
    lastEtag = etag;
  } catch (e) {
    console.warn('Update-Check fehlgeschlagen', e);
  }
}

function notifyUpdate() {
  if (Notification.permission === 'granted') {
    new Notification('VDD Rittatlas', {
      body: 'Neue Ritt-Daten verfügbar.',
      icon: 'favicon.svg',
    });
  }
}

// Berechtigung einmal anfragen (am besten nach Klick, nicht beim Laden)
document.getElementById('notify-btn')?.addEventListener('click', async () => {
  const perm = await Notification.requestPermission();
  if (perm === 'granted') {
    setInterval(checkForUpdate, 5 * 60 * 1000); // alle 5 Min
    checkForUpdate();
  }
});

Ein paar Hinweise: GitHub Pages liefert für statische Dateien einen stabilen ETag, der sich bei Inhaltsänderung ändert – ideal für diesen Zweck. HEAD mit cache: 'no-store' verhindert, dass der Browser-Cache dir einen alten Stand vortäuscht. Browser drosseln setInterval in Hintergrund-Tabs, deshalb ist 5 Min eher eine Untergrenze.

Da deine Daten ohnehin nur stündlich aktualisiert werden, reicht ein Intervall von z.B. 15–30 Min völlig.

Option B — Echtes Web Push (auch bei geschlossenem Tab)

Damit eine Benachrichtigung kommt, wenn der Tab/Browser zu ist, brauchst du Web Push mit Service Worker + einen Dienst, der den Push absetzt. „Statisch" reicht dann nicht mehr — aber du musst keinen eigenen Server betreiben:

    Du könntest deinen bestehenden stündlichen GitHub-Actions-Lauf erweitern: wenn sich data.min.json geändert hat, schickt der Workflow einen Web-Push an abonnierte Clients (VAPID-Keys + Push-Endpoint, z.B. via einer kleinen Function bei Cloudflare/Netlify oder einem Push-Dienst).
    Die Subscriptions müssten irgendwo gespeichert werden – das ist der Teil, der dein „komplett statisch" bricht.

Empfehlung für dich: Option A. Sie passt zu GitHub Pages ohne Backend, und „benachrichtige mich über neue Ritte, während ich die Karte offen habe" ist für so ein Tool meist genau richtig. Den ETag-Check kannst du direkt mit deinem bestehenden fetch()-Reload-Mechanismus koppeln, sodass Karte und Tabelle sich bei Änderung gleich mit aktualisieren.

Willst du, dass ich dir das als fertigen Patch für deine app.js mit Button-UI und Auto-Reload der MapLibre-Daten baue?

wie sehe Option B aus? ich kann z.b. einen server kostenlos bei fly.io hosten der nur ausgeführt wird wenn die github action läuft die die daten aktualisiert.
was brauceh ich ausßerdem?
11:26

Gute Idee — Fly.io passt da gut rein. Lass mich die komplette Architektur durchgehen und was du brauchst.
Was Web Push grundsätzlich braucht

Web Push besteht immer aus diesen Teilen:

    Service Worker auf der statischen Seite — empfängt Push-Events auch bei geschlossenem Tab und zeigt die Notification.
    VAPID-Keypair — ein Public/Private-Key-Paar, das dich als Absender identifiziert. Public Key liegt im Frontend, Private Key beim Sender (Fly.io). Einmal generieren, dann fix.
    Subscriptions speichern — wenn ein Nutzer „Ja, benachrichtige mich" klickt, erzeugt der Browser ein Subscription-Objekt (eine URL beim Push-Dienst von Google/Mozilla + Keys). Das musst du irgendwo persistent ablegen.
    Push-Sender — der Code, der beim Daten-Update an alle gespeicherten Subscriptions einen Push schickt. Das ist dein Fly.io-Dienst.

Der Knackpunkt für „komplett statisch": Schritt 3. Subscriptions müssen irgendwo liegen, und das Frontend allein kann das nicht. Genau das löst dein Fly.io-Server.
Das „nur wenn die Action läuft"-Problem

Hier ist eine Spannung in deinem Plan. Dein Fly.io-Dienst hat zwei Aufgaben mit unterschiedlichen Anforderungen:

    Push senden (1×/Stunde, getriggert von der Action) — kann tatsächlich „nur dann laufen".
    Subscriptions entgegennehmen (jederzeit, wenn ein Nutzer den Button klickt) — muss eigentlich immer erreichbar sein.

Wenn der Server nur während der Action läuft, kann sich niemand anmelden, während er aus ist. Es gibt zwei saubere Wege:

Variante 1 — Fly.io „scale to zero", immer erreichbar bei Bedarf Fly.io kann Maschinen automatisch stoppen wenn kein Traffic kommt und bei der nächsten Anfrage in ~1 Sek wieder starten (auto_stop_machines/auto_start_machines). Du zahlst praktisch nur für die Sekunden, in denen wirklich was passiert. Damit ist der Server formal „aus", aber für Subscriptions und Push jederzeit verfügbar. Das ist meist die beste Lösung — du musst nichts manuell starten/stoppen.

Variante 2 — Subscriptions woanders speichern, Server wirklich nur für Push Subscriptions landen z.B. in einem externen Storage (Fly's eigenes Volume, oder ein kleiner KV-Dienst). Der Fly-Server wird nur von der Action gestartet, liest die Subscriptions, schickt Push, fährt runter. Aber: das Subscription-Speichern braucht trotzdem einen erreichbaren Endpoint — du verlagerst das Problem nur. Komplizierter als Variante 1.

Ich würde Variante 1 nehmen. Scale-to-zero ist genau das, was du willst.
Konkrete Teile, die du brauchst

Server (Fly.io), z.B. Node + web-push-Library:

    Endpoint POST /subscribe — speichert ein Subscription-Objekt.
    Endpoint POST /notify — von der GitHub Action aufgerufen, schickt Push an alle Subscriptions. Mit einem Secret-Token geschützt, damit nicht jeder Pushes auslösen kann.
    Persistenz: ein Fly Volume mit einer simplen Datei oder SQLite reicht für ein Hobby-Projekt völlig. Subscriptions sind nur ein paar KB pro Nutzer.
    Beim Push: tote Subscriptions (HTTP 410/404 vom Push-Dienst) wegräumen.

Frontend (deine statische Seite):

    sw.js (Service Worker) mit push- und notificationclick-Handler.
    Button „Benachrichtigungen aktivieren" → Notification.requestPermission() → serviceWorker.register() → pushManager.subscribe({ applicationServerKey: VAPID_PUBLIC }) → das Ergebnis an POST /subscribe schicken.

GitHub Action (Erweiterung deines bestehenden Workflows):

    Nach dem Commit von data.min.json: prüfen ob sich die Datei geändert hat (z.B. git diff), und wenn ja curl -X POST https://dein-app.fly.dev/notify mit dem Secret-Header.

Secrets:

    VAPID Private Key → als Fly Secret (fly secrets set).
    VAPID Public Key → im Frontend (darf öffentlich sein).
    Ein Notify-Token → als Fly Secret und als GitHub Actions Secret.

iOS-Einschränkung

Web Push auf iPhone/iPad funktioniert nur, wenn der Nutzer die Seite als PWA zum Homescreen hinzufügt (Safari, ab iOS 16.4). Dafür brauchst du ein Web App Manifest. Auf Android/Desktop läuft es direkt im Browser.
Aufwandseinschätzung

Realistisch ein überschaubares Projekt: ~100–150 Zeilen Server, ~50 Zeilen Frontend, paar Zeilen Workflow. Die Fly-Konfiguration mit scale-to-zero ist Standard. Laufkosten praktisch null bei deinem Traffic.

Soll ich dir das komplett ausbauen — also Node-Server mit web-push + fly.toml mit scale-to-zero, den Service Worker, das Frontend-Snippet und den Action-Step? Sag mir nur, ob der Server Node oder lieber Python sein soll (du nutzt beides im Repo), dann baue ich dir das passende Set an Dateien.

tatsächlich würde ich das gerne in Go haben. Kannst du einen markdown plan erstellen dass ich den einem lokalen agent geben kann?
Hier geht es nur um die server variante.

Ein event aus data.json hat folgende Struktur:
{
      "id": "Frühjahrsdistanz am Meer 2026",
      "wiki_title": "Frühjahrsdistanz am Meer 2026",
      "wiki_url": "https://vdd-aktuell.de/mediawiki/index.php?title=Fr%C3%BChjahrsdistanz_am_Meer_2026",
      "vdd_url": "https://vdd-aktuell.de/ritt/Fruehjahrsdistanz-am-Meer-2026/",
      "name": "Frühjahrsdistanz am Meer",
      "subtitle": null,
      "start_date": "2026-02-21",
      "end_date": null,
      "multi_day": 0,
      "region": "Weser-Ems",
      "country": "Deutschland",
      "venue": "Jade-Rennbahn\n\nAn der Rennbahn 1\n\n26434 Wanderland\n\nDeutschland",
      "lat": 53.6443972222,
      "lon": 7.99672222222,
      "organizer": "Lisa Falk\n\nWassener Straße 10\n\n26434 Wangerland\n\nDeutschland\n\nMobil: 0175 8295439\n\nE-Mail: Lisa.Falk@yahoo.de",
      "contact": null,
      "patron": null,
      "event_types": "Distanzritt, Distanzfahrt",
      "efr": "26,38",
      "kdr": "54",
      "mdr": "64,80",
      "ldr": null,
      "mtr": null,
      "cei": null,
      "announcement_pdf": "2026-02-FruehjahrWeserEms.pdf",
      "announcement_updated": null,
      "results_pdf": "NeujahrsDistanz2026 VDD Liste.pdf",
      "registration_pdf": "VDD-Nennung.pdf",
      "status": "steht fest",
      "first_edition_year": null,
      "website": null,
      "bemerkung": null,
      "ritt_bild": null,
      "rittvorrat": 0,
      "wiki_touched": "2026-03-03T11:26:51Z"
    },

nur wenn sich wiki_touched ändert muss isch das event angesehen werden
Wir brauchen noch ein Mapping von welche Felder haben sich geändert zu welche nachricht soll angezeigt werden. was wäre dein Vorschlag?
13:21

Bevor ich den Plan schreibe, ein paar Designentscheidungen — vor allem beim Feld-zu-Nachricht-Mapping, das ist der Teil mit den meisten sinnvollen Varianten.
Mein Vorschlag fürs Mapping

Die Grundidee: nicht jedes geänderte Feld verdient eine eigene Notification. Nutzer interessieren sich für bedeutsame Änderungen, nicht für korrigierte Tippfehler im organizer. Ich würde Felder in Kategorien einteilen und pro Event eine zusammengefasste Notification schicken statt fünf einzelne.

Erkennung der Änderung: wiki_touched ist nur der Trigger („dieses Event lohnt einen Blick"). Welche Felder sich geändert haben, ermittelst du durch Vergleich des aktuellen Events mit einem gespeicherten Snapshot des vorherigen Stands. Also brauchst du serverseitig den letzten bekannten Zustand pro Event-ID.

Vorschlag für die Feld-Gruppen und Nachrichten:
Kategorie	Felder	Beispiel-Nachricht
Neues Event	(ID existierte vorher nicht)	„Neuer Ritt: {name} ({region}) am {start_date}"
Termin	start_date, end_date, multi_day	„{name}: Termin geändert auf {start_date}"
Status	status	„{name}: Status jetzt »{status}«"
Ort	venue, lat, lon	„{name}: Veranstaltungsort aktualisiert"
Distanzen	efr, kdr, mdr, ldr, mtr, cei	„{name}: Distanzen/Klassen aktualisiert"
Dokumente	announcement_pdf, results_pdf, registration_pdf, announcement_updated	„{name}: Neue Ausschreibung/Ergebnisse/Nennung verfügbar"
Sonstiges (still)	organizer, contact, patron, bemerkung, website, wiki_url, vdd_url, ...	keine Notification

Bei mehreren Kategorien gleichzeitig: eine Notification mit Sammeltitel, z.B. „{name}: 3 Änderungen (Termin, Status, Dokumente)". Klick öffnet vdd_url bzw. die Karte.

Besonders relevant sind wahrscheinlich Status (z.B. „steht fest" → abgesagt) und Dokumente (Ergebnis-PDF erscheint nach dem Ritt). Die würde ich höher priorisieren.

Ein paar offene Fragen, die ich gern vor dem Plan klären würde — damit der Agent nicht rät:

Q: Wie soll mit Änderungen am Dokumenten-Inhalt umgegangen werden? Die PDF-Felder enthalten nur Dateinamen — ein neues PDF mit gleichem Namen würde nicht erkannt.
A: Nur Dateiname vergleichen (einfach, reicht meist)

Q: Sollen Notifications pro Event oder gesammelt verschickt werden, wenn ein Action-Lauf mehrere Events ändert?
A: Pro Event, aber max. N, dann Sammel-Fallback

Q: Welche Persistenz für den letzten Zustand + Subscriptions auf Fly.io?
A: SQLite auf Fly-Volume (robust, mehr Setup)
13:22

Perfekt, dann baue ich den Plan mit diesen Entscheidungen. Ich schreibe ihn so, dass ein lokaler Coding-Agent ihn direkt umsetzen kann — mit konkreten Dateien, Schemas, Endpunkten und der Mapping-Logik.
Ran a command, created a file, read a file

Fertig. Der Plan ist auf deine drei Entscheidungen zugeschnitten (Dateinamen-Vergleich für PDFs, Einzel-Notification mit Sammel-Fallback ab N=5, SQLite auf Fly-Volume).

Ein paar Punkte, die ich proaktiv mit reingebaut habe und die dem Agenten sonst Probleme bereitet hätten:

    CGo-freies SQLite (modernc.org/sqlite) statt mattn/go-sqlite3 — sonst wird das Dockerfile und der scale-to-zero-Build deutlich umständlicher.
    Seeding beim ersten Lauf: bei leerer DB gelten sonst alle Events als „neu" und würden hunderte Notifications auf einmal auslösen. Der Plan unterdrückt das explizit.
    wiki_touched als Gate vor dem Diff, nicht nur als ein Feld unter vielen — so wie du es spezifiziert hast.
    scale-to-zero + Volume: Hinweis, bei einer Maschine zu bleiben, weil ein Volume sonst nicht von allen Instanzen gesehen wird.

Zum Mapping: ich habe status und documents als höchste Priorität gesetzt (Absage bzw. Ergebnis-PDF sind die Dinge, die einen Reiter wirklich interessieren), distances als niedrigste. Falls du die Reihenfolge anders gewichten willst, ist das die eine Stelle, die du im Plan noch anpassen solltest — der Rest hängt nicht davon ab.

Frontend (Service Worker + Subscribe-Button) und der konkrete Action-Step sind bewusst ausgeklammert, aber die Schnittstellen sind am Ende so dokumentiert, dass sie sauber andocken. Wenn du die später auch als Plan willst, sag Bescheid.
Plan push server
Document · MD 

kann die diff logik nicht in der github action laufen? dort habe ich zugriff auf neue und alte Daten
was passiert wenn ein Handy offline ist? werden push benachrichtigungen zwischen gespeichert? wenn ja wie lange?
13:29

Zwei gute Fragen, die beide das Design vereinfachen bzw. beeinflussen.
Diff in der Action statt im Server

Ja — und das ist sogar die sauberere Aufteilung. In der Action hast du git und damit beide Stände direkt: git show HEAD~1:data.min.json (alt) vs. die neue Datei (neu). Du brauchst dann gar keine Snapshot-Persistenz auf dem Server mehr. Das eliminiert die komplette event_snapshots-Tabelle, das Seeding-Problem und einen Großteil der Server-Komplexität.

Die Verantwortung verschiebt sich so:

    Action rechnet den Diff (Python — du hast mit vdd_scrape.py ohnehin schon Python im Repo), baut die fertigen Notifications nach der Mapping-Tabelle und schickt sie als fertige Payloads an den Server.
    Server wird zum reinen „Briefträger": nimmt Subscriptions entgegen (SQLite, nur noch eine Tabelle) und verschickt beim /notify-Aufruf die mitgelieferten Notifications an alle Abonnenten. Keine Event-Logik mehr.

Der /notify-Body ändert sich dann von „komplettes data.min.json" zu „Liste fertiger Notifications", z.B.:
json

{
  "notifications": [
    { "title": "Frühjahrsdistanz am Meer", "body": "Status: abgesagt", "url": "...", "tag": "..." }
  ]
}

Die Mapping-Logik (welches Feld → welche Nachricht, Prioritäten, N-Schwelle für Sammel-Notification) wandert damit komplett in ein Python-Skript in der Action. Vorteile: testbar im Repo, kein Server-State, der Server bleibt trivial und übersteht scale-to-zero ohne jede Datenmigration. Einziger „Nachteil": die Logik liegt jetzt im Repo statt im Go-Server — was in deinem Fall eher ein Vorteil ist.

Das ist klar die bessere Architektur. Soll ich den Plan entsprechend umschreiben?
Was passiert, wenn das Handy offline ist?

Ja, Push-Nachrichten werden zwischengespeichert — aber mit Einschränkungen, die du kennen solltest.

Der Push-Dienst (FCM bei Chrome/Android, Mozilla autopush bei Firefox, Apple bei Safari/iOS) puffert eine Nachricht, wenn das Gerät offline ist, und stellt sie zu, sobald es wieder online ist. Wie lange, steuerst du über den TTL-Wert (Time To Live) beim Senden:

    TTL = 0: nur zustellen, wenn das Gerät gerade jetzt erreichbar ist, sonst verwerfen.
    TTL > 0: bis zu so viele Sekunden puffern.
    Das Maximum liegt bei FCM und Web Push bei 4 Wochen (2.419.200 Sekunden). Das ist die Obergrenze, nicht die Garantie.

Wichtige Realitäten dabei:

    Collapse/Replace: Wenn du beim Senden einen Topic-Header (FCM) bzw. bei manchen Diensten denselben Mechanismus setzt, ersetzt eine neue Nachricht eine noch nicht zugestellte ältere mit gleichem Key. Sinnvoll, damit ein Gerät nach 3 Tagen offline nicht 72 „neue Daten"-Pushes auf einmal bekommt. Der tag im Notification-Payload macht das clientseitig (gestapelte Notifications werden ersetzt) — der collapse-Key macht es schon im Transit.
    Keine Garantie: Push ist best-effort. Bei sehr langer Offline-Zeit, App vom Nutzer „force-stopped", Akkuspar-Maßnahmen (gerade aggressiv auf Android, und du nutzt ja GrapheneOS — da ist das nochmal strenger) kann eine Nachricht verloren gehen.
    iOS: nur als installierte PWA, und das System ist beim Zustellen alter Pushes konservativer.

Für dein Szenario heißt das konkret: Daten ändern sich stündlich, aber die interessanten Änderungen (Absage, Ergebnis-PDF) sind selten und nicht extrem zeitkritisch. Ich würde einen TTL von etwa 24 Stunden wählen und einen collapse-Key pro Event setzen — dann bekommt ein einen Tag offline gewesenes Handy beim Wiederverbinden den jeweils aktuellsten Stand pro Ritt, statt eines Stapels veralteter Zwischenstände. Genau diese „aktuellster Stand pro Event"-Semantik passt auch gut dazu, dass die Action ohnehin pro Event aggregiert.

Soll ich den Plan auf die neue Architektur umstellen (Diff in Python in der Action, Server nur noch Subscription-Store + Versand) und TTL/collapse-Key gleich mit reinschreiben?

ein topic pro event klingt logisch ja bitte umschreiben und als zusätzlichen output ein plan für die notwenigen github action

die schaut aktuell so aus:
name: Update map
on:
  schedule:
    - cron: '0 * * * *'   # every hour
  workflow_dispatch:        # manual trigger from GitHub UI
jobs:
  update:
    runs-on: ubuntu-24.04
    container: python:3.12-slim
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v5
      - run: pip install --quiet requests
      - name: Check for wiki changes
        id: check
        run: |
          result=$(python vdd_scrape.py --check-only)
          echo "changed=$result" >> "$GITHUB_OUTPUT"
      - name: Run scraper
        if: steps.check.outputs.changed == 'true'
        run: python vdd_scrape.py
      - name: Commit & push
        if: steps.check.outputs.changed == 'true'
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data.json data.min.json
          git diff --cached --quiet || (git commit -m "chore: auto-update data $(date -u +%Y-%m-%d)" && git push)
13:33

Verstanden. Ich schreibe den Server-Plan auf die neue Architektur um (reiner Subscription-Store + Versand, Diff raus) und erstelle einen zweiten Plan für die Action inkl. Diff-Skript, der zu deinem bestehenden Workflow passt.
Rewrite the server plan for the courier-only architecture
Done

Jetzt der Action-Plan mit dem Diff-Skript, abgestimmt auf deinen bestehenden Workflow.
Ran a command, read a file

Beide Pläne sind fertig.

Was sich am Server-Plan geändert hat: Die komplette Event- und Diff-Logik ist raus. Keine event_snapshots-Tabelle mehr, kein Seeding-Problem, nur noch die subscriptions-Tabelle. Der Server nimmt eine fertige Notification-Liste entgegen und verteilt sie. Neu drin: TTL (Default 24h) und der Topic-Header pro Event für das Zusammenfassen offline gepufferter Pushes — inklusive Hinweis, dass die Event-ID gehasht werden muss (der Topic-Header erlaubt nur base64url, max. 32 Zeichen, und der Hash muss über Läufe hinweg stabil sein, sonst greift collapse nicht).

Der Action-Plan enthält die Mapping-Logik als Python-Skript notify_diff.py plus den angepassten Workflow. Zwei Stolpersteine, die ich explizit reingeschrieben habe, weil sie deinen Lauf sonst stillschweigend kaputt machen würden:

    git show HEAD:data.min.json muss vor dem Commit-Step laufen (in einem „Snapshot old data"-Step), sonst vergleichst du den neuen Stand mit sich selbst.
    safe.directory muss gesetzt werden, weil im python:3.12-slim-Container das Checkout-Verzeichnis einem anderen User gehört und git show sonst mit „dubious ownership" abbricht.

Außerdem: lat/lon mit Toleranz vergleichen (1e-6), damit Float-Rauschen aus dem Nominatim-Geocoding keine „Ort geändert"-Pushes auslöst — das wäre sonst eine häufige Fehlalarm-Quelle. Und das Notify-Skript bricht den Workflow bewusst nicht ab, falls der Fly-Server gerade nicht erreichbar ist; der Daten-Commit ist wichtiger als die Benachrichtigung.

Die Einzel-vs-Sammel-Entscheidung (max. 5) liegt jetzt sauber in der Action — der Server bekommt entweder fünf Einzelne oder eine Sammel-Notification und muss nichts entscheiden.
Plan push server
Document · MD 
Plan github action
Document · MD 

für die github action: vergleiche nur felder wenn "rittvorrat" = 0 alles andere kann getrost ignoriert werden und soll niemals eine notification erzeugen
13:40

Verstanden — rittvorrat == 0 als zusätzliches Gate. Ich passe den Action-Plan an.

Kurz zur Sicherheit, wie ich das einbaue (sag Bescheid, falls du's anders meinst): Ein Event wird nur dann auf Feldänderungen geprüft, wenn im neuen Stand rittvorrat == 0 ist. Ist rittvorrat != 0, wird das Event komplett ignoriert — auch „new" und auch wenn sich wiki_touched geändert hat. Das Gate kommt also noch vor wiki_touched.
Viewed a file, edited a file

Jetzt der Hinweis zur Semantik direkt darunter und ein passender Testfall.
Edited 2 files

Und das Akzeptanzkriterium ergänzen.
Edited a file, read a file

Erledigt. Das rittvorrat == 0-Gate ist jetzt als Schritt 0 vor dem wiki_touched-Check eingebaut, also greift es zuerst — Events mit rittvorrat != 0 werden komplett übersprungen, inklusive „new" und unabhängig von wiki_touched.

Eine Sache, bei der ich eine Annahme getroffen habe und die du prüfen solltest: Ich werte rittvorrat aus dem neuen Stand aus (nicht alt), weil „soll das Event aktuell beachtet werden" sich am aktuellen Zustand orientiert. Und null/fehlend habe ich defensiv als „nicht 0" → ignorieren behandelt. Falls in deinen Daten rittvorrat mal als String "0" statt Zahl 0 vorkommen kann, sollte das Skript beide Fälle als 0 akzeptieren — sag kurz Bescheid, dann schreibe ich das explizit rein, sonst lasse ich es beim numerischen Vergleich.
Plan github action
Document · MD 
Plan push server
Document · MD 

wie sieht eine sample payload für /notify? aus?
13:45

Basierend auf den Plänen sieht ein /notify-Request so aus:

Request-Header:

POST https://vdd-rittatlas-push.fly.dev/notify
Content-Type: application/json
X-Notify-Token: <dein-geheimes-token>

Body — Fall A: Einzel-Notifications (≤ 5 geänderte Events)
json

{
  "notifications": [
    {
      "title": "Frühjahrsdistanz am Meer",
      "body": "Status: abgesagt",
      "url": "https://vdd-aktuell.de/ritt/Fruehjahrsdistanz-am-Meer-2026/",
      "tag": "Frühjahrsdistanz am Meer 2026",
      "topic": "Frühjahrsdistanz am Meer 2026"
    },
    {
      "title": "Frühjahrsdistanz am Meer",
      "body": "3 Änderungen: Status, Dokumente, Termin",
      "url": "https://vdd-aktuell.de/ritt/Fruehjahrsdistanz-am-Meer-2026/",
      "tag": "Frühjahrsdistanz am Meer 2026",
      "topic": "Frühjahrsdistanz am Meer 2026"
    },
    {
      "title": "Neuer Ritt: Herbstdistanz Eifel",
      "body": "Rheinland · 12.09.2026",
      "url": "https://techtimo.github.io/vdd-rittatlas/",
      "tag": "Herbstdistanz Eifel 2026",
      "topic": "Herbstdistanz Eifel 2026"
    }
  ]
}

(Die ersten beiden zeigen nur die zwei Body-Varianten — pro Event entsteht real natürlich nur eine.)

Body — Fall B: Sammel-Notification (> 5 geänderte Events)
json

{
  "notifications": [
    {
      "title": "VDD Rittatlas",
      "body": "8 Ritte aktualisiert",
      "url": "https://techtimo.github.io/vdd-rittatlas/",
      "tag": "vdd-bulk",
      "topic": "vdd-bulk"
    }
  ]
}

Feld-Bedeutung:

    title / body — was der Nutzer in der Notification sieht.
    url — Klickziel; vdd_url des Events, sonst der Fallback auf die Karte.
    tag — clientseitiges Stapeln: gleiche tag → neue Notification ersetzt die alte im System-Tray (Service Worker liest das aus).
    topic — der Server hasht das selbst auf base64url ≤ 32 Zeichen und setzt damit den Web-Push-Topic-Header (collapse offline gepufferter Pushes). tag und topic sind beide die Event-ID; bei der Sammel-Notification beide "vdd-bulk".

Ein Detail zum Testen: Bei leerer Liste ({"notifications": []}) antwortet der Server mit 200 und tut nichts — das Notify-Skript schickt in dem Fall ohnehin gar nicht erst.

Soll ich dir einen fertigen curl-Befehl zum manuellen Testen des Endpoints zusammenbauen?

mir ist nicht ofensichtlich wie die payload auszusehen hat für das python skript. jedes Feld und die Beduetung sollte erklärt werden
13:48

Guter Punkt — im Plan ist das Body-Format zwar genannt, aber die Bedeutung jedes Feldes ist über mehrere Stellen verstreut. Ich ergänze im Action-Plan einen eigenen, expliziten Abschnitt, der genau das Payload-Schema dokumentiert, das notify_diff.py bauen muss.
Viewed a file, edited a file, read a file

Erledigt. Im Action-Plan steht jetzt ein eigener Abschnitt „Payload-Schema für POST /notify" mit einer Tabelle, die jedes der fünf Felder einzeln erklärt: Typ, ob Pflicht, Bedeutung, und wie notify_diff.py den Wert konkret füllt.

Die wichtigsten Klarstellungen darin:

    Alle fünf Felder sind immer Strings und immer gesetzt — kein null, keine fehlenden Schlüssel. Wo kein echter Wert da ist (z.B. vdd_url fehlt), kommt der Fallback rein. Das nimmt dem Skript und dem Go-Server eine Fehlerquelle.
    tag vs. topic ist jetzt explizit auseinandergehalten: tag wirkt clientseitig (ersetzt eine sichtbare Notification im Tray), topic wirkt im Transit beim Push-Dienst (ersetzt eine noch nicht zugestellte für offline-Geräte). Beide tragen die Event-ID, aber aus unterschiedlichem Grund.
    Das Skript schickt die rohe Event-ID als topic, nicht den Hash — das Hashen auf base64url ≤32 Zeichen macht der Server. Sonst hätte man die Sanitizing-Logik doppelt.
    Was nicht drin ist: keine rohen Event-Daten, kein wiki_touched, keine Kategorie. Alles ist schon in title/body aufgelöst, der Server interpretiert nichts.

Plan github action
Document · MD 

ist es möglich nur für bestimmte topics eine meldung zu bekommen?
neuer ritt sollte topic new event sein oder ähnlich
13:51

Ja, das ist möglich — aber wichtig: Der Web-Push-Topic-Header, den wir bisher im Plan haben, ist nicht dafür da. Der dient nur dem Zusammenfassen (collapse) von Nachrichten im Transit, nicht dem Filtern oder Abonnieren. Ein Nutzer kann darüber nichts „abonnieren".

Was du willst, ist eine Themen-/Kategorie-Subscription: der Nutzer wählt aus, welche Arten von Meldungen er bekommen will (z.B. nur „neue Ritte", oder nur „Status-Änderungen"), und der Versand respektiert das. Das ist gut machbar, ändert aber das Design an mehreren Stellen. Lass mich die Optionen skizzieren, bevor ich die Pläne anfasse.
Begriffsklärung zuerst

Es gibt jetzt zwei verschiedene Dinge, die beide gern „topic" heißen — das müssen wir sauber trennen:

    Collapse-Topic (bisher im Plan): technischer Web-Push-Header, pro Event (Event-ID), damit offline gepufferte Updates desselben Ritts sich überschreiben. Hat nichts mit Nutzerwahl zu tun.
    Kategorie / Channel (das, was du jetzt willst): fachliche Klasse einer Meldung — new_event, status, documents, date, location, distances — die ein Nutzer abonnieren oder abbestellen kann.

Ich würde Letzteres im Plan konsequent „category" nennen, damit es nicht mit dem Collapse-Topic kollidiert.
Wo kann gefiltert werden?

Variante A — serverseitig (pro Subscription gespeicherte Kategorien) Der Nutzer wählt im Frontend seine Kategorien, das Frontend schickt sie beim /subscribe mit, der Server speichert pro Subscription eine Kategorien-Menge. Die Action liefert pro Notification ihre category mit; der Server sendet eine Notification nur an Subscriptions, die diese Kategorie abonniert haben.

    Vorteil: echte Filterung, das Gerät bekommt nur, was es will. Funktioniert auch offline/bei geschlossenem Tab.
    Kosten: subscriptions-Tabelle bekommt eine Kategorien-Spalte; /notify-Notifications brauchen ein category-Feld; /subscribe akzeptiert die Auswahl; ein /preferences-Update-Endpoint ist sinnvoll, damit man die Auswahl ändern kann.

Variante B — clientseitig (Service Worker filtert) Server schickt alles, der Service Worker entscheidet beim push-Event anhand der mitgeschickten category, ob er die Notification anzeigt.

    Vorteil: Server bleibt simpel, keine DB-Änderung.
    Nachteil: Das Gerät empfängt trotzdem jeden Push (Akku/Daten), und die Präferenz liegt nur lokal im Browser. Auf GrapheneOS mit aggressivem Hintergrund-Handling eher unschön, und „unterdrückte" Pushes sind verschwendet.

Empfehlung: Variante A. Sie ist das, was man unter „nur bestimmte Themen bekommen" versteht, und der Mehraufwand ist überschaubar. Variante B ist nur ein Hack, wenn man den Server nicht anfassen will.
Wie das konkret aussähe (Variante A)

    Kategorien: new_event, status, documents, date, location, distances. Deine Idee „neuer Ritt = eigene Kategorie" ist genau new_event.
    /subscribe-Body bekommt ein Feld, z.B. "categories": ["new_event", "status"]. Leer oder fehlend = alle (sinnvolle Default-Semantik).
    /notify-Notification bekommt ein Feld "category": "new_event". Bei der Sammel-Notification wird's kniffliger (siehe Frage unten).
    Versand: Server sendet eine Notification nur an Subs, deren categories die category enthält (oder die „alle" abonniert haben).
    DB: einfachste Form — eine Spalte categories TEXT (kommasepariert oder JSON-Array) in subscriptions.

Ein paar Entscheidungen, die ich brauche, bevor ich die Pläne umschreibe — vor allem rund um die Sammel-Notification, die mit Kategorie-Filtern nicht mehr ganz sauber funktioniert:

Q: Wo soll gefiltert werden?
A: ein user soll auswählen wofür es meldungen gibt (z.b. nur favorisierte Ritte und neue Ritte)

Q: Die Sammel-Notification (>5 Events) mischt Kategorien. Wie damit umgehen?
A: Sammelung ganz abschaffen, immer Einzel-Notifications

Q: Soll die Kategorie-Auswahl änderbar sein, ohne neu zu abonnieren?
A: Ja, eigener /preferences-Endpoint
13:53

Deine erste Antwort führt eine neue, wichtige Dimension ein, die über die Kategorien hinausgeht: favorisierte Ritte. Das ist kein Kategorie-Filter („alle Status-Änderungen"), sondern ein Filter auf bestimmte Events („nur Updates zu diesen Ritten, die mich interessieren"). Bevor ich die Pläne umschreibe, muss ich das sauber verstehen, weil es das Datenmodell deutlich beeinflusst.

So wie ich es lese, will der Nutzer zwei unabhängige Filter kombinieren können:

    Kategorien — welche Arten von Meldungen (z.B. new_event, status, documents …).
    Favoriten — eine Liste konkreter Event-IDs, für die er Updates will, auch wenn er nicht „alle Status-Änderungen" abonniert hat.

Die spannende Frage ist, wie die beiden zusammenwirken. Ein paar Punkte, die ich klären muss:

Wie verhalten sich Kategorien und Favoriten zueinander? Beispiel: Nutzer hat Ritt X favorisiert und als Kategorie nur documents gewählt. Ritt X ändert seinen status. Bekommt er die Meldung?

    Variante „Favorit schlägt alles": Bei favorisierten Ritten jede Änderung melden, egal welche Kategorie. Kategorien gelten nur für nicht-favorisierte Ritte.
    Variante „UND": Nur melden, wenn Event favorisiert und Kategorie passt.
    Variante „getrennte Kanäle": new_event ist global (neue Ritte kennt man ja noch nicht, kann sie also nicht vorher favorisieren), alle anderen Kategorien gelten nur für Favoriten.

Die dritte Variante klingt nach dem, was du andeutest („nur favorisierte Ritte und neue Ritte") — neue Ritte global, Detail-Updates nur für die, die mich interessieren.

Das new_event-Henne-Ei-Problem: Einen Ritt kann man erst favorisieren, nachdem man von ihm weiß. Neue Ritte muss man also global bekommen können (Kategorie new_event), und favorisieren kommt danach. Das spricht dafür, new_event als eigenen globalen Schalter zu behandeln, getrennt von den „Update-Kategorien".

Wo werden Favoriten gespeichert und wie kommen sie zum Server? Die Favoriten-Auswahl passiert im Frontend (Nutzer tippt auf der Karte „merken"). Diese Liste von Event-IDs muss beim /subscribe bzw. /preferences mitgeschickt und pro Subscription gespeichert werden. Bei vielen Favoriten wird das eine längere Liste — speicherbar als JSON-Array in der subscriptions-Zeile oder als eigene Tabelle (subscription_favorites).

Damit ich das Datenmodell und die Versand-Logik richtig aufsetze:

Q: Wie sollen Kategorien und Favoriten zusammenwirken?
A: kategorie gibt es nur neuer Ritt und bestehender Rittänderung favorisiert könenn nur ritt IDs zusätzlich wird ausgewählt ob über neue Ritte informiert werden soll

Q: Soll der Nutzer die Update-Kategorien (status/date/docs/...) überhaupt einzeln wählen, oder reicht 'neue Ritte' + 'meine Favoriten'?
A: genau das reicht: neue Ritte und favoriten (oder auch alles)

Q: Wie Favoriten-IDs pro Subscription speichern?
A: Eigene Tabelle subscription_favorites (sauberer bei vielen)
13:56

Klar, jetzt ist das Modell sauber. Lass mich es einmal in meinen Worten zusammenfassen, damit wir auf demselben Stand sind, bevor ich die Pläne umschreibe:

Das Präferenz-Modell pro Subscription:

    notify_new_events (Bool) — will der Nutzer über neue Ritte informiert werden? Global, unabhängig von Favoriten (man kann einen Ritt nicht favorisieren, bevor man ihn kennt).
    Favoriten (Liste von Event-IDs) — für bestehende Ritte: der Nutzer bekommt jede inhaltliche Änderung (Status, Termin, Doks, Ort, Distanzen) nur zu den Ritten in seiner Favoritenliste.

Es gibt also nur zwei „Kategorien" im Versand: new_event und event_change. Keine feingranulare Wahl nach Status/Termin/Doks mehr — eine Änderung an einem favorisierten Ritt meldet sich als eine event_change-Notification (Body fasst zusammen, was sich geändert hat, wie bisher).

Versand-Entscheidung pro Notification:

    new_event → an alle Subs mit notify_new_events = true.
    event_change für Event X → an alle Subs, die X in ihren Favoriten haben.

Sammel-Notification: abgeschafft, immer Einzel-Notifications (deine vorige Antwort).

Eine letzte Konsequenz, die ich klären will, weil sie sonst zu „toten" Notifications führt: Bei einem neuen Ritt weiß noch niemand von ihm, also kann er nicht favorisiert sein — die new_event-Meldung geht daher rein über notify_new_events. Eine Änderung an einem Ritt, den niemand favorisiert hat, geht an niemanden (das ist gewollt). Passt soweit?

Dann schreibe ich beide Pläne entsprechend um:
Check current length of both plans before rewriting
Claude's response was interrupted.

event_change für Event X → an alle Subs, die X in ihren Favoriten haben. 

Oder eben alle Ritte änderungen haben wollen (vielelciht auch ein bool flag?)
13:57

Ja, sinnvoll — ein dritter Schalter. Damit hat eine Subscription drei unabhängige Präferenzen:

    notify_new_events (Bool) — neue Ritte.
    notify_all_changes (Bool) — jede Änderung an jedem bestehenden Ritt, unabhängig von Favoriten.
    Favoriten (Event-IDs) — Änderungen nur an diesen Ritten.

Versand-Logik pro Notification:

    new_event → an alle Subs mit notify_new_events = true.
    event_change für Event X → an alle Subs mit notify_all_changes = true ODER X in ihren Favoriten (ODER-Verknüpfung). Wer „alles" angehakt hat, braucht keine Favoriten zu pflegen; die Favoritenliste wird dann schlicht ignoriert.

Das ist die natürliche Obermenge — notify_all_changes macht Favoriten überflüssig, schließt sie aber nicht aus. Ich schreibe beide Pläne jetzt entsprechend um (Server-seitige Filterung, neuer /preferences-Endpoint, Tabelle subscription_favorites, Sammel-Notification raus).
Rewrite server plan with preferences/favorites filtering

bash
cd /home/claude/out && cat > PLAN-push-server.md << 'PLANEOF'
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
PLANEOF
echo "server plan rewritten: $(wc -l < PLAN-push-server.md) lines"

Output
server plan rewritten: 382 lines
Done

Jetzt der Action-Plan: category + event_id statt topic im Payload, nur noch zwei Kategorien, Sammel-Notification raus.
Ran a command, read a file

Beide Pläne sind umgeschrieben.

Server-Plan — die Filterung sitzt jetzt serverseitig:

    Drei Präferenzen pro Subscription: notify_new_events, notify_all_changes und die Favoritenliste.
    Die Versand-Entscheidung ist als isolierte, testbare Funktion shouldSend(notification, sub) herausgezogen — new_event geht an alle mit notify_new_events, event_change an alle mit notify_all_changes oder die das Event favorisiert haben.
    Neue Tabelle subscription_favorites mit ON DELETE CASCADE und einem Index auf event_id (damit „wer hat Ritt X favorisiert" schnell bleibt).
    Neuer Endpoint POST /preferences zum Ändern ohne Neu-Abo; Favoriten werden transaktional komplett ersetzt statt gemerged (vermeidet Merge-Edgecases).

Action-Plan — der Payload trägt jetzt die Zielinfo:

    Jede Notification bekommt category (new_event/event_change) und event_id. Das Skript filtert nicht nach Nutzern, es markiert nur — die Zuordnung macht der Server.
    topic ist aus dem Payload raus; der Server bildet den Collapse-Topic selbst aus event_id. So liegt die Sanitizing-Logik nur an einer Stelle.
    Sammel-Notification komplett entfernt, immer Einzel-Notifications.
    Das rittvorrat == 0-Gate und alle vorherigen Entscheidungen (PDF-Dateinamen, lat/lon-Toleranz, wiki_touched-Gate) sind erhalten.

Zwei Dinge, auf die ich dich aktiv hinweisen will:

Erstens, eine Begriffsfalle, die ich im Server-Plan explizit markiert habe: „Topic" meint jetzt zwei verschiedene Sachen. Der Web-Push-Topic-Header (Collapse pro Event) hat nichts mit den Präferenz-Kategorien zu tun. Im Code unbedingt getrennt halten, sonst baut der Agent das versehentlich zusammen.

Zweitens eine Design-Konsequenz, die dir bewusst sein sollte: Favoriten liegen pro Subscription (also pro Browser/Gerät). Wenn derselbe Nutzer die Seite auf Handy und Laptop öffnet, sind das zwei Subscriptions mit getrennten Favoritenlisten. Ohne Login/Nutzerkonto gibt es keine geräteübergreifende Synchronisation — das ist für so ein Tool normal und völlig okay, aber falls du später „meine Favoriten auf allen Geräten" willst, bräuchte es eine Nutzer-Identität. Für jetzt würde ich es bei pro-Gerät belassen.
Plan push server
Document · MD 
Plan github action
Document · MD 

kann eine präferenz geändert werden?
14:00

Ja — dafür ist der POST /preferences-Endpoint da, den ich im Server-Plan ergänzt habe. Genau das war deine Anforderung „änderbar ohne neu zu abonnieren".

So funktioniert es laut Plan: Das Frontend schickt den vollständigen Präferenz-Stand an /preferences, identifiziert die Subscription über ihren endpoint, und der Server überschreibt damit die drei Präferenzfelder und ersetzt die Favoritenliste (transaktional).

POST /preferences
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "notify_new_events": true,
  "notify_all_changes": false,
  "favorites": ["Frühjahrsdistanz am Meer 2026"]
}

Ein paar Punkte dazu, die im Plan so festgelegt sind:

Identifikation über endpoint, nicht über Login. Das Frontend holt den endpoint aus der aktiven PushSubscription des Browsers (registration.pushManager.getSubscription()). Den braucht es nicht zu speichern — er ist jederzeit aus dem Service Worker abrufbar. Existiert der endpoint serverseitig nicht (z.B. Subscription wurde nie angelegt oder schon weggeräumt), antwortet der Server mit 404, und das Frontend sollte dann neu /subscribe-n.

Vollständiges Überschreiben statt Teil-Update. Der Client schickt immer den kompletten Stand, der Server ersetzt alles. Das ist bewusst simpel gehalten — kein Merge, keine „nur dieses eine Feld ändern"-Logik, also auch keine Edgecases damit. In der Praxis hat das Frontend den aktuellen Stand ohnehin im UI (Checkboxen + Favoritensterne), also ist „schick mir den ganzen Stand" natürlich.

Typische Auslöser im Frontend:

    Nutzer hakt in den Einstellungen „neue Ritte" oder „alle Änderungen" an/ab → /preferences.
    Nutzer tippt auf der Karte einen Favoriten-Stern an/aus → /preferences mit aktualisierter Favoritenliste.

Eine Sache, die ich im Plan nicht explizit gemacht habe und die du eventuell willst: Soll /preferences bei unbekanntem endpoint wirklich nur 404 zurückgeben, oder soll es in dem Fall automatisch anlegen (Upsert), sofern die keys mitgeschickt werden? Letzteres macht das Frontend robuster (ein einziger Endpoint für „setze meine Präferenzen", egal ob schon abonniert). Soll ich /preferences zu einem Upsert erweitern, oder bei der klaren Trennung /subscribe (anlegen) vs. /preferences (ändern) bleiben?

jetzt sendet der action workflow pro event eine notification und der server selektiert was wohin gesendet werden soll?
14:03

Ja, genau so ist die Arbeitsteilung im aktuellen Plan:

Action (notify_diff.py): berechnet den Diff und erzeugt pro betroffenem Event eine Notification, markiert mit category (new_event/event_change) und event_id. Sie filtert nicht nach Nutzern — sie weiß nichts über Subscriptions oder Favoriten. Sie schickt einmal alle Notifications gebündelt an POST /notify.

Server: lädt alle Subscriptions samt Präferenzen + Favoriten und entscheidet pro Notification × Subscription über shouldSend(...), wer sie bekommt — new_event an alle mit notify_new_events, event_change an alle mit notify_all_changes oder die das Event favorisiert haben. Dann verschickt er gezielt.

Also: Action = was hat sich geändert (eine Notification je Event), Server = wer will das (Fan-out + Filter).

Eine Präzisierung, damit kein Missverständnis entsteht: „pro Event eine Notification" heißt eine Notification im /notify-Payload. Der Server vervielfältigt sie beim Versand — wenn fünf Leute denselben favorisierten Ritt haben, wird aus der einen Notification im Payload fünf tatsächliche Push-Zustellungen. Die Action erzeugt also N Notifications (N = geänderte Events), der Server daraus N × (passende Abonnenten) Pushes.

Das ist auch der Grund, warum diese Aufteilung gut ist: Die Action braucht keinerlei Wissen über Abonnenten (bleibt zustandslos und einfach), und die Abonnentendaten verlassen nie den Server. Die Logik „was ist eine meldenswerte Änderung" liegt im Repo (testbar, versioniert), die Logik „wer kriegt was" liegt beim einzigen Ding, das die Nutzerdaten hat.


Claude is AI and can make mistakes. Please double-check responses.
Plan github action · MD
# Implementierungsplan: GitHub Action — Diff & Notify für VDD Rittatlas
 
## Ziel
 
Den Workflow `Update map` erweitern: nach erfolgreichem Daten-Update den **Diff** zwischen altem
und neuem `data.min.json` berechnen, in **fertige Notifications mit Zielangabe** übersetzen und an
`POST /notify` des Fly-Servers schicken. Der Server filtert dann anhand der pro Subscription
gespeicherten Präferenzen (siehe `PLAN-push-server.md`).
 
Die Diff- und Text-Logik lebt in einem Python-Skript `notify_diff.py`.
 
---
 
## Notification-Kategorien (nur zwei)
 
- **`new_event`** — Event-ID war im alten Stand nicht vorhanden.
- **`event_change`** — bestehendes Event hat sich inhaltlich geändert.
Der Server entscheidet anhand `category` + `event_id`, welche Subscription die Notification
bekommt (neue Ritte → wer `notify_new_events` hat; Änderungen → wer `notify_all_changes` hat oder
das Event favorisiert hat). **Das Skript filtert nicht nach Nutzern** — es erzeugt nur die
Notifications und markiert sie mit Kategorie und Event-ID.
 
---
 
## Schnittstelle zum Server
 
```
POST https://<app>.fly.dev/notify
Header: X-Notify-Token: <NOTIFY_TOKEN>
Body:   { "notifications": [ <Notification>, ... ] }
```
 
GitHub Actions Secrets:
- `NOTIFY_TOKEN` — identisch zum Fly-Secret.
- `PUSH_SERVER_URL` — z.B. `https://vdd-rittatlas-push.fly.dev`.
---
 
## Payload-Schema für `POST /notify`
 
Body = ein Objekt mit Schlüssel `notifications` (Liste). Jedes Element:
 
| Feld        | Typ    | Pflicht | Bedeutung / Befüllung durch `notify_diff.py` |
|-------------|--------|---------|-----------------------------------------------|
| `category`  | String | ja | `"new_event"` oder `"event_change"`. Steuert serverseitig die Zielgruppe. |
| `event_id`  | String | ja | Die Event-`id` des betroffenen Ritts. Bei `event_change` für den Favoriten-Abgleich; bei `new_event` die ID des neuen Ritts. Der Server leitet daraus auch den Collapse-Topic ab. |
| `title`     | String | ja | Überschrift. `new_event`: `Neuer Ritt: {name}`. `event_change`: `{name}`. |
| `body`      | String | ja | Fließtext. `new_event`: `{region} · {start_date}`. `event_change`: Zusammenfassung der Änderungen (siehe Mapping). |
| `url`       | String | ja | Klickziel = `vdd_url`; falls leer/`null` → Fallback `https://techtimo.github.io/vdd-rittatlas/`. |
| `tag`       | String | ja | = `event_id`. Clientseitiges Stapeln (neue Notification ersetzt alte mit gleichem `tag` im Tray). |
 
Alle Felder immer setzen (Strings, kein `null`). Es gibt **keine** Sammel-Notification mehr und
**kein** `topic`-Feld im Payload (Server bildet den Collapse-Topic selbst aus `event_id`).
 
**Beispiel:**
```json
{
  "notifications": [
    {
      "category": "event_change",
      "event_id": "Frühjahrsdistanz am Meer 2026",
      "title": "Frühjahrsdistanz am Meer",
      "body": "2 Änderungen: Status, Dokumente",
      "url": "https://vdd-aktuell.de/ritt/Fruehjahrsdistanz-am-Meer-2026/",
      "tag": "Frühjahrsdistanz am Meer 2026"
    },
    {
      "category": "new_event",
      "event_id": "Herbstdistanz Eifel 2026",
      "title": "Neuer Ritt: Herbstdistanz Eifel",
      "body": "Rheinland · 12.09.2026",
      "url": "https://techtimo.github.io/vdd-rittatlas/",
      "tag": "Herbstdistanz Eifel 2026"
    }
  ]
}
```
 
---
 
## Diff-Quelle: Git
 
- **Alt:** committeter Stand vor dem neuen Commit — `git show HEAD:data.min.json`, ausgeführt
  **vor** dem Commit-Step und in `old.min.json` gesichert. Existiert nicht (erster Lauf) → `[]`.
- **Neu:** das frisch von `vdd_scrape.py` geschriebene `data.min.json`.
---
 
## `notify_diff.py` — Spezifikation
 
### Aufruf
```
python notify_diff.py --old old.min.json --new data.min.json --server "$PUSH_SERVER_URL"
```
Token via Env `NOTIFY_TOKEN`. `--dry-run` gibt nur aus, was gesendet würde.
 
### Einlesen
- Beide Dateien als Event-Listen laden, nach `id` indexieren (`old_by_id`, `new_by_id`).
### Verarbeitung pro Event aus `new_by_id`
```
0. rittvorrat (neu) != 0   -> Event komplett ignorieren (niemals Notification),
                              auch kein "new", auch bei geändertem wiki_touched.
                              rittvorrat fehlt/null -> als "nicht 0" behandeln (ignorieren).
1. id nicht in old_by_id    -> Kategorie "new_event"
2. wiki_touched unverändert -> Event überspringen (kein Diff)
3. wiki_touched verändert   -> Kategorie-Felder vergleichen -> ggf. "event_change"
```
Nur in `old` vorhandene (entfernte) Events: ignorieren.
 
> **`rittvorrat`-Gate (Schritt 0):** maßgeblich ist der **neue** Wert. Nur `rittvorrat == 0` wird
> betrachtet. Akzeptiere `0` (int) und `"0"` (string) als 0.
 
### Änderungs-Mapping (für `event_change`-Body)
 
Geänderte Felder werden Kategorien zugeordnet (Priorität = Reihenfolge, für Sortierung der Labels):
 
| Gruppe       | Felder                                                              | Prio | Label     |
|--------------|---------------------------------------------------------------------|------|-----------|
| status       | `status`                                                            | 1    | Status    |
| documents    | `announcement_pdf`, `results_pdf`, `registration_pdf`, `announcement_updated` | 2 | Dokumente |
| date         | `start_date`, `end_date`, `multi_day`                               | 3    | Termin    |
| location     | `venue`, `lat`, `lon`                                               | 4    | Ort       |
| distances    | `efr`, `kdr`, `mdr`, `ldr`, `mtr`, `cei`                            | 5    | Distanzen |
 
- PDF-Felder: reiner Dateiname-String-Vergleich.
- `lat`/`lon`: Float-Vergleich mit Toleranz `abs(a-b) < 1e-6`.
- Stille Felder (`organizer`, `contact`, `patron`, `bemerkung`, `website`, `wiki_url`, `vdd_url`,
  `subtitle`, `country`, `ritt_bild`, `rittvorrat`, `first_edition_year`, `name`, `region`, …):
  lösen nichts aus.
- Geändertes `wiki_touched`, aber keine Gruppe getroffen → keine Notification.
### Texte (Deutsch)
`{name}`=`name`, `{region}`=`region`, `{start_date}`=`start_date` als `TT.MM.JJJJ` (null → „Termin offen").
 
- **new_event:** Title `Neuer Ritt: {name}` · Body `{region} · {start_date}`
- **event_change, 1 Gruppe:**
  - status:    Body `Status: {status}`
  - documents: Body `Neue Dokumente verfügbar`
  - date:      Body `Termin geändert: {start_date}`
  - location:  Body `Veranstaltungsort aktualisiert`
  - distances: Body `Distanzen/Klassen aktualisiert`
  (Title jeweils `{name}`)
- **event_change, mehrere Gruppen:** Title `{name}` · Body `{n} Änderungen: {Labels nach Prio}`
  (z.B. `2 Änderungen: Status, Dokumente`)
Jede Notification: `category` entsprechend, `event_id = id`, `tag = id`, `url = vdd_url or Fallback`.
 
### Senden
- Liste leer → nichts senden, Exit 0.
- Sonst `POST {server}/notify` mit Header `X-Notify-Token`, Body `{"notifications":[...]}`.
- HTTP-Fehler nur loggen, Workflow **nicht** rot färben (Daten-Commit ist wichtiger). Exit 0 auch
  bei Push-Fehler, mit deutlicher Warnung.
- `requests` ist installiert.
### Tests (`test_notify_diff.py`, pytest)
1. neues Event (`rittvorrat==0`) → `new_event`.
2. `wiki_touched` unverändert → keine Notification.
3. nur `status` geändert → `event_change`, Body `Status: ...`.
4. `status`+`results_pdf` geändert → Body `2 Änderungen: Status, Dokumente`.
5. nur `organizer` geändert → keine Notification.
6. PDF gleicher Name → nichts; anderer Name → documents.
7. `lat` ändert sich um 1e-8 → keine location-Änderung (Toleranz).
8. `rittvorrat != 0`, `status` geändert → keine Notification (Gate).
9. `rittvorrat == 0`, neues Event → `new_event`.
10. `rittvorrat` fehlt/null → ignoriert.
11. `rittvorrat == "0"` (string) → wie 0 behandelt.
---
 
## Angepasster Workflow
 
```yaml
name: Update map
on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:
jobs:
  update:
    runs-on: ubuntu-24.04
    container: python:3.12-slim
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v5
 
      - run: pip install --quiet requests
 
      - name: Check for wiki changes
        id: check
        run: |
          result=$(python vdd_scrape.py --check-only)
          echo "changed=$result" >> "$GITHUB_OUTPUT"
 
      - name: Snapshot old data
        if: steps.check.outputs.changed == 'true'
        run: |
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
          if git show HEAD:data.min.json > old.min.json 2>/dev/null; then
            echo "old data saved"
          else
            echo "[]" > old.min.json
          fi
 
      - name: Run scraper
        if: steps.check.outputs.changed == 'true'
        run: python vdd_scrape.py
 
      - name: Commit & push
        if: steps.check.outputs.changed == 'true'
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data.json data.min.json
          git diff --cached --quiet || (git commit -m "chore: auto-update data $(date -u +%Y-%m-%d)" && git push)
 
      - name: Send push notifications
        if: steps.check.outputs.changed == 'true'
        env:
          NOTIFY_TOKEN: ${{ secrets.NOTIFY_TOKEN }}
          PUSH_SERVER_URL: ${{ secrets.PUSH_SERVER_URL }}
        run: |
          python notify_diff.py --old old.min.json --new data.min.json --server "$PUSH_SERVER_URL"
```
 
### Wichtige Details
- **`safe.directory`** nötig, sonst „dubious ownership" bei `git show` im Container.
- **„Snapshot old data" vor „Run scraper"**, sonst vergleicht man Neu mit Neu.
- **Erster Lauf:** `old.min.json = []` → alle aktuellen Events wären `new_event`. Real meist
  unkritisch, weil zu dem Zeitpunkt kaum Abonnenten existieren und der Server an 0 passende Subs
  sendet. Wer ganz sicher gehen will: ersten Lauf mit `--dry-run`.
- **Notify-Fehler bricht den Workflow nicht.**
---
 
## Akzeptanzkriterien
 
- [ ] `notify_diff.py` erzeugt Notifications mit `category` + `event_id` laut Schema.
- [ ] `rittvorrat == 0` (neuer Stand, akzeptiert int 0 und "0") ist Vor-Gate; sonst nie Notification.
- [ ] `wiki_touched` ist striktes Gate für `event_change`.
- [ ] PDF-Dateinamen-Vergleich, `lat`/`lon`-Toleranz, stille Felder wie spezifiziert.
- [ ] Keine Sammel-Notification; eine Notification pro betroffenem Event.
- [ ] Alle `test_notify_diff.py`-Fälle grün.
- [ ] Workflow sichert alten Stand vor dem Scrape; sendet nur bei `changed == 'true'`.
- [ ] Push-Fehler färben den Workflow nicht rot.
- [ ] `NOTIFY_TOKEN` / `PUSH_SERVER_URL` als GitHub Secrets dokumentiert.
 

