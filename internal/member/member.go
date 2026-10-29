// Package member answers "was this stock in its index on this date?" from the membership history
// in universe/history, to keep stocks out of past samples before they joined (look-ahead bias).
package member

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"strings"
)

type span struct{ from, to string } // to == "" while still a member

// History holds S&P 500 membership spans by ticker (with earlier tickers of renamed companies).
type History struct {
	spans map[string][]span
}

// Load reads universe/history; a missing directory gives an empty history (everyone counts).
func Load(dir string) *History {
	h := &History{spans: map[string][]span{}}
	rows := readCSV(filepath.Join(dir, "sp500_membership.csv"))
	for _, r := range rows {
		if len(r) >= 3 && r[0] != "ticker" {
			h.spans[norm(r[0])] = append(h.spans[norm(r[0])], span{r[1], r[2]})
		}
	}
	// renamed companies: the new ticker inherits the old ticker's spans (chains resolve in order)
	for pass := 0; pass < 3; pass++ {
		for _, r := range readCSV(filepath.Join(dir, "sp500_aliases.csv")) {
			if len(r) >= 2 && r[0] != "ticker" {
				t, prev := norm(r[0]), norm(r[1])
				for _, s := range h.spans[prev] {
					if !has(h.spans[t], s) {
						h.spans[t] = append(h.spans[t], s)
					}
				}
			}
		}
	}
	return h
}

func has(ss []span, s span) bool {
	for _, x := range ss {
		if x == s {
			return true
		}
	}
	return false
}

func norm(t string) string { return strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(t), "-", ".")) }

func readCSV(path string) [][]string {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, _ := r.ReadAll()
	return rows
}

// Known reports whether there is any membership record for a US ticker.
func (h *History) Known(ticker string) bool { return len(h.spans[norm(ticker)]) > 0 }

// Member reports whether the stock counted on date (YYYY-MM-DD). UK stocks, and US tickers with
// no record, count throughout (unknown, so not excluded).
func (h *History) Member(market, ticker, date string) bool {
	if h == nil || market == "UK" {
		return true
	}
	ss := h.spans[norm(ticker)]
	if len(ss) == 0 {
		return true
	}
	for _, s := range ss {
		if s.from <= date && (s.to == "" || date < s.to) {
			return true
		}
	}
	return false
}
