package main

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"sort"

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
)

// recordMembership appends to path every change in the universe files since the last run:
// "joined" and "left" with the index, so future tests know who was in each index on each date.
// The first run records everyone as "present" (their real joining dates are unknown).
func recordMembership(path, day string, stocks []core.Stock) error {
	cur := map[string]string{}
	for _, s := range stocks {
		cur[s.ID()] = s.Index
	}
	state := map[string]string{}
	first := true
	if f, err := os.Open(path); err == nil {
		rows, _ := csv.NewReader(f).ReadAll()
		f.Close()
		for _, r := range rows {
			if len(r) < 4 || r[0] == "date" {
				continue
			}
			first = false
			if r[3] == "left" {
				delete(state, r[1])
			} else {
				state[r[1]] = r[2]
			}
		}
	}
	var add [][]string
	ids := make([]string, 0, len(cur))
	for id := range cur {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if old, ok := state[id]; !ok || old != cur[id] {
			ev := "joined"
			if first {
				ev = "present"
			}
			if ok && old != cur[id] {
				add = append(add, []string{day, id, old, "left"})
			}
			add = append(add, []string{day, id, cur[id], ev})
		}
	}
	gone := []string{}
	for id := range state {
		if _, ok := cur[id]; !ok {
			gone = append(gone, id)
		}
	}
	sort.Strings(gone)
	for _, id := range gone {
		add = append(add, []string{day, id, state[id], "left"})
	}
	if len(add) == 0 {
		return nil
	}
	os.MkdirAll(filepath.Dir(path), 0o755)
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	if first {
		w.Write([]string{"date", "id", "index", "event"})
	}
	w.WriteAll(add)
	return w.Error()
}
