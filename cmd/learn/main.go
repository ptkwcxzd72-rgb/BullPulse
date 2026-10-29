// Command learn is BullPulse's learning loop, run monthly after the history panel is rebuilt.
//
// It asks one question: which signals have helped pick stocks that beat their own sector over
// the next six months, and by how much? It answers it the careful way:
//
//   - Outcomes are returns relative to the stock's sector in its market, so it learns stock
//     selection rather than which sector happened to boom.
//   - Each month's lesson is a cross-sectional regression; weights are the average lesson, shrunk
//     towards zero by the strength of its evidence (no weight at all below t = 2).
//   - Walk-forward only: every month is predicted with weights learned from earlier months whose
//     outcomes were already known, never from the future.
//   - The current model (the champion) is replaced only when a challenger beats it out of sample
//     by more than the bar for the number of variants ever tried, and does not lose over the last
//     24 months, which are held back from the decision.
//   - Every trial is logged (data/learning/trials.jsonl), and every change of model is recorded
//     with its reason (data/learning/model.json), for the website to show.
//
// It also measures what happened after particular events (event studies) and grades the nightly
// predictions once their outcomes are known (the live record).
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"time"
)

const (
	horizon    = 6  // months: the outcome the model is chosen on
	minTrain   = 36 // months of known outcomes before the first out-of-sample prediction
	holdout    = 24 // final out-of-sample months kept out of the decision
	sentWeight = 0.2
)

type Change struct {
	Date   string             `json:"date"`
	Event  string             `json:"event"`
	Reason string             `json:"reason"`
	From   map[string]float64 `json:"from,omitempty"`
	To     map[string]float64 `json:"to,omitempty"`
}

// Model is data/learning/model.json, read by the nightly screener.
type Model struct {
	Adopted     bool                          `json:"adopted"` // false: the original fixed recipe is in use
	Since       string                        `json:"since"`
	Horizon     int                           `json:"horizonMonths"`
	Weights     map[string]float64            `json:"weights"`
	Regime      map[string]map[string]float64 `json:"regime,omitempty"`
	Sentiment   float64                       `json:"sentimentWeight"`
	Calibration []CalBin                      `json:"calibration"`
	Tried       []string                      `json:"tried"` // every distinct challenger ever tested
	Updated     string                        `json:"updated"`
	Changes     []Change                      `json:"changes"`
}

func defaultModel(today string) *Model {
	return &Model{Since: today, Horizon: horizon, Weights: map[string]float64{"T": 0.5, "M": 0.5}, Sentiment: sentWeight,
		Changes: []Change{{Date: today, Event: "start", Reason: "Original recipe: trend and momentum equally, plus 20% news sentiment. Weights set by hand before any test."}}}
}

func vec(w map[string]float64) []float64 {
	v := make([]float64, len(Features))
	for k, f := range Features {
		v[k] = w[f.Key]
	}
	return v
}

func toMap(v []float64) map[string]float64 {
	m := map[string]float64{}
	for k, f := range Features {
		if v[k] != 0 {
			m[f.Key] = math.Round(v[k]*10000) / 10000
		}
	}
	return m
}

func readJSON(path string, v any) bool {
	b, err := os.ReadFile(path)
	return err == nil && json.Unmarshal(b, v) == nil
}

func writeJSON(path string, v any, indent bool) error {
	os.MkdirAll(filepath.Dir(path), 0o755)
	var b []byte
	var err error
	if indent {
		b, err = json.MarshalIndent(v, "", " ")
	} else {
		b, err = json.Marshal(v)
	}
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}

func r4(x float64) any {
	if math.IsNaN(x) || math.IsInf(x, 0) {
		return nil
	}
	return math.Round(x*10000) / 10000
}

func main() {
	panelPath := flag.String("panel", "site/data/panel.json", "month-end history (cmd/panel)")
	modelPath := flag.String("model", "data/learning/model.json", "the model in use (read and updated)")
	trialsPath := flag.String("trials", "data/learning/trials.jsonl", "log of every challenger tried (appended)")
	outPath := flag.String("out", "site/data/learning.json", "results for the website")
	prices := flag.String("prices", "data/prices", "daily prices, for event studies and grading")
	universe := flag.String("universe", "universe", "universe files")
	insDir := flag.String("insiders", "data/history/insiders", "insider-dealing history")
	newsDir := flag.String("news", "data/history/news_daily", "daily news history")
	pitUS := flag.String("pit-us", "data/fundamentals_pit.jsonl", "point-in-time US fundamentals (earnings surprises)")
	memDir := flag.String("membership", "universe/history", "index membership history")
	histPath := flag.String("history", "data/history/predictions.csv", "nightly prediction log")
	scoresPath := flag.String("scores", "data/history/scores.csv", "nightly score history")
	eventsOut := flag.String("events-out", "site/data/eventstudy.json", "event-study results")
	liveOut := flag.String("live-out", "site/data/live.json", "graded live record")
	flag.Parse()
	today := time.Now().UTC().Format("2006-01-02")

	p, err := loadPanel(*panelPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "panel:", err)
		os.Exit(1)
	}
	model := defaultModel(today)
	readJSON(*modelPath, model)
	if model.Weights == nil {
		model.Weights = map[string]float64{"T": 0.5, "M": 0.5}
	}

	res := learn(p, model, today)
	// log the trials and update the model
	f, err := os.OpenFile(*trialsPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err == nil {
		for _, t := range res.Trials {
			b, _ := json.Marshal(t)
			f.Write(append(b, '\n'))
		}
		f.Close()
	} else {
		os.MkdirAll(filepath.Dir(*trialsPath), 0o755)
		if f, err := os.Create(*trialsPath); err == nil {
			for _, t := range res.Trials {
				b, _ := json.Marshal(t)
				f.Write(append(b, '\n'))
			}
			f.Close()
		}
	}
	for _, t := range res.Trials {
		seen := false
		for _, x := range model.Tried {
			seen = seen || x == t.Name
		}
		if !seen {
			model.Tried = append(model.Tried, t.Name)
		}
	}
	model.Updated = today
	model.Calibration = res.Calibration
	if res.Adopt != nil {
		model.Changes = append(model.Changes, Change{Date: today, Event: "adopted", Reason: res.Decision,
			From: model.Weights, To: res.Adopt.Weights})
		model.Adopted, model.Since, model.Weights, model.Regime = true, today, res.Adopt.Weights, res.Adopt.Regime
		model.Calibration = res.Adopt.Calibration
	}
	if err := writeJSON(*modelPath, model, true); err != nil {
		fmt.Fprintln(os.Stderr, "model:", err)
		os.Exit(1)
	}
	res.Out["model"] = model
	if err := writeJSON(*outPath, res.Out, false); err != nil {
		fmt.Fprintln(os.Stderr, "learning:", err)
		os.Exit(1)
	}
	fmt.Println(res.Decision)

	// event studies and the live record need daily prices
	data := loadDaily(*universe, *prices, *memDir)
	ev := eventStudies(data, *insDir, *pitUS, *newsDir)
	if err := writeJSON(*eventsOut, ev, false); err != nil {
		fmt.Fprintln(os.Stderr, "events:", err)
	}
	live := grade(data, *histPath, *scoresPath)
	if err := writeJSON(*liveOut, live, false); err != nil {
		fmt.Fprintln(os.Stderr, "live:", err)
	}
}

type Trial struct {
	Date       string             `json:"date"`
	Name       string             `json:"name"`
	Months     int                `json:"months"`
	MeanDiffIC float64            `json:"meanDiffIC"`
	T          float64            `json:"t"`
	Bar        float64            `json:"bar"`
	HoldoutIC  float64            `json:"holdoutDiffIC"`
	Passed     bool               `json:"passed"`
	Weights    map[string]float64 `json:"weights"`
}

type candidate struct {
	Weights     map[string]float64
	Regime      map[string]map[string]float64
	Calibration []CalBin
}

type result struct {
	Trials      []Trial
	Adopt       *candidate
	Decision    string
	Calibration []CalBin
	Out         map[string]any
}

func learn(p *Panel, model *Model, today string) result {
	nM := len(p.Months)
	reg := regimes(p)
	mos := make([]month, nM)
	cs := make([][]float64, nM)
	known := make([]bool, nM)
	for m := 0; m < nM; m++ {
		mos[m] = buildMonth(p, m, horizon)
		c := 0
		for _, y := range mos[m].y {
			if !math.IsNaN(y) {
				c++
			}
		}
		known[m] = c >= 50
		if known[m] {
			cs[m] = coefs(mos[m])
		}
	}
	champ := func(m int) []float64 {
		if model.Regime != nil {
			if w, ok := model.Regime[reg[m]]; ok {
				return vec(w)
			}
		}
		return vec(model.Weights)
	}
	type oos struct {
		m                int
		champ, chal, rch float64
		pChamp, pChal    []float64
		pReg             []float64
	}
	var rows []oos
	for m := 0; m < nM; m++ {
		if !known[m] {
			continue
		}
		var train, same [][]float64
		for t := 0; t+horizon <= m; t++ {
			if cs[t] != nil {
				train = append(train, cs[t])
				if reg[t] == reg[m] {
					same = append(same, cs[t])
				}
			}
		}
		if len(train) < minTrain {
			continue
		}
		wl := estimate(train, horizon).W
		wr := wl
		if len(same) >= 24 {
			wr = estimate(same, horizon).W
		}
		pc, pl, pr := score(mos[m], champ(m)), score(mos[m], wl), score(mos[m], wr)
		rows = append(rows, oos{m, ic(p, mos[m], pc), ic(p, mos[m], pl), ic(p, mos[m], pr), pc, pl, pr})
	}
	out := map[string]any{"generated": time.Now().UTC().Format(time.RFC3339), "horizonMonths": horizon, "holdoutMonths": holdout,
		"features": Features}
	// evidence now: everything known, for 6 months and for 1 month ahead
	var all [][]float64
	for m := range cs {
		if cs[m] != nil {
			all = append(all, cs[m])
		}
	}
	full := estimate(all, horizon)
	var cs1 [][]float64
	for m := 0; m < nM; m++ {
		mo := buildMonth(p, m, 1)
		if c := coefs(mo); c != nil {
			cs1 = append(cs1, c)
		}
	}
	one := estimate(cs1, 1)
	cover := make([]float64, len(Features))
	for _, c := range all {
		for a := range c {
			if !math.IsNaN(c[a]) {
				cover[a]++
			}
		}
	}
	var ev []map[string]any
	for k, f := range Features {
		ev = append(ev, map[string]any{"key": f.Key, "name": f.Name, "about": f.About,
			"coef6": r4(full.Mean[k]), "t6": r4(full.T[k]), "weight6": r4(full.W[k]),
			"coef1": r4(one.Mean[k]), "t1": r4(one.T[k]), "months": int(cover[k]), "inModel": model.Weights[f.Key]})
	}
	out["evidence"] = ev
	out["evidenceMonths"] = full.Months
	if len(rows) < 12 {
		d := fmt.Sprintf("Not enough history to learn from yet (%d out-of-sample months); the current model stays.", len(rows))
		out["decision"] = d
		return result{Decision: d, Out: out, Calibration: model.Calibration}
	}
	sel := rows
	var hold []oos
	if len(rows) > holdout+12 {
		sel, hold = rows[:len(rows)-holdout], rows[len(rows)-holdout:]
	}
	diff := func(rs []oos, f func(o oos) float64) []float64 {
		v := make([]float64, len(rs))
		for k, o := range rs {
			v[k] = f(o) - o.champ
		}
		return v
	}
	// the bar rises with every distinct kind of challenger ever tried (Bonferroni): try ten ideas and
	// one will look good by luck. Monthly re-tests of the same idea are guarded by the holdout.
	tried := map[string]bool{}
	for _, x := range model.Tried {
		tried[x] = true
	}
	tried["Learned weights"], tried["Learned weights by market conditions"] = true, true
	n := len(tried)
	bar := math.Max(2, normInv(1-0.05/(2*float64(n))))
	type cand struct {
		name string
		f    func(o oos) float64
		pr   func(o oos) []float64
	}
	cands := []cand{
		{"Learned weights", func(o oos) float64 { return o.chal }, func(o oos) []float64 { return o.pChal }},
		{"Learned weights by market conditions", func(o oos) float64 { return o.rch }, func(o oos) []float64 { return o.pReg }},
	}
	var trials []Trial
	best := -1
	for k, c := range cands {
		md, t, _ := meanT(diff(sel, c.f), horizon)
		hd, _, hn := meanT(diff(hold, c.f), horizon)
		passed := !math.IsNaN(t) && t >= bar && md > 0 && (hn < 6 || hd >= 0)
		w := full.W
		trials = append(trials, Trial{Date: today, Name: c.name, Months: len(sel), MeanDiffIC: round(md), T: round(t), Bar: round(bar),
			HoldoutIC: round(hd), Passed: passed, Weights: toMap(w)})
		if passed && (best < 0 || t > trials[best].T) {
			best = k
		}
	}
	// out-of-sample record by year, for the chart
	type yr struct{ champ, chal, reg []float64 }
	years := map[string]*yr{}
	for _, o := range rows {
		y := p.Months[o.m][:4]
		if years[y] == nil {
			years[y] = &yr{}
		}
		years[y].champ = append(years[y].champ, o.champ)
		years[y].chal = append(years[y].chal, o.chal)
		years[y].reg = append(years[y].reg, o.rch)
	}
	var byYear []map[string]any
	for _, y := range sortedKeysYr(years) {
		a, _, _ := meanT(years[y].champ, 1)
		b, _, _ := meanT(years[y].chal, 1)
		c, _, _ := meanT(years[y].reg, 1)
		byYear = append(byYear, map[string]any{"year": y, "champion": r4(a), "learned": r4(b), "regime": r4(c), "months": len(years[y].champ)})
	}
	out["oosByYear"] = byYear
	mc, tc, _ := meanT(func() []float64 {
		v := []float64{}
		for _, o := range rows {
			v = append(v, o.champ)
		}
		return v
	}(), horizon)
	out["championIC"] = map[string]any{"mean": r4(mc), "t": r4(tc), "months": len(rows)}
	out["trials"] = trials
	out["bar"] = r4(bar)
	out["trialsEver"] = n
	out["from"], out["to"] = p.Months[rows[0].m], p.Months[rows[len(rows)-1].m]
	// calibration of the champion's predictions (all out-of-sample months)
	var cm []month
	var cp [][]float64
	for _, o := range rows {
		cm = append(cm, mos[o.m])
		cp = append(cp, o.pChamp)
	}
	cal := calibrate(p, cm, cp)
	out["calibration"] = cal
	out["brier"] = r4(brier(p, cm, cp, cal))
	res := result{Trials: trials, Out: out, Calibration: cal}
	if best < 0 {
		res.Decision = fmt.Sprintf("Kept the current model: no challenger beat it out of sample by enough (bar: t ≥ %.2f after %d trials).", bar, n)
	} else {
		c := cands[best]
		var pr [][]float64
		for _, o := range rows {
			pr = append(pr, c.pr(o))
		}
		ad := &candidate{Weights: toMap(full.W), Calibration: calibrate(p, cm, pr)}
		if best == 1 {
			ad.Regime = map[string]map[string]float64{}
			for _, r := range []string{"up", "down"} {
				var same [][]float64
				for m := range cs {
					if cs[m] != nil && reg[m] == r {
						same = append(same, cs[m])
					}
				}
				ad.Regime[r] = toMap(estimate(same, horizon).W)
			}
		}
		res.Adopt = ad
		res.Decision = fmt.Sprintf("Adopted %q: it beat the current model out of sample (t = %.2f against a bar of %.2f after %d trials) and did not lose in the last %d months.",
			c.name, trials[best].T, bar, n, holdout)
	}
	out["decision"] = res.Decision
	out["regimeNow"] = reg[len(reg)-1]
	return res
}

func round(x float64) float64 {
	if math.IsNaN(x) || math.IsInf(x, 0) {
		return 0
	}
	return math.Round(x*10000) / 10000
}

func sortedKeysYr[T any](m map[string]T) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	for a := 1; a < len(ks); a++ {
		for b := a; b > 0 && ks[b] < ks[b-1]; b-- {
			ks[b], ks[b-1] = ks[b-1], ks[b]
		}
	}
	return ks
}
