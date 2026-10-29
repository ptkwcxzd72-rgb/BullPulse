package main

import (
	"encoding/csv"
	"math"
	"os"
	"sort"
	"strconv"
	"time"
)

// grade checks the nightly predictions against what happened. Each night's scores
// (data/history/scores.csv) and probabilities (data/history/predictions.csv) are kept as they
// were made; once 21 or 126 trading days have passed, each stock's return against its sector is
// known. This is the only fully out-of-sample record: nothing in it can be revised afterwards.
func grade(d *daily, predPath, scoresPath string) map[string]any {
	type pred struct {
		i     int
		score float64
		prob  float64
	}
	byDate := map[string]map[int]*pred{}
	read := func(path string) [][]string {
		f, err := os.Open(path)
		if err != nil {
			return nil
		}
		defer f.Close()
		r := csv.NewReader(f)
		r.FieldsPerRecord = -1
		rows, _ := r.ReadAll()
		return rows
	}
	cols := func(h []string) map[string]int {
		m := map[string]int{}
		for k, c := range h {
			m[c] = k
		}
		return m
	}
	if rows := read(scoresPath); len(rows) > 1 {
		c := cols(rows[0])
		for _, r := range rows[1:] {
			i, ok := d.pos[r[c["id"]]]
			v, err := strconv.ParseFloat(r[c["score"]], 64)
			if !ok || err != nil {
				continue
			}
			dt := r[c["date"]]
			if byDate[dt] == nil {
				byDate[dt] = map[int]*pred{}
			}
			byDate[dt][i] = &pred{i: i, score: v, prob: math.NaN()}
		}
	}
	if rows := read(predPath); len(rows) > 1 {
		c := cols(rows[0])
		for _, r := range rows[1:] {
			i, ok := d.pos[r[c["id"]]]
			v, err := strconv.ParseFloat(r[c["prob"]], 64)
			if !ok || err != nil || byDate[r[c["date"]]] == nil || byDate[r[c["date"]]][i] == nil {
				continue
			}
			byDate[r[c["date"]]][i].prob = v
		}
	}
	dates := make([]string, 0, len(byDate))
	for k := range byDate {
		dates = append(dates, k)
	}
	sort.Strings(dates)
	out := map[string]any{"generated": time.Now().UTC().Format(time.RFC3339), "predictionDays": len(dates)}
	if len(dates) == 0 {
		return out
	}
	out["since"] = dates[0]
	var hs []map[string]any
	type bin struct{ hit, n float64 }
	cal := make([]bin, 10)
	for _, k := range []int{21, 126} {
		var spreads []float64
		graded, hits, calls := 0, 0, 0
		for _, ds := range dates {
			t, _ := time.Parse("2006-01-02", ds)
			ps := byDate[ds]
			// score percentiles within each market on that night
			var top, bot []float64
			for _, ex := range []string{"US", "UK"} {
				var ids []int
				var sc []float64
				for i, p := range ps {
					if d.stocks[i].Market == ex {
						ids = append(ids, i)
						sc = append(sc, p.score)
					}
				}
				rk := ranks(sc)
				for a, i := range ids {
					x, _ := d.excess(i, t, k)
					if math.IsNaN(x) {
						continue
					}
					if rk[a] >= 0.8 {
						top = append(top, x)
					} else if rk[a] <= 0.2 {
						bot = append(bot, x)
					}
					if p := ps[i].prob; !math.IsNaN(p) && k == 126 {
						b := int(math.Min(9, math.Floor(p*10)))
						cal[b].n++
						if x > 0 {
							cal[b].hit++
						}
						calls++
						if (p > 0.5) == (x > 0) {
							hits++
						}
					}
				}
			}
			if len(top) >= 5 && len(bot) >= 5 {
				mt, _, _ := meanT(top, 1)
				mb, _, _ := meanT(bot, 1)
				spreads = append(spreads, mt-mb)
				graded++
			}
		}
		m, t, _ := meanT(spreads, k)
		h := map[string]any{"days": k, "gradedDays": graded, "spread": r4(m), "t": r4(t)}
		if calls > 0 {
			h["probCalls"], h["probRight"] = calls, r4(float64(hits)/float64(calls))
		}
		// when the first outcome at this horizon is due
		if graded == 0 {
			if t0, err := time.Parse("2006-01-02", dates[0]); err == nil {
				h["firstDue"] = day(t0.AddDate(0, 0, k*7/5+3))
			}
		}
		hs = append(hs, h)
	}
	out["horizons"] = hs
	var cb []map[string]any
	for b, c := range cal {
		if c.n > 0 {
			cb = append(cb, map[string]any{"from": float64(b) / 10, "to": float64(b+1) / 10, "n": int(c.n), "actual": r4(c.hit / c.n)})
		}
	}
	out["calibration"] = cb
	return out
}
