package main

import (
	"encoding/csv"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"
)

// bench is one index proxy's adjusted closes.
type bench struct {
	Dates  []string
	Closes []float64
}

func loadBench(path string) *bench {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	rows, err := csv.NewReader(f).ReadAll()
	if err != nil || len(rows) < 30 {
		return nil
	}
	b := &bench{}
	for _, r := range rows[1:] {
		if len(r) < 5 {
			continue
		}
		c, err := strconv.ParseFloat(r[4], 64)
		if err != nil || c <= 0 {
			continue
		}
		b.Dates, b.Closes = append(b.Dates, r[0][:10]), append(b.Closes, c)
	}
	return b
}

// at returns the close on or before day.
func (b *bench) at(day string) float64 {
	k := sort.SearchStrings(b.Dates, day+"~") - 1
	if k < 0 {
		return math.NaN()
	}
	return b.Closes[k]
}

// ret1y is the return over the 252 trading days to day.
func (b *bench) ret1y(day string) float64 {
	k := sort.SearchStrings(b.Dates, day+"~") - 1
	if k < 252 {
		return math.NaN()
	}
	return b.Closes[k]/b.Closes[k-252] - 1
}

// writeBenchJSON publishes the last year of daily closes and ten years of month-end closes.
func writeBenchJSON(path string, benches map[string]*bench) error {
	out := map[string]any{}
	for name, b := range benches {
		if b == nil {
			continue
		}
		n := len(b.Dates)
		from := n - 260
		if from < 0 {
			from = 0
		}
		daily := make([][2]any, 0, n-from)
		for i := from; i < n; i++ {
			daily = append(daily, [2]any{b.Dates[i], math.Round(b.Closes[i]*100) / 100})
		}
		monthly := [][2]any{}
		for i := 0; i < n; i++ {
			if i == n-1 || b.Dates[i][:7] != b.Dates[i+1][:7] {
				monthly = append(monthly, [2]any{b.Dates[i], math.Round(b.Closes[i]*100) / 100})
			}
		}
		out[name] = map[string]any{"daily": daily, "monthly": monthly}
	}
	bs, err := json.Marshal(out)
	if err != nil {
		return err
	}
	return os.WriteFile(path, bs, 0o644)
}

// divInfo summarises an ex-dividend history at day, with the next ex-date estimated from the
// usual gap between payments.
func divInfo(hist [][2]any, day string, price float64) *DivInfo {
	type ev struct {
		d string
		a float64
	}
	var evs []ev
	for _, h := range hist {
		d, _ := h[0].(string)
		a, _ := h[1].(float64)
		if d != "" && a > 0 && d <= day {
			evs = append(evs, ev{d, a})
		}
	}
	if len(evs) == 0 {
		return nil
	}
	sort.Slice(evs, func(i, j int) bool { return evs[i].d < evs[j].d })
	last := evs[len(evs)-1]
	t, _ := time.Parse("2006-01-02", day)
	cut := t.AddDate(-1, 0, 0).Format("2006-01-02")
	var ttm float64
	for _, e := range evs {
		if e.d > cut {
			ttm += e.a
		}
	}
	info := &DivInfo{Last: last.d, Amt: math.Round(last.a*10000) / 10000, TTM: math.Round(ttm*10000) / 10000}
	if price > 0 {
		info.Yld = math.Round(ttm/price*10000) / 10000
		if info.Yld > 0.25 { // amounts in the wrong unit (pounds vs pence): not shown
			return nil
		}
	}
	if len(evs) >= 3 {
		var gaps []float64
		for i := len(evs) - 1; i > 0 && len(gaps) < 4; i-- {
			a, _ := time.Parse("2006-01-02", evs[i-1].d)
			b, _ := time.Parse("2006-01-02", evs[i].d)
			gaps = append(gaps, b.Sub(a).Hours()/24)
		}
		sort.Float64s(gaps)
		g := gaps[len(gaps)/2]
		lt, _ := time.Parse("2006-01-02", last.d)
		next := lt.Add(time.Duration(g*24) * time.Hour)
		if g >= 25 && g <= 400 && next.After(t.AddDate(0, 0, -7)) && ttm > 0 {
			info.Next = next.Format("2006-01-02")
		}
	}
	return info
}

// ukResultsEstimate gives the next expected results date from the financial year end:
// annual results about 75 days after the year end, half-year results about 75 days after
// the half-year end.
func ukResultsEstimate(fyEnd, day string) string {
	fy, err := time.Parse("2006-01-02", fyEnd)
	if err != nil {
		return ""
	}
	today, _ := time.Parse("2006-01-02", day)
	for k := 0; k < 8; k++ {
		end := fy.AddDate(0, 6*k, 0)
		d := end.AddDate(0, 0, 75)
		if d.After(today) {
			return d.Format("2006-01-02")
		}
	}
	return ""
}

func readJSON(path string, v any) bool {
	b, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	return json.Unmarshal(b, v) == nil
}

func benchPaths(dir string) map[string]string {
	return map[string]string{"ftse100": filepath.Join(dir, "bench-ftse100.csv"), "sp500": filepath.Join(dir, "bench-sp500.csv")}
}
