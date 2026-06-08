package main

import "testing"

func sub(notifyNew, notifyAll bool, favs ...string) Subscription {
	return Subscription{
		NotifyNewEvents:  notifyNew,
		NotifyAllChanges: notifyAll,
		Favorites:        favs,
	}
}

func notif(category, eventID string) Notification {
	return Notification{Category: category, EventID: eventID}
}

func TestShouldSend(t *testing.T) {
	tests := []struct {
		name string
		n    Notification
		s    Subscription
		want bool
	}{
		{
			name: "new_event sent to subscriber with notify_new_events=true",
			n:    notif("new_event", "Ritt A"),
			s:    sub(true, false),
			want: true,
		},
		{
			name: "new_event not sent when notify_new_events=false",
			n:    notif("new_event", "Ritt A"),
			s:    sub(false, false),
			want: false,
		},
		{
			name: "event_change sent when notify_all_changes=true regardless of favorites",
			n:    notif("event_change", "Ritt B"),
			s:    sub(false, true),
			want: true,
		},
		{
			name: "event_change sent when event is in favorites",
			n:    notif("event_change", "Ritt C"),
			s:    sub(false, false, "Ritt C", "Ritt D"),
			want: true,
		},
		{
			name: "event_change not sent when event not in favorites and notify_all_changes=false",
			n:    notif("event_change", "Ritt X"),
			s:    sub(false, false, "Ritt C", "Ritt D"),
			want: false,
		},
		{
			name: "unknown category never sent",
			n:    notif("unknown_category", "Ritt E"),
			s:    sub(true, true, "Ritt E"),
			want: false,
		},
		{
			name: "event_change with notify_all_changes overrides missing favorites",
			n:    notif("event_change", "Ritt F"),
			s:    sub(false, true, "Ritt G"),
			want: true,
		},
		{
			name: "new_event with notify_new_events=false even if all_changes is true",
			n:    notif("new_event", "Ritt H"),
			s:    sub(false, true),
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := shouldSend(tt.n, tt.s)
			if got != tt.want {
				t.Errorf("shouldSend(%q, ...) = %v, want %v", tt.n.Category, got, tt.want)
			}
		})
	}
}
