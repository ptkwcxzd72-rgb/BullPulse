// Command screener computes the nightly BullPulse ranking.
//
// It reads the universe lists, daily price histories (written by the library's
// indicator-sync tool) and scored news articles, then writes the static JSON the
// website loads: site/data/snapshot.json plus one file per stock.
package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/cinar/indicator/v2/asset"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
)

const keep = 260 // bars sent to the browser for charts

// eventWeight gives company-specific news (results, guidance, deals, legal) more say in the
// sentiment score than general coverage.
var eventWeight = map[string]float64{"Earnings": 1.5, "Guidance": 1.5, "M&A": 1.2, "Legal / regulatory": 1.2,
	"Management": 1.0, "Capital": 1.0, "Other": 0.8}

// Article is one scored news item (written by scripts/score_news.py).
type Article struct {
	Date     string   `json:"date"`
	Ticker   string   `json:"ticker"`
	Market   string   `json:"market"`
	Headline string   `json:"headline"`
	Source   string   `json:"source"`
	URL      string   `json:"url"`
	Event    string   `json:"event"`
	Score    *float64 `json:"score"`
	Label    string   `json:"label"`
	Conf     float64  `json:"conf"`
	Rel      float64  `json:"rel"`
}

type pos struct {
	Long  int `json:"long"`
	Since int `json:"since"`
}

// Row is one stock in snapshot.json (field names match the website).
type Row struct {
	T        string    `json:"t"`
	Ex       string    `json:"ex"`
	Name     string    `json:"name"`
	Sector   string    `json:"sector"`
	Ccy      string    `json:"ccy"`
	ID       string    `json:"id"`
	Price    float64   `json:"price"`
	Chg1d    float64   `json:"chg1d"`
	Ret1y    float64   `json:"ret1y"`
	Mom      float64   `json:"mom"`
	TrRaw    float64   `json:"tr_raw"`
	Above200 bool      `json:"above200"`
	GC       pos       `json:"gc"`
	ST       pos       `json:"st"`
	RSI      float64   `json:"rsi"`
	ATRPct   float64   `json:"atrPct"`
	HV       float64   `json:"hv"`
	Vol1y    float64   `json:"vol1y"`
	Hi52     float64   `json:"hi52"`
	Lo52     float64   `json:"lo52"`
	SMA200   float64   `json:"sma200"`
	SMA50    float64   `json:"sma50"`
	Cross200 *int      `json:"cross200"`
	Tone30   float64   `json:"tone30"`
	Tone90   float64   `json:"tone90"`
	ToneChg  float64   `json:"toneChg"`
	NewsVol  float64   `json:"newsVol"`
	NewsN30  int       `json:"newsN30"`
	Event    bool      `json:"event"`
	Spark    []float64 `json:"spark"`
	TP       float64   `json:"T"`
	MP       float64   `json:"M"`
	SP       float64   `json:"S"`
	Mp       float64   `json:"Mp"`
	Score    float64   `json:"score"`
	Rank     int       `json:"rank"`
	RankChg  int       `json:"rankChg"`
	Early    bool      `json:"early"`
	// growth (US, from SEC filings); shown and screened on, not part of the composite until validated
	RevGrowth *float64 `json:"revGrowth"`
	RevAccel  *float64 `json:"revAccel"`
	EpsGrowth *float64 `json:"epsGrowth"`
	FundAsOf  string   `json:"fundAsOf,omitempty"`
	FundBasis string   `json:"fundBasis,omitempty"`
	GP        *float64 `json:"G"`
	Grower    bool     `json:"grower"`
	Flags     []string `json:"flags,omitempty"` // data-quality warnings shown on the site

	sentRaw  float64
	lastDate time.Time
	provider string
	detail   map[string]any
}

// Fund is one company's growth figures from scripts/fetch_fundamentals.py.
type Fund struct {
	Period    string   `json:"period"`
	AsOf      string   `json:"asof"`
	RevGrowth *float64 `json:"rev_growth"`
	RevAccel  *float64 `json:"rev_accel"`
	EpsGrowth *float64 `json:"eps_growth"`
}

// issue records a data-quality problem for data/quality.json.
type issue struct {
	ID     string `json:"id"`
	Reason string `json:"reason"`
}

func r2(v float64) float64 { return math.Round(v*100) / 100 }
func r4(v float64) float64 { return math.Round(v*10000) / 10000 }

func nullable(xs []float64, from int) []*float64 {
	out := make([]*float64, 0, len(xs)-from)
	for _, v := range xs[from:] {
		if math.IsNaN(v) || math.IsInf(v, 0) {
			out = append(out, nil)
			continue
		}
		w := math.Round(v*1000) / 1000
		out = append(out, &w)
	}
	return out
}

func loadArticles(path string) map[string][]Article {
	out := map[string][]Article{}
	f, err := os.Open(path)
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var a Article
		if json.Unmarshal(sc.Bytes(), &a) == nil && a.Score != nil {
			key := core.Exchange(a.Market) + "-" + a.Ticker
			out[key] = append(out[key], a)
		}
	}
	return out
}

func main() {
	universe := flag.String("universe", "universe", "directory of universe CSV files")
	prices := flag.String("prices", "data/prices", "price repository directory (filesystem)")
	news := flag.String("news", "data/news/articles.jsonl", "scored news articles (JSON lines)")
	out := flag.String("out", "site/data", "output directory for the website data")
	fundPath := flag.String("fundamentals", "data/fundamentals.json", "growth figures from SEC filings")
	histPath := flag.String("history", "data/history/scores.csv", "daily score history (appended)")
	qualPath := flag.String("quality", "data/quality.json", "data-quality report (read by the price sync)")
	flag.Parse()
	log := slog.Default()

	stocks, err := core.LoadUniverse(*universe)
	if err != nil {
		log.Error("universe", "error", err)
		os.Exit(1)
	}
	repo := asset.NewFileSystemRepository(*prices)
	arts := loadArticles(*news)
	funds := map[string]Fund{}
	if b, err := os.ReadFile(*fundPath); err == nil {
		var f struct {
			Stocks map[string]Fund `json:"stocks"`
		}
		if json.Unmarshal(b, &f) == nil {
			funds = f.Stocks
		}
	}
	history := loadHistory(*histPath)
	flagged := []issue{}
	resync := []string{}

	// previous snapshot, for week-on-week rank change and momentum trend
	prev := map[string]Row{}
	if b, err := os.ReadFile(filepath.Join(*out, "snapshot.json")); err == nil {
		var old struct {
			Demo   bool  `json:"demo"`
			Stocks []Row `json:"stocks"`
		}
		if json.Unmarshal(b, &old) == nil && !old.Demo {
			for _, r := range old.Stocks {
				prev[r.ID] = r
			}
		}
	}

	os.MkdirAll(filepath.Join(*out, "stocks"), 0o755)
	var rows []*Row
	var asof time.Time
	for _, s := range stocks {
		x, err := core.Load(repo, s)
		if err != nil || len(x.Close) < core.MinBars+20 {
			continue
		}
		n := len(x.Close)
		j := n - 1
		if x.Dates[j].After(asof) {
			asof = x.Dates[j]
		}
		id := s.ID()
		row := &Row{T: s.Ticker, Ex: core.Exchange(s.Market), Name: s.Name, Sector: s.Sector, Ccy: core.Currency(s.Market), ID: id,
			Price: x.Close[j], Chg1d: x.Close[j]/x.Close[j-1] - 1, Ret1y: x.Close[j]/x.Close[j-252] - 1,
			Mom: x.Momentum(j), TrRaw: x.TrendRaw(j), Above200: x.Close[j] > x.SMA200[j],
			GC: pos{x.GoldenCross[j], core.Since(x.GoldenCross, j)}, ST: pos{x.SuperTrend[j], core.Since(x.SuperTrend, j)},
			RSI: r2(x.RSI[j]), ATRPct: r4(x.ATR[j] / x.Close[j]), HV: r4(x.HV[j] * math.Sqrt(252)), Vol1y: r4(x.RealisedVol(j)),
			SMA200: r2(x.SMA200[j]), SMA50: r2(x.SMA50[j])}
		hi, lo := 0.0, math.Inf(1)
		for i := n - 252; i < n; i++ {
			hi, lo = math.Max(hi, x.High[i]), math.Min(lo, x.Low[i])
		}
		row.Hi52, row.Lo52 = hi, lo
		row.lastDate, row.provider = x.Dates[j], s.ProviderTicker

		// data quality: split-like jumps (stored history not re-adjusted) and long gaps
		for i := n - 300; i < n; i++ {
			if i < 1 {
				continue
			}
			r := x.Close[i]/x.Close[i-1] - 1
			if math.Abs(r) > 0.45 {
				row.Flags = append(row.Flags, fmt.Sprintf("price moved %+.0f%% on %s; history will be re-downloaded in case of an unadjusted split", r*100, x.Dates[i].Format("2 Jan 2006")))
				resync = append(resync, s.ProviderTicker)
				break
			}
		}
		for i := n - keep + 1; i < n; i++ {
			if x.Dates[i].Sub(x.Dates[i-1]) > 8*24*time.Hour {
				row.Flags = append(row.Flags, fmt.Sprintf("no prices between %s and %s", x.Dates[i-1].Format("2 Jan"), x.Dates[i].Format("2 Jan 2006")))
				break
			}
		}
		if f, ok := funds[id]; ok {
			row.RevGrowth, row.RevAccel, row.EpsGrowth, row.FundAsOf, row.FundBasis = f.RevGrowth, f.RevAccel, f.EpsGrowth, f.AsOf, f.Period
		}
		if d := x.DaysAbove200(j); d >= 0 {
			row.Cross200 = &d
		}
		for i := n - keep; i < n; i += 5 {
			row.Spark = append(row.Spark, r2(x.Close[i]))
		}

		// news: daily relevance-weighted tone over the charted window
		dates := make([]string, 0, keep)
		idx := map[string]int{}
		for i := n - keep; i < n; i++ {
			d := x.Dates[i].Format("2006-01-02")
			idx[d] = len(dates)
			dates = append(dates, d)
		}
		sum, wsum := make([]float64, keep), make([]float64, keep)
		cnt := make([]float64, keep)
		var list []map[string]any
		sa := arts[id]
		sort.Slice(sa, func(a, b int) bool { return sa[a].Date > sa[b].Date })
		for _, a := range sa {
			// attach the article to the last trading day on or before its date, so weekend
			// and holiday news (and news dated after the latest close) still counts
			k, in := idx[a.Date]
			if !in {
				k = sort.SearchStrings(dates, a.Date) - 1
				if k < 0 || a.Date < dates[0] {
					continue
				}
			}
			w := a.Rel * eventWeight[a.Event]
			if w == 0 {
				w = a.Rel * 0.8
			}
			sum[k] += *a.Score * w
			wsum[k] += w
			cnt[k]++
			if len(list) < 60 {
				list = append(list, map[string]any{"d": a.Date, "h": a.Headline, "src": a.Source, "url": a.URL, "ev": a.Event,
					"s": r2(*a.Score), "rel": r2(a.Rel), "lab": a.Label, "conf": r2(a.Conf)})
			}
		}
		tone := func(from int) float64 {
			var s, w float64
			for k := from; k < keep; k++ {
				s, w = s+sum[k], w+wsum[k]
			}
			if w == 0 {
				return 0
			}
			return s / w
		}
		row.Tone30, row.Tone90 = r4(tone(keep-21)), r4(tone(keep-63))
		row.ToneChg = r4(row.Tone30 - row.Tone90)
		var n30, nAll, n5 float64
		for k := 0; k < keep; k++ {
			nAll += cnt[k]
			if k >= keep-21 {
				n30 += cnt[k]
			}
			if k >= keep-5 {
				n5 += cnt[k]
			}
		}
		row.NewsN30 = int(n30)
		if nAll > 0 {
			row.NewsVol = r2((n30 / 21) / (nAll / keep))
		}
		row.Event = n5 >= 3 && n5 >= 3*(nAll/keep)*5
		row.sentRaw = row.Tone30
		daily := make([]*float64, keep)
		for k := range daily {
			if wsum[k] > 0 {
				v := math.Round(sum[k]/wsum[k]*1000) / 1000
				daily[k] = &v
			}
		}

		bars := make([][6]any, 0, keep)
		for i := n - keep; i < n; i++ {
			bars = append(bars, [6]any{x.Dates[i].Format("2006-01-02"), r2(x.Open[i]), r2(x.High[i]), r2(x.Low[i]), r2(x.Close[i]), int64(x.Volume[i])})
		}
		from := n - keep
		detail := map[string]any{"bars": bars, "tone": daily, "arts": list, "ind": map[string]any{
			"sma50": nullable(x.SMA50, from), "sma200": nullable(x.SMA200, from), "bbU": nullable(x.BBUpper, from), "bbL": nullable(x.BBLower, from),
			"rsi": nullable(x.RSI, from), "macd": nullable(x.MACD, from), "sig": nullable(x.Sig, from), "atr": nullable(x.ATR, from), "obv": nullable(x.OBV, from)}}
		row.detail = detail
		rows = append(rows, row)
	}

	// stale prices: anything more than a week behind the latest close is left out of the ranking
	var fresh []*Row
	excluded := []issue{}
	for _, r := range rows {
		if asof.Sub(r.lastDate) > 7*24*time.Hour {
			excluded = append(excluded, issue{r.ID, "last price " + r.lastDate.Format("2006-01-02") + " is more than a week old"})
			continue
		}
		if len(r.Flags) > 0 {
			flagged = append(flagged, issue{r.ID, strings.Join(r.Flags, "; ")})
		}
		fresh = append(fresh, r)
	}
	rows = fresh

	if len(rows) == 0 {
		// Never replace the published data (or the demo) with an empty ranking.
		fmt.Println("screener: no stocks have enough price history yet; leaving site/data unchanged")
		return
	}

	// percentile scores and ranks within each market
	breadth := map[string]map[string]any{}
	for _, ex := range []string{"LSE", "US"} {
		var m []*Row
		for _, r := range rows {
			if r.Ex == ex {
				m = append(m, r)
			}
		}
		if len(m) == 0 {
			continue
		}
		get := func(f func(*Row) float64) []float64 {
			v := make([]float64, len(m))
			for i, r := range m {
				v[i] = f(r)
			}
			return v
		}
		tp := core.Percentiles(get(func(r *Row) float64 { return r.TrRaw }))
		mp := core.Percentiles(get(func(r *Row) float64 { return r.Mom }))
		sp := core.Percentiles(get(func(r *Row) float64 { return r.sentRaw }))
		gp := core.Percentiles(get(func(r *Row) float64 {
			if r.RevGrowth == nil {
				return math.NaN()
			}
			return *r.RevGrowth
		}))
		for i, r := range m {
			r.TP, r.MP, r.SP = math.Round(tp[i]), math.Round(mp[i]), math.Round(sp[i])
			if !math.IsNaN(gp[i]) {
				g := math.Round(gp[i])
				r.GP = &g
			}
			r.Score = math.Round(core.WTrend*r.TP + core.WMomentum*r.MP + core.WSentiment*r.SP)
			r.Mp = r.MP
			if p, ok := prev[r.ID]; ok {
				r.Mp = p.MP
			}
		}
		sort.SliceStable(m, func(a, b int) bool { return m[a].Score > m[b].Score })
		above, gc, adv, events := 0, 0, 0, 0
		var toneSum float64
		for i, r := range m {
			r.Rank = i + 1
			if p, ok := prev[r.ID]; ok && p.Rank > 0 {
				r.RankChg = p.Rank - r.Rank
			}
			fresh := (r.GC.Long == 1 && r.GC.Since <= 60) || (r.Cross200 != nil && *r.Cross200 <= 40)
			r.Early = fresh && (r.MP >= r.Mp || r.MP >= 50) && r.ToneChg > 0 && r.RSI < 70
			// growing and turning up: revenue growth of 15%+ that is holding or speeding up,
			// with the long-term trend positive or freshly turned
			if r.RevGrowth != nil && *r.RevGrowth >= 0.15 && (r.RevAccel == nil || *r.RevAccel >= -0.02) &&
				(r.Early || (r.Above200 && r.GC.Long == 1)) {
				r.Grower = true
			}
			if r.Above200 {
				above++
			}
			gc += r.GC.Long
			if r.Chg1d > 0 {
				adv++
			}
			if r.Event {
				events++
			}
			toneSum += r.Tone30
		}
		breadth[ex] = map[string]any{"n": len(m), "above200": above, "gc": gc, "adv": adv, "events": events, "tone": r4(toneSum / float64(len(m)))}
	}

	day := asof.Format("2006-01-02")
	history = history.with(day, rows)
	for _, r := range rows {
		r.detail["hist"] = history.forStock(r.ID, 180)
		b, _ := json.Marshal(r.detail)
		if err := os.WriteFile(filepath.Join(*out, "stocks", r.ID+".json"), b, 0o644); err != nil {
			log.Error("write", "id", r.ID, "error", err)
		}
	}
	if err := history.save(*histPath); err != nil {
		log.Error("history", "error", err)
	}
	qual := map[string]any{"asof": day, "checked": len(rows) + len(excluded), "excluded": excluded, "flagged": flagged, "resync": resync}
	qb, _ := json.MarshalIndent(qual, "", " ")
	os.MkdirAll(filepath.Dir(*qualPath), 0o755)
	os.WriteFile(*qualPath, qb, 0o644)
	os.WriteFile(filepath.Join(*out, "quality.json"), qb, 0o644)
	fundAsOf := ""
	if b, err := os.ReadFile(*fundPath); err == nil {
		var f struct {
			Generated string `json:"generated"`
		}
		json.Unmarshal(b, &f)
		fundAsOf = f.Generated
	}

	snap := map[string]any{"demo": false, "fundamentals": fundAsOf, "quality": map[string]int{"excluded": len(excluded), "flagged": len(flagged)}, "asof": asof.Format("2006-01-02"), "generated": time.Now().UTC().Format(time.RFC3339),
		"stocks": rows, "breadth": breadth, "weights": map[string]float64{"trend": core.WTrend, "momentum": core.WMomentum, "sentiment": core.WSentiment}}
	b, _ := json.Marshal(snap)
	if err := os.WriteFile(filepath.Join(*out, "snapshot.json"), b, 0o644); err != nil {
		log.Error("write snapshot", "error", err)
		os.Exit(1)
	}
	fmt.Printf("screener: %d stocks ranked, prices to %s; %d excluded (stale), %d flagged, %d to re-download\n",
		len(rows), day, len(excluded), len(flagged), len(resync))
}

// scoreHistory holds one line per stock per day: date,id,score,T,M,S,rank.
type scoreHistory [][]string

func loadHistory(path string) scoreHistory {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	rows, _ := csv.NewReader(f).ReadAll()
	if len(rows) > 0 && rows[0][0] == "date" {
		rows = rows[1:]
	}
	return rows
}

// with replaces any rows for day and appends today's scores.
func (h scoreHistory) with(day string, rows []*Row) scoreHistory {
	out := h[:0:0]
	for _, r := range h {
		if r[0] != day {
			out = append(out, r)
		}
	}
	for _, r := range rows {
		out = append(out, []string{day, r.ID, fmt.Sprint(r.Score), fmt.Sprint(r.TP), fmt.Sprint(r.MP), fmt.Sprint(r.SP), fmt.Sprint(r.Rank)})
	}
	return out
}

// forStock returns the last n [date, score, rank] points for one stock.
func (h scoreHistory) forStock(id string, n int) [][3]any {
	var pts [][3]any
	for _, r := range h {
		if r[1] == id {
			sc, _ := strconv.ParseFloat(r[2], 64)
			rk, _ := strconv.Atoi(r[6])
			pts = append(pts, [3]any{r[0], sc, rk})
		}
	}
	if len(pts) > n {
		pts = pts[len(pts)-n:]
	}
	return pts
}

func (h scoreHistory) save(path string) error {
	os.MkdirAll(filepath.Dir(path), 0o755)
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	w.Write([]string{"date", "id", "score", "T", "M", "S", "rank"})
	w.WriteAll(h)
	return w.Error()
}
