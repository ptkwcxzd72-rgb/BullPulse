// Command panel builds the month-end history behind "Test this screen" on the website.
//
// For every month-end of the last ten years and every stock with enough price history it
// records the measures a screen can use, computed only from information available at that
// date: price-based factors from the price history, and fundamentals from the filings
// published by then (point in time; scripts/fundamentals_history.py and
// scripts/uk_fundamentals_history.py). It also records each stock's return over the following
// month and the index proxies' monthly returns, so the browser can replay any screen.
//
// Sentiment, news tone and insider dealing have no history and are left out.
package main

import (
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"

	"github.com/cinar/indicator/v2/asset"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/fund"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/pit"
)

// fields and the factor each value is multiplied by before rounding to an integer
var fields = []struct {
	Key   string
	Scale float64
}{
	{"score", 1}, {"T", 1}, {"M", 1}, {"G", 1}, {"FP", 1}, {"FA0", 1}, {"FA1", 1}, {"FA2", 1}, {"FA3", 1}, {"FA4", 1},
	{"ret1y", 1000}, {"mom", 1000}, {"d200", 1000}, {"hi52", 1000}, {"rsi", 1}, {"vol1y", 1000},
	{"revGrowth", 1000}, {"epsGrowth", 1000}, {"pe", 10}, {"divY", 1000}, {"fcfY", 1000}, {"roe", 1000}, {"de", 1000},
	{"fairVs", 1000}, {"implied", 1000}, {"mcapBn", 10}, {"Vp", 1},
}

type fxRow struct {
	date     string
	usd, eur float64 // per pound
}

func loadFX(path string) []fxRow {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	rows, _ := csv.NewReader(f).ReadAll()
	var out []fxRow
	for _, r := range rows {
		if len(r) < 3 || r[0] == "date" {
			continue
		}
		u, e1 := strconv.ParseFloat(r[1], 64)
		e, e2 := strconv.ParseFloat(r[2], 64)
		if e1 == nil && e2 == nil && u > 0 && e > 0 {
			out = append(out, fxRow{r[0], u, e})
		}
	}
	return out
}

// toGBP is pounds per unit of ccy on day (latest rate on or before it; first rate before the series).
func toGBP(fx []fxRow, ccy, day string) float64 {
	if ccy == "" || ccy == "GBP" {
		return 1
	}
	if len(fx) == 0 {
		return math.NaN()
	}
	k := sort.Search(len(fx), func(i int) bool { return fx[i].date > day }) - 1
	if k < 0 {
		k = 0
	}
	switch ccy {
	case "USD":
		return 1 / fx[k].usd
	case "EUR":
		return 1 / fx[k].eur
	}
	return math.NaN()
}

func pct(xs []float64) []float64 { return core.Percentiles(xs) }

func main() {
	universe := flag.String("universe", "universe", "directory of universe CSV files")
	prices := flag.String("prices", "data/prices", "price repository directory")
	pitUS := flag.String("pit-us", "data/fundamentals_pit.jsonl", "US point-in-time fundamentals")
	pitUK := flag.String("pit-uk", "data/fundamentals_pit_uk.jsonl", "UK point-in-time fundamentals")
	fxPath := flag.String("fx-history", "data/fx_history.csv", "daily dollars and euros per pound")
	out := flag.String("out", "site/data/panel.json", "output")
	years := flag.Int("years", 10, "history length")
	flag.Parse()

	stocks, err := core.LoadUniverse(*universe)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	repo := asset.NewFileSystemRepository(*prices)
	rowsPIT := pit.Load(*pitUS)
	for k, v := range pit.Load(*pitUK) {
		rowsPIT[k] = v
	}
	fx := loadFX(*fxPath)

	var ss []core.Stock
	var xs []*core.Series
	for _, s := range stocks {
		x, err := core.Load(repo, s)
		if err != nil || len(x.Close) < core.MinBars+21 {
			continue
		}
		ss, xs = append(ss, s), append(xs, x)
	}
	// month-end calendar from all stocks, last N years, excluding the current (unfinished) month
	last := time.Time{}
	seen := map[string]time.Time{}
	for _, x := range xs {
		for _, d := range x.Dates {
			k := d.Format("2006-01")
			if d.After(seen[k]) {
				seen[k] = d
			}
			if d.After(last) {
				last = d
			}
		}
	}
	var ends []time.Time
	for k, d := range seen {
		if k != last.Format("2006-01") && d.After(last.AddDate(-*years, 0, 0)) {
			ends = append(ends, d)
		}
	}
	sort.Slice(ends, func(a, b int) bool { return ends[a].Before(ends[b]) })
	// index of the last trading day on or before t, per stock
	at := func(x *core.Series, t time.Time) int {
		return sort.Search(len(x.Dates), func(i int) bool { return x.Dates[i].After(t) }) - 1
	}
	divs := make([]func(time.Time) float64, len(xs))
	for i, s := range ss {
		if rs := rowsPIT[s.ID()]; len(rs) > 0 {
			divs[i] = pit.DivFactor(rs, xs[i])
		}
	}

	n := len(ss)
	data := map[string][][]any{}
	for _, f := range fields {
		data[f.Key] = make([][]any, len(ends))
	}
	fwd := make([][]any, len(ends))
	months := make([]string, len(ends))
	for mi, d := range ends {
		months[mi] = d.Format("2006-01-02")
		ds := months[mi]
		vals := map[string][]float64{}
		for _, f := range fields {
			v := make([]float64, n)
			for i := range v {
				v[i] = math.NaN()
			}
			vals[f.Key] = v
		}
		fw := make([]float64, n)
		for i := range fw {
			fw[i] = math.NaN()
		}
		type fitem struct {
			i   int
			f   fund.Fin
			m   fund.Metrics
			dc  fund.DCF
			row pit.Row
		}
		byMkt := map[string][]*fitem{}
		trRaw, momRaw, revG := make([]float64, n), make([]float64, n), make([]float64, n)
		for i := range trRaw {
			trRaw[i], momRaw[i], revG[i] = math.NaN(), math.NaN(), math.NaN()
		}
		for i, x := range xs {
			j := at(x, d)
			// the stock must have traded within the last week of the month
			if j < core.MinBars || d.Sub(x.Dates[j]) > 7*24*time.Hour {
				continue
			}
			c := x.Close[j]
			trRaw[i], momRaw[i] = x.TrendRaw(j), x.Momentum(j)
			vals["ret1y"][i] = c/x.Close[j-252] - 1
			vals["mom"][i] = x.Momentum(j)
			if x.SMA200[j] > 0 {
				vals["d200"][i] = c/x.SMA200[j] - 1
			}
			hi := 0.0
			for k := j - 251; k <= j; k++ {
				hi = math.Max(hi, x.High[k])
			}
			if hi > 0 {
				vals["hi52"][i] = c/hi - 1
			}
			vals["rsi"][i] = x.RSI[j]
			vals["vol1y"][i] = x.RealisedVol(j)
			if mi+1 < len(ends) {
				if k := at(x, ends[mi+1]); k > j && ends[mi+1].Sub(x.Dates[k]) <= 7*24*time.Hour {
					fw[i] = x.Close[k]/c - 1
				}
			} else if j+1 < len(x.Close) { // last month-end: return to the latest close
				fw[i] = x.Close[len(x.Close)-1]/c - 1
			}
			// fundamentals as published by this date
			rs := rowsPIT[ss[i].ID()]
			k := sort.Search(len(rs), func(q int) bool { return rs[q].Date > ds }) - 1
			if k < 0 || rs[k].Date < d.AddDate(0, -15, 0).Format("2006-01-02") || ss[i].Trust {
				continue
			}
			r := rs[k]
			f := r.Fin.PerShare(1 / r.Split)
			if ss[i].Market == "UK" {
				g := toGBP(fx, r.Fin.Ccy, ds)
				if math.IsNaN(g) {
					continue
				}
				f = f.Scale(g * 100) // reporting currency -> pence, like UK prices
			}
			px := c
			if divs[i] != nil {
				px = c / divs[i](d)
			}
			it := &fitem{i: i, f: f, row: r, m: fund.Compute(f, px)}
			it.dc = fund.EstimateDCF(f, ss[i].Sector, px, r.RevGrowth)
			byMkt[ss[i].Market] = append(byMkt[ss[i].Market], it)
			if r.RevGrowth != nil {
				revG[i] = *r.RevGrowth
			}
		}
		// percentiles within each market
		for _, mkt := range []string{"US", "UK"} {
			var idx []int
			for i := range ss {
				if ss[i].Market == mkt && !math.IsNaN(trRaw[i]) {
					idx = append(idx, i)
				}
			}
			if len(idx) < 20 {
				continue
			}
			sub := func(src []float64) []float64 {
				o := make([]float64, len(idx))
				for q, i := range idx {
					o[q] = src[i]
				}
				return o
			}
			tp, mp, gp := pct(sub(trRaw)), pct(sub(momRaw)), pct(sub(revG))
			for q, i := range idx {
				vals["T"][i], vals["M"][i] = math.Round(tp[q]), math.Round(mp[q])
				vals["score"][i] = math.Round((tp[q] + mp[q]) / 2) // trend and momentum only: sentiment has no history
				if !math.IsNaN(gp[q]) {
					vals["G"][i] = math.Round(gp[q])
				}
			}
			items := byMkt[mkt]
			if len(items) == 0 {
				continue
			}
			peers := make([]fund.Peer, len(items))
			for q, it := range items {
				peers[q] = fund.Peer{Sector: ss[it.i].Sector, M: it.m, RevGrowth: it.row.RevGrowth}
			}
			med := fund.PeerMedians(peers)
			cheap := make([]float64, len(items))
			for q, it := range items {
				i := it.i
				p := fund.Build(it.f, it.m, it.dc, ss[i].Sector, it.row.RevGrowth, it.row.RevAccel, it.row.EpsGrowth, med)
				vals["FP"][i] = float64(p.Total)
				for a := 0; a < 5 && a < len(p.Areas); a++ {
					vals[fmt.Sprintf("FA%d", a)][i] = float64(p.Areas[a].Score)
				}
				set := func(k string, v *float64) {
					if v != nil {
						vals[k][i] = *v
					}
				}
				set("revGrowth", it.row.RevGrowth)
				set("epsGrowth", it.row.EpsGrowth)
				set("pe", it.m.PE)
				set("divY", it.m.DivYield)
				set("fcfY", it.m.FCFYield)
				set("roe", it.m.ROE)
				set("de", it.m.DebtToEquity)
				set("fairVs", it.dc.VsPrice)
				set("implied", it.dc.Implied)
				if it.m.MarketCap != nil {
					mc := *it.m.MarketCap / 1e9
					if mkt == "UK" {
						mc = *it.m.MarketCap / 100 / toGBP(fx, "USD", ds) / 1e9 // pence -> pounds -> dollars
					}
					vals["mcapBn"][i] = mc
				}
				cheap[q] = math.NaN()
				if it.dc.VsPrice != nil {
					cheap[q] = -*it.dc.VsPrice
				}
			}
			cp := pct(cheap)
			for q, it := range items {
				if !math.IsNaN(cp[q]) {
					vals["Vp"][it.i] = math.Round(cp[q])
				}
			}
		}
		for _, f := range fields {
			row := make([]any, n)
			for i, v := range vals[f.Key] {
				if math.IsNaN(v) || math.IsInf(v, 0) {
					row[i] = nil
				} else {
					row[i] = int64(math.Round(v * f.Scale))
				}
			}
			data[f.Key][mi] = row
		}
		row := make([]any, n)
		for i, v := range fw {
			if math.IsNaN(v) || math.IsInf(v, 0) || math.Abs(v) > 3 {
				row[i] = nil
			} else {
				row[i] = int64(math.Round(v * 10000)) // basis points
			}
		}
		fwd[mi] = row
	}

	// index proxies: monthly returns aligned to the month-ends
	bench := map[string][]any{}
	for name, file := range map[string]string{"ftse100": "bench-ftse100", "sp500": "bench-sp500"} {
		x, err := core.Load(repo, core.Stock{ProviderTicker: file})
		if err != nil {
			continue
		}
		r := make([]any, len(ends))
		for mi, d := range ends {
			j := at(x, d)
			var k int
			if mi+1 < len(ends) {
				k = at(x, ends[mi+1])
			} else {
				k = len(x.Close) - 1
			}
			if j >= 0 && k > j {
				r[mi] = int64(math.Round((x.Close[k]/x.Close[j] - 1) * 10000))
			}
		}
		bench[name] = r
	}
	ids, ex, sec, idx := make([]string, n), make([]string, n), make([]string, n), make([]string, n)
	trust := make([]int, n)
	for i, s := range ss {
		ids[i], ex[i], sec[i], idx[i] = s.ID(), core.Exchange(s.Market), s.Sector, s.Index
		if s.Trust {
			trust[i] = 1
		}
	}
	scale := map[string]float64{}
	for _, f := range fields {
		scale[f.Key] = f.Scale
	}
	doc := map[string]any{"generated": time.Now().UTC().Format(time.RFC3339), "months": months, "ids": ids, "ex": ex, "sector": sec, "idx": idx, "trust": trust,
		"scale": scale, "fields": data, "fwd": fwd, "bench": bench,
		"note": "Month-end values from information available at each date. Returns include dividends. Sentiment, news and insider data have no history."}
	b, err := json.Marshal(doc)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.MkdirAll(filepath.Dir(*out), 0o755)
	if err := os.WriteFile(*out, b, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("panel: %d stocks, %d month-ends (%s to %s), %.1f MB\n", n, len(ends), months[0], months[len(months)-1], float64(len(b))/1e6)
	if err := writeValHist(filepath.Join(filepath.Dir(*out), "valhist.json"), months, ids, data, scale, 60); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// writeValHist saves each stock's month-end P/E, dividend yield and free-cash-flow yield for the
// last n months (as published at the time), so a stock page can show today's valuation against
// its own history without loading the whole panel.
func writeValHist(path string, months, ids []string, data map[string][][]any, scale map[string]float64, n int) error {
	from := len(months) - n
	if from < 0 {
		from = 0
	}
	keys := []string{"pe", "divY", "fcfY"}
	out := map[string]map[string][]any{}
	for i, id := range ids {
		rec := map[string][]any{}
		for _, k := range keys {
			col, have := make([]any, 0, len(months)-from), 0
			for mi := from; mi < len(months); mi++ {
				var v any
				if mi < len(data[k]) && data[k][mi] != nil {
					v = data[k][mi][i]
				}
				if v != nil {
					have++
				}
				col = append(col, v)
			}
			if have >= 12 {
				rec[k] = col
			}
		}
		if len(rec) > 0 {
			out[id] = rec
		}
	}
	doc := map[string]any{"months": months[from:], "scale": map[string]float64{"pe": scale["pe"], "divY": scale["divY"], "fcfY": scale["fcfY"]}, "stocks": out}
	b, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	fmt.Printf("valuation history: %d stocks, %.2f MB\n", len(out), float64(len(b))/1e6)
	return os.WriteFile(path, b, 0o644)
}
