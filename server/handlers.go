package main

import (
	"encoding/json"
	"log"
	"net/http"
)

type Handler struct {
	cfg   Config
	store *Store
}

func NewHandler(cfg Config, store *Store) *Handler {
	return &Handler{cfg: cfg, store: store}
}

func (h *Handler) cors(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		allowed := ""
		for _, o := range h.cfg.AllowedOrigins {
			if o == "*" || o == origin {
				allowed = o
				break
			}
		}
		if allowed != "" {
			w.Header().Set("Access-Control-Allow-Origin", allowed)
			w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			w.Header().Set("Vary", "Origin")
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

func (h *Handler) Health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

// subscribeRequest uses *bool pointers so missing fields can get default values.
type subscribeRequest struct {
	Endpoint string `json:"endpoint"`
	Keys     struct {
		P256dh string `json:"p256dh"`
		Auth   string `json:"auth"`
	} `json:"keys"`
	NotifyNewEvents  *bool    `json:"notify_new_events"`
	NotifyAllChanges *bool    `json:"notify_all_changes"`
	Favorites        []string `json:"favorites"`
}

func (h *Handler) Subscribe(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req subscribeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if req.Endpoint == "" || req.Keys.P256dh == "" || req.Keys.Auth == "" {
		http.Error(w, "missing required fields", http.StatusBadRequest)
		return
	}

	sub := Subscription{Endpoint: req.Endpoint}
	sub.Keys.P256dh = req.Keys.P256dh
	sub.Keys.Auth = req.Keys.Auth
	sub.NotifyNewEvents = ptrBoolOr(req.NotifyNewEvents, true)
	sub.NotifyAllChanges = ptrBoolOr(req.NotifyAllChanges, false)
	sub.Favorites = req.Favorites

	created, err := h.store.Upsert(sub)
	if err != nil {
		log.Printf("subscribe: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	if created {
		w.WriteHeader(http.StatusCreated)
	} else {
		w.WriteHeader(http.StatusOK)
	}
}

func (h *Handler) Preferences(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		Endpoint         string   `json:"endpoint"`
		NotifyNewEvents  bool     `json:"notify_new_events"`
		NotifyAllChanges bool     `json:"notify_all_changes"`
		Favorites        []string `json:"favorites"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if req.Endpoint == "" {
		http.Error(w, "missing endpoint", http.StatusBadRequest)
		return
	}

	found, err := h.store.UpdatePreferences(req.Endpoint, req.NotifyNewEvents, req.NotifyAllChanges, req.Favorites)
	if err != nil {
		log.Printf("preferences: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	if !found {
		http.Error(w, "subscription not found", http.StatusNotFound)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func (h *Handler) Unsubscribe(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req struct {
		Endpoint string `json:"endpoint"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if req.Endpoint == "" {
		http.Error(w, "missing endpoint", http.StatusBadRequest)
		return
	}
	if err := h.store.Delete(req.Endpoint); err != nil {
		log.Printf("unsubscribe: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func (h *Handler) Notify(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if r.Header.Get("X-Notify-Token") != h.cfg.NotifyToken {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	var req NotifyRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json")

	if len(req.Notifications) == 0 {
		json.NewEncoder(w).Encode(NotifyResponse{})
		return
	}

	subs, err := h.store.All()
	if err != nil {
		log.Printf("notify: load subs: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}

	delivered, skippedNoTarget, deadEps, err := sendNotifications(h.cfg, subs, req.Notifications)
	if err != nil {
		log.Printf("notify: send: %v", err)
	}

	if len(deadEps) > 0 {
		if err := h.store.DeleteBatch(deadEps); err != nil {
			log.Printf("notify: prune dead subs: %v", err)
		}
	}

	json.NewEncoder(w).Encode(NotifyResponse{
		Notifications:   len(req.Notifications),
		Subscriptions:   len(subs),
		Delivered:       delivered,
		SkippedNoTarget: skippedNoTarget,
		Pruned:          len(deadEps),
	})
}

func ptrBoolOr(p *bool, def bool) bool {
	if p != nil {
		return *p
	}
	return def
}
