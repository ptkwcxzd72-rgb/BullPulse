// Command validate runs the BullPulse out-of-sample test described in the design doc.
//
// At every month-end it scores each stock on trend and momentum (percentiles within
// its market, equal weights because historical news sentiment is not available),
// sorts the market into quintiles, and measures forward 1-, 3- and 6-month returns
// against the equal-weight average of the same market. The weights are fixed in
// advance, so no parameter is fitted on the data being tested.
//
// It also checks the "early trend change" flag (without its news-tone condition,
// which has no history) and estimates trading costs for holding the top quintile.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/cinar/indicator/v2/asset"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/member"
)

var horizons = []int{21, 63, 126}
var hNames = []string{"1 month", "3 months", "6 months"}

type obs struct {
	stock int
	j     int
	score float64
	mp    float64 // momentum percentile
	early bool
	fwd   [3]float64
}

type stat struct {
	n         int
	sum, sum2 float64
}

func (s *stat) add(v float64) { s.n++; s.sum += v; s.sum2 += v * v }
func (s stat) mean() float64  { return s.sum / float64(s.n) }
func (s stat) t() float64 {
	if s.n < 3 {
		return math.NaN()
	}
	m := s.mean()
	sd := math.Sqrt((s.sum2/float64(s.n) - m*m) * float64(s.n) / float64(s.n-1))
	return m / (sd / math.Sqrt(float64(s.n)))
}

// Cost per side as a fraction of value: spread + commission; UK buys add 0.5% stamp duty.
func costs(market string) (buy, sell float64) {
	if market == "UK" {
		return 0.001 + 0.005, 0.001
	}
	return 0.001, 0.001
}

type marketResult struct {
	Market     string             `json:"market"`
	Stocks     int                `json:"stocks"`
	From       string             `json:"from,omitempty"`
	To         string             `json:"to,omitempty"`
	Months     int                `json:"months"`
	Quintile   [3][5]float64      `json:"quintile_excess"` // mean forward excess return by horizon and quintile (Q1 = lowest)
	Spread     [3]float64         `json:"q5_minus_q1"`
	SpreadT    [3]float64         `json:"q5_minus_q1_t"`
	SpreadHit  float64            `json:"q5_beats_q1_share_1m"`
	Q5Turnover float64            `json:"q5_monthly_turnover"`
	Q5NetMonth float64            `json:"q5_net_monthly_excess"`
	Early      map[string]float64 `json:"early"`
	ByYear     map[string]float64 `json:"spread_1m_by_year"`
}

func pct(v float64) string { return fmt.Sprintf("%+.2f%%", v*100) }

func main() {
	universe := flag.String("universe", "universe", "directory of universe CSV files")
	prices := flag.String("prices", "data/prices", "price repository directory")
	outMD := flag.String("report", "reports/validation.md", "markdown report path")
	outJSON := flag.String("json", "site/data/validation.json", "JSON results path")
	pitPath := flag.String("fund-pit", "data/fundamentals_pit.jsonl", "point-in-time fundamentals (scripts/fundamentals_history.py)")
	memDir := flag.String("membership", "universe/history", "index membership history")
	flag.Parse()

	stocks, err := core.LoadUniverse(*universe)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	repo := asset.NewFileSystemRepository(*prices)

	var results []marketResult
	var fres *fundResult
	pit := loadPIT(*pitPath)
	mem := member.Load(*memDir)
	for _, market := range []string{"US", "UK"} {
		var ss []core.Stock
		var xs []*core.Series
		for _, s := range stocks {
			if s.Market != market {
				continue
			}
			x, err := core.Load(repo, s)
			if err != nil || len(x.Close) < core.MinBars+130 {
				continue
			}
			ss, xs = append(ss, s), append(xs, x)
		}
		if len(xs) < 20 {
			fmt.Printf("validate: %s skipped (%d stocks with enough history)\n", market, len(xs))
			continue
		}
		// month-end calendar: every date seen, keep the last trading day of each month
		seen := map[string]time.Time{}
		for _, x := range xs {
			for _, d := range x.Dates {
				k := d.Format("2006-01")
				if d.After(seen[k]) {
					seen[k] = d
				}
			}
		}
		var ends []time.Time
		for _, d := range seen {
			ends = append(ends, d)
		}
		sort.Slice(ends, func(a, b int) bool { return ends[a].Before(ends[b]) })
		pos := make([]map[time.Time]int, len(xs))
		for i, x := range xs {
			pos[i] = map[time.Time]int{}
			for j, d := range x.Dates {
				pos[i][d] = j
			}
		}

		res := marketResult{Market: market, Stocks: len(xs), Early: map[string]float64{}, ByYear: map[string]float64{}}
		var qs [3][5]stat
		var spread [3]stat
		var spreadNO [3]stat // non-overlapping samples for the t-statistic
		var early [3]stat
		earlyN, months, hit := 0, 0, 0
		var turnover stat
		var prevQ5 map[int]bool
		byYear := map[string]*stat{}
		prevMP := map[int]float64{}

		for mi, d := range ends {
			var ob []obs
			var tr, mo []float64
			for i, x := range xs {
				j, ok := pos[i][d]
				if !ok || j < core.MinBars || !mem.Member(ss[i].Market, ss[i].Ticker, d.Format("2006-01-02")) {
					continue // not trading yet, or not in its index at the time
				}
				t, m := x.TrendRaw(j), x.Momentum(j)
				if math.IsNaN(t) || math.IsNaN(m) {
					continue
				}
				o := obs{stock: i, j: j}
				for h, n := range horizons {
					if j+n < len(x.Close) {
						o.fwd[h] = x.Close[j+n]/x.Close[j] - 1
					} else {
						o.fwd[h] = math.NaN()
					}
				}
				ob = append(ob, o)
				tr, mo = append(tr, t), append(mo, m)
			}
			if len(ob) < 20 || math.IsNaN(ob[0].fwd[0]) {
				continue
			}
			tp, mp := core.Percentiles(tr), core.Percentiles(mo)
			for k := range ob {
				ob[k].score = 0.5*tp[k] + 0.5*mp[k]
				ob[k].mp = mp[k]
				x, j := xs[ob[k].stock], ob[k].j
				fresh := (x.GoldenCross[j] == 1 && core.Since(x.GoldenCross, j) <= 60) || (func() bool { a := x.DaysAbove200(j); return a >= 0 && a <= 20 })()
				pm, had := prevMP[ob[k].stock]
				ob[k].early = fresh && ((had && mp[k] > pm) || mp[k] >= 40) && x.RSI[j] < 70
			}
			for k := range ob {
				prevMP[ob[k].stock] = mp[k]
			}
			sort.Slice(ob, func(a, b int) bool { return ob[a].score < ob[b].score })
			months++
			if res.From == "" {
				res.From = d.Format("2006-01-02")
			}
			res.To = d.Format("2006-01-02")
			q5 := map[int]bool{}
			for h := range horizons {
				var mkt stat
				for _, o := range ob {
					if !math.IsNaN(o.fwd[h]) {
						mkt.add(o.fwd[h])
					}
				}
				if mkt.n < 20 {
					continue
				}
				var qm [5]stat
				for k, o := range ob {
					q := k * 5 / len(ob)
					if !math.IsNaN(o.fwd[h]) {
						qm[q].add(o.fwd[h] - mkt.mean())
					}
					if h == 0 && q == 4 {
						q5[o.stock] = true
					}
					if o.early && !math.IsNaN(o.fwd[h]) {
						early[h].add(o.fwd[h] - mkt.mean())
						if h == 0 {
							earlyN++
						}
					}
				}
				for q := 0; q < 5; q++ {
					qs[h][q].add(qm[q].mean())
				}
				sp := qm[4].mean() - qm[0].mean()
				spread[h].add(sp)
				if mi%(horizons[h]/21) == 0 {
					spreadNO[h].add(sp)
				}
				if h == 0 {
					if sp > 0 {
						hit++
					}
					y := d.Format("2006")
					if byYear[y] == nil {
						byYear[y] = &stat{}
					}
					byYear[y].add(sp)
				}
			}
			if prevQ5 != nil && len(q5) > 0 {
				changed := 0
				for k := range q5 {
					if !prevQ5[k] {
						changed++
					}
				}
				turnover.add(float64(changed) / float64(len(q5)))
			}
			prevQ5 = q5
		}
		for h := range horizons {
			for q := 0; q < 5; q++ {
				res.Quintile[h][q] = qs[h][q].mean()
			}
			res.Spread[h] = spread[h].mean()
			res.SpreadT[h] = spreadNO[h].t()
			res.Early[hNames[h]] = early[h].mean()
		}
		res.Early["observations"] = float64(earlyN)
		res.Months = months
		res.SpreadHit = float64(hit) / float64(spread[0].n)
		buy, sell := costs(market)
		res.Q5Turnover = turnover.mean()
		res.Q5NetMonth = res.Quintile[0][4] - res.Q5Turnover*(buy+sell)
		for y, s := range byYear {
			res.ByYear[y] = s.mean()
		}
		results = append(results, res)
		if market == "US" {
			fres = fundamentalsTest(ss, xs, ends, pos, pit)
		}
	}

	// report
	var b strings.Builder
	fmt.Fprintf(&b, "# BullPulse validation report\n\nGenerated %s. Price-only composite (50%% trend, 50%% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.\n\n", time.Now().UTC().Format("2006-01-02"))
	b.WriteString("**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.\n\n")
	for _, r := range results {
		fmt.Fprintf(&b, "## %s (%d stocks, %d month-ends, %s to %s)\n\n", r.Market, r.Stocks, r.Months, r.From, r.To)
		b.WriteString("| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |\n|---|---|---|---|---|---|---|---|\n")
		for h := range horizons {
			fmt.Fprintf(&b, "| %s | %s | %s | %s | %s | %s | %s | %.2f |\n", hNames[h], pct(r.Quintile[h][0]), pct(r.Quintile[h][1]), pct(r.Quintile[h][2]), pct(r.Quintile[h][3]), pct(r.Quintile[h][4]), pct(r.Spread[h]), r.SpreadT[h])
		}
		fmt.Fprintf(&b, "\nQ5 beat Q1 in %.0f%% of months (1-month horizon). Top-quintile monthly turnover %.0f%%; estimated net monthly excess return of holding Q5 after costs: %s.\n\n", r.SpreadHit*100, r.Q5Turnover*100, pct(r.Q5NetMonth))
		fmt.Fprintf(&b, "Early trend changes (%.0f flags): mean excess return %s at 1 month, %s at 3 months, %s at 6 months.\n\n", r.Early["observations"], pct(r.Early["1 month"]), pct(r.Early["3 months"]), pct(r.Early["6 months"]))
		years := make([]string, 0, len(r.ByYear))
		for y := range r.ByYear {
			years = append(years, y)
		}
		sort.Strings(years)
		b.WriteString("| Year | Mean monthly Q5 − Q1 |\n|---|---|\n")
		for _, y := range years {
			fmt.Fprintf(&b, "| %s | %s |\n", y, pct(r.ByYear[y]))
		}
		b.WriteString("\n")
	}
	if fres != nil && fres.Profile.Months > 0 {
		fmt.Fprintf(&b, "## Fundamentals (US, %d companies, %s to %s)\n\n", fres.Stocks, fres.From, fres.To)
		b.WriteString("Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.\n\n")
		b.WriteString("| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |\n|---|---|---|---|---|---|---|\n")
		row := func(name string, q qres) {
			for h := range horizons {
				fmt.Fprintf(&b, "| %s | %s | %s | %s | %s | %s | %.2f |\n", name, hNames[h], pct(q.Quintile[h][0]), pct(q.Quintile[h][2]), pct(q.Quintile[h][4]), pct(q.Spread[h]), q.SpreadT[h])
				name = ""
			}
		}
		row("Profile (30 checks)", fres.Profile)
		row("Price below DCF", fres.DCF)
		row("Low implied growth", fres.Implied)
		for _, n := range []string{"Value", "Growth", "Track record", "Health", "Dividends"} {
			row(n, fres.Areas[n])
		}
		b.WriteString("\n")
	}
	if len(results) == 0 {
		b.WriteString("No market had enough price history to test (at least 20 stocks with 390+ trading days).\n")
	}
	os.MkdirAll(filepath.Dir(*outMD), 0o755)
	os.WriteFile(*outMD, []byte(b.String()), 0o644)
	js, _ := json.MarshalIndent(map[string]any{"generated": time.Now().UTC().Format(time.RFC3339), "markets": results, "fundamentals": fres}, "", " ")
	os.MkdirAll(filepath.Dir(*outJSON), 0o755)
	os.WriteFile(*outJSON, js, 0o644)
	fmt.Print(b.String())
}
