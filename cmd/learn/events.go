package main

import (
	"encoding/csv"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"

	"github.com/cinar/indicator/v2/asset"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/insider"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/member"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/pit"
)

// daily is every stock's price history plus an equal-weighted index of each sector in each
// market, so returns can be measured against the stock's own sector.
type daily struct {
	stocks []core.Stock
	xs     []*core.Series
	pos    map[string]int                // id -> index
	sector map[string]map[string]float64 // market|sector -> date -> index level
	mem    *member.History
}

func day(t time.Time) string { return t.Format("2006-01-02") }

func loadDaily(universe, prices, memDir string) *daily {
	d := &daily{pos: map[string]int{}, sector: map[string]map[string]float64{}, mem: member.Load(memDir)}
	stocks, err := core.LoadUniverse(universe)
	if err != nil {
		return d
	}
	repo := asset.NewFileSystemRepository(prices)
	for _, s := range stocks {
		x, err := core.Load(repo, s)
		if err != nil || len(x.Close) < core.MinBars {
			continue
		}
		d.pos[s.ID()] = len(d.stocks)
		d.stocks, d.xs = append(d.stocks, s), append(d.xs, x)
	}
	// sector indices: average daily return of the members trading that day
	type acc struct {
		sum float64
		n   int
	}
	rets := map[string]map[string]*acc{}
	for i, x := range d.xs {
		s := d.stocks[i]
		g := s.Market + "|" + s.Sector
		if rets[g] == nil {
			rets[g] = map[string]*acc{}
		}
		for j := 1; j < len(x.Close); j++ {
			if x.Close[j-1] <= 0 {
				continue
			}
			r := x.Close[j]/x.Close[j-1] - 1
			if math.Abs(r) > 0.5 { // a bad tick, not a return
				continue
			}
			k := day(x.Dates[j])
			if !d.mem.Member(s.Market, s.Ticker, k) {
				continue
			}
			a := rets[g][k]
			if a == nil {
				a = &acc{}
				rets[g][k] = a
			}
			a.sum += r
			a.n++
		}
	}
	for g, byDay := range rets {
		days := make([]string, 0, len(byDay))
		for k := range byDay {
			days = append(days, k)
		}
		sort.Strings(days)
		lvl := 1.0
		d.sector[g] = map[string]float64{}
		for _, k := range days {
			lvl *= 1 + byDay[k].sum/float64(byDay[k].n)
			d.sector[g][k] = lvl
		}
	}
	return d
}

// excess is the stock's return over k trading days from its first trading day after `after`,
// relative to its sector; NaN when the period hasn't finished or data is missing.
func (d *daily) excess(i int, after time.Time, k int) (float64, string) {
	x := d.xs[i]
	j := sort.Search(len(x.Dates), func(q int) bool { return x.Dates[q].After(after) })
	if j >= len(x.Dates) || j+k >= len(x.Dates) || x.Dates[j].Sub(after) > 10*24*time.Hour {
		return math.NaN(), ""
	}
	s := d.stocks[i]
	g := d.sector[s.Market+"|"+s.Sector]
	a, b := g[day(x.Dates[j])], g[day(x.Dates[j+k])]
	if a <= 0 || b <= 0 || x.Close[j] <= 0 {
		return math.NaN(), ""
	}
	return (x.Close[j+k]/x.Close[j])/(b/a) - 1, day(x.Dates[j])
}

type event struct {
	i int
	t time.Time
}

// EventType describes one kind of event the studies measure.
type EventType struct {
	Key, Name, About string
	Market           string
}

var eventTypes = []EventType{
	{"ins_cluster", "Several insiders buying", "two or more directors or officers buy shares in the open market within 30 days", "US"},
	{"ins_big", "Large insider purchase", "a director or officer buys $250,000 or more in the open market", "US"},
	{"ins_sell_cluster", "Several insiders selling", "three or more directors or officers sell within 30 days", "US"},
	{"sue_pos", "Strong earnings surprise", "quarterly earnings well above the same quarter a year earlier (standardised surprise of 2 or more)", "US"},
	{"sue_neg", "Weak earnings surprise", "quarterly earnings well below the same quarter a year earlier (standardised surprise of -2 or less)", "US"},
	{"golden_cross", "Golden cross", "the 50-day average crosses above the 200-day average", ""},
	{"death_cross", "Death cross", "the 50-day average crosses below the 200-day average", ""},
	{"high52", "New 52-week high", "the first close at a 52-week high in three months", ""},
	{"news_results_good", "Upbeat results coverage", "news about results with clearly positive tone", ""},
	{"news_results_bad", "Downbeat results coverage", "news about results with clearly negative tone", ""},
	{"news_guidance_up", "Positive guidance news", "news about guidance or outlook with positive tone", ""},
	{"news_guidance_down", "Negative guidance news", "news about guidance or outlook with negative tone (profit warnings)", ""},
	{"news_deal", "Takeover or deal news", "news about mergers, acquisitions or bids", ""},
	{"news_legal", "Legal or regulatory news", "news about lawsuits, investigations or regulators", ""},
}

var horizonsDays = []int{21, 63, 126}

func eventStudies(d *daily, insDir, pitPath, newsDir string) map[string]any {
	evs := map[string][]event{}
	add := func(k string, i int, t time.Time, last map[string]time.Time, cool int) {
		key := k + "|" + strconv.Itoa(i)
		if l, ok := last[key]; ok && t.Sub(l) < time.Duration(cool)*24*time.Hour {
			return
		}
		s := d.stocks[i]
		if !d.mem.Member(s.Market, s.Ticker, day(t)) {
			return
		}
		last[key] = t
		evs[k] = append(evs[k], event{i, t})
	}
	last := map[string]time.Time{}
	// insider dealing
	for id, txs := range insider.Load(insDir) {
		i, ok := d.pos[id]
		if !ok {
			continue
		}
		for q, tx := range txs {
			if !tx.Insider() {
				continue
			}
			if tx.Code == 'P' && tx.Value >= 250000 {
				add("ins_big", i, tx.Filed, last, 30)
			}
			buy, sell := map[string]bool{}, map[string]bool{}
			for r := q; r >= 0 && tx.Filed.Sub(txs[r].Filed) <= 30*24*time.Hour; r-- {
				if txs[r].Insider() {
					if txs[r].Code == 'P' {
						buy[txs[r].Owner] = true
					} else if txs[r].Code == 'S' {
						sell[txs[r].Owner] = true
					}
				}
			}
			if tx.Code == 'P' && len(buy) >= 2 {
				add("ins_cluster", i, tx.Filed, last, 90)
			}
			if tx.Code == 'S' && len(sell) >= 3 {
				add("ins_sell_cluster", i, tx.Filed, last, 90)
			}
		}
	}
	// earnings surprises, dated when the quarter was filed
	for id, rows := range pit.Load(pitPath) {
		i, ok := d.pos[id]
		if !ok {
			continue
		}
		prev := ""
		for _, r := range rows {
			if r.Fin.EPSQEnd == "" || r.Fin.EPSQEnd == prev {
				continue
			}
			prev = r.Fin.EPSQEnd
			t, err := time.Parse("2006-01-02", r.Date)
			if err != nil {
				continue
			}
			if sue := r.Fin.SUE(); sue >= 2 {
				add("sue_pos", i, t, last, 60)
			} else if sue <= -2 {
				add("sue_neg", i, t, last, 60)
			}
		}
	}
	// price events
	for i, x := range d.xs {
		lastHigh := -1000
		for j := 253; j < len(x.Close); j++ {
			a0, a1, b0, b1 := x.SMA50[j-1], x.SMA50[j], x.SMA200[j-1], x.SMA200[j]
			if !math.IsNaN(a0 + a1 + b0 + b1) {
				if a0 <= b0 && a1 > b1 {
					add("golden_cross", i, x.Dates[j], last, 60)
				} else if a0 >= b0 && a1 < b1 {
					add("death_cross", i, x.Dates[j], last, 60)
				}
			}
			hi := 0.0
			for k := j - 252; k < j; k++ {
				hi = math.Max(hi, x.Close[k])
			}
			if x.Close[j] > hi && j-lastHigh > 63 {
				add("high52", i, x.Dates[j], last, 0)
				lastHigh = j
			} else if x.Close[j] > hi {
				lastHigh = j
			}
		}
	}
	// news (only as much as has been collected so far)
	files, _ := filepath.Glob(filepath.Join(newsDir, "*.csv"))
	sort.Strings(files)
	for _, f := range files {
		fh, err := os.Open(f)
		if err != nil {
			continue
		}
		rows, _ := csv.NewReader(fh).ReadAll()
		fh.Close()
		if len(rows) < 2 {
			continue
		}
		col := map[string]int{}
		for k, h := range rows[0] {
			col[h] = k
		}
		num := func(r []string, k string) float64 {
			if c, ok := col[k]; ok && c < len(r) {
				v, err := strconv.ParseFloat(r[c], 64)
				if err == nil {
					return v
				}
			}
			return math.NaN()
		}
		for _, r := range rows[1:] {
			i, ok := d.pos[r[col["id"]]]
			if !ok {
				continue
			}
			t, err := time.Parse("2006-01-02", r[col["date"]])
			if err != nil {
				continue
			}
			tone := num(r, "tone")
			if num(r, "results") >= 1 && tone >= 0.3 {
				add("news_results_good", i, t, last, 20)
			}
			if num(r, "results") >= 1 && tone <= -0.3 {
				add("news_results_bad", i, t, last, 20)
			}
			if num(r, "guidance") >= 1 && tone >= 0.3 {
				add("news_guidance_up", i, t, last, 20)
			}
			if num(r, "guidance") >= 1 && tone <= -0.3 {
				add("news_guidance_down", i, t, last, 20)
			}
			if num(r, "deal") >= 1 {
				add("news_deal", i, t, last, 20)
			}
			if num(r, "legal") >= 1 {
				add("news_legal", i, t, last, 20)
			}
		}
	}
	// measure
	var out []map[string]any
	for _, et := range eventTypes {
		list := evs[et.Key]
		row := map[string]any{"key": et.Key, "name": et.Name, "about": et.About, "market": et.Market, "events": len(list)}
		var res []map[string]any
		for hk, k := range horizonsDays {
			byMonth := map[string][]float64{}
			var all []float64
			hit := 0
			for _, e := range list {
				x, start := d.excess(e.i, e.t, k)
				if math.IsNaN(x) || math.Abs(x) > 3 {
					continue
				}
				all = append(all, x)
				if x > 0 {
					hit++
				}
				byMonth[start[:7]] = append(byMonth[start[:7]], x)
			}
			var mm []float64
			for _, v := range byMonth {
				s := 0.0
				for _, x := range v {
					s += x
				}
				mm = append(mm, s/float64(len(v)))
			}
			mean, _, _ := meanT(all, 1)
			_, t, nMonths := meanT(mm, []int{1, 3, 6}[hk])
			r := map[string]any{"days": k, "n": len(all), "months": nMonths, "mean": r4(mean), "t": r4(t)}
			if len(all) > 0 {
				r["hit"] = r4(float64(hit) / float64(len(all)))
			}
			res = append(res, r)
		}
		row["horizons"] = res
		// recent events (last 120 days of each stock's data), for stock pages
		var recent []map[string]string
		for _, e := range list {
			x := d.xs[e.i]
			if x.Dates[len(x.Dates)-1].Sub(e.t) <= 120*24*time.Hour {
				recent = append(recent, map[string]string{"id": d.stocks[e.i].ID(), "date": day(e.t)})
			}
		}
		row["recent"] = recent
		out = append(out, row)
	}
	return map[string]any{"generated": time.Now().UTC().Format(time.RFC3339), "types": out,
		"note": "Returns are measured against an equal-weighted index of the stock's own sector in its market, from the first close after the event, only while the stock was in its index."}
}
