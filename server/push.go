package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"log"
	"net/http"
	"sync"

	webpush "github.com/SherClockHolmes/webpush-go"
)

type pushPayload struct {
	Title   string               `json:"title"`
	Body    string               `json:"body"`
	URL     string               `json:"url"`
	Tag     string               `json:"tag"`
	Actions []NotificationAction `json:"actions,omitempty"`
	DocURLs map[string]string    `json:"doc_urls,omitempty"`
}

func resolveURL(u string) string {
	if u == "" {
		return "/"
	}
	return u
}

// sanitizeTopic returns a deterministic, base64url-encoded, ≤32-char collapse key for a given event ID.
func sanitizeTopic(eventID string) string {
	h := sha256.Sum256([]byte(eventID))
	s := base64.RawURLEncoding.EncodeToString(h[:])
	if len(s) > 32 {
		return s[:32]
	}
	return s
}

// sendNotifications fans out notifications to matching subscriptions.
// Returns delivered count, skipped-no-target count, dead endpoint list, and any fatal error.
func sendNotifications(cfg Config, subs []Subscription, notifs []Notification) (delivered, skippedNoTarget int, dead []string, err error) {
	type job struct {
		sub     Subscription
		payload []byte
		topic   string
	}

	var jobs []job
	for _, n := range notifs {
		p := pushPayload{Title: n.Title, Body: n.Body, URL: resolveURL(n.URL), Tag: n.Tag, Actions: n.Actions, DocURLs: n.DocURLs}
		payload, _ := json.Marshal(p)
		topic := sanitizeTopic(n.EventID)

		hasTarget := false
		for _, s := range subs {
			if shouldSend(n, s) {
				jobs = append(jobs, job{sub: s, payload: payload, topic: topic})
				hasTarget = true
			}
		}
		if !hasTarget {
			skippedNoTarget++
		}
	}

	type result struct {
		endpoint  string
		delivered bool
		dead      bool
	}

	results := make(chan result, len(jobs))
	sem := make(chan struct{}, 10)
	var wg sync.WaitGroup

	for _, j := range jobs {
		wg.Add(1)
		go func(j job) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			resp, sendErr := webpush.SendNotification(j.payload, &webpush.Subscription{
				Endpoint: j.sub.Endpoint,
				Keys: webpush.Keys{
					P256dh: j.sub.Keys.P256dh,
					Auth:   j.sub.Keys.Auth,
				},
			}, &webpush.Options{
				VAPIDPublicKey:  cfg.VAPIDPublicKey,
				VAPIDPrivateKey: cfg.VAPIDPrivateKey,
				Subscriber:      cfg.VAPIDSubscriber,
				TTL:             cfg.PushTTL,
				Topic:           j.topic,
			})

			if sendErr != nil {
				log.Printf("push send error for %s: %v", j.sub.Endpoint, sendErr)
				results <- result{endpoint: j.sub.Endpoint}
				return
			}
			defer resp.Body.Close()

			switch resp.StatusCode {
			case http.StatusNotFound, http.StatusGone:
				results <- result{endpoint: j.sub.Endpoint, dead: true}
			case http.StatusOK, http.StatusCreated:
				results <- result{endpoint: j.sub.Endpoint, delivered: true}
			default:
				log.Printf("push unexpected status %d for %s", resp.StatusCode, j.sub.Endpoint)
				results <- result{endpoint: j.sub.Endpoint}
			}
		}(j)
	}

	wg.Wait()
	close(results)

	deadSet := make(map[string]struct{})
	for r := range results {
		if r.delivered {
			delivered++
		}
		if r.dead {
			deadSet[r.endpoint] = struct{}{}
		}
	}

	dead = make([]string, 0, len(deadSet))
	for ep := range deadSet {
		dead = append(dead, ep)
	}

	return delivered, skippedNoTarget, dead, nil
}
