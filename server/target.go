package main

func shouldSend(n Notification, s Subscription) bool {
	switch n.Category {
	case "new_event":
		return s.NotifyNewEvents
	case "event_change":
		if s.NotifyAllChanges {
			return true
		}
		return contains(s.Favorites, n.EventID)
	default:
		return false
	}
}

func contains(slice []string, val string) bool {
	for _, v := range slice {
		if v == val {
			return true
		}
	}
	return false
}
