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

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
)

// learnedModel is data/learning/model.json, written monthly by cmd/learn.
type learnedModel struct {
	Adopted     bool                          `json:"adopted"`
	Since       string                        `json:"since"`
	Weights     map[string]float64            `json:"weights"`
	Regime      map[string]map[string]float64 `json:"regime"`
	Sentiment   float64                       `json:"sentimentWeight"`
	Calibration []struct {
		Decile int     `json:"decile"`
		Prob   float64 `json:"prob"`
	} `json:"calibration"`
}

func loadModel(path string) *learnedModel {
	m := &learnedModel{Weights: map[string]float64{"T": 0.5, "M": 0.5}, Sentiment: core.WSentiment}
	if b, err := os.ReadFile(path); err == nil {
		json.Unmarshal(b, m)
	}
	if len(m.Weights) == 0 {
		m.Weights = map[string]float64{"T": 0.5, "M": 0.5}
	}
	return m
}

// marketRegime is "up" when the index proxies stand above their average of the last ten
// month-ends, as in cmd/learn.
func marketRegime(benches []*bench) string {
	var lv []float64
	up, n := 0, 0
	for _, b := range benches {
		if b == nil || len(b.Closes) < 260 {
			continue
		}
		lv = lv[:0]
		for i := range b.Dates {
			if i == len(b.Dates)-1 || b.Dates[i][:7] != b.Dates[i+1][:7] {
				lv = append(lv, b.Closes[i])
			}
		}
		if len(lv) < 10 {
			continue
		}
		var avg float64
		for _, v := range lv[len(lv)-10:] {
			avg += v
		}
		avg /= 10
		n++
		if lv[len(lv)-1] >= avg {
			up++
		}
	}
	if n > 0 && up*2 < n {
		return "down"
	}
	return "up"
}

// featureValue is a row's value for one of cmd/learn's signals, oriented so higher is better.
func featureValue(r *Row, key string) float64 {
	nan := math.NaN()
	switch key {
	case "T":
		return r.TP
	case "M":
		return r.MP
	case "G":
		if r.RevGrowth != nil {
			return *r.RevGrowth
		}
	case "FP":
		if r.FP != nil {
			return float64(*r.FP)
		}
	case "Vp":
		if r.FairVs != nil {
			return -*r.FairVs
		}
	case "vol1y":
		return -r.Vol1y
	case "rev1m":
		return -r.ret1m
	case "insB":
		if r.Ex == "US" {
			if r.Ins != nil {
				return float64(r.Ins.Buyers)
			}
			return 0
		}
	case "sue":
		if r.SUE != nil {
			return *r.SUE
		}
	}
	return nan
}

// applyModel scores one market's stocks with the learned model: each signal's percentile within
// the market (missing = middle), weighted, then turned into a percentile itself. With an adopted
// model the score is that percentile blended with news sentiment; otherwise the original recipe
// stays and the model part only sets the probability. The probability is the calibrated chance of
// beating the stock's sector over six months.
func applyModel(m []*Row, model *learnedModel, regime string) {
	w := model.Weights
	if model.Regime != nil {
		if rw, ok := model.Regime[regime]; ok {
			w = rw
		}
	}
	part := make([]float64, len(m))
	for key, wt := range w {
		if wt == 0 {
			continue
		}
		vals := make([]float64, len(m))
		have := 0
		for i, r := range m {
			vals[i] = featureValue(r, key)
			if !math.IsNaN(vals[i]) {
				have++
			}
		}
		if float64(have) < 0.3*float64(len(m)) {
			continue
		}
		pc := core.Percentiles(vals)
		for i := range m {
			z := 0.0
			if !math.IsNaN(pc[i]) {
				z = pc[i]/100 - 0.5
			}
			part[i] += wt * z
		}
	}
	pp := core.Percentiles(part)
	for i, r := range m {
		r.modelPct = pp[i]
		if model.Adopted {
			s := model.Sentiment
			r.Score = math.Round((1-s)*pp[i] + s*r.SP)
		}
		if len(model.Calibration) == 10 && !math.IsNaN(pp[i]) {
			d := int(math.Min(9, math.Floor(pp[i]/10)))
			v := model.Calibration[d].Prob
			r.Prob6 = &v
		}
	}
}

// savePredictions appends tonight's predictions to the permanent log, replacing only rows made
// earlier the same day (a same-day re-run, before anything could be known about the outcome).
func savePredictions(path, day, modelName string, rows []*Row) error {
	var keep [][]string
	if f, err := os.Open(path); err == nil {
		all, _ := csv.NewReader(f).ReadAll()
		f.Close()
		for _, r := range all {
			if len(r) > 0 && r[0] != "date" && r[0] != day {
				keep = append(keep, r)
			}
		}
	}
	sorted := append([]*Row(nil), rows...)
	sort.Slice(sorted, func(a, b int) bool { return sorted[a].ID < sorted[b].ID })
	for _, r := range sorted {
		prob := ""
		if r.Prob6 != nil {
			prob = strconv.FormatFloat(*r.Prob6, 'f', 3, 64)
		}
		keep = append(keep, []string{day, r.ID, strconv.FormatFloat(r.Score, 'f', 0, 64), strconv.FormatFloat(math.Round(r.modelPct), 'f', 0, 64), prob, modelName})
	}
	os.MkdirAll(filepath.Dir(path), 0o755)
	f, err := os.Create(path + ".tmp")
	if err != nil {
		return err
	}
	w := csv.NewWriter(f)
	w.Write([]string{"date", "id", "score", "modelPct", "prob", "model"})
	w.WriteAll(keep)
	f.Close()
	if w.Error() != nil {
		return w.Error()
	}
	return os.Rename(path+".tmp", path)
}

// sueOf is the standardised earnings surprise while the quarter is the latest one (135 days).
func sueOf(f Fund, asof time.Time) *float64 {
	if f.Fin == nil {
		return nil
	}
	qe, err := time.Parse("2006-01-02", f.Fin.EPSQEnd)
	if err != nil || asof.Sub(qe) > 135*24*time.Hour {
		return nil
	}
	v := f.Fin.SUE()
	if math.IsNaN(v) {
		return nil
	}
	v = math.Round(v*100) / 100
	return &v
}
