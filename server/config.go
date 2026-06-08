package main

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Port            string
	DBPath          string
	VAPIDPublicKey  string
	VAPIDPrivateKey string
	VAPIDSubscriber string
	NotifyToken     string
	AllowedOrigins  []string
	PushTTL         int
}

func loadConfig() Config {
	ttl := 86400
	if v := os.Getenv("PUSH_TTL"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			ttl = n
		}
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	return Config{
		Port:            port,
		DBPath:          envOr("DB_PATH", "push.db"),
		VAPIDPublicKey:  os.Getenv("VAPID_PUBLIC_KEY"),
		VAPIDPrivateKey: os.Getenv("VAPID_PRIVATE_KEY"),
		VAPIDSubscriber: os.Getenv("VAPID_SUBSCRIBER"),
		NotifyToken:     os.Getenv("NOTIFY_TOKEN"),
		AllowedOrigins:  strings.Split(envOr("ALLOWED_ORIGIN", "*"), ","),
		PushTTL:         ttl,
	}
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
