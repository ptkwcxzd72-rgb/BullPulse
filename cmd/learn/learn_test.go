package main

import (
	"math"
	"math/rand"
	"testing"
)

// synthetic panel: 300 stocks, 120 months, one sector per market; "T" predicts next month's
// return strongly, "M" is noise. The learner must find T, ignore M, and adopt.
func synth(signal float64) *Panel {
	rng := rand.New(rand.NewSource(1))
	nM, n := 120, 300
	p := &Panel{F: map[string][][]float64{}, Bench: map[string][]float64{"sp500": make([]float64, nM)}}
	for i := 0; i < n; i++ {
		p.IDs = append(p.IDs, "US-X"+string(rune('A'+i%26))+string(rune('A'+i/26)))
		p.Ex = append(p.Ex, "US")
		p.Sector = append(p.Sector, "S")
		p.Trust = append(p.Trust, false)
	}
	for _, k := range []string{"T", "M"} {
		p.F[k] = make([][]float64, nM)
	}
	p.Fwd = make([][]float64, nM)
	for m := 0; m < nM; m++ {
		p.Months = append(p.Months, "2016-01-31")
		p.F["T"][m], p.F["M"][m], p.Fwd[m] = make([]float64, n), make([]float64, n), make([]float64, n)
		for i := 0; i < n; i++ {
			t := rng.Float64() * 100
			p.F["T"][m][i] = t
			p.F["M"][m][i] = rng.Float64() * 100
			p.Fwd[m][i] = signal*(t-50)/50*0.02 + rng.NormFloat64()*0.05
		}
		p.Bench["sp500"][m] = 0.01
	}
	return p
}

func TestLearnerFindsRealSignalAndIgnoresNoise(t *testing.T) {
	p := synth(1)
	m := defaultModel("2026-10-29")
	m.Weights = map[string]float64{"M": 1} // a champion built on noise
	res := learn(p, m, "2026-10-29")
	if res.Adopt == nil {
		t.Fatalf("expected adoption; decision: %s", res.Decision)
	}
	if res.Adopt.Weights["T"] <= 0 || res.Adopt.Weights["M"] != 0 {
		t.Errorf("weights = %v, want T > 0 and no M", res.Adopt.Weights)
	}
	cal := res.Adopt.Calibration
	for d := 1; d < len(cal); d++ {
		if cal[d].Prob < cal[d-1].Prob {
			t.Errorf("calibration not monotonic: %v", cal)
		}
	}
	if cal[9].Prob <= cal[0].Prob {
		t.Errorf("calibration flat: %v", cal)
	}
}

func TestLearnerKeepsChampionWhenThereIsNoSignal(t *testing.T) {
	p := synth(0)
	res := learn(p, defaultModel("2026-10-29"), "2026-10-29")
	if res.Adopt != nil {
		t.Fatalf("adopted on pure noise: %s", res.Decision)
	}
}

func TestShrinkage(t *testing.T) {
	cs := [][]float64{}
	for k := 0; k < 60; k++ {
		c := make([]float64, len(Features))
		c[0] = 0.05 + 0.01*math.Sin(float64(k)) // strong and steady
		c[1] = 0.05 * math.Sin(float64(k))      // averages to nothing
		for a := 2; a < len(c); a++ {
			c[a] = math.NaN()
		}
		cs = append(cs, c)
	}
	e := estimate(cs, 1)
	if e.W[0] < 0.045 || e.W[1] != 0 || e.W[2] != 0 {
		t.Errorf("weights = %v", e.W[:3])
	}
}

func TestRelReturnsAndRanks(t *testing.T) {
	r := ranks([]float64{3, 1, 2, math.NaN(), 2})
	if r[1] != 0 || r[0] != 1 || r[2] != 0.5 || r[4] != 0.5 || !math.IsNaN(r[3]) {
		t.Errorf("ranks = %v", r)
	}
	if v := normInv(0.975); math.Abs(v-1.959964) > 1e-5 {
		t.Errorf("normInv(0.975) = %v", v)
	}
}
