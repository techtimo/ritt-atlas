#!/usr/bin/env python3
"""Compute diff between old and new VDD event data and send push notifications."""

import argparse
import datetime
import json
import os
import sys
import urllib.parse

import requests

SITE_URL = "https://techtimo.github.io/vdd-rittatlas/"

ICON_ACTION = SITE_URL + "favicon.svg"
WIKI_FILE = "https://vdd-aktuell.de/mediawiki/index.php?title=Special:Redirect/file/"

DOC_GROUPS = [
    ("announcement", "announcement_pdf", "Ausschreibung"),
    ("results",      "results_pdf",      "Ergebnisliste"),
    ("registration", "registration_pdf", "Nennformular"),
]
ACTION_OPEN = {"action": "open", "title": "Zum Ritt", "icon": ICON_ACTION}

# Ordered by priority (ascending). Only these groups trigger notifications.
FIELD_GROUPS = [
    ("status",       ["status"],                                1, "Status"),
    ("announcement", ["announcement_pdf", "announcement_updated"], 2, "Ausschreibung"),
    ("results",      ["results_pdf"],                           3, "Ergebnisliste"),
    ("registration", ["registration_pdf"],                      4, "Nennformular"),
    ("bemerkung",    ["bemerkung"],                              5, "Bemerkung"),
    ("date",         ["start_date", "end_date", "multi_day"],   6, "Termin"),
    ("location",     ["venue", "lat", "lon"],                   7, "Ort"),
    ("distances",    ["efr", "kdr", "mdr", "ldr", "mtr", "cei"], 8, "Distanzen"),
]

LAT_LON_FIELDS = {"lat", "lon"}
LAT_LON_TOLERANCE = 1e-6


def is_rittvorrat_zero(event):
    v = event.get("rittvorrat")
    if v is None:
        return False
    try:
        return int(v) == 0
    except (ValueError, TypeError):
        return False


def format_date(date_str):
    if not date_str:
        return "Termin offen"
    try:
        d = datetime.date.fromisoformat(date_str)
        return d.strftime("%d.%m.%Y")
    except ValueError:
        return date_str


def field_changed(field, old_val, new_val):
    if field in LAT_LON_FIELDS:
        try:
            return abs(float(old_val or 0) - float(new_val or 0)) >= LAT_LON_TOLERANCE
        except (ValueError, TypeError):
            return old_val != new_val
    return old_val != new_val


def get_changed_groups(old_event, new_event):
    changed = []
    for group_name, fields, prio, label in FIELD_GROUPS:
        for f in fields:
            if field_changed(f, old_event.get(f), new_event.get(f)):
                changed.append((prio, label, group_name))
                break
    return changed  # already in priority order due to FIELD_GROUPS ordering


def build_event_change_body(event, changed_groups):
    if len(changed_groups) == 1:
        _, label, group_name = changed_groups[0]
        if group_name == "status":
            return f"Status: {event.get('status', '')}"
        if group_name == "announcement":
            return "Die Ausschreibung wurde aktualisiert"
        if group_name == "results":
            return "Die Ergebnisliste ist verfügbar"
        if group_name == "registration":
            return "Das Nennformular wurde aktualisiert"
        if group_name == "bemerkung":
            return "Die Bemerkung wurde aktualisiert"
        if group_name == "date":
            return f"Der Termin geändert: {format_date(event.get('start_date'))}"
        if group_name == "location":
            return "Veranstaltungsort aktualisiert"
        if group_name == "distances":
            return "Distanzen/Klassen aktualisiert"
        return f"{label} aktualisiert"
    labels = [g[1] for g in changed_groups]
    return f"{len(changed_groups)} Änderungen: {', '.join(labels)}"


def build_event_change_notification(event, changed_groups):
    event_id = event["id"]
    group_names = {g[2] for g in changed_groups}
    event_url = SITE_URL + "#" + urllib.parse.quote(event_id)
    pdf_doc_urls = {
        group: WIKI_FILE + urllib.parse.quote(event[field], safe="")
        for group, field, _ in DOC_GROUPS
        if group in group_names and event.get(field)
    }
    # "open" lets the SW resolve "Zum Ritt" to the event page via doc_urls
    doc_urls = {**pdf_doc_urls, "open": event_url}
    actions = [
        {"action": group, "title": label, "icon": ICON_ACTION}
        for group, _, label in DOC_GROUPS
        if group in pdf_doc_urls
    ]
    if len(actions) < 2:
        actions.append(ACTION_OPEN)
    # For single-PDF notifications put the redirect URL as the body-tap target
    # so tapping anywhere on the notification opens the PDF, not just the action button.
    if len(pdf_doc_urls) == 1:
        primary_pdf = next(iter(pdf_doc_urls.values()))
        url = SITE_URL + "redirect.html?url=" + urllib.parse.quote(primary_pdf, safe="")
    else:
        url = event_url
    return {
        "category": "event_change",
        "event_id": event_id,
        "title": event.get("name", event_id),
        "body": build_event_change_body(event, changed_groups),
        "url": url,
        "tag": event_id,
        "actions": actions,
        "doc_urls": doc_urls,
    }


def build_new_event_notification(event):
    event_id = event["id"]
    region = event.get("region", "")
    start_date = format_date(event.get("start_date"))
    return {
        "category": "new_event",
        "event_id": event_id,
        "title": f"Neuer Ritt: {event.get('name', event_id)}",
        "body": f"{region} · {start_date}",
        "url": SITE_URL + "#" + urllib.parse.quote(event_id),
        "tag": event_id,
        "actions": [ACTION_OPEN],
    }


def compute_notifications(old_events, new_events):
    old_by_id = {e["id"]: e for e in old_events if "id" in e}
    notifications = []

    for event in new_events:
        event_id = event.get("id")
        if not event_id:
            continue

        # Gate 0: ignore rittvorrat entries
        if not is_rittvorrat_zero(event):
            continue

        # New event
        if event_id not in old_by_id:
            notifications.append(build_new_event_notification(event))
            continue

        old_event = old_by_id[event_id]

        # wiki_touched gate
        if event.get("wiki_touched") == old_event.get("wiki_touched"):
            continue

        changed_groups = get_changed_groups(old_event, event)
        if not changed_groups:
            continue

        notifications.append(build_event_change_notification(event, changed_groups))

    return notifications


def load_events(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("events", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def send_notifications(server_url, token, notifications, dry_run=False):
    if not notifications:
        print("No notifications to send.")
        return

    if dry_run:
        print(f"[dry-run] Would send {len(notifications)} notification(s):")
        for n in notifications:
            print(f"  [{n['category']}] {n['title']}: {n['body']}")
        return

    url = f"{server_url.rstrip('/')}/notify"
    try:
        resp = requests.post(
            url,
            json={"notifications": notifications},
            headers={"X-Notify-Token": token},
            timeout=30,
        )
        if resp.status_code != 200:
            print(
                f"WARNING: push server returned {resp.status_code}: {resp.text}",
                file=sys.stderr,
            )
        else:
            print(f"Sent {len(notifications)} notification(s): {resp.text}")
    except Exception as exc:
        print(f"WARNING: failed to reach push server: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--server", default=os.environ.get("PUSH_SERVER_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("NOTIFY_TOKEN", "")

    old_events = load_events(args.old)
    new_events = load_events(args.new)

    notifications = compute_notifications(old_events, new_events)

    if not args.dry_run and not args.server:
        print(
            "WARNING: no --server URL and PUSH_SERVER_URL not set; skipping send.",
            file=sys.stderr,
        )
        return

    send_notifications(args.server, token, notifications, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
