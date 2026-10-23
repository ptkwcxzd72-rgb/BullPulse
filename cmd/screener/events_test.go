package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDetectEventsAndFeeds(t *testing.T) {
	g := 0.2
	prev := map[string]Row{"US-A": {ID: "US-A", Rank: 40, Above200: false, FundAsOf: "2026-03-31"}}
	rows := []*Row{{ID: "US-A", T: "A", Name: "Alpha", Rank: 10, Above200: true, FundAsOf: "2026-06-30", RevGrowth: &g, Ins: &Insider{Buyers: 3, Cluster: true}},
		{ID: "US-B", T: "B", Name: "Beta", Rank: 5}}
	ev := detectEvents("2026-10-20", rows, prev)
	kinds := map[string]bool{}
	for _, e := range ev {
		kinds[e.Kind] = true
		if e.ID != "US-A" {
			t.Fatalf("new stock should not raise events: %+v", e)
		}
	}
	for _, k := range []string{"rank", "trend", "results", "insider"} {
		if !kinds[k] {
			t.Errorf("missing %s event in %+v", k, ev)
		}
	}
	dir := t.TempDir()
	log := filepath.Join(dir, "e.jsonl")
	all := loadEvents(log, "2026-10-20", 90, ev, true)
	if err := saveEvents(log, all); err != nil {
		t.Fatal(err)
	}
	again := loadEvents(log, "2026-10-20", 90, ev, true)  // rerun on the same day replaces, not duplicates
	keep := loadEvents(log, "2026-10-20", 90, nil, false) // re-run on the same prices keeps the day's alerts
	if len(keep) != len(ev) {
		t.Fatalf("same-day re-run kept %d events, want %d", len(keep), len(ev))
	}
	if len(again) != len(ev) {
		t.Fatalf("got %d events after rerun, want %d", len(again), len(ev))
	}
	if err := writeFeeds(dir, "https://x/", rows, all); err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(filepath.Join(dir, "US-A.xml"))
	if !strings.Contains(string(b), "<rss version=\"2.0\"") || !strings.Contains(string(b), "isPermaLink=\"false\"") || !strings.Contains(string(b), "https://x/app.html#US-A") {
		t.Fatalf("feed looks wrong: %s", b)
	}
}
