package main

import (
	"bufio"
	"encoding/json"
	"hash/fnv"
	"math"
	"os"
	"sort"
	"time"

	"github.com/ptkwcxzd72-rgb/BullPulse/internal/core"
	"github.com/ptkwcxzd72-rgb/BullPulse/internal/fund"
)

// pitRow is one company's figures as they stood after one filing (scripts/fundamentals_history.py).
type pitRow struct {
	ID        string   `json:"id"`
	Date      string   `json:"date"`
	Fin       fund.Fin `json:"fin"`
	RevGrowth *float64 `json:"rev_growth"`
	RevAccel  *float64 `json:"rev_accel"`
	EpsGrowth *float64 `json:"eps_growth"`
	Split     float64  `json:"split"`
}

// qres is a quintile test of one measure: forward excess returns by quintile (Q5 = highest).
type qres struct {
	Quintile [3][5]float64 `json:"quintile_excess"`
	Spread   [3]float64    `json:"q5_minus_q1"`
	SpreadT  [3]float64    `json:"q5_minus_q1_t"`
	Months   int           `json:"months"`
	Obs      int           `json:"observations"`
}

type fundResult struct {
	Stocks  int             `json:"stocks"`
	From    string          `json:"from"`
	To      string          `json:"to"`
	Profile qres            `json:"profile"`
	DCF     qres            `json:"dcf_cheapness"`
	Implied qres            `json:"implied_growth_low"`
	Areas   map[string]qres `json:"areas"`
}

type mobs struct {
	v   float64
	fwd [3]float64
}

func loadPIT(path string) map[string][]pitRow {
	out := map[string][]pitRow{}
	f, err := os.Open(path)
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var r pitRow
		if json.Unmarshal(sc.Bytes(), &r) == nil && r.Split > 0 {
			out[r.ID] = append(out[r.ID], r)
		}
	}
	for _, rs := range out {
		sort.Slice(rs, func(a, b int) bool { return rs[a].Date < rs[b].Date })
	}
	return out
}

// divFactor returns, for a date, the cumulative dividend adjustment that the total-return price
// series carries for dividends paid after that date (1 = none). Dividends are approximated as a
// quarter of the trailing-twelve-month dividend per share at each reported period end.
func divFactor(rows []pitRow, x *core.Series) func(time.Time) float64 {
	type ev struct {
		d   time.Time
		amt float64
	}
	byEnd := map[string]float64{}
	for _, r := range rows {
		f := r.Fin.PerShare(1 / r.Split)
		dps := math.NaN()
		if f.DPSTTM != nil {
			dps = *f.DPSTTM
		} else if f.DividendsPaidTTM != nil && f.Shares != nil && *f.Shares > 0 {
			dps = *f.DividendsPaidTTM / *f.Shares
		}
		if !math.IsNaN(dps) && dps > 0 && r.Fin.TTMEnd != "" {
			byEnd[r.Fin.TTMEnd] = dps / 4
		}
	}
	var evs []ev
	for d, a := range byEnd {
		if t, err := time.Parse("2006-01-02", d); err == nil {
			evs = append(evs, ev{t, a})
		}
	}
	sort.Slice(evs, func(a, b int) bool { return evs[a].d.After(evs[b].d) }) // newest first
	type step struct {
		d time.Time
		f float64 // factor for dates before d
	}
	var steps []step
	f := 1.0
	for _, e := range evs {
		// adjusted price on the last trading day on or before the dividend date
		k := sort.Search(len(x.Dates), func(i int) bool { return x.Dates[i].After(e.d) }) - 1
		if k < 0 || x.Close[k] <= 0 {
			continue
		}
		y := math.Min(e.amt*f/x.Close[k], 0.2)
		f *= 1 - y
		steps = append(steps, step{e.d, f})
	}
	return func(t time.Time) float64 {
		out := 1.0
		for _, s := range steps { // newest first: keep the factor of the earliest dividend after t
			if s.d.After(t) {
				out = s.f
			} else {
				break
			}
		}
		return out
	}
}

func jitter(i int, d time.Time) float64 {
	h := fnv.New32a()
	h.Write([]byte(d.Format("20060102")))
	h.Write([]byte{byte(i), byte(i >> 8)})
	return float64(h.Sum32()%1000) / 1e6
}

func quintiles(months [][]mobs) qres {
	var r qres
	var qs [3][5]stat
	var spNO [3]stat
	var sp [3]stat
	for mi, ob := range months {
		if len(ob) < 25 {
			continue
		}
		sort.Slice(ob, func(a, b int) bool { return ob[a].v < ob[b].v })
		r.Months++
		r.Obs += len(ob)
		for h := range horizons {
			var mkt stat
			for _, o := range ob {
				if !math.IsNaN(o.fwd[h]) {
					mkt.add(o.fwd[h])
				}
			}
			if mkt.n < 25 {
				continue
			}
			var qm [5]stat
			for k, o := range ob {
				if !math.IsNaN(o.fwd[h]) {
					qm[k*5/len(ob)].add(o.fwd[h] - mkt.mean())
				}
			}
			for q := 0; q < 5; q++ {
				qs[h][q].add(qm[q].mean())
			}
			s := qm[4].mean() - qm[0].mean()
			sp[h].add(s)
			if mi%(horizons[h]/21) == 0 {
				spNO[h].add(s)
			}
		}
	}
	for h := range horizons {
		for q := 0; q < 5; q++ {
			r.Quintile[h][q] = qs[h][q].mean()
		}
		r.Spread[h] = sp[h].mean()
		r.SpreadT[h] = spNO[h].t()
	}
	return r
}

// fundamentalsTest rebuilds the Fundamentals Profile and DCF at every month-end from filings
// published by then, and measures forward returns by quintile of each measure.
func fundamentalsTest(ss []core.Stock, xs []*core.Series, ends []time.Time, pos []map[time.Time]int, pit map[string][]pitRow) *fundResult {
	if len(pit) == 0 {
		return nil
	}
	divs := make([]func(time.Time) float64, len(xs))
	covered := 0
	for i, s := range ss {
		if rs := pit[s.ID()]; len(rs) > 0 {
			divs[i] = divFactor(rs, xs[i])
			covered++
		}
	}
	areaNames := []string{"Value", "Growth", "Track record", "Health", "Dividends"}
	var prof, dcf, impl [][]mobs
	areas := make([][][]mobs, 5)
	res := &fundResult{Stocks: covered, Areas: map[string]qres{}}
	for _, d := range ends {
		type item struct {
			i   int
			f   fund.Fin
			m   fund.Metrics
			dc  fund.DCF
			row pitRow
			fwd [3]float64
		}
		var items []item
		ds := d.Format("2006-01-02")
		stale := d.AddDate(0, -15, 0).Format("2006-01-02")
		for i, x := range xs {
			rs := pit[ss[i].ID()]
			j, ok := pos[i][d]
			if len(rs) == 0 || !ok {
				continue
			}
			k := sort.Search(len(rs), func(n int) bool { return rs[n].Date > ds }) - 1
			if k < 0 || rs[k].Date < stale {
				continue
			}
			r := rs[k]
			f := r.Fin.PerShare(1 / r.Split)
			px := x.Close[j] / divs[i](d)
			it := item{i: i, f: f, row: r, m: fund.Compute(f, px)}
			it.dc = fund.EstimateDCF(f, ss[i].Sector, px, r.RevGrowth)
			for h, n := range horizons {
				it.fwd[h] = math.NaN()
				if j+n < len(x.Close) {
					it.fwd[h] = x.Close[j+n]/x.Close[j] - 1
				}
			}
			items = append(items, it)
		}
		if len(items) < 25 || math.IsNaN(items[0].fwd[0]) {
			continue
		}
		if res.From == "" {
			res.From = ds
		}
		res.To = ds
		peers := make([]fund.Peer, len(items))
		for k, it := range items {
			peers[k] = fund.Peer{Sector: ss[it.i].Sector, M: it.m, RevGrowth: it.row.RevGrowth}
		}
		med := fund.PeerMedians(peers)
		var mp, md, mi []mobs
		ma := make([][]mobs, 5)
		for _, it := range items {
			p := fund.Build(it.f, it.m, it.dc, ss[it.i].Sector, it.row.RevGrowth, it.row.RevAccel, it.row.EpsGrowth, med)
			jt := jitter(it.i, d)
			mp = append(mp, mobs{float64(p.Total) + jt, it.fwd})
			for a := range p.Areas {
				ma[a] = append(ma[a], mobs{float64(p.Areas[a].Score) + jt, it.fwd})
			}
			if it.dc.VsPrice != nil {
				md = append(md, mobs{-*it.dc.VsPrice, it.fwd}) // higher = cheaper
			}
			if it.dc.Implied != nil {
				mi = append(mi, mobs{-*it.dc.Implied, it.fwd}) // higher = less growth priced in
			}
		}
		prof, dcf, impl = append(prof, mp), append(dcf, md), append(impl, mi)
		for a := range ma {
			areas[a] = append(areas[a], ma[a])
		}
	}
	res.Profile, res.DCF, res.Implied = quintiles(prof), quintiles(dcf), quintiles(impl)
	for a, n := range areaNames {
		res.Areas[n] = quintiles(areas[a])
	}
	return res
}
