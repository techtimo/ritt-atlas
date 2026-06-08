"""Tests for notify_diff.py — compute_notifications logic."""

import pytest
from notify_diff import compute_notifications

TOUCHED_OLD = "2026-01-01T00:00:00Z"
TOUCHED_NEW = "2026-02-01T00:00:00Z"
VDD_URL = "https://vdd-aktuell.de/ritt/Test/"


def base_event(**overrides):
    e = {
        "id": "Test Ritt 2026",
        "name": "Test Ritt",
        "region": "Bayern",
        "start_date": "2026-06-01",
        "end_date": None,
        "multi_day": 0,
        "status": "steht fest",
        "venue": "Musterplatz 1",
        "lat": 48.1,
        "lon": 11.5,
        "efr": "26",
        "kdr": None,
        "mdr": None,
        "ldr": None,
        "mtr": None,
        "cei": None,
        "announcement_pdf": None,
        "results_pdf": None,
        "registration_pdf": None,
        "announcement_updated": None,
        "organizer": "Max Mustermann",
        "vdd_url": VDD_URL,
        "rittvorrat": 0,
        "wiki_touched": TOUCHED_OLD,
    }
    e.update(overrides)
    return e


# 1. New event with rittvorrat==0 → new_event notification
def test_new_event_rittvorrat_zero():
    new = base_event()
    result = compute_notifications([], [new])
    assert len(result) == 1
    assert result[0]["category"] == "new_event"
    assert result[0]["event_id"] == "Test Ritt 2026"
    assert "Test Ritt" in result[0]["title"]


# 2. wiki_touched unchanged → no notification
def test_no_notification_when_wiki_touched_unchanged():
    old = base_event()
    new = base_event(status="abgesagt")  # changed field, but same wiki_touched
    result = compute_notifications([old], [new])
    assert result == []


# 3. Only status changed → event_change with body "Status: ..."
def test_status_changed():
    old = base_event()
    new = base_event(status="abgesagt", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["category"] == "event_change"
    assert result[0]["body"] == "Status: abgesagt"


# 4. status + results_pdf changed → "2 Änderungen: Status, Ergebnisliste"
def test_status_and_results_changed():
    old = base_event()
    new = base_event(status="abgesagt", results_pdf="ergebnis.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "2 Änderungen: Status, Ergebnisliste"


# 5. Only organizer changed → no notification (silent field)
def test_silent_field_no_notification():
    old = base_event()
    new = base_event(organizer="Neuer Mensch", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert result == []


# 6a. PDF same filename → no notification
def test_pdf_same_name_no_notification():
    old = base_event(announcement_pdf="ausschreibung.pdf")
    new = base_event(announcement_pdf="ausschreibung.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert result == []


# 6b. announcement_pdf different filename → Ausschreibung notification
def test_announcement_pdf_changed():
    old = base_event(announcement_pdf="alt.pdf")
    new = base_event(announcement_pdf="neu.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Ausschreibung aktualisiert"


# 6c. results_pdf added → Ergebnisliste notification
def test_results_pdf_added():
    old = base_event(results_pdf=None)
    new = base_event(results_pdf="ergebnis.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Ergebnisliste verfügbar"


# 6d. registration_pdf added → Nennformular notification
def test_registration_pdf_added():
    old = base_event(registration_pdf=None)
    new = base_event(registration_pdf="nennformular.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Nennformular aktualisiert"


# 6e. announcement + results both changed → "2 Änderungen: Ausschreibung, Ergebnisliste"
def test_announcement_and_results_changed():
    old = base_event()
    new = base_event(announcement_pdf="neu.pdf", results_pdf="ergebnis.pdf", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "2 Änderungen: Ausschreibung, Ergebnisliste"


# 7. lat changes by 1e-8 → no location notification (within tolerance)
def test_lat_within_tolerance_no_notification():
    old = base_event(lat=48.1000000)
    new = base_event(lat=48.1000000 + 1e-8, wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert result == []


# 8. rittvorrat != 0 with status changed → no notification (gate)
def test_rittvorrat_nonzero_gate():
    old = base_event()
    new = base_event(status="abgesagt", wiki_touched=TOUCHED_NEW, rittvorrat=1)
    result = compute_notifications([old], [new])
    assert result == []


# 9. rittvorrat == 0 (explicit int), new event → new_event
def test_rittvorrat_zero_int_new_event():
    new = base_event(rittvorrat=0)
    result = compute_notifications([], [new])
    assert len(result) == 1
    assert result[0]["category"] == "new_event"


# 10. rittvorrat missing/None → ignored
def test_rittvorrat_missing_ignored():
    new = base_event()
    del new["rittvorrat"]
    result = compute_notifications([], [new])
    assert result == []


def test_rittvorrat_none_ignored():
    new = base_event(rittvorrat=None)
    result = compute_notifications([], [new])
    assert result == []


# 11. rittvorrat == "0" (string) → treated as 0 → new_event
def test_rittvorrat_string_zero():
    new = base_event(rittvorrat="0")
    result = compute_notifications([], [new])
    assert len(result) == 1
    assert result[0]["category"] == "new_event"


# Additional: lat changes significantly → location notification
def test_lat_exceeds_tolerance_location_notification():
    old = base_event(lat=48.1)
    new = base_event(lat=49.0, wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Veranstaltungsort aktualisiert"


# Additional: url falls back to FALLBACK_URL when vdd_url is empty
def test_url_fallback():
    from notify_diff import FALLBACK_URL
    new = base_event(vdd_url=None)
    result = compute_notifications([], [new])
    assert len(result) == 1
    assert result[0]["url"] == FALLBACK_URL


# Additional: event with no id is skipped
def test_event_without_id_skipped():
    new = base_event()
    del new["id"]
    result = compute_notifications([], [new])
    assert result == []


# Additional: correct new_event body format (region · date)
def test_new_event_body_format():
    new = base_event(region="Weser-Ems", start_date="2026-06-01")
    result = compute_notifications([], [new])
    assert result[0]["body"] == "Weser-Ems · 01.06.2026"


# bemerkung changed → Bemerkung notification
def test_bemerkung_changed():
    old = base_event(bemerkung=None)
    new = base_event(bemerkung="Neuer Hinweis", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Bemerkung aktualisiert"


# Additional: date change notification
def test_date_changed():
    old = base_event()
    new = base_event(start_date="2026-07-15", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Termin geändert: 15.07.2026"


# Additional: distances change notification
def test_distances_changed():
    old = base_event()
    new = base_event(efr="30", wiki_touched=TOUCHED_NEW)
    result = compute_notifications([old], [new])
    assert len(result) == 1
    assert result[0]["body"] == "Distanzen/Klassen aktualisiert"
