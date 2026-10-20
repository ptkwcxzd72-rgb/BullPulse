package main

import (
	"math"
	"testing"
	"time"

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/fund"
)

func TestDivFactor(t *testing.T) {
	x := &core.Series{}
	d0 := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := 0; i < 400; i++ {
		x.Dates = append(x.Dates, d0.AddDate(0, 0, i))
		x.Close = append(x.Close, 100)
	}
	dps := 4.0
	rows := []pitRow{{Date: "2025-07-01", Split: 1, Fin: fund.Fin{DPSTTM: &dps, TTMEnd: "2025-06-30"}}}
	f := divFactor(rows, x)
	if got := f(time.Date(2025, 3, 1, 0, 0, 0, 0, time.UTC)); math.Abs(got-0.99) > 1e-9 {
		t.Fatalf("before the dividend: %v, want 0.99", got)
	}
	if got := f(time.Date(2025, 9, 1, 0, 0, 0, 0, time.UTC)); got != 1 {
		t.Fatalf("after the dividend: %v, want 1", got)
	}
}

func TestQuintilesFindSignal(t *testing.T) {
	var months [][]mobs
	for m := 0; m < 30; m++ {
		var ob []mobs
		for i := 0; i < 50; i++ {
			r := float64(i) / 1000 // higher measure, higher return
			ob = append(ob, mobs{float64(i), [3]float64{r, r, r}})
		}
		months = append(months, ob)
	}
	q := quintiles(months)
	if q.Months != 30 || q.Spread[0] <= 0 || q.Quintile[0][4] <= q.Quintile[0][0] {
		t.Fatalf("unexpected %+v", q)
	}
}
