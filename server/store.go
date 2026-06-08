package main

import (
	"database/sql"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type Store struct {
	db *sql.DB
}

func NewStore(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec("PRAGMA foreign_keys = ON"); err != nil {
		db.Close()
		return nil, err
	}
	if err := migrate(db); err != nil {
		db.Close()
		return nil, err
	}
	return &Store{db: db}, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

func migrate(db *sql.DB) error {
	_, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS subscriptions (
			endpoint           TEXT PRIMARY KEY,
			p256dh             TEXT NOT NULL,
			auth               TEXT NOT NULL,
			notify_new_events  INTEGER NOT NULL DEFAULT 0,
			notify_all_changes INTEGER NOT NULL DEFAULT 0,
			created_at         TEXT NOT NULL,
			updated_at         TEXT NOT NULL
		);
		CREATE TABLE IF NOT EXISTS subscription_favorites (
			endpoint  TEXT NOT NULL,
			event_id  TEXT NOT NULL,
			PRIMARY KEY (endpoint, event_id),
			FOREIGN KEY (endpoint) REFERENCES subscriptions(endpoint) ON DELETE CASCADE
		);
		CREATE INDEX IF NOT EXISTS idx_fav_event ON subscription_favorites(event_id);
	`)
	return err
}

// Upsert creates or updates a subscription including preferences and favorites.
// Returns created=true if the endpoint was new.
func (s *Store) Upsert(sub Subscription) (created bool, err error) {
	now := time.Now().UTC().Format(time.RFC3339)
	tx, err := s.db.Begin()
	if err != nil {
		return false, err
	}
	defer tx.Rollback()

	var dummy int
	scanErr := tx.QueryRow("SELECT 1 FROM subscriptions WHERE endpoint = ?", sub.Endpoint).Scan(&dummy)
	created = scanErr == sql.ErrNoRows

	if created {
		_, err = tx.Exec(
			`INSERT INTO subscriptions(endpoint, p256dh, auth, notify_new_events, notify_all_changes, created_at, updated_at)
			 VALUES (?, ?, ?, ?, ?, ?, ?)`,
			sub.Endpoint, sub.Keys.P256dh, sub.Keys.Auth,
			sub.NotifyNewEvents, sub.NotifyAllChanges, now, now,
		)
	} else {
		_, err = tx.Exec(
			`UPDATE subscriptions SET p256dh=?, auth=?, notify_new_events=?, notify_all_changes=?, updated_at=?
			 WHERE endpoint=?`,
			sub.Keys.P256dh, sub.Keys.Auth,
			sub.NotifyNewEvents, sub.NotifyAllChanges, now, sub.Endpoint,
		)
	}
	if err != nil {
		return false, err
	}

	if err := replaceFavorites(tx, sub.Endpoint, sub.Favorites); err != nil {
		return false, err
	}

	return created, tx.Commit()
}

// UpdatePreferences updates preferences and favorites for an existing subscription.
// Returns found=false if the endpoint is unknown.
func (s *Store) UpdatePreferences(endpoint string, notifyNew, notifyAll bool, favorites []string) (found bool, err error) {
	now := time.Now().UTC().Format(time.RFC3339)
	tx, err := s.db.Begin()
	if err != nil {
		return false, err
	}
	defer tx.Rollback()

	res, err := tx.Exec(
		`UPDATE subscriptions SET notify_new_events=?, notify_all_changes=?, updated_at=? WHERE endpoint=?`,
		notifyNew, notifyAll, now, endpoint,
	)
	if err != nil {
		return false, err
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return false, nil
	}

	if err := replaceFavorites(tx, endpoint, favorites); err != nil {
		return false, err
	}

	return true, tx.Commit()
}

// Delete removes a subscription and its favorites (via CASCADE).
func (s *Store) Delete(endpoint string) error {
	_, err := s.db.Exec("DELETE FROM subscriptions WHERE endpoint=?", endpoint)
	return err
}

// DeleteBatch removes multiple subscriptions in one statement.
func (s *Store) DeleteBatch(endpoints []string) error {
	if len(endpoints) == 0 {
		return nil
	}
	placeholders := strings.Repeat("?,", len(endpoints))
	placeholders = placeholders[:len(placeholders)-1]
	args := make([]any, len(endpoints))
	for i, ep := range endpoints {
		args[i] = ep
	}
	_, err := s.db.Exec("DELETE FROM subscriptions WHERE endpoint IN ("+placeholders+")", args...)
	return err
}

// All loads every subscription with its preferences and favorites.
func (s *Store) All() ([]Subscription, error) {
	rows, err := s.db.Query(`
		SELECT s.endpoint, s.p256dh, s.auth, s.notify_new_events, s.notify_all_changes,
		       COALESCE(GROUP_CONCAT(f.event_id, '|||'), '') AS favs
		FROM subscriptions s
		LEFT JOIN subscription_favorites f ON s.endpoint = f.endpoint
		GROUP BY s.endpoint
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var subs []Subscription
	for rows.Next() {
		var sub Subscription
		var notifyNew, notifyAll int
		var favStr string
		if err := rows.Scan(&sub.Endpoint, &sub.Keys.P256dh, &sub.Keys.Auth, &notifyNew, &notifyAll, &favStr); err != nil {
			return nil, err
		}
		sub.NotifyNewEvents = notifyNew == 1
		sub.NotifyAllChanges = notifyAll == 1
		if favStr != "" {
			sub.Favorites = strings.Split(favStr, "|||")
		}
		subs = append(subs, sub)
	}
	return subs, rows.Err()
}

func replaceFavorites(tx *sql.Tx, endpoint string, favorites []string) error {
	if _, err := tx.Exec("DELETE FROM subscription_favorites WHERE endpoint=?", endpoint); err != nil {
		return err
	}
	for _, fav := range favorites {
		if fav == "" {
			continue
		}
		if _, err := tx.Exec("INSERT INTO subscription_favorites(endpoint, event_id) VALUES (?, ?)", endpoint, fav); err != nil {
			return err
		}
	}
	return nil
}
