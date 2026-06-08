package main

type Subscription struct {
	Endpoint string `json:"endpoint"`
	Keys     struct {
		P256dh string `json:"p256dh"`
		Auth   string `json:"auth"`
	} `json:"keys"`
	NotifyNewEvents  bool     `json:"notify_new_events"`
	NotifyAllChanges bool     `json:"notify_all_changes"`
	Favorites        []string `json:"favorites"`
}

type Notification struct {
	Category string `json:"category"` // "new_event" | "event_change"
	EventID  string `json:"event_id"`
	Title    string `json:"title"`
	Body     string `json:"body"`
	URL      string `json:"url"`
	Tag      string `json:"tag"`
}

type NotifyRequest struct {
	Notifications []Notification `json:"notifications"`
}

type NotifyResponse struct {
	Notifications   int `json:"notifications"`
	Subscriptions   int `json:"subscriptions"`
	Delivered       int `json:"delivered"`
	SkippedNoTarget int `json:"skipped_no_target"`
	Pruned          int `json:"pruned"`
}
