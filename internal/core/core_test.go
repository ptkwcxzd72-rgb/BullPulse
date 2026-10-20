package core

import (
	"math"
	"os"
	"path/filepath"
	"testing"
)

func TestPercentiles(t *testing.T) {
	got := Percentiles([]float64{10, 30, 20, math.NaN(), 20})
	want := []float64{0, 100, 50, math.NaN(), 50} // ties share the average rank; NaN stays NaN
	for i := range want {
		if math.IsNaN(want[i]) {
			if !math.IsNaN(got[i]) {
				t.Fatalf("index %d: want NaN, got %v", i, got[i])
			}
			continue
		}
		if math.Abs(got[i]-want[i]) > 1e-9 {
			t.Fatalf("index %d: want %v, got %v (all %v)", i, want[i], got[i], got)
		}
	}
	if p := Percentiles([]float64{5}); p[0] != 50 {
		t.Fatalf("single value should be 50, got %v", p[0])
	}
}

func TestSince(t *testing.T) {
	pos := []int{0, 0, 1, 1, 1, 0}
	if s := Since(pos, 4); s != 2 {
		t.Fatalf("want 2 bars since the switch to long, got %d", s)
	}
	if s := Since(pos, 5); s != 0 {
		t.Fatalf("want 0 on the bar of the change, got %d", s)
	}
}

func series(closes []float64) *Series {
	n := len(closes)
	x := &Series{Close: closes, SMA50: make([]float64, n), SMA200: make([]float64, n), SuperTrend: make([]int, n)}
	for i := range closes {
		x.SMA50[i], x.SMA200[i] = math.NaN(), math.NaN()
		if i >= 199 {
			var s50, s200 float64
			for k := i - 199; k <= i; k++ {
				s200 += closes[k]
			}
			for k := i - 49; k <= i; k++ {
				s50 += closes[k]
			}
			x.SMA50[i], x.SMA200[i] = s50/50, s200/200
		}
	}
	return x
}

func TestTrendAndMomentum(t *testing.T) {
	up := make([]float64, 300)
	for i := range up {
		up[i] = 100 * math.Pow(1.002, float64(i))
	}
	x := series(up)
	x.SuperTrend[299] = 1
	if tr := x.TrendRaw(299); tr != 100 {
		t.Fatalf("steady uptrend should score 100, got %v", tr)
	}
	want := up[299-21]/up[299-252] - 1
	if m := x.Momentum(299); math.Abs(m-want) > 1e-12 {
		t.Fatalf("momentum: want %v, got %v", want, m)
	}
	if !math.IsNaN(x.TrendRaw(100)) || !math.IsNaN(x.Momentum(100)) {
		t.Fatal("too little history should give NaN")
	}
	if d := x.DaysAbove200(299); d < 90 {
		t.Fatalf("an uptrend should have been above its 200-day for a long time, got %d", d)
	}
}

func TestLoadUniverseByHeader(t *testing.T) {
	dir := t.TempDir()
	csv := "name,ticker,market,provider_ticker,sector,cik\nApple,AAPL,US,aapl,Technology,320193\nBP,BP,UK,,Energy,\n"
	if err := os.WriteFile(filepath.Join(dir, "x.csv"), []byte(csv), 0o644); err != nil {
		t.Fatal(err)
	}
	u, err := LoadUniverse(dir)
	if err != nil || len(u) != 2 {
		t.Fatalf("want 2 stocks, got %d (%v)", len(u), err)
	}
	if u[0].Ticker != "AAPL" || u[0].CIK != "320193" || u[0].ProviderTicker != "aapl" || u[0].ID() != "US-AAPL" {
		t.Fatalf("columns read by name went wrong: %+v", u[0])
	}
	if u[1].ID() != "LSE-BP" || Currency(u[1].Market) != "GBX" {
		t.Fatalf("UK mapping went wrong: %+v", u[1])
	}
}
