// Package fund builds the BullPulse Fundamentals Profile (five areas x six checks = 30) and a
// discounted-cash-flow (DCF) estimate from SEC filing figures and the latest price.
//
// The profile and DCF are shown on the website and used in screens, but they are not part of
// the composite score until the monthly validation shows they help.
package fund

import (
	"fmt"
	"math"
	"sort"
	"strings"
)

// Fin holds the raw figures extracted by scripts/sec_financials.py (all optional).
type Fin struct {
	RevenueTTM       *float64 `json:"revenue_ttm"`
	NetIncomeTTM     *float64 `json:"net_income_ttm"`
	OpIncomeTTM      *float64 `json:"op_income_ttm"`
	OCFTTM           *float64 `json:"ocf_ttm"`
	CapexTTM         *float64 `json:"capex_ttm"`
	InterestTTM      *float64 `json:"interest_ttm"`
	DividendsPaidTTM *float64 `json:"dividends_paid_ttm"`
	EPSTTM           *float64 `json:"eps_ttm"`
	DPSTTM           *float64 `json:"dps_ttm"`
	RevCAGR3         *float64 `json:"rev_cagr3"`
	RevCAGR5         *float64 `json:"rev_cagr5"`
	EPS5yAgo         *float64 `json:"eps_5y_ago"`
	EPSFY            *float64 `json:"eps_fy"`
	DPS3yAgo         *float64 `json:"dps_3y_ago"`
	DPSFY            *float64 `json:"dps_fy"`
	Profitable3y     *bool    `json:"profitable_3y"`
	NetMarginFY      *float64 `json:"net_margin_fy"`
	NetMarginPrevFY  *float64 `json:"net_margin_prev_fy"`
	FCFAvg3          *float64 `json:"fcf_avg3"`
	FCFFAvg3         *float64 `json:"fcff_avg3"` // to the whole business: OCF - capex - share-based pay + after-tax interest
	SBCAvg3          *float64 `json:"sbc_avg3"`
	Equity           *float64 `json:"equity"`
	Cash             *float64 `json:"cash"`
	AssetsCur        *float64 `json:"assets_cur"`
	LiabCur          *float64 `json:"liab_cur"`
	Debt             *float64 `json:"debt"`
	Shares           *float64 `json:"shares"`
	TTMEnd           string   `json:"ttm_end"`
	Ccy              string   `json:"ccy"` // reporting currency when not USD (UK annual reports)
	BalanceEnd       string   `json:"balance_end"`
}

// Scale multiplies every money amount by k (for example reporting currency -> pence),
// leaving ratios, growth rates and share counts alone.
func (f Fin) Scale(k float64) Fin {
	for _, x := range []**float64{&f.RevenueTTM, &f.NetIncomeTTM, &f.OpIncomeTTM, &f.OCFTTM, &f.CapexTTM, &f.InterestTTM,
		&f.DividendsPaidTTM, &f.EPSTTM, &f.DPSTTM, &f.EPS5yAgo, &f.EPSFY, &f.DPS3yAgo, &f.DPSFY, &f.FCFAvg3, &f.FCFFAvg3,
		&f.SBCAvg3, &f.Equity, &f.Cash, &f.AssetsCur, &f.LiabCur, &f.Debt} {
		if *x != nil {
			v := **x * k
			*x = &v
		}
	}
	return f
}

// Metrics are the ratios derived from Fin and the price (nil when not meaningful).
type Metrics struct {
	MarketCap     *float64 `json:"mcap"`
	PE            *float64 `json:"pe"`
	PS            *float64 `json:"ps"`
	PB            *float64 `json:"pb"`
	FCFYield      *float64 `json:"fcfYield"`
	DivYield      *float64 `json:"divYield"`
	Payout        *float64 `json:"payout"`
	ROE           *float64 `json:"roe"`
	OpMargin      *float64 `json:"opMargin"`
	NetMargin     *float64 `json:"netMargin"`
	CurrentRatio  *float64 `json:"currentRatio"`
	DebtToEquity  *float64 `json:"debtToEquity"`
	OCFToDebt     *float64 `json:"ocfToDebt"`
	InterestCover *float64 `json:"interestCover"`
	NetCash       *float64 `json:"netCash"`
}

func p(v float64) *float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return nil
	}
	r := math.Round(v*10000) / 10000
	return &r
}

// Compute derives the ratios. price is in the same currency as the filings (USD).
func Compute(f Fin, price float64) Metrics {
	var m Metrics
	if f.Shares != nil && *f.Shares > 0 && price > 0 {
		m.MarketCap = p(price * *f.Shares)
	}
	mc := func() float64 {
		if m.MarketCap == nil {
			return math.NaN()
		}
		return *m.MarketCap
	}
	if f.EPSTTM != nil && *f.EPSTTM > 0 {
		m.PE = p(price / *f.EPSTTM)
	}
	if f.RevenueTTM != nil && *f.RevenueTTM > 0 {
		m.PS = p(mc() / *f.RevenueTTM)
		if f.OpIncomeTTM != nil {
			m.OpMargin = p(*f.OpIncomeTTM / *f.RevenueTTM)
		}
		if f.NetIncomeTTM != nil {
			m.NetMargin = p(*f.NetIncomeTTM / *f.RevenueTTM)
		}
	}
	if f.Equity != nil && *f.Equity > 0 {
		m.PB = p(mc() / *f.Equity)
		if f.NetIncomeTTM != nil {
			m.ROE = p(*f.NetIncomeTTM / *f.Equity)
		}
		if f.Debt != nil {
			m.DebtToEquity = p(*f.Debt / *f.Equity)
		}
	}
	if f.OCFTTM != nil && m.MarketCap != nil && *m.MarketCap > 0 {
		capex := 0.0
		if f.CapexTTM != nil {
			capex = *f.CapexTTM
		}
		m.FCFYield = p((*f.OCFTTM - capex) / *m.MarketCap)
	}
	switch {
	case f.DPSTTM != nil && price > 0:
		m.DivYield = p(*f.DPSTTM / price)
	case f.DividendsPaidTTM != nil && m.MarketCap != nil && *m.MarketCap > 0:
		m.DivYield = p(*f.DividendsPaidTTM / *m.MarketCap)
	}
	if f.DividendsPaidTTM != nil && f.NetIncomeTTM != nil && *f.NetIncomeTTM > 0 {
		m.Payout = p(*f.DividendsPaidTTM / *f.NetIncomeTTM)
	}
	if f.AssetsCur != nil && f.LiabCur != nil && *f.LiabCur > 0 {
		m.CurrentRatio = p(*f.AssetsCur / *f.LiabCur)
	}
	if f.Debt != nil && *f.Debt > 0 && f.OCFTTM != nil {
		m.OCFToDebt = p(*f.OCFTTM / *f.Debt)
	}
	if f.InterestTTM != nil && *f.InterestTTM > 0 && f.OpIncomeTTM != nil {
		m.InterestCover = p(*f.OpIncomeTTM / *f.InterestTTM)
	}
	if f.Cash != nil {
		debt := 0.0
		if f.Debt != nil {
			debt = *f.Debt
		}
		m.NetCash = p(*f.Cash - debt)
	}
	return m
}

// ---------------------------------------------------------------- DCF

// DCFInputs are everything the website needs to recompute the estimate with its sliders.
type DCFInputs struct {
	BaseFCF  float64 `json:"baseFcf"`  // average free cash flow to the business over the last three fiscal years
	NetDebt  float64 `json:"netDebt"`  // debt minus cash, subtracted from the business value to get equity value
	SBC      float64 `json:"sbc"`      // average yearly share-based pay already deducted from BaseFCF (for display)
	Shares   float64 `json:"shares"`   // shares outstanding
	Growth   float64 `json:"growth"`   // yearly growth for years 1-5 (from 3- or 5-year revenue growth, capped)
	Terminal float64 `json:"terminal"` // growth after year 10
	Discount float64 `json:"discount"` // required return
}

// DCF is a two-stage free-cash-flow estimate with a bear/base/bull range.
type DCF struct {
	Inputs   *DCFInputs `json:"inputs,omitempty"`
	Implied  *float64   `json:"implied,omitempty"` // growth for years 1-5 that the current price implies (reverse DCF)
	Bear     *float64   `json:"bear,omitempty"`
	Base     *float64   `json:"base,omitempty"`
	Bull     *float64   `json:"bull,omitempty"`
	VsPrice  *float64   `json:"vsPrice,omitempty"` // price / base - 1 (negative = price below estimate)
	Skipped  string     `json:"skipped,omitempty"`
	Currency string     `json:"ccy,omitempty"`
}

// Defaults for the model; the website lets visitors change them.
const (
	DefaultDiscount = 0.09
	DefaultTerminal = 0.025
	MaxGrowth       = 0.20
	MinGrowth       = 0.0 // the default never assumes shrinking cash flow; visitors can slide below zero
)

// Value is the equity value per share: five years at `growth`, five years fading linearly to
// `terminal`, then a Gordon terminal value, all discounted at `discount`.
func Value(in DCFInputs) float64 {
	if in.Shares <= 0 || in.Discount <= in.Terminal {
		return math.NaN()
	}
	fcf, pv := in.BaseFCF, 0.0
	for t := 1; t <= 10; t++ {
		g := in.Growth
		if t > 5 {
			g = in.Growth + (in.Terminal-in.Growth)*float64(t-5)/5
		}
		fcf *= 1 + g
		pv += fcf / math.Pow(1+in.Discount, float64(t))
	}
	tv := fcf * (1 + in.Terminal) / (in.Discount - in.Terminal)
	pv += tv / math.Pow(1+in.Discount, 10)
	return (pv - in.NetDebt) / in.Shares
}

// ImpliedGrowth is the reverse DCF: the growth rate for years 1-5 at which the model's value
// equals the price, holding the other inputs. NaN when no rate in [-50%, +100%] fits.
func ImpliedGrowth(in DCFInputs, price float64) float64 {
	if price <= 0 || in.BaseFCF <= 0 {
		return math.NaN()
	}
	lo, hi := -0.5, 1.0
	at := func(g float64) float64 { in.Growth = g; return Value(in) }
	if at(lo) > price || at(hi) < price {
		return math.NaN()
	}
	for i := 0; i < 60; i++ {
		mid := (lo + hi) / 2
		if at(mid) < price {
			lo = mid
		} else {
			hi = mid
		}
	}
	return (lo + hi) / 2
}

// noDCFSectors are businesses whose cash flows don't fit a free-cash-flow model.
func noDCF(sector string) bool {
	s := strings.ToLower(sector)
	for _, w := range []string{"financ", "bank", "insur", "real estate", "reit"} {
		if strings.Contains(s, w) {
			return true
		}
	}
	return false
}

// EstimateDCF returns the DCF for one company, or the reason it was skipped.
func EstimateDCF(f Fin, sector string, price float64, revGrowth *float64) DCF {
	switch {
	case noDCF(sector):
		return DCF{Skipped: "Not meaningful for banks, insurers and property companies, whose cash flows don't follow a free-cash-flow model."}
	case (f.FCFFAvg3 == nil && f.FCFAvg3 == nil) || f.Shares == nil:
		return DCF{Skipped: "Not enough cash-flow data in the filings."}
	}
	// prefer cash flow to the whole business, less share-based pay, then subtract net debt;
	// fall back to free cash flow to shareholders (older data) with no debt adjustment
	base, netDebt, sbc := 0.0, 0.0, 0.0
	if f.FCFFAvg3 != nil {
		base = *f.FCFFAvg3
		if f.Debt != nil {
			netDebt += *f.Debt
		}
		if f.Cash != nil {
			netDebt -= *f.Cash
		}
		if f.SBCAvg3 != nil {
			sbc = *f.SBCAvg3
		}
	} else {
		base = *f.FCFAvg3
	}
	if base <= 0 {
		return DCF{Skipped: "Free cash flow has been negative on average over the last three years, so a cash-flow valuation isn't meaningful."}
	}
	g := math.NaN()
	for _, c := range []*float64{f.RevCAGR3, f.RevCAGR5, revGrowth} {
		if c != nil {
			g = *c
			break
		}
	}
	if math.IsNaN(g) {
		g = 0.03
	}
	g = math.Max(MinGrowth, math.Min(MaxGrowth, g))
	in := DCFInputs{BaseFCF: base, NetDebt: netDebt, SBC: sbc, Shares: *f.Shares, Growth: math.Round(g*1000) / 1000, Terminal: DefaultTerminal, Discount: DefaultDiscount}
	mid := Value(in)
	bearIn, bullIn := in, in
	bearIn.Growth, bearIn.Discount = in.Growth-0.03, in.Discount+0.01
	bullIn.Growth, bullIn.Discount = in.Growth+0.03, in.Discount-0.01
	d := DCF{Inputs: &in, Bear: p(Value(bearIn)), Base: p(mid), Bull: p(Value(bullIn))}
	if mid <= 0 {
		d.Skipped = "Net debt is larger than the estimated value of the business, so the estimate per share is below zero."
	}
	if mid > 0 && price > 0 {
		d.VsPrice = p(price/mid - 1)
	}
	d.Implied = p(ImpliedGrowth(in, price))
	return d
}

// ---------------------------------------------------------------- profile

// Check is one of the 30 tests. Pass is nil when the data isn't available.
type Check struct {
	Name   string `json:"n"`
	Pass   *bool  `json:"ok"`
	Detail string `json:"d"`
}

// Area is one of the five parts of the profile, scored 0-6.
type Area struct {
	Key    string  `json:"key"`
	Name   string  `json:"name"`
	Score  int     `json:"score"`
	Checks []Check `json:"checks"`
}

// Profile is the full 30-check Fundamentals Profile.
type Profile struct {
	Total int    `json:"total"`
	Areas []Area `json:"areas"`
	AsOf  string `json:"asof,omitempty"`
}

// Medians are cross-sectional reference points from the stocks being ranked.
type Medians struct {
	PEMarket, FCFYieldMarket, RevGrowthMarket, OpMarginMarket, DivYieldPayers float64
	PESector, PSSector                                                        map[string]float64
}

// Median of the non-nil values (NaN when empty).
func Median(vals []*float64) float64 {
	var xs []float64
	for _, v := range vals {
		if v != nil && !math.IsNaN(*v) {
			xs = append(xs, *v)
		}
	}
	if len(xs) == 0 {
		return math.NaN()
	}
	sort.Float64s(xs)
	n := len(xs)
	if n%2 == 1 {
		return xs[n/2]
	}
	return (xs[n/2-1] + xs[n/2]) / 2
}

func pct(v float64) string { return fmt.Sprintf("%.1f%%", v*100) }
func x1(v float64) string  { return fmt.Sprintf("%.1f×", v) }

type checker struct{ checks []Check }

// add records a check; ok is evaluated only when have is true.
func (c *checker) add(name string, have bool, ok func() bool, detail func() string, missing string) {
	ch := Check{Name: name}
	if have {
		b := ok()
		ch.Pass, ch.Detail = &b, detail()
	} else {
		ch.Detail = missing
	}
	c.checks = append(c.checks, ch)
}

func area(key, name string, c *checker) Area {
	a := Area{Key: key, Name: name, Checks: c.checks}
	for _, ch := range c.checks {
		if ch.Pass != nil && *ch.Pass {
			a.Score++
		}
	}
	return a
}

func v(x *float64) float64 { return *x }

// Build scores the 30 checks.
func Build(f Fin, m Metrics, d DCF, sector string, revGrowth, revAccel, epsGrowth *float64, med Medians) Profile {
	const nodata = "Not available in the filings"
	nan := func(x float64) bool { return math.IsNaN(x) }

	// 1. Value
	var c checker
	c.add("Price is below the DCF estimate", d.VsPrice != nil, func() bool { return v(d.VsPrice) < 0 },
		func() string { return fmt.Sprintf("Price is %s the base estimate", relWord(v(d.VsPrice))) }, dcfMissing(d))
	c.add("Price is at least 20% below the DCF estimate", d.VsPrice != nil, func() bool { return v(d.VsPrice) <= -0.2 },
		func() string { return fmt.Sprintf("Price is %s the base estimate", relWord(v(d.VsPrice))) }, dcfMissing(d))
	sp := med.PESector[sector]
	c.add("P/E below its sector's median", m.PE != nil && !nan(sp), func() bool { return v(m.PE) < sp },
		func() string { return fmt.Sprintf("P/E %s vs sector median %s", x1(v(m.PE)), x1(sp)) }, peMissing(f))
	c.add("P/E below the market median", m.PE != nil && !nan(med.PEMarket), func() bool { return v(m.PE) < med.PEMarket },
		func() string { return fmt.Sprintf("P/E %s vs market median %s", x1(v(m.PE)), x1(med.PEMarket)) }, peMissing(f))
	ss := med.PSSector[sector]
	c.add("Price-to-sales below its sector's median", m.PS != nil && !nan(ss), func() bool { return v(m.PS) < ss },
		func() string { return fmt.Sprintf("P/S %s vs sector median %s", x1(v(m.PS)), x1(ss)) }, nodata)
	c.add("Free-cash-flow yield above the market median", m.FCFYield != nil && !nan(med.FCFYieldMarket), func() bool { return v(m.FCFYield) > med.FCFYieldMarket },
		func() string {
			return fmt.Sprintf("FCF yield %s vs market median %s", pct(v(m.FCFYield)), pct(med.FCFYieldMarket))
		}, nodata)
	value := area("value", "Value", &c)

	// 2. Growth (momentum of reported growth; not analyst forecasts)
	c = checker{}
	c.add("Revenue is growing", revGrowth != nil, func() bool { return v(revGrowth) > 0 },
		func() string { return "Revenue " + signed(v(revGrowth)) + " year on year" }, nodata)
	c.add("Revenue growth above the market median", revGrowth != nil && !nan(med.RevGrowthMarket), func() bool { return v(revGrowth) > med.RevGrowthMarket },
		func() string {
			return fmt.Sprintf("%s vs market median %s", signed(v(revGrowth)), signed(med.RevGrowthMarket))
		}, nodata)
	c.add("Revenue growing 10% or more", revGrowth != nil, func() bool { return v(revGrowth) >= 0.10 },
		func() string { return "Revenue " + signed(v(revGrowth)) + " year on year" }, nodata)
	c.add("Revenue growth is speeding up", revAccel != nil, func() bool { return v(revAccel) > 0 },
		func() string {
			return fmt.Sprintf("Growth changed by %+.1f points versus the previous quarter", v(revAccel)*100)
		}, "Needs two comparable quarters")
	c.add("Earnings per share growing", epsGrowth != nil, func() bool { return v(epsGrowth) > 0 },
		func() string { return "EPS " + signed(v(epsGrowth)) + " year on year" }, "Needs positive year-ago EPS")
	c.add("Earnings per share growing 15% or more", epsGrowth != nil, func() bool { return v(epsGrowth) >= 0.15 },
		func() string { return "EPS " + signed(v(epsGrowth)) + " year on year" }, "Needs positive year-ago EPS")
	growth := area("growth", "Growth", &c)

	// 3. Track record
	c = checker{}
	c.add("Earnings per share higher than 3-5 years ago", f.EPSFY != nil && f.EPS5yAgo != nil, func() bool { return v(f.EPSFY) > v(f.EPS5yAgo) },
		func() string { return fmt.Sprintf("EPS %.2f now vs %.2f then", v(f.EPSFY), v(f.EPS5yAgo)) }, nodata)
	c.add("Revenue grew over 5% a year for 3 years", f.RevCAGR3 != nil, func() bool { return v(f.RevCAGR3) > 0.05 },
		func() string { return "3-year revenue growth " + signed(v(f.RevCAGR3)) + " a year" }, nodata)
	c.add("Profitable in each of the last 3 years", f.Profitable3y != nil, func() bool { return *f.Profitable3y },
		func() string {
			if *f.Profitable3y {
				return "Net income positive in all three years"
			}
			return "At least one loss-making year"
		}, nodata)
	c.add("Profit margin higher than a year earlier", f.NetMarginFY != nil && f.NetMarginPrevFY != nil, func() bool { return v(f.NetMarginFY) > v(f.NetMarginPrevFY) },
		func() string {
			return fmt.Sprintf("Net margin %s vs %s", pct(v(f.NetMarginFY)), pct(v(f.NetMarginPrevFY)))
		}, nodata)
	c.add("Return on equity of 15% or more", m.ROE != nil, func() bool { return v(m.ROE) >= 0.15 },
		func() string { return "ROE " + pct(v(m.ROE)) }, nodata)
	c.add("Operating margin above the market median", m.OpMargin != nil && !nan(med.OpMarginMarket), func() bool { return v(m.OpMargin) > med.OpMarginMarket },
		func() string {
			return fmt.Sprintf("%s vs market median %s", pct(v(m.OpMargin)), pct(med.OpMarginMarket))
		}, nodata)
	past := area("past", "Track record", &c)

	// 4. Financial health
	c = checker{}
	c.add("Short-term assets cover short-term liabilities", m.CurrentRatio != nil, func() bool { return v(m.CurrentRatio) >= 1 },
		func() string { return "Current ratio " + x1(v(m.CurrentRatio)) }, "Not reported (common for banks and insurers)")
	c.add("Debt below shareholders' equity", m.DebtToEquity != nil, func() bool { return v(m.DebtToEquity) < 1 },
		func() string { return "Debt to equity " + pct(v(m.DebtToEquity)) }, nodata)
	c.add("Operating cash flow covers 20%+ of debt", m.OCFToDebt != nil || (f.Debt != nil && *f.Debt == 0), func() bool { return m.OCFToDebt == nil || v(m.OCFToDebt) >= 0.2 },
		func() string {
			if m.OCFToDebt == nil {
				return "No debt"
			}
			return "Cash flow equals " + pct(v(m.OCFToDebt)) + " of debt"
		}, nodata)
	c.add("Interest covered 3× by operating profit", m.InterestCover != nil, func() bool { return v(m.InterestCover) >= 3 },
		func() string { return "Interest cover " + x1(v(m.InterestCover)) }, "No interest expense reported")
	c.add("More cash than debt", m.NetCash != nil, func() bool { return v(m.NetCash) > 0 },
		func() string {
			if v(m.NetCash) > 0 {
				return "Net cash position"
			}
			return "Net debt position"
		}, nodata)
	c.add("Positive shareholders' equity", f.Equity != nil, func() bool { return v(f.Equity) > 0 },
		func() string {
			if v(f.Equity) > 0 {
				return "Assets exceed liabilities"
			}
			return "Liabilities exceed assets"
		}, nodata)
	health := area("health", "Health", &c)

	// 5. Dividends
	c = checker{}
	pays := m.DivYield != nil && v(m.DivYield) > 0
	c.add("Pays a dividend", true, func() bool { return pays },
		func() string {
			if pays {
				return "Yield " + pct(v(m.DivYield))
			}
			return "No dividend in the last twelve months"
		}, "")
	c.add("Yield of 2% or more", pays, func() bool { return v(m.DivYield) >= 0.02 }, func() string { return "Yield " + pct(v(m.DivYield)) }, "No dividend")
	c.add("Yield above the median dividend payer", pays && !nan(med.DivYieldPayers), func() bool { return v(m.DivYield) > med.DivYieldPayers },
		func() string { return fmt.Sprintf("%s vs %s", pct(v(m.DivYield)), pct(med.DivYieldPayers)) }, "No dividend")
	c.add("Dividend covered by earnings (payout under 75%)", pays && m.Payout != nil, func() bool { return v(m.Payout) < 0.75 },
		func() string { return "Payout ratio " + pct(v(m.Payout)) }, "No dividend")
	fcf := math.NaN()
	if f.OCFTTM != nil {
		fcf = v(f.OCFTTM)
		if f.CapexTTM != nil {
			fcf -= v(f.CapexTTM)
		}
	}
	c.add("Dividend covered by free cash flow", pays && f.DividendsPaidTTM != nil && !nan(fcf), func() bool { return v(f.DividendsPaidTTM) < fcf },
		func() string {
			if fcf > 0 {
				return "Dividends use " + pct(v(f.DividendsPaidTTM)/fcf) + " of free cash flow"
			}
			return "Free cash flow is negative"
		}, "No dividend")
	c.add("Dividend per share higher than 3 years ago", pays && f.DPSFY != nil && f.DPS3yAgo != nil, func() bool { return v(f.DPSFY) > v(f.DPS3yAgo) },
		func() string { return fmt.Sprintf("%.2f now vs %.2f three years ago", v(f.DPSFY), v(f.DPS3yAgo)) }, "Needs three years of dividend history")
	div := area("dividends", "Dividends", &c)

	pr := Profile{Areas: []Area{value, growth, past, health, div}, AsOf: f.TTMEnd}
	for _, a := range pr.Areas {
		pr.Total += a.Score
	}
	return pr
}

func relWord(r float64) string {
	if r < 0 {
		return pct(-r) + " below"
	}
	return pct(r) + " above"
}

func signed(v float64) string {
	if v >= 0 {
		return "+" + pct(v)
	}
	return "−" + pct(-v)
}

func dcfMissing(d DCF) string {
	if d.Skipped != "" {
		return d.Skipped
	}
	return "No DCF estimate"
}

func peMissing(f Fin) string {
	if f.EPSTTM != nil && *f.EPSTTM <= 0 {
		return "Loss-making over the last twelve months, so P/E isn't meaningful"
	}
	return "Not available in the filings"
}

// Peer is one company's inputs to the cross-sectional medians.
type Peer struct {
	Sector    string
	M         Metrics
	RevGrowth *float64
}

// PeerMedians computes the market and sector reference points for Build from one market's
// companies. Sector medians need at least four peers with data, otherwise they are NaN.
func PeerMedians(peers []Peer) Medians {
	col := func(get func(Peer) *float64, keep func(Peer) bool) []*float64 {
		var v []*float64
		for _, p := range peers {
			if keep == nil || keep(p) {
				v = append(v, get(p))
			}
		}
		return v
	}
	pays := func(p Peer) bool { return p.M.DivYield != nil && *p.M.DivYield > 0 }
	med := Medians{
		PEMarket:        Median(col(func(p Peer) *float64 { return p.M.PE }, nil)),
		FCFYieldMarket:  Median(col(func(p Peer) *float64 { return p.M.FCFYield }, nil)),
		RevGrowthMarket: Median(col(func(p Peer) *float64 { return p.RevGrowth }, nil)),
		OpMarginMarket:  Median(col(func(p Peer) *float64 { return p.M.OpMargin }, nil)),
		DivYieldPayers:  Median(col(func(p Peer) *float64 { return p.M.DivYield }, pays)),
		PESector:        map[string]float64{}, PSSector: map[string]float64{},
	}
	count := func(v []*float64) int {
		n := 0
		for _, x := range v {
			if x != nil {
				n++
			}
		}
		return n
	}
	for _, p := range peers {
		sec := p.Sector
		if _, done := med.PESector[sec]; done {
			continue
		}
		in := func(q Peer) bool { return q.Sector == sec }
		med.PESector[sec], med.PSSector[sec] = math.NaN(), math.NaN()
		if v := col(func(q Peer) *float64 { return q.M.PE }, in); count(v) >= 4 {
			med.PESector[sec] = Median(v)
		}
		if v := col(func(q Peer) *float64 { return q.M.PS }, in); count(v) >= 4 {
			med.PSSector[sec] = Median(v)
		}
	}
	return med
}

// PerShare multiplies the per-share amounts by k and divides the share count by k
// (k = 1/split factor puts as-reported figures on today's split-adjusted basis).
func (f Fin) PerShare(k float64) Fin {
	for _, x := range []**float64{&f.EPSTTM, &f.DPSTTM, &f.EPS5yAgo, &f.EPSFY, &f.DPS3yAgo, &f.DPSFY} {
		if *x != nil {
			v := **x * k
			*x = &v
		}
	}
	if f.Shares != nil && k != 0 {
		v := *f.Shares / k
		f.Shares = &v
	}
	return f
}
