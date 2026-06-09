#!/usr/bin/env python3
"""Send a mock 'Ergebnisliste verfügbar' push notification for a real event.

Usage:
    NOTIFY_TOKEN=xxx python send_test_push.py [--event-id "Ritt Name 2026"]
"""
import argparse
import json
import os
import sys
import urllib.parse

import requests

from notify_diff import (
    SITE_URL, WIKI_FILE, ICON_ACTION, ACTION_OPEN,
    build_event_change_body, DOC_GROUPS,
)

PUSH_SERVER_URL = "https://vdd-rittatlas-server.fly.dev"


def load_events(path="data.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["events"] if isinstance(data, dict) else data


def find_event(events, event_id=None):
    if event_id:
        ev = next((e for e in events if e.get("id") == event_id), None)
        if not ev:
            sys.exit(f"Event '{event_id}' not found in data.json")
        return ev
    # pick first upcoming non-vorrat event that would realistically get results
    from datetime import date
    today = date.today().isoformat()
    candidates = [
        e for e in events
        if not e.get("rittvorrat")
        and (e.get("start_date") or "") <= today
        and e.get("id")
    ]
    if not candidates:
        candidates = [e for e in events if e.get("id")]
    return candidates[0]


def build_mock_notification(event):
    event_id = event["id"]
    fake_pdf = "Ergebnisliste_Mock_2026.pdf"
    pdf_url = WIKI_FILE + urllib.parse.quote(fake_pdf, safe="")
    event_url = SITE_URL + "#" + urllib.parse.quote(event_id)
    doc_urls = {
        "results": pdf_url,
        "open": event_url,
    }
    actions = [
        {"action": "results", "title": "Ergebnisliste", "icon": ICON_ACTION},
        ACTION_OPEN,
    ]
    return {
        "category": "event_change",
        "event_id": event_id,
        "title": event.get("name", event_id),
        "body": "Ergebnisliste verfügbar",
        "url": SITE_URL + "redirect.html?url=" + urllib.parse.quote(pdf_url, safe=""),
        "tag": event_id,
        "actions": actions,
        "doc_urls": doc_urls,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", help="Specific event id (default: auto-pick)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("NOTIFY_TOKEN", "")
    if not token and not args.dry_run:
        sys.exit("Set NOTIFY_TOKEN env var or use --dry-run")

    events = load_events()
    event = find_event(events, args.event_id)
    notif = build_mock_notification(event)

    print(f"Event : {event.get('name', event['id'])}")
    print(f"Body  : {notif['body']}")
    print(f"URL   : {notif['url']}")
    print(f"Actions: {[a['title'] for a in notif['actions']]}")
    print(f"DocURLs: {notif['doc_urls']}")

    if args.dry_run:
        print("\n[dry-run] not sending")
        return

    resp = requests.post(
        PUSH_SERVER_URL + "/notify",
        json={"notifications": [notif]},
        headers={"X-Notify-Token": token},
        timeout=30,
    )
    print(f"\nServer: {resp.status_code} {resp.text}")


if __name__ == "__main__":
    main()
