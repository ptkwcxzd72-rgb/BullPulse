package fund

import (
	"math"
	"testing"
)

func f(v float64) *float64 { return &v }

func TestValueNoGrowthIsPerpetuity(t *testing.T) {
	// with zero growth everywhere the DCF equals FCF / r per share
	got := Value(DCFInputs{BaseFCF: 90, Shares: 10, Growth: 0, Terminal: 0, Discount: 0.09})
	if math.Abs(got-100) > 1e-9 {
		t.Fatalf("got %v, want 100", got)
	}
	if !math.IsNaN(Value(DCFInputs{BaseFCF: 1, Shares: 1, Discount: 0.02, Terminal: 0.03})) {
		t.Fatal("discount below terminal growth must be NaN")
	}
}

func TestEstimateDCF(t *testing.T) {
	fin := Fin{FCFAvg3: f(100), Shares: f(10), RevCAGR3: f(0.5)}
	d := EstimateDCF(fin, "Information Technology", 50, nil)
	if d.Inputs == nil || d.Inputs.Growth != MaxGrowth {
		t.Fatalf("growth should be capped at %v: %+v", MaxGrowth, d.Inputs)
	}
	if !(*d.Bear < *d.Base && *d.Base < *d.Bull) {
		t.Fatalf("range out of order: %v %v %v", *d.Bear, *d.Base, *d.Bull)
	}
	if *d.VsPrice >= 0 {
		t.Fatalf("price 50 should be below the estimate %v", *d.Base)
	}
	if EstimateDCF(fin, "Financials", 50, nil).Skipped == "" {
		t.Fatal("banks should be skipped")
	}
	if EstimateDCF(Fin{FCFAvg3: f(-5), Shares: f(10)}, "Industrials", 50, nil).Skipped == "" {
		t.Fatal("negative FCF should be skipped")
	}
}

func TestCompute(t *testing.T) {
	fin := Fin{Shares: f(10), EPSTTM: f(2), RevenueTTM: f(200), OpIncomeTTM: f(40), NetIncomeTTM: f(20),
		Equity: f(100), Debt: f(50), Cash: f(80), OCFTTM: f(30), CapexTTM: f(10), DividendsPaidTTM: f(8),
		AssetsCur: f(60), LiabCur: f(30), InterestTTM: f(5)}
	m := Compute(fin, 40)
	check := func(name string, got *float64, want float64) {
		if got == nil || math.Abs(*got-want) > 1e-4 {
			t.Errorf("%s = %v, want %v", name, got, want)
		}
	}
	check("mcap", m.MarketCap, 400)
	check("pe", m.PE, 20)
	check("ps", m.PS, 2)
	check("pb", m.PB, 4)
	check("fcfYield", m.FCFYield, 0.05)
	check("divYield", m.DivYield, 0.02)
	check("payout", m.Payout, 0.4)
	check("roe", m.ROE, 0.2)
	check("currentRatio", m.CurrentRatio, 2)
	check("interestCover", m.InterestCover, 8)
	check("netCash", m.NetCash, 30)
	if Compute(Fin{Shares: f(10), EPSTTM: f(-1)}, 40).PE != nil {
		t.Error("P/E must be empty for loss-makers")
	}
}

func TestBuildCountsChecks(t *testing.T) {
	fin := Fin{Shares: f(10), EPSTTM: f(2), RevenueTTM: f(200), OpIncomeTTM: f(40), NetIncomeTTM: f(20),
		Equity: f(100), Debt: f(50), Cash: f(80), OCFTTM: f(30), CapexTTM: f(10), DividendsPaidTTM: f(8),
		AssetsCur: f(60), LiabCur: f(30), InterestTTM: f(5), FCFAvg3: f(20), RevCAGR3: f(0.08),
		Profitable3y: new(bool), EPSFY: f(2), EPS5yAgo: f(1), DPSFY: f(0.8), DPS3yAgo: f(0.6)}
	*fin.Profitable3y = true
	m := Compute(fin, 40)
	d := EstimateDCF(fin, "Industrials", 40, f(0.12))
	med := Medians{PEMarket: 25, FCFYieldMarket: 0.04, RevGrowthMarket: 0.05, OpMarginMarket: 0.15, DivYieldPayers: 0.015,
		PESector: map[string]float64{"Industrials": 22}, PSSector: map[string]float64{"Industrials": 3}}
	p := Build(fin, m, d, "Industrials", f(0.12), f(0.01), f(0.2), med)
	if len(p.Areas) != 5 {
		t.Fatalf("want 5 areas, got %d", len(p.Areas))
	}
	n, sum := 0, 0
	for _, a := range p.Areas {
		n += len(a.Checks)
		sum += a.Score
		if len(a.Checks) != 6 {
			t.Errorf("%s has %d checks", a.Name, len(a.Checks))
		}
	}
	if n != 30 || sum != p.Total {
		t.Fatalf("checks %d, total %d vs sum %d", n, p.Total, sum)
	}
	if p.Areas[4].Score != 6 {
		t.Errorf("dividend area should pass all six: %+v", p.Areas[4].Checks)
	}
	// missing data never counts as a pass
	empty := Build(Fin{}, Metrics{}, DCF{Skipped: "x"}, "Industrials", nil, nil, nil, Medians{PEMarket: math.NaN()})
	if empty.Total != 0 {
		t.Fatalf("empty profile scored %d", empty.Total)
	}
}

func TestMedian(t *testing.T) {
	if Median([]*float64{f(3), nil, f(1), f(2)}) != 2 || Median([]*float64{f(1), f(4)}) != 2.5 || !math.IsNaN(Median(nil)) {
		t.Fatal("median wrong")
	}
}
