#!/usr/bin/env python3
"""Compute diff between old and new VDD event data and send push notifications."""

import argparse
import datetime
import json
import os
import sys

import requests

FALLBACK_URL = "https://techtimo.github.io/vdd-rittatlas/"

# Ordered by priority (ascending). Only these groups trigger notifications.
FIELD_GROUPS = [
    ("status",    ["status"],                                                           1, "Status"),
    ("documents", ["announcement_pdf", "results_pdf", "registration_pdf",
                   "announcement_updated"],                                             2, "Dokumente"),
    ("date",      ["start_date", "end_date", "multi_day"],                             3, "Termin"),
    ("location",  ["venue", "lat", "lon"],                                             4, "Ort"),
    ("distances", ["efr", "kdr", "mdr", "ldr", "mtr", "cei"],                         5, "Distanzen"),
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
        if group_name == "documents":
            return "Neue Dokumente verfügbar"
        if group_name == "date":
            return f"Termin geändert: {format_date(event.get('start_date'))}"
        if group_name == "location":
            return "Veranstaltungsort aktualisiert"
        if group_name == "distances":
            return "Distanzen/Klassen aktualisiert"
        return f"{label} aktualisiert"
    labels = [g[1] for g in changed_groups]
    return f"{len(changed_groups)} Änderungen: {', '.join(labels)}"


def build_event_change_notification(event, changed_groups):
    event_id = event["id"]
    return {
        "category": "event_change",
        "event_id": event_id,
        "title": event.get("name", event_id),
        "body": build_event_change_body(event, changed_groups),
        "url": event.get("vdd_url") or FALLBACK_URL,
        "tag": event_id,
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
        "url": event.get("vdd_url") or FALLBACK_URL,
        "tag": event_id,
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
