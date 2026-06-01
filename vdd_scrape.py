import requests
import sqlite3
import time
import re
from datetime import datetime, timezone

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "VDD-Distanzwettbewerbe-Scraper/1.0 (giese.timo@gmail.com)"}

API_URL = "https://vdd-aktuell.de/mediawiki/api.php"

PROPS = (
    "|?Startdatum#ISO"
    "|?Enddatum#ISO"
    "|?Ritt-Name"
    "|?Untertitel"
    "|?Region"
    "|?Veranstaltungsland"
    "|?Veranstaltungsort"
    "|?Koordinaten"
    "|?Veranstalter"
    "|?Organisator"
    "|?Schirmherr"
    "|?Ritt-Arten"
    "|?EFR"
    "|?KDR"
    "|?MDR"
    "|?LDR"
    "|?MTR"
    "|?CEI"
    "|?Ausschreibung"
    "|?Ausschreibung_aktualisiert"
    "|?Ergebnisliste"
    "|?Nennform"
    "|?Termin"
    "|?Erstveranstaltung"
    "|?Mehrtägig"
    "|?Website"
    "|sort=Startdatum"
    "|order=ascending"
)

QUERY_ACTIVE   = "[[Veranstaltungsland::Deutschland]][[Kategorie:Ritt in 2026]][[Freigeschaltet::Ja]]"  + PROPS
QUERY_VORRAT   = "[[Kategorie:Ritt in 2026]][[Freigeschaltet::Nein]]" + PROPS

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_title                  TEXT UNIQUE,
    wiki_url                    TEXT,
    vdd_url                     TEXT,
    name                        TEXT,
    subtitle                    TEXT,
    start_date                  TEXT,
    end_date                    TEXT,
    multi_day                   INTEGER,
    region                      TEXT,
    country                     TEXT,
    venue                       TEXT,
    lat                         REAL,
    lon                         REAL,
    geocoded                    INTEGER DEFAULT 0,
    organizer                   TEXT,
    contact                     TEXT,
    patron                      TEXT,
    event_types                 TEXT,
    efr                         TEXT,
    kdr                         TEXT,
    mdr                         TEXT,
    ldr                         TEXT,
    mtr                         TEXT,
    cei                         TEXT,
    announcement_pdf            TEXT,
    announcement_updated        INTEGER,
    results_pdf                 TEXT,
    registration_pdf            TEXT,
    status                      TEXT,
    first_edition_year          INTEGER,
    website                     TEXT,
    rittvorrat                  INTEGER DEFAULT 0,
    fetched_at                  TEXT DEFAULT (datetime('now'))
)
"""


def wiki_title_to_vdd_url(wiki_title):
    """Convert 'Über die Alb 2026' -> 'https://vdd-aktuell.de/ritt/Ueber-die-Alb-2026/'"""
    if not wiki_title:
        return None
    slug = wiki_title
    for old, new in [
        ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"),
        ("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
        ("ß", "ss"),
    ]:
        slug = slug.replace(old, new)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-")
    return f"https://vdd-aktuell.de/ritt/{slug}/"


def address_parts(raw):
    """Split a raw SMW address into non-empty, non-email lines."""
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"\n+", raw) if p.strip()]
    return [p for p in parts if "@" not in p and len(p) > 2]


def extract_postcode_city(raw):
    """Try to pull 'XXXXX Cityname' out of a raw address string."""
    if not raw:
        return None
    m = re.search(r"\b(\d{5})\s+(\S.*)", raw)
    return f"{m.group(1)} {m.group(2).split(',')[0].strip()}" if m else None


def _nominatim(q):
    """Single Nominatim request; returns (lat, lon) or (None, None)."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "de"},
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"    Nominatim error: {e}")
    return None, None


def nominatim_geocode(venue, organizer, region=None):
    """Try progressively simpler queries; return (lat, lon) or (None, None)."""
    queries = []

    # 1. Full venue address
    parts = address_parts(venue)
    if parts:
        queries.append(", ".join(parts) + ", Deutschland")

    # 2. Postal code + city from venue (Nominatim handles these well)
    pc = extract_postcode_city(venue)
    if pc:
        queries.append(pc + ", Deutschland")

    # 3. Organizer address lines, skip first line (usually the name)
    org_parts = address_parts(organizer)
    if len(org_parts) > 1:
        queries.append(", ".join(org_parts[1:]) + ", Deutschland")

    # 4. Postal code from organizer
    pc_org = extract_postcode_city(organizer)
    if pc_org and pc_org != pc:
        queries.append(pc_org + ", Deutschland")

    # 5. Just the raw postal code alone (most reliable fallback)
    for raw in (venue, organizer):
        m = re.search(r"\b(\d{5})\b", raw or "")
        if m:
            queries.append(m.group(1) + ", Deutschland")

    seen = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        print(f"    querying: {q!r}")
        lat, lon = _nominatim(q)
        time.sleep(1.1)
        if lat:
            return lat, lon

    return None, None


def fetch_all_events(query):
    events = []
    offset = 0
    limit = 500

    while True:
        params = {
            "action": "ask",
            "query": f"{query}|limit={limit}|offset={offset}",
            "format": "json",
            "formatversion": "2",
        }
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("query", {}).get("results", {})
        if not results:
            break

        events.extend(results.values())

        meta = data.get("query", {}).get("meta", {})
        count = int(meta.get("count", 0))
        print(f"  offset={offset}: got {count} (total so far: {len(events)})")
        if count < limit:
            break
        offset += limit

    return events


def first(lst, default=None):
    return lst[0] if lst else default


def join_list(lst):
    return ", ".join(str(x) for x in lst) if lst else None


def ts_to_date(entry):
    if not entry:
        return None
    ts = entry.get("timestamp")
    if ts:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    # raw format: "1/2026/9/26"
    parts = entry.get("raw", "").split("/")
    if len(parts) >= 4:
        return f"{parts[1]}-{int(parts[2]):02d}-{int(parts[3]):02d}"
    return None


def bool_val(lst):
    v = first(lst)
    if v is None:
        return None
    return 1 if str(v).lower() in ("t", "true", "1", "yes") else 0


def first_year(lst):
    v = first(lst)
    if not v:
        return None
    # raw format may be "1/2017" or just "2017"
    if isinstance(v, dict):
        raw = v.get("raw", "")
        parts = raw.split("/")
        return int(parts[1]) if len(parts) >= 2 else None
    try:
        return int(str(v).split("/")[-1])
    except ValueError:
        return None


def parse_event(raw):
    p = raw.get("printouts", {})

    coords = first(p.get("Koordinaten", []))
    lat = coords.get("lat") if coords else None
    lon = coords.get("lon") if coords else None

    return {
        "wiki_title":           raw.get("fulltext"),
        "wiki_url":             raw.get("fullurl"),
        "vdd_url":              wiki_title_to_vdd_url(raw.get("fulltext")),
        "name":                 first(p.get("Ritt-Name", [])),
        "subtitle":             first(p.get("Untertitel", [])),
        "start_date":           ts_to_date(first(p.get("Startdatum", []))),
        "end_date":             ts_to_date(first(p.get("Enddatum", []))),
        "multi_day":            bool_val(p.get("Mehrtägig", [])),
        "region":               first(p.get("Region", [])),
        "country":              first(p.get("Veranstaltungsland", [])),
        "venue":                first(p.get("Veranstaltungsort", [])),
        "lat":                  lat,
        "lon":                  lon,
        "organizer":            first(p.get("Veranstalter", [])),
        "contact":              first(p.get("Organisator", [])),
        "patron":               first(p.get("Schirmherr", [])),
        "event_types":          join_list(p.get("Ritt-Arten", [])),
        "efr":                  join_list(p.get("EFR", [])),
        "kdr":                  join_list(p.get("KDR", [])),
        "mdr":                  join_list(p.get("MDR", [])),
        "ldr":                  join_list(p.get("LDR", [])),
        "mtr":                  join_list(p.get("MTR", [])),
        "cei":                  join_list(p.get("CEI", [])),
        "announcement_pdf":     join_list(p.get("Ausschreibung", [])),
        "announcement_updated": bool_val(p.get("Ausschreibung_aktualisiert", [])),
        "results_pdf":          join_list(p.get("Ergebnisliste", [])),
        "registration_pdf":     join_list(p.get("Nennform", [])),
        "status":               first(p.get("Termin", [])),
        "first_edition_year":   first_year(p.get("Erstveranstaltung", [])),
        "website":              first(p.get("Website", [])),
    }


def main():
    db_path = "vdd_events.db"

    print("Fetching active events (Freigeschaltet=Ja)...")
    active_events = fetch_all_events(QUERY_ACTIVE)
    print(f"  {len(active_events)} active events")

    print("Fetching Rittvorrat events (Freigeschaltet=Nein)...")
    vorrat_events = fetch_all_events(QUERY_VORRAT)
    print(f"  {len(vorrat_events)} Rittvorrat events")

    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS events")
    con.execute(SCHEMA)
    con.commit()

    cols = [
        "wiki_title", "wiki_url", "vdd_url", "name", "subtitle", "start_date", "end_date",
        "multi_day", "region", "country", "venue", "lat", "lon", "geocoded",
        "organizer", "contact", "patron", "event_types",
        "efr", "kdr", "mdr", "ldr", "mtr", "cei",
        "announcement_pdf", "announcement_updated", "results_pdf",
        "registration_pdf", "status", "first_edition_year", "website", "rittvorrat",
    ]
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "wiki_title")
    sql = (
        f"INSERT INTO events ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(wiki_title) DO UPDATE SET {updates}"
    )

    for raw in active_events:
        event = parse_event(raw)
        event["geocoded"] = 0
        event["rittvorrat"] = 0
        con.execute(sql, event)

    for raw in vorrat_events:
        event = parse_event(raw)
        event["geocoded"] = 0
        event["rittvorrat"] = 1
        con.execute(sql, event)

    con.commit()

    # Nominatim geocoding for events still missing coordinates
    missing = con.execute(
        "SELECT id, name, venue, organizer, region FROM events WHERE lat IS NULL"
    ).fetchall()

    if missing:
        print(f"\nGeocoding {len(missing)} events via Nominatim ...")
        for row_id, name, venue, organizer, region in missing:
            if not venue and not organizer:
                print(f"  [{name}] no address -- skipping")
                continue
            print(f"  [{name}]")
            lat, lon = nominatim_geocode(venue, organizer, region)
            if lat:
                con.execute(
                    "UPDATE events SET lat=?, lon=?, geocoded=1 WHERE id=?",
                    (lat, lon, row_id),
                )
                print(f"    -> {lat:.5f}, {lon:.5f}")
            else:
                print(f"    -> no result")
        con.commit()

    total, with_coords, geocoded, with_venue, vorrat = con.execute(
        "SELECT COUNT(*), COUNT(lat), SUM(geocoded), COUNT(venue), SUM(rittvorrat) FROM events"
    ).fetchone()
    con.close()

    print(f"\nSaved {total} events to {db_path}")
    print(f"  {with_coords}/{total} have coordinates ({geocoded} geocoded via Nominatim)")
    print(f"  {with_venue}/{total} have venue address")
    print(f"  {vorrat} Rittvorrat events")


if __name__ == "__main__":
    main()
