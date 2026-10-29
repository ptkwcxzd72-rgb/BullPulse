package main

import (
	"math"
	"sort"
)

// Feature is one candidate signal. Sign +1 means "higher is expected to be better"; -1 flips it
// (low volatility, short-term reversal), so every learned weight reads the same way.
type Feature struct {
	Key, Name string
	Sign      float64
	About     string
}

var Features = []Feature{
	{"T", "Trend", 1, "200-day average, golden cross and Super Trend"},
	{"M", "Momentum", 1, "12-month return, leaving out the latest month"},
	{"G", "Revenue growth", 1, "reported revenue growth"},
	{"FP", "Fundamentals checks", 1, "the 30 pass-or-fail checks"},
	{"Vp", "Below fair value", 1, "price against the cash-flow fair-value estimate"},
	{"vol1y", "Low volatility", -1, "steadier shares over the past year"},
	{"rev1m", "Short-term reversal", -1, "last month's losers tend to bounce, winners to give back"},
	{"insB", "Insider buying", 1, "officers and directors buying in the last 90 days (US)"},
	{"sue", "Earnings surprise", 1, "latest quarter against the same quarter a year earlier (US)"},
}

// minCoverage: a feature counts in a month only if at least this share of stocks have it.
const minCoverage = 0.3

// month holds one month-end cross-section: feature scores z (rank - 0.5, 0 when missing) and
// the target y (rank of the sector-relative return over the horizon, 0..1), members only.
type month struct {
	idx []int       // stock indices
	z   [][]float64 // per stock, per feature
	y   []float64   // NaN when the outcome is not known yet
	rel []float64   // sector-relative return over the horizon
}

// relReturns is each stock's return over h months from month m, minus the median of its sector
// in its market (or of its market when the sector has fewer than five members). NaN if unknown.
func relReturns(p *Panel, m, h int) []float64 {
	n := len(p.IDs)
	r := make([]float64, n)
	for i := range r {
		r[i] = math.NaN()
		if m+h > len(p.Fwd)-1 || !p.member(m, i) { // the last row runs to the latest close: not a full month
			continue
		}
		v := 1.0
		for k := 0; k < h; k++ {
			f := p.Fwd[m+k][i]
			if math.IsNaN(f) {
				v = math.NaN()
				break
			}
			v *= 1 + f
		}
		r[i] = v - 1
	}
	groups := map[string][]int{}
	mkts := map[string][]int{}
	for i := range r {
		if !math.IsNaN(r[i]) {
			groups[p.Ex[i]+"|"+p.Sector[i]] = append(groups[p.Ex[i]+"|"+p.Sector[i]], i)
			mkts[p.Ex[i]] = append(mkts[p.Ex[i]], i)
		}
	}
	med := func(ix []int) float64 {
		v := make([]float64, len(ix))
		for k, i := range ix {
			v[k] = r[i]
		}
		return median(v)
	}
	out := make([]float64, n)
	for i := range out {
		out[i] = math.NaN()
	}
	for _, ix := range groups {
		var ref float64
		if len(ix) >= 5 {
			ref = med(ix)
		} else {
			ref = med(mkts[p.Ex[ix[0]]])
		}
		for _, i := range ix {
			out[i] = r[i] - ref
		}
	}
	return out
}

// buildMonth assembles month m for horizon h. Ranks are taken within each market.
func buildMonth(p *Panel, m, h int) month {
	var mo month
	for i := range p.IDs {
		if p.member(m, i) && !math.IsNaN(p.F["T"][m][i]) {
			mo.idx = append(mo.idx, i)
		}
	}
	rel := relReturns(p, m, h)
	mo.z = make([][]float64, len(mo.idx))
	for q := range mo.z {
		mo.z[q] = make([]float64, len(Features))
	}
	mo.y = make([]float64, len(mo.idx))
	mo.rel = make([]float64, len(mo.idx))
	for _, ex := range []string{"US", "LSE"} {
		var sub []int // positions in mo.idx
		for q, i := range mo.idx {
			if p.Ex[i] == ex {
				sub = append(sub, q)
			}
		}
		if len(sub) < 20 {
			continue
		}
		for k, f := range Features {
			col, ok := p.F[f.Key]
			if !ok {
				continue
			}
			vals := make([]float64, len(sub))
			have := 0
			for a, q := range sub {
				vals[a] = col[m][mo.idx[q]] * f.Sign
				if !math.IsNaN(vals[a]) {
					have++
				}
			}
			if float64(have) < minCoverage*float64(len(sub)) {
				continue
			}
			rk := ranks(vals)
			for a, q := range sub {
				if !math.IsNaN(rk[a]) {
					mo.z[q][k] = rk[a] - 0.5
				}
			}
		}
		ys := make([]float64, len(sub))
		for a, q := range sub {
			ys[a] = rel[mo.idx[q]]
		}
		ry := ranks(ys)
		for a, q := range sub {
			mo.y[q] = ry[a]
			mo.rel[q] = rel[mo.idx[q]]
		}
	}
	return mo
}

// coefs is the month's cross-sectional regression of the outcome rank on the feature scores
// (a light ridge keeps correlated signals such as trend and momentum stable). nil if too few.
func coefs(mo month) []float64 {
	k := len(Features)
	A := make([][]float64, k)
	for i := range A {
		A[i] = make([]float64, k)
	}
	y := make([]float64, k)
	n := 0
	for q := range mo.idx {
		if math.IsNaN(mo.y[q]) {
			continue
		}
		n++
		z := mo.z[q]
		for a := 0; a < k; a++ {
			y[a] += z[a] * (mo.y[q] - 0.5)
			for b := 0; b < k; b++ {
				A[a][b] += z[a] * z[b]
			}
		}
	}
	if n < 50 {
		return nil
	}
	present := make([]bool, k)
	for a := 0; a < k; a++ {
		present[a] = A[a][a] > 1e-9
		A[a][a] += 0.5 // ridge
	}
	c := solve(A, y)
	for a := range c {
		if !present[a] { // no data for this signal this month: unknown, not zero
			c[a] = math.NaN()
		}
	}
	return c
}

// Estimate is a set of weights with the evidence behind each.
type Estimate struct {
	Mean, T, W []float64 // average monthly coefficient, its t-statistic, and the shrunk weight
	Months     int
}

// estimate averages monthly coefficients and shrinks each weight towards zero by its own
// evidence: w = mean * max(0, 1 - 4/t^2). A signal whose t-statistic is below 2 gets no weight,
// and a strong one keeps nearly all of it. h is the outcome horizon (for overlap).
func estimate(cs [][]float64, h int) Estimate {
	k := len(Features)
	e := Estimate{Mean: make([]float64, k), T: make([]float64, k), W: make([]float64, k)}
	for a := 0; a < k; a++ {
		var xs []float64
		for _, c := range cs {
			if c != nil && !math.IsNaN(c[a]) {
				xs = append(xs, c[a])
			}
		}
		m, t, n := meanT(xs, h)
		if n > e.Months {
			e.Months = n
		}
		if math.IsNaN(m) {
			continue
		}
		e.Mean[a], e.T[a] = m, t
		if !math.IsNaN(t) && t*t > 4 {
			e.W[a] = m * (1 - 4/(t*t))
		}
	}
	return e
}

// score applies weights to a month's feature scores.
func score(mo month, w []float64) []float64 {
	out := make([]float64, len(mo.idx))
	for q := range mo.idx {
		for a, v := range mo.z[q] {
			out[q] += w[a] * v
		}
	}
	return out
}

// ic is the rank correlation between a prediction and the outcome rank within each market,
// averaged over markets weighted by their size.
func ic(p *Panel, mo month, pred []float64) float64 {
	var tot, wsum float64
	for _, ex := range []string{"US", "LSE"} {
		var a, b []float64
		for q, i := range mo.idx {
			if p.Ex[i] == ex && !math.IsNaN(mo.y[q]) {
				a, b = append(a, pred[q]), append(b, mo.y[q])
			}
		}
		if c := spearman(a, b); !math.IsNaN(c) {
			tot += c * float64(len(a))
			wsum += float64(len(a))
		}
	}
	if wsum == 0 {
		return math.NaN()
	}
	return tot / wsum
}

// regimes marks each month as "up" when the index proxies (averaged) stand above their own
// 10-month average, else "down"; momentum in particular behaves differently after falls.
func regimes(p *Panel) []string {
	n := len(p.Months)
	lvl := make([]float64, n+1)
	lvl[0] = 1
	for m := 0; m < n; m++ {
		var s float64
		c := 0
		for _, r := range p.Bench {
			if m < len(r) && !math.IsNaN(r[m]) {
				s += r[m]
				c++
			}
		}
		g := 0.0
		if c > 0 {
			g = s / float64(c)
		}
		lvl[m+1] = lvl[m] * (1 + g)
	}
	out := make([]string, n)
	for m := 0; m < n; m++ {
		// level at month-end m is lvl[m] (returns in Bench[m] run from m to m+1)
		lo := m - 9
		if lo < 0 {
			lo = 0
		}
		var avg float64
		for k := lo; k <= m; k++ {
			avg += lvl[k]
		}
		avg /= float64(m - lo + 1)
		if lvl[m] >= avg {
			out[m] = "up"
		} else {
			out[m] = "down"
		}
	}
	return out
}

// calibration turns a model's out-of-sample predictions into probabilities: for each tenth of
// stocks by prediction (within its market and month), the share whose sector-relative return over
// the horizon was positive, made monotonic and pulled towards 50% when the sample is small.
type CalBin struct {
	Decile int     `json:"decile"`
	Prob   float64 `json:"prob"`
	N      int     `json:"n"`
}

func calibrate(p *Panel, months []month, preds [][]float64) []CalBin {
	hit, cnt := make([]float64, 10), make([]float64, 10)
	for mi, mo := range months {
		for _, ex := range []string{"US", "LSE"} {
			var qs []int
			var v []float64
			for q, i := range mo.idx {
				if p.Ex[i] == ex && !math.IsNaN(mo.rel[q]) {
					qs = append(qs, q)
					v = append(v, preds[mi][q])
				}
			}
			rk := ranks(v)
			for a, q := range qs {
				d := int(math.Min(9, math.Floor(rk[a]*10)))
				cnt[d]++
				if mo.rel[q] > 0 {
					hit[d]++
				}
			}
		}
	}
	prob := make([]float64, 10)
	w := make([]float64, 10)
	for d := 0; d < 10; d++ {
		prob[d] = (hit[d] + 10) / (cnt[d] + 20) // 20 pseudo-observations at 50%
		w[d] = cnt[d] + 20
	}
	// pool adjacent violators: probabilities must not fall as the prediction rises
	type blk struct {
		v, w float64
		n    int
	}
	var st []blk
	for d := 0; d < 10; d++ {
		st = append(st, blk{prob[d], w[d], 1})
		for len(st) > 1 && st[len(st)-2].v > st[len(st)-1].v {
			a, b := st[len(st)-2], st[len(st)-1]
			st = st[:len(st)-2]
			st = append(st, blk{(a.v*a.w + b.v*b.w) / (a.w + b.w), a.w + b.w, a.n + b.n})
		}
	}
	out := make([]CalBin, 0, 10)
	d := 0
	for _, b := range st {
		for k := 0; k < b.n; k++ {
			out = append(out, CalBin{Decile: d + 1, Prob: math.Round(b.v*1000) / 1000, N: int(cnt[d])})
			d++
		}
	}
	return out
}

// brier is the mean squared error of probabilities against outcomes (0.25 = a coin toss).
func brier(p *Panel, months []month, preds [][]float64, cal []CalBin) float64 {
	var s float64
	n := 0
	for mi, mo := range months {
		for _, ex := range []string{"US", "LSE"} {
			var qs []int
			var v []float64
			for q, i := range mo.idx {
				if p.Ex[i] == ex && !math.IsNaN(mo.rel[q]) {
					qs = append(qs, q)
					v = append(v, preds[mi][q])
				}
			}
			rk := ranks(v)
			for a, q := range qs {
				d := int(math.Min(9, math.Floor(rk[a]*10)))
				o := 0.0
				if mo.rel[q] > 0 {
					o = 1
				}
				s += (cal[d].Prob - o) * (cal[d].Prob - o)
				n++
			}
		}
	}
	if n == 0 {
		return math.NaN()
	}
	return s / float64(n)
}

func sortedKeys(m map[string]float64) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}
