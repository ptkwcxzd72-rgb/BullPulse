package fund

import (
	"math"
	"testing"
)

func f(v float64) *float64 { return &v }

func TestValueNoGrowthIsPerpetuity(t *testing.T) {
	// with zero growth everywhere the DCF equals FCF / r per share
	got := Value(DCFInputs{BaseFCF: 90, Shares: 10, Growth: 0, Terminal: 0, Discount: 0.09})
	if v := Value(DCFInputs{BaseFCF: 90, NetDebt: 200, Shares: 10, Discount: 0.09}); math.Abs(v-80) > 1e-9 {
		t.Fatalf("net debt: got %v, want 80", v)
	}
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

func TestImpliedGrowthRoundTrips(t *testing.T) {
	in := DCFInputs{BaseFCF: 50, NetDebt: 100, Shares: 10, Growth: 0.07, Terminal: 0.025, Discount: 0.09}
	price := Value(in)
	if g := ImpliedGrowth(in, price); math.Abs(g-0.07) > 1e-6 {
		t.Fatalf("implied %v, want 0.07", g)
	}
	if !math.IsNaN(ImpliedGrowth(in, 1e9)) {
		t.Fatal("an impossible price should give NaN")
	}
}

func TestDCFUsesFCFFAndNetDebt(t *testing.T) {
	fin := Fin{FCFAvg3: f(100), FCFFAvg3: f(80), SBCAvg3: f(15), Debt: f(300), Cash: f(100), Shares: f(10), RevCAGR3: f(0.05)}
	d := EstimateDCF(fin, "Industrials", 50, nil)
	if d.Inputs.BaseFCF != 80 || d.Inputs.NetDebt != 200 || d.Inputs.SBC != 15 {
		t.Fatalf("inputs %+v", d.Inputs)
	}
	if d.Implied == nil || *d.Implied >= d.Inputs.Growth {
		t.Fatalf("price below value should imply lower growth: %v", d.Implied)
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

func TestScale(t *testing.T) {
	fin := Fin{RevenueTTM: f(10), EPSTTM: f(0.5), Shares: f(7), RevCAGR3: f(0.1)}
	g := fin.Scale(100)
	if *g.RevenueTTM != 1000 || *g.EPSTTM != 50 || *g.Shares != 7 || *g.RevCAGR3 != 0.1 || *fin.RevenueTTM != 10 {
		t.Fatalf("scale wrong: %v %v %v %v %v", *g.RevenueTTM, *g.EPSTTM, *g.Shares, *g.RevCAGR3, *fin.RevenueTTM)
	}
}

func TestMedian(t *testing.T) {
	if Median([]*float64{f(3), nil, f(1), f(2)}) != 2 || Median([]*float64{f(1), f(4)}) != 2.5 || !math.IsNaN(Median(nil)) {
		t.Fatal("median wrong")
	}
}

func TestPlausibleShares(t *testing.T) {
	n := func(v float64) *float64 { return &v }
	// Fox: a share count near zero gave a free-cash-flow yield in the millions of per cent
	f := PlausibleShares(Fin{Shares: n(1000), OCFTTM: n(3e9)}, 50, "S&P 500", false)
	if f.Shares != nil || Compute(f, 50).FCFYield != nil {
		t.Fatalf("an impossible market value should leave market value and yields blank")
	}
	if PlausibleShares(Fin{Shares: n(2e9)}, 50, "S&P 500", false).Shares == nil {
		t.Fatalf("a $100bn company is plausible")
	}
	// UK prices are in pence: 970m shares at 2,525p is about GBP 24bn
	if PlausibleShares(Fin{Shares: n(9.7e8)}, 2525, "FTSE 100", false).Shares == nil {
		t.Fatalf("3i at GBP 24bn is plausible")
	}
	if PlausibleShares(Fin{Shares: n(9.7e6)}, 2525, "FTSE 100", false).Shares != nil {
		t.Fatalf("3i at GBP 0.24bn is not a FTSE 100 company")
	}
	// in a backtest the floor is lower: today's member may have been small years ago
	if PlausibleShares(Fin{Shares: n(4e8)}, 100, "S&P 500", true).Shares == nil {
		t.Fatalf("a $400m company before it joined the S&P 500 is plausible in the past")
	}
}

func TestImplausibleYieldsAreBlank(t *testing.T) {
	n := func(v float64) *float64 { return &v }
	m := Compute(Fin{Shares: n(1e8), OCFTTM: n(2e10), DividendsPaidTTM: n(5e9)}, 100) // $10bn company
	if m.FCFYield != nil || m.DivYield != nil {
		t.Fatalf("200%% free-cash-flow and 50%% dividend yields should be blank, got %v %v", m.FCFYield, m.DivYield)
	}
	m = Compute(Fin{Shares: n(1e8), OCFTTM: n(8e8), DividendsPaidTTM: n(3e8)}, 100)
	if m.FCFYield == nil || m.DivYield == nil || *m.FCFYield != 0.08 || *m.DivYield != 0.03 {
		t.Fatalf("ordinary yields kept, got %v %v", m.FCFYield, m.DivYield)
	}
}

func TestIssuanceIgnoresSplits(t *testing.T) {
	p := func(v float64) *float64 { return &v }
	if v := (Fin{Shares: p(95), SharesPrev: p(100)}).Issuance(); math.Abs(v-math.Log(0.95)) > 1e-9 {
		t.Fatalf("buyback: %v", v)
	}
	if v := (Fin{Shares: p(200), SharesPrev: p(100)}).Issuance(); !math.IsNaN(v) {
		t.Fatalf("2-for-1 split counted as issuance: %v", v)
	}
	gp, accr, agr := (Fin{Assets: p(100), AssetsPrev: p(80), GrossProfitTTM: p(30), NetIncomeTTM: p(10), OCFTTM: p(15)}).Quality()
	if gp != 0.3 || accr != -0.05 || agr != 0.25 {
		t.Fatalf("quality %v %v %v", gp, accr, agr)
	}
}

func TestAltmanZ(t *testing.T) {
	p := func(v float64) *float64 { return &v }
	f := Fin{Assets: p(1000), AssetsCur: p(400), LiabCur: p(200), RetainedEarnings: p(300), OpIncomeTTM: p(100), RevenueTTM: p(1200), Liabilities: p(500), Equity: p(500)}
	z, m := f.AltmanZ(800, "Industrials")
	want := 1.2*0.2 + 1.4*0.3 + 3.3*0.1 + 0.6*800/500 + 1.0*1.2
	if m != "Z" || math.Abs(z-want) > 1e-9 || AltmanZone(z, m) != "safe" {
		t.Fatalf("Z %v %v", z, m)
	}
	z, m = f.AltmanZ(800, "Information Technology")
	if want := 6.56*0.2 + 3.26*0.3 + 6.72*0.1 + 1.05*1; m != "Z''" || math.Abs(z-want) > 1e-9 || AltmanZone(z, m) != "safe" {
		t.Fatalf("Z'' %v %v", z, m)
	}
	if z, _ := f.AltmanZ(800, "Financials"); !math.IsNaN(z) {
		t.Fatal("banks have no Z-score")
	}
}
