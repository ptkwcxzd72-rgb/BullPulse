package main

import (
	"encoding/json"
	"math"
	"os"
	"sort"
)

// Panel is site/data/panel.json (cmd/panel), decoded with missing values as NaN.
type Panel struct {
	Months []string
	IDs    []string
	Ex     []string
	Sector []string
	Trust  []bool
	F      map[string][][]float64 // field -> month -> stock (already divided by its scale)
	Fwd    [][]float64            // month -> stock: return to the next month-end
	Bench  map[string][]float64   // index proxy monthly returns
}

func loadPanel(path string) (*Panel, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var raw struct {
		Months []string                `json:"months"`
		IDs    []string                `json:"ids"`
		Ex     []string                `json:"ex"`
		Sector []string                `json:"sector"`
		Trust  []int                   `json:"trust"`
		Scale  map[string]float64      `json:"scale"`
		Fields map[string][][]*float64 `json:"fields"`
		Fwd    [][]*float64            `json:"fwd"`
		Bench  map[string][]*float64   `json:"bench"`
	}
	if err := json.Unmarshal(b, &raw); err != nil {
		return nil, err
	}
	conv := func(rows [][]*float64, scale float64) [][]float64 {
		out := make([][]float64, len(rows))
		for m, r := range rows {
			out[m] = make([]float64, len(raw.IDs))
			for i := range out[m] {
				out[m][i] = math.NaN()
				if i < len(r) && r[i] != nil {
					out[m][i] = *r[i] / scale
				}
			}
		}
		return out
	}
	p := &Panel{Months: raw.Months, IDs: raw.IDs, Ex: raw.Ex, Sector: raw.Sector, F: map[string][][]float64{}, Bench: map[string][]float64{}}
	p.Trust = make([]bool, len(raw.IDs))
	for i, t := range raw.Trust {
		if i < len(p.Trust) {
			p.Trust[i] = t == 1
		}
	}
	for k, rows := range raw.Fields {
		sc := raw.Scale[k]
		if sc == 0 {
			sc = 1
		}
		p.F[k] = conv(rows, sc)
	}
	p.Fwd = conv(raw.Fwd, 1e4) // basis points
	for k, r := range raw.Bench {
		v := make([]float64, len(r))
		for m := range r {
			v[m] = math.NaN()
			if r[m] != nil {
				v[m] = *r[m] / 1e4
			}
		}
		p.Bench[k] = v
	}
	return p, nil
}

// member reports whether stock i counts at month m (in its index then; panels without the
// field count everyone).
func (p *Panel) member(m, i int) bool {
	mm, ok := p.F["mem"]
	if !ok {
		return true
	}
	return math.IsNaN(mm[m][i]) || mm[m][i] >= 0.5
}

// ranks returns percentile ranks in [0,1] (ties share the average rank) of vals at idx; NaN stays NaN.
func ranks(vals []float64) []float64 {
	type kv struct {
		v float64
		i int
	}
	var xs []kv
	for i, v := range vals {
		if !math.IsNaN(v) {
			xs = append(xs, kv{v, i})
		}
	}
	out := make([]float64, len(vals))
	for i := range out {
		out[i] = math.NaN()
	}
	if len(xs) < 2 {
		for _, x := range xs {
			out[x.i] = 0.5
		}
		return out
	}
	sort.Slice(xs, func(a, b int) bool { return xs[a].v < xs[b].v })
	n := float64(len(xs) - 1)
	for a := 0; a < len(xs); {
		b := a
		for b+1 < len(xs) && xs[b+1].v == xs[a].v {
			b++
		}
		r := float64(a+b) / 2 / n
		for k := a; k <= b; k++ {
			out[xs[k].i] = r
		}
		a = b + 1
	}
	return out
}

func median(xs []float64) float64 {
	var v []float64
	for _, x := range xs {
		if !math.IsNaN(x) {
			v = append(v, x)
		}
	}
	if len(v) == 0 {
		return math.NaN()
	}
	sort.Float64s(v)
	if len(v)%2 == 1 {
		return v[len(v)/2]
	}
	return (v[len(v)/2-1] + v[len(v)/2]) / 2
}

// meanT is the mean and its t-statistic, treating every `overlap`-th observation as independent
// (returns over h months that start a month apart share most of their months).
func meanT(xs []float64, overlap int) (mean, t float64, n int) {
	var v []float64
	for _, x := range xs {
		if !math.IsNaN(x) {
			v = append(v, x)
		}
	}
	n = len(v)
	if n < 3 {
		return math.NaN(), math.NaN(), n
	}
	for _, x := range v {
		mean += x
	}
	mean /= float64(n)
	var ss float64
	for _, x := range v {
		ss += (x - mean) * (x - mean)
	}
	sd := math.Sqrt(ss / float64(n-1))
	if overlap < 1 {
		overlap = 1
	}
	neff := float64(n) / float64(overlap)
	if sd == 0 || neff < 2 {
		return mean, math.NaN(), n
	}
	return mean, mean / (sd / math.Sqrt(neff)), n
}

// spearman is the rank correlation of a and b over pairs where both are present.
func spearman(a, b []float64) float64 {
	var x, y []float64
	for i := range a {
		if !math.IsNaN(a[i]) && !math.IsNaN(b[i]) {
			x, y = append(x, a[i]), append(y, b[i])
		}
	}
	if len(x) < 10 {
		return math.NaN()
	}
	return pearson(ranks(x), ranks(y))
}

func pearson(x, y []float64) float64 {
	n := float64(len(x))
	var mx, my float64
	for i := range x {
		mx += x[i]
		my += y[i]
	}
	mx /= n
	my /= n
	var sxy, sxx, syy float64
	for i := range x {
		sxy += (x[i] - mx) * (y[i] - my)
		sxx += (x[i] - mx) * (x[i] - mx)
		syy += (y[i] - my) * (y[i] - my)
	}
	if sxx == 0 || syy == 0 {
		return math.NaN()
	}
	return sxy / math.Sqrt(sxx*syy)
}

// normInv is the inverse of the standard normal distribution function (Acklam's approximation,
// accurate to about 1e-9), used for the multiple-testing bar.
func normInv(p float64) float64 {
	a := []float64{-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00}
	b := []float64{-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01}
	c := []float64{-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00}
	d := []float64{7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00}
	switch {
	case p <= 0:
		return math.Inf(-1)
	case p >= 1:
		return math.Inf(1)
	case p < 0.02425:
		q := math.Sqrt(-2 * math.Log(p))
		return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q + c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q + 1)
	case p > 1-0.02425:
		return -normInv(1 - p)
	}
	q := p - 0.5
	r := q * q
	return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r + a[5]) * q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r + 1)
}

// solve returns x with A x = y (A is k x k, modified in place); nil if singular.
func solve(A [][]float64, y []float64) []float64 {
	k := len(y)
	for c := 0; c < k; c++ {
		p := c
		for r := c + 1; r < k; r++ {
			if math.Abs(A[r][c]) > math.Abs(A[p][c]) {
				p = r
			}
		}
		if math.Abs(A[p][c]) < 1e-12 {
			return nil
		}
		A[c], A[p] = A[p], A[c]
		y[c], y[p] = y[p], y[c]
		for r := c + 1; r < k; r++ {
			f := A[r][c] / A[c][c]
			for cc := c; cc < k; cc++ {
				A[r][cc] -= f * A[c][cc]
			}
			y[r] -= f * y[c]
		}
	}
	x := make([]float64, k)
	for r := k - 1; r >= 0; r-- {
		s := y[r]
		for cc := r + 1; cc < k; cc++ {
			s -= A[r][cc] * x[cc]
		}
		x[r] = s / A[r][r]
	}
	return x
}
