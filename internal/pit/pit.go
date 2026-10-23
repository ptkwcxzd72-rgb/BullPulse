// Package pit holds point-in-time fundamentals: each company's figures as they stood after each
// filing (scripts/fundamentals_history.py), and the dividend adjustment needed to compare them
// with total-return prices.
package pit

import (
	"bufio"
	"encoding/json"
	"math"
	"os"
	"sort"
	"time"

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/fund"
)

// Row is one company's figures as they stood after one filing (scripts/fundamentals_history.py).
type Row struct {
	ID        string   `json:"id"`
	Date      string   `json:"date"`
	Fin       fund.Fin `json:"fin"`
	RevGrowth *float64 `json:"rev_growth"`
	RevAccel  *float64 `json:"rev_accel"`
	EpsGrowth *float64 `json:"eps_growth"`
	Split     float64  `json:"split"`
}

func Load(path string) map[string][]Row {
	out := map[string][]Row{}
	f, err := os.Open(path)
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var r Row
		if json.Unmarshal(sc.Bytes(), &r) == nil && r.Split > 0 {
			out[r.ID] = append(out[r.ID], r)
		}
	}
	for _, rs := range out {
		sort.Slice(rs, func(a, b int) bool { return rs[a].Date < rs[b].Date })
	}
	return out
}

// divFactor returns, for a date, the cumulative dividend adjustment that the total-return price
// series carries for dividends paid after that date (1 = none). Dividends are approximated as a
// quarter of the trailing-twelve-month dividend per share at each reported period end.
func DivFactor(rows []Row, x *core.Series) func(time.Time) float64 {
	type ev struct {
		d   time.Time
		amt float64
	}
	byEnd := map[string]float64{}
	for _, r := range rows {
		f := r.Fin.PerShare(1 / r.Split)
		dps := math.NaN()
		if f.DPSTTM != nil {
			dps = *f.DPSTTM
		} else if f.DividendsPaidTTM != nil && f.Shares != nil && *f.Shares > 0 {
			dps = *f.DividendsPaidTTM / *f.Shares
		}
		if !math.IsNaN(dps) && dps > 0 && r.Fin.TTMEnd != "" {
			byEnd[r.Fin.TTMEnd] = dps / 4
		}
	}
	var evs []ev
	for d, a := range byEnd {
		if t, err := time.Parse("2006-01-02", d); err == nil {
			evs = append(evs, ev{t, a})
		}
	}
	sort.Slice(evs, func(a, b int) bool { return evs[a].d.After(evs[b].d) }) // newest first
	type step struct {
		d time.Time
		f float64 // factor for dates before d
	}
	var steps []step
	f := 1.0
	for _, e := range evs {
		// adjusted price on the last trading day on or before the dividend date
		k := sort.Search(len(x.Dates), func(i int) bool { return x.Dates[i].After(e.d) }) - 1
		if k < 0 || x.Close[k] <= 0 {
			continue
		}
		y := math.Min(e.amt*f/x.Close[k], 0.2)
		f *= 1 - y
		steps = append(steps, step{e.d, f})
	}
	return func(t time.Time) float64 {
		out := 1.0
		for _, s := range steps { // newest first: keep the factor of the earliest dividend after t
			if s.d.After(t) {
				out = s.f
			} else {
				break
			}
		}
		return out
	}
}
