package main

import (
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// --- sanitizeTopic tests ---

func TestSanitizeTopic_Deterministic(t *testing.T) {
	id := "Frühjahrsdistanz am Meer 2026"
	a := sanitizeTopic(id)
	b := sanitizeTopic(id)
	if a != b {
		t.Errorf("sanitizeTopic not deterministic: %q vs %q", a, b)
	}
}

func TestSanitizeTopic_MaxLength(t *testing.T) {
	ids := []string{"a", "very long event id that exceeds typical lengths for testing", "Herbstdistanz Eifel 2026"}
	for _, id := range ids {
		got := sanitizeTopic(id)
		if len(got) > 32 {
			t.Errorf("sanitizeTopic(%q) = %q (len %d), want ≤32", id, got, len(got))
		}
	}
}

func TestSanitizeTopic_Base64URL(t *testing.T) {
	topic := sanitizeTopic("test event")
	// base64url chars: A-Z a-z 0-9 - _  (no + / =)
	for _, c := range topic {
		if !strings.ContainsRune("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_", c) {
			t.Errorf("sanitizeTopic produced non-base64url char %q in %q", c, topic)
		}
	}
	// also verify it's valid base64url
	if _, err := base64.RawURLEncoding.DecodeString(topic); err != nil {
		t.Errorf("sanitizeTopic(%q) = %q is not valid base64url: %v", "test event", topic, err)
	}
}

func TestSanitizeTopic_DifferentIDs(t *testing.T) {
	a := sanitizeTopic("Ritt A 2026")
	b := sanitizeTopic("Ritt B 2026")
	if a == b {
		t.Errorf("different event IDs produced same topic: %q", a)
	}
}

// --- payload structure test ---

func TestResolveURL_EmptyFallsBack(t *testing.T) {
	if got := resolveURL(""); got != "/" {
		t.Errorf("resolveURL(\"\") = %q, want /", got)
	}
}

func TestResolveURL_NonEmptyPreserved(t *testing.T) {
	u := "https://example.com/event/123"
	if got := resolveURL(u); got != u {
		t.Errorf("resolveURL(%q) = %q, want unchanged", u, got)
	}
}

// --- /notify token auth test ---

func TestNotifyHandler_MissingToken_Returns401(t *testing.T) {
	store, err := NewStore(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer store.Close()

	cfg := Config{NotifyToken: "secret123", AllowedOrigins: []string{"*"}}
	h := NewHandler(cfg, store)

	body := `{"notifications":[]}`
	req := httptest.NewRequest(http.MethodPost, "/notify", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	// deliberately omit X-Notify-Token

	rr := httptest.NewRecorder()
	h.Notify(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

func TestNotifyHandler_WrongToken_Returns401(t *testing.T) {
	store, err := NewStore(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer store.Close()

	cfg := Config{NotifyToken: "secret123", AllowedOrigins: []string{"*"}}
	h := NewHandler(cfg, store)

	body := `{"notifications":[]}`
	req := httptest.NewRequest(http.MethodPost, "/notify", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Notify-Token", "wrong-token")

	rr := httptest.NewRecorder()
	h.Notify(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

func TestNotifyHandler_CorrectToken_EmptyList_Returns200(t *testing.T) {
	store, err := NewStore(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	defer store.Close()

	cfg := Config{NotifyToken: "secret123", AllowedOrigins: []string{"*"}}
	h := NewHandler(cfg, store)

	body := `{"notifications":[]}`
	req := httptest.NewRequest(http.MethodPost, "/notify", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Notify-Token", "secret123")

	rr := httptest.NewRecorder()
	h.Notify(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rr.Code)
	}
}
