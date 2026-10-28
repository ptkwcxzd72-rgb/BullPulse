package main

// Static, indexable pages: one per stock at /stock/<id>/ plus sitemap.xml. The screener itself
// lives behind app.html#ID, which search engines don't index, so these pages give each company a
// findable address with its key figures in plain HTML and a link into the full analysis.

import (
	"bytes"
	"fmt"
	"html/template"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

var pageTmpl = template.Must(template.New("stock").Funcs(template.FuncMap{
	"pct":  func(v float64) string { return signed(v*100, 1) + "%" },
	"pct0": func(v float64) string { return signed(v*100, 0) + "%" },
	"pctp": func(v *float64) string {
		if v == nil {
			return "–"
		}
		return signed(*v*100, 1) + "%"
	},
	"num0": func(v float64) string { return fmt.Sprintf("%.0f", v) },
}).Parse(`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{.R.Name}} ({{.R.T}}) shares: score, trend and value | BullPulse</title>
<meta name="description" content="{{.Desc}}">
<link rel="canonical" href="{{.URL}}">
<meta property="og:title" content="{{.R.Name}} ({{.R.T}}) on BullPulse">
<meta property="og:description" content="{{.Desc}}">
<meta property="og:url" content="{{.URL}}">
<meta property="og:image" content="{{.Base}}og.png">
<link rel="icon" href="../../favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#0E1828">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=Instrument+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="../../bp.css">
<style>
.pagehead{padding-block:6px 26px}.pagehead h1{margin:0;font:700 clamp(26px,3.4vw,36px)/1.1 var(--f-display);letter-spacing:-.02em}
.pagehead p{margin:8px 0 0;color:var(--night-muted);max-width:72ch}
main{display:grid;gap:22px;padding-block:24px 40px;max-width:1100px}
.sec{padding:18px 20px;display:grid;gap:12px}.sec h2{margin:0;font:650 18px var(--f-display)}.sec p{margin:0;max-width:85ch}
.kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.kv div{background:var(--surface);padding:12px 14px;display:grid;gap:2px}.kv .v{font:650 20px/1.15 var(--f-display);font-variant-numeric:tabular-nums}
.tt{width:100%;border-collapse:collapse;font-size:13.5px}.tt th,.tt td{padding:8px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums}
.tt th:first-child,.tt td:first-child{text-align:left}.tt th{font-size:12px;color:var(--muted);font-weight:600}
.cta{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:#fff;text-decoration:none;border-radius:10px;padding:10px 16px;font-weight:600;justify-self:start}
@media (max-width:760px){.kv{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
<script src="../../common.js" data-root="../../" defer></script>
</head>
<body>
<header class="masthead night">
  <div class="in mastbar">
    <a href="../../" class="home" aria-label="BullPulse home"><img src="../../brand/bullpulse-logo-on-dark.svg" alt="BullPulse" width="148" height="28"></a>
    <nav class="nav" aria-label="Site"><a href="../../">Home</a><a href="../../app.html">Screener</a><a href="../../portfolio.html">Portfolio</a><a href="../../alerts.html">Alerts</a></nav>
  </div>
  <div class="in pagehead">
    <h1>{{.R.Name}} <span style="color:var(--night-muted);font-weight:600">{{.R.T}}</span></h1>
    <p>{{.Market}}{{if .R.Idx}} · {{.R.Idx}}{{end}} · {{.R.Sector}}{{if .R.Trust}} · investment trust{{end}}</p>
  </div>
</header>
<main class="in">
  <section class="card sec">
    <h2>In brief</h2>
    <p>{{.Summary}}</p>
    <a class="cta" href="../../app.html#{{.R.ID}}">Open the full analysis: charts, news, fundamentals →</a>
  </section>
  <section class="card sec" aria-label="Key figures">
    <div class="kv">
      <div><span class="sub">BullPulse score</span><span class="v">{{num0 .R.Score}}<span class="sub"> /100</span></span><span class="sub">#{{.R.Rank}} of {{.N}} {{.Mkt}} stocks</span></div>
      <div><span class="sub">Share price</span><span class="v">{{.Price}}</span><span class="sub">close on {{.AsOf}}</span></div>
      <div><span class="sub">Past year</span><span class="v {{if ge .R.Ret1y 0.0}}pos{{else}}neg{{end}}">{{pct .R.Ret1y}}</span><span class="sub">{{if .R.VsIdx}}{{pctp .R.VsIdx}} vs {{.IdxName}}{{else}}price change{{end}}</span></div>
      <div><span class="sub">Dividend, last 12 months</span><span class="v">{{if .R.Div}}{{printf "%.1f" .DivYld}}%{{else}}–{{end}}</span><span class="sub">{{if .R.Div}}of the share price{{else}}none recorded{{end}}</span></div>
    </div>
    <table class="tt"><thead><tr><th>Part of the score</th><th>Percentile in its market</th><th>Weight</th></tr></thead><tbody>
      <tr><td>Trend (200-day average, golden cross, Super Trend)</td><td>{{num0 .R.TP}}</td><td>40%</td></tr>
      <tr><td>Momentum (12-month return, leaving out the last month)</td><td>{{num0 .R.MP}}</td><td>40%</td></tr>
      <tr><td>News sentiment (30 days)</td><td>{{num0 .R.SP}}</td><td>20%</td></tr>
    </tbody></table>
    {{if .Fund}}<p class="sub">{{.Fund}}</p>{{end}}
  </section>
  {{if .Peers}}<section class="card sec">
    <h2>Similar {{.Mkt}} {{.R.Sector}} companies</h2>
    <table class="tt"><thead><tr><th>Company</th><th>Score</th><th>Past year</th><th>Rank</th></tr></thead><tbody>
    {{range .Peers}}<tr><td><a href="../{{.Slug}}/">{{.Name}}</a> <span class="sub">{{.T}}</span></td><td>{{num0 .Score}}</td><td class="{{if ge .Ret1y 0.0}}pos{{else}}neg{{end}}">{{pct .Ret1y}}</td><td>#{{.Rank}}</td></tr>
    {{end}}</tbody></table>
  </section>{{end}}
  <p class="disc">Figures are from end-of-day prices to {{.AsOf}} and are updated every weekday night. The score summarises past prices and news; it is not a forecast or a recommendation to buy or sell, and you can <a href="../../score.html">see how well it has worked</a>. Not investment advice.</p>
</main>
</body>
</html>
`))

type peerLink struct {
	Name, T, Slug string
	Score, Ret1y  float64
	Rank          int
}

func slug(id string) string { return strings.ToLower(id) }

func signed(v float64, d int) string {
	s := fmt.Sprintf("%.*f", d, math.Abs(v))
	if v < 0 && s != fmt.Sprintf("%.*f", d, 0.0) {
		return "−" + s
	}
	return "+" + s
}

// peersOf returns up to n companies in the same market and sector, closest in market value
// (or in score where the size isn't known).
func peersOf(r *Row, rows []*Row, n int) []*Row {
	var ps []*Row
	for _, o := range rows {
		if o != r && o.Ex == r.Ex && o.Sector == r.Sector && o.Trust == r.Trust {
			ps = append(ps, o)
		}
	}
	dist := func(o *Row) float64 {
		if r.McapBn != nil && o.McapBn != nil && *r.McapBn > 0 && *o.McapBn > 0 {
			return math.Abs(math.Log(*o.McapBn / *r.McapBn))
		}
		return 10 + math.Abs(o.Score-r.Score)/10
	}
	sort.SliceStable(ps, func(a, b int) bool { return dist(ps[a]) < dist(ps[b]) })
	if len(ps) > n {
		ps = ps[:n]
	}
	return ps
}

func pageSummary(r *Row, n int, idxName string) string {
	var b strings.Builder
	fmt.Fprintf(&b, "%s ranks #%d of %d %s stocks on BullPulse, with a score of %.0f out of 100. ", r.Name, r.Rank, n, marketName(r.Ex), r.Score)
	trend := "down"
	if r.TrRaw >= 75 {
		trend = "up"
	} else if r.TrRaw >= 40 {
		trend = "mixed"
	}
	where := "below"
	if r.Above200 {
		where = "above"
	}
	mom := "weak"
	if r.MP >= 67 {
		mom = "strong"
	} else if r.MP >= 34 {
		mom = "middling"
	}
	fmt.Fprintf(&b, "Its long-term trend is %s (%s the 200-day average) and 12-month momentum is %s for its market. ", trend, where, mom)
	verb := "rose"
	if r.Ret1y < 0 {
		verb = "fell"
	}
	fmt.Fprintf(&b, "Over the past year the shares %s %.0f%%", verb, math.Abs(r.Ret1y*100))
	if r.VsIdx != nil {
		d := *r.VsIdx * 100
		switch {
		case math.Abs(d) < 0.5:
			fmt.Fprintf(&b, ", in line with the %s", idxName)
		case d > 0:
			fmt.Fprintf(&b, ", %.0f points better than the %s", d, idxName)
		default:
			fmt.Fprintf(&b, ", %.0f points worse than the %s", -d, idxName)
		}
	}
	b.WriteString(".")
	if r.Early {
		b.WriteString(" It is flagged as an early trend change.")
	}
	if r.NextRes != "" {
		if t, err := time.Parse("2006-01-02", r.NextRes); err == nil {
			if r.ResEst {
				fmt.Fprintf(&b, " Results are expected around %s.", t.Format("2 January"))
			} else {
				fmt.Fprintf(&b, " Results are due on %s.", t.Format("2 January"))
			}
		}
	}
	return b.String()
}

func marketName(ex string) string {
	if ex == "LSE" {
		return "UK"
	}
	return "US"
}

func priceText(r *Row) string {
	if r.Ccy == "GBX" {
		return fmt.Sprintf("%.1fp", r.Price)
	}
	return fmt.Sprintf("$%.2f", r.Price)
}

// writePages writes site/stock/<id>/index.html for every ranked stock, removes pages for stocks
// no longer ranked, and writes site/sitemap.xml.
func writePages(siteDir, base string, rows []*Row, asof time.Time) error {
	if !strings.HasSuffix(base, "/") {
		base += "/"
	}
	count := map[string]int{}
	for _, r := range rows {
		count[r.Ex]++
	}
	dir := filepath.Join(siteDir, "stock")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	keep := map[string]bool{}
	asofTxt := asof.Format("2 January 2006")
	for _, r := range rows {
		s := slug(r.ID)
		keep[s] = true
		idxName := "S&P 500"
		if r.Ex == "LSE" {
			idxName = "FTSE 100"
		}
		var peers []peerLink
		for _, p := range peersOf(r, rows, 5) {
			peers = append(peers, peerLink{Name: p.Name, T: p.T, Slug: slug(p.ID), Score: p.Score, Ret1y: p.Ret1y, Rank: p.Rank})
		}
		fundTxt := ""
		switch {
		case r.Trust:
			fundTxt = "As an investment trust it is valued on the investments it holds, so profit-based checks and the fair-value estimate are not shown."
		case r.FP != nil:
			fundTxt = fmt.Sprintf("It passes %d of 30 fundamental checks from its filings.", *r.FP)
			if r.FairVs != nil {
				dir := "above"
				if *r.FairVs < 0 {
					dir = "below"
				}
				fundTxt += fmt.Sprintf(" The price is %.0f%% %s BullPulse's base cash-flow fair-value estimate.", math.Abs(*r.FairVs*100), dir)
			}
		}
		divY := 0.0
		if r.Div != nil {
			divY = r.Div.Yld * 100
		}
		sum := pageSummary(r, count[r.Ex], idxName)
		desc := fmt.Sprintf("%s (%s): BullPulse score %.0f/100, #%d of %d %s stocks. Past year %s%%. Trend, momentum, news tone, fundamentals and fair value, updated nightly.", r.Name, r.T, r.Score, r.Rank, count[r.Ex], marketName(r.Ex), signed(r.Ret1y*100, 0))
		var buf bytes.Buffer
		err := pageTmpl.Execute(&buf, map[string]any{
			"R": r, "N": count[r.Ex], "Mkt": marketName(r.Ex), "Market": map[string]string{"LSE": "London Stock Exchange", "US": "US"}[r.Ex],
			"URL": base + "stock/" + s + "/", "Base": base, "Desc": desc, "Summary": sum, "AsOf": asofTxt, "Price": priceText(r),
			"IdxName": idxName, "DivYld": divY, "Peers": peers, "Fund": fundTxt,
		})
		if err != nil {
			return err
		}
		if err := os.MkdirAll(filepath.Join(dir, s), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(dir, s, "index.html"), buf.Bytes(), 0o644); err != nil {
			return err
		}
	}
	if ents, err := os.ReadDir(dir); err == nil {
		for _, e := range ents {
			if e.IsDir() && !keep[e.Name()] {
				os.RemoveAll(filepath.Join(dir, e.Name()))
			}
		}
	}
	// sitemap
	var sm strings.Builder
	sm.WriteString(`<?xml version="1.0" encoding="UTF-8"?>` + "\n" + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">` + "\n")
	day := asof.Format("2006-01-02")
	for _, p := range []string{"", "app.html", "portfolio.html", "alerts.html", "score.html"} {
		fmt.Fprintf(&sm, "  <url><loc>%s%s</loc><lastmod>%s</lastmod></url>\n", base, p, day)
	}
	ids := make([]string, 0, len(keep))
	for s := range keep {
		ids = append(ids, s)
	}
	sort.Strings(ids)
	for _, s := range ids {
		fmt.Fprintf(&sm, "  <url><loc>%sstock/%s/</loc><lastmod>%s</lastmod></url>\n", base, s, day)
	}
	sm.WriteString("</urlset>\n")
	if err := os.WriteFile(filepath.Join(siteDir, "sitemap.xml"), []byte(sm.String()), 0o644); err != nil {
		return err
	}
	return nil
}
