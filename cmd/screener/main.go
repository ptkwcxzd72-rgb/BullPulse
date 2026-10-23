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
	"runtime/debug"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/cinar/indicator/v2/asset"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/fund"
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
	// Fundamentals Profile (30 checks) and DCF; shown and screened on, not in the composite
	FP     *int     `json:"FP,omitempty"`     // checks passed out of 30
	FA     []int    `json:"FA,omitempty"`     // value, growth, track record, health, dividends (0-6 each)
	FairVs *float64 `json:"fairVs,omitempty"` // price vs DCF base estimate (negative = below)
	// headline ratios for the custom screen builder and portfolio page
	PE      *float64 `json:"pe,omitempty"`
	DivY    *float64 `json:"divY,omitempty"`
	FCFY    *float64 `json:"fcfY,omitempty"`
	ROE     *float64 `json:"roe,omitempty"`
	DE      *float64 `json:"de,omitempty"`
	Implied *float64 `json:"implied,omitempty"` // growth the price implies (reverse DCF)
	McapBn  *float64 `json:"mcapBn,omitempty"`  // market cap, USD billions
	Grower  bool     `json:"grower"`
	Flags   []string `json:"flags,omitempty"` // data-quality warnings shown on the site
	Ins     *Insider `json:"ins,omitempty"`   // open-market insider dealing, last 90 days (US)

	sentRaw   float64
	insRecent []map[string]any
	lastDate  time.Time
	provider  string
	detail    map[string]any
}

// Fund is one company's growth figures from scripts/fetch_fundamentals.py.
type Fund struct {
	Period    string    `json:"period"`
	AsOf      string    `json:"asof"`
	RevGrowth *float64  `json:"rev_growth"`
	RevAccel  *float64  `json:"rev_accel"`
	EpsGrowth *float64  `json:"eps_growth"`
	Fin       *fund.Fin `json:"fin"`
}

// Insider summarises Form 4 open-market dealing from scripts/fetch_insiders.py.
type Insider struct {
	Buyers  int              `json:"buyers"`
	BuyVal  float64          `json:"buyVal"`
	Sellers int              `json:"sellers"`
	SellVal float64          `json:"sellVal"`
	Cluster bool             `json:"cluster"`
	Recent  []map[string]any `json:"recent,omitempty"`
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
	fundUK := flag.String("fundamentals-uk", "data/fundamentals_uk.json", "annual-report figures for UK companies (ESEF)")
	evPath := flag.String("events", "data/events.jsonl", "alert log (appended)")
	feedDir := flag.String("feeds", "site/feeds", "RSS feeds directory")
	siteURL := flag.String("site-url", "https://bullpulse.co.uk/", "public address used in feed links")
	insPath := flag.String("insiders", "data/insiders.json", "insider dealing from SEC Form 4 filings")
	fxPath := flag.String("fx", "data/fx.json", "GBP exchange rates for UK companies reporting in other currencies")
	histPath := flag.String("history", "data/history/scores.csv", "daily score history (appended)")
	qualPath := flag.String("quality", "data/quality.json", "data-quality report (read by the price sync)")
	flag.Parse()
	log := slog.Default()
	// a crash is reported as a GitHub annotation (run logs are not always readable), with the
	// innermost frames of our own code
	defer func() {
		if r := recover(); r != nil {
			var frames []string
			for _, l := range strings.Split(string(debug.Stack()), "\n") {
				if strings.Contains(l, "BullPulse/") && strings.Contains(l, ".go:") {
					frames = append(frames, strings.TrimSpace(l))
				}
			}
			fmt.Printf("::error::screener crashed: %v at %s\n", r, strings.Join(frames, " <- "))
			os.Exit(2)
		}
	}()

	stocks, err := core.LoadUniverse(*universe)
	if err != nil {
		fmt.Printf("::error::screener: universe: %v\n", err)
		os.Exit(1)
	}
	repo := asset.NewFileSystemRepository(*prices)
	arts := loadArticles(*news)
	funds := map[string]Fund{}
	if b, err := os.ReadFile(*fundPath); err == nil {
		var f struct {
			Stocks map[string]Fund `json:"stocks"`
		}
		if json.Unmarshal(b, &f) == nil && f.Stocks != nil {
			funds = f.Stocks
		}
	}
	// UK: annual-report figures, converted from the reporting currency into pence so they
	// line up with London prices
	var fx struct {
		ToGBP map[string]float64 `json:"to_gbp"`
	}
	if b, err := os.ReadFile(*fxPath); err == nil {
		json.Unmarshal(b, &fx)
	}
	if b, err := os.ReadFile(*fundUK); err == nil {
		var f struct {
			Stocks map[string]Fund `json:"stocks"`
		}
		if json.Unmarshal(b, &f) == nil {
			for id, e := range f.Stocks {
				if e.Fin != nil {
					ccy := e.Fin.Ccy
					if ccy == "" {
						ccy = "GBP"
					}
					if r, ok := fx.ToGBP[ccy]; ok && r > 0 {
						sc := e.Fin.Scale(r * 100)
						e.Fin = &sc
					} else {
						e.Fin = nil
					}
				}
				funds[id] = e
			}
		}
	}
	insiders := map[string]*Insider{}
	if b, err := os.ReadFile(*insPath); err == nil {
		var f struct {
			Stocks map[string]*Insider `json:"stocks"`
		}
		if json.Unmarshal(b, &f) == nil && f.Stocks != nil {
			insiders = f.Stocks
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
		if in, ok := insiders[id]; ok && in != nil {
			recent := in.Recent
			sum := *in
			sum.Recent = nil
			row.Ins = &sum
			row.insRecent = recent
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
		list := []map[string]any{}
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
		if row.insRecent != nil {
			detail["insiders"] = row.insRecent
		}
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
	addFundamentals(rows, funds, fx.ToGBP)

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
			fresh := (r.GC.Long == 1 && r.GC.Since <= 60) || (r.Cross200 != nil && *r.Cross200 <= 20)
			// news must not be turning against the stock: tone steady or improving, and not clearly
			// negative. (Requiring a strict improvement excluded everything while the news history
			// was only days old, because 30- and 90-day tone are then identical.)
			newsOK := r.ToneChg >= 0 && (r.NewsN30 == 0 || r.Tone30 > -0.1)
			r.Early = fresh && (r.MP > r.Mp || r.MP >= 40) && newsOK && r.RSI < 70
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
	events := loadEvents(*evPath, day, 90, detectEvents(day, rows, prev))
	if err := saveEvents(*evPath, events); err != nil {
		log.Error("events", "error", err)
	}
	if err := writeFeeds(*feedDir, *siteURL, rows, events); err != nil {
		log.Error("feeds", "error", err)
	}
	if err := writeEventsJSON(filepath.Join(*out, "events.json"), events, 600); err != nil {
		log.Error("events json", "error", err)
	}
	evByID := map[string][]Event{}
	for _, e := range events {
		if len(evByID[e.ID]) < 10 {
			evByID[e.ID] = append(evByID[e.ID], e)
		}
	}
	for _, r := range rows {
		r.detail["events"] = evByID[r.ID]
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
		"stocks": rows, "breadth": breadth, "fx": fx.ToGBP, "weights": map[string]float64{"trend": core.WTrend, "momentum": core.WMomentum, "sentiment": core.WSentiment}}
	b, _ := json.Marshal(snap)
	if err := os.WriteFile(filepath.Join(*out, "snapshot.json"), b, 0o644); err != nil {
		fmt.Printf("::error::screener: writing snapshot: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("screener: %d stocks ranked, prices to %s; %d excluded (stale), %d flagged, %d to re-download\n",
		len(rows), day, len(excluded), len(flagged), len(resync))
}

// addFundamentals computes ratios, the DCF and the 30-check profile for stocks with filing data.
// Medians are taken within each market so "cheap" and "strong" are relative to peers.
// usdPerGBP converts pounds to dollars from data/fx.json (which stores GBP per unit).
func usdPerGBP(fx map[string]float64) (float64, bool) {
	if g, ok := fx["USD"]; ok && g > 0 {
		return 1 / g, true
	}
	return 0, false
}

func addFundamentals(rows []*Row, funds map[string]Fund, fx map[string]float64) {
	type item struct {
		r *Row
		f fund.Fin
		m fund.Metrics
		d fund.DCF
	}
	byEx := map[string][]*item{}
	for _, r := range rows {
		f, ok := funds[r.ID]
		if !ok || f.Fin == nil {
			continue
		}
		it := &item{r: r, f: *f.Fin, m: fund.Compute(*f.Fin, r.Price)}
		it.d = fund.EstimateDCF(it.f, r.Sector, r.Price, r.RevGrowth)
		byEx[r.Ex] = append(byEx[r.Ex], it)
	}
	for _, items := range byEx {
		peers := make([]fund.Peer, len(items))
		for k, it := range items {
			peers[k] = fund.Peer{Sector: it.r.Sector, M: it.m, RevGrowth: it.r.RevGrowth}
		}
		med := fund.PeerMedians(peers)
		for _, it := range items {
			pr := fund.Build(it.f, it.m, it.d, it.r.Sector, it.r.RevGrowth, it.r.RevAccel, it.r.EpsGrowth, med)
			total := pr.Total
			it.r.FP = &total
			for _, a := range pr.Areas {
				it.r.FA = append(it.r.FA, a.Score)
			}
			it.r.FairVs = it.d.VsPrice
			it.r.PE, it.r.DivY, it.r.FCFY, it.r.ROE, it.r.DE, it.r.Implied = it.m.PE, it.m.DivYield, it.m.FCFYield, it.m.ROE, it.m.DebtToEquity, it.d.Implied
			if it.m.MarketCap != nil {
				usd := *it.m.MarketCap / 1e9 // US: dollars
				if it.r.Ex == "LSE" {
					usd = math.NaN()
					if r, ok := usdPerGBP(fx); ok {
						usd = *it.m.MarketCap / 100 * r / 1e9 // pence -> pounds -> dollars
					}
				}
				if !math.IsNaN(usd) {
					v := math.Round(usd*100) / 100
					it.r.McapBn = &v
				}
			}
			it.r.detail["fund"] = map[string]any{"profile": pr, "dcf": it.d, "metrics": it.m,
				"fin": map[string]any{"revenue": it.f.RevenueTTM, "netIncome": it.f.NetIncomeTTM, "fcfAvg3": it.f.FCFAvg3,
					"revCagr3": it.f.RevCAGR3, "cash": it.f.Cash, "debt": it.f.Debt, "equity": it.f.Equity, "shares": it.f.Shares, "ttmEnd": it.f.TTMEnd, "balanceEnd": it.f.BalanceEnd}}
		}
	}
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
