package main

import "slices"

func shouldSend(n Notification, s Subscription) bool {
	switch n.Category {
	case "new_event":
		return s.NotifyNewEvents
	case "event_change":
		if s.NotifyAllChanges {
			return true
		}
		return slices.Contains(s.Favorites, n.EventID)
	default:
		return false
	}
}
