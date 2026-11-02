package main

import (
	"encoding/json"
	"math"
	"os"
	"time"

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
)

// monthlyPrices collects, for the Strategy Lab's forward tracking, each stock's closing price
// (adjusted for splits and dividends) at every month-end of the last ten years plus the latest
// close, and the dates of the latest closes.
type monthlyPrices struct {
	months []string // "2016-10" ... current month (its value is the latest close)
	ids    []string
	px     [][]any
}

func newMonthly(asof time.Time) *monthlyPrices {
	m := &monthlyPrices{}
	start := time.Date(asof.Year()-10, asof.Month(), 1, 0, 0, 0, 0, time.UTC)
	for t := start; !t.After(asof); t = t.AddDate(0, 1, 0) {
		m.months = append(m.months, t.Format("2006-01"))
	}
	return m
}

// add records one stock: the last close in each month (the current month: the latest close).
func (m *monthlyPrices) add(id string, x *core.Series) {
	row := make([]any, len(m.months))
	pos := map[string]int{}
	for k, s := range m.months {
		pos[s] = k
	}
	for j, d := range x.Dates {
		if k, ok := pos[d.Format("2006-01")]; ok && x.Close[j] > 0 {
			v := x.Close[j]
			p := math.Pow(10, math.Max(0, 4-math.Ceil(math.Log10(v)))) // about five significant figures
			row[k] = math.Round(v*p) / p
		}
	}
	m.ids = append(m.ids, id)
	m.px = append(m.px, row)
}

func (m *monthlyPrices) write(path string, asof time.Time) error {
	b, err := json.Marshal(map[string]any{"asof": asof.Format("2006-01-02"), "months": m.months, "ids": m.ids, "px": m.px,
		"note": "Month-end closes adjusted for splits and dividends; the last month is the latest close. UK in pence, US in dollars."})
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o644)
}
