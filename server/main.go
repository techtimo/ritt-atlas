package main

import (
	"log"
	"net/http"
)

func main() {
	cfg := loadConfig()

	store, err := NewStore(cfg.DBPath)
	if err != nil {
		log.Fatalf("open store: %v", err)
	}
	defer store.Close()

	h := NewHandler(cfg, store)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", h.Health)
	mux.HandleFunc("/subscribe", h.cors(h.Subscribe))
	mux.HandleFunc("/preferences", h.cors(h.Preferences))
	mux.HandleFunc("/unsubscribe", h.cors(h.Unsubscribe))
	mux.HandleFunc("/notify", h.Notify)

	log.Printf("listening on :%s", cfg.Port)
	if err := http.ListenAndServe(":"+cfg.Port, mux); err != nil {
		log.Fatalf("server: %v", err)
	}
}
