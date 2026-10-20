// Package core holds the BullPulse universe loading, indicator computation and
// scoring logic shared by the nightly screener and the validation backtest.
//
// All technical indicators and strategy states are computed with
// github.com/cinar/indicator/v2. Scores are percentiles within each market.
package core

import (
	"encoding/csv"
	"errors"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/cinar/indicator/v2/asset"
	extrend "github.com/cinar/indicator/v2/examples/trend"
	exvol "github.com/cinar/indicator/v2/examples/volatility"
	"github.com/cinar/indicator/v2/helper"
	"github.com/cinar/indicator/v2/momentum"
	"github.com/cinar/indicator/v2/strategy"
	"github.com/cinar/indicator/v2/trend"
	"github.com/cinar/indicator/v2/volatility"
	"github.com/cinar/indicator/v2/volume"
)

// Stock is one row of a universe file.
type Stock struct {
	Ticker         string // exchange ticker, e.g. AAPL or BP
	Name           string
	Sector         string
	Market         string // "US" or "UK"
	CIK            string // SEC company identifier (US only), for growth data
	ProviderTicker string // file name of the price history in the price repository
}

// ID is the stable identifier used in file names and URLs, e.g. US-AAPL or LSE-BP.
func (s Stock) ID() string { return Exchange(s.Market) + "-" + strings.ReplaceAll(s.Ticker, ".", "") }

// Exchange maps a market to the exchange code used by the website.
func Exchange(market string) string {
	if market == "UK" {
		return "LSE"
	}
	return "US"
}

// Currency of quoted prices: UK shares are quoted in pence.
func Currency(market string) string {
	if market == "UK" {
		return "GBX"
	}
	return "USD"
}

// LoadUniverse reads every *.csv file in dir. Columns are matched by header name:
// ticker,name,sector,market,cik,provider_ticker (cik is optional).
func LoadUniverse(dir string) ([]Stock, error) {
	files, err := filepath.Glob(filepath.Join(dir, "*.csv"))
	if err != nil {
		return nil, err
	}
	var out []Stock
	for _, f := range files {
		fh, err := os.Open(f)
		if err != nil {
			return nil, err
		}
		rows, err := csv.NewReader(fh).ReadAll()
		fh.Close()
		if err != nil {
			return nil, err
		}
		if len(rows) == 0 {
			continue
		}
		col := map[string]int{}
		for i, h := range rows[0] {
			col[strings.TrimSpace(strings.ToLower(h))] = i
		}
		get := func(r []string, name string) string {
			if i, ok := col[name]; ok && i < len(r) {
				return strings.TrimSpace(r[i])
			}
			return ""
		}
		for _, r := range rows[1:] {
			s := Stock{Ticker: get(r, "ticker"), Name: get(r, "name"), Sector: get(r, "sector"), Market: get(r, "market"),
				CIK: get(r, "cik"), ProviderTicker: get(r, "provider_ticker")}
			if s.Ticker != "" {
				out = append(out, s)
			}
		}
	}
	return out, nil
}

// Series is a stock's full price history with indicators aligned bar by bar.
// Missing values (indicator warm-up) are NaN.
type Series struct {
	Dates                          []time.Time
	Open, High, Low, Close, Volume []float64
	SMA50, SMA200, RSI, MACD, Sig  []float64
	BBUpper, BBLower, ATR, OBV, HV []float64
	GoldenCross, SuperTrend        []int // long (1) or flat (0) at each bar
}

// ErrNoData means the stock has no price file yet.
var ErrNoData = errors.New("no price data")

// align left-pads a shorter indicator output with NaN to length n.
func align(n int, xs []float64) []float64 {
	out := make([]float64, n)
	off := n - len(xs)
	for i := range out {
		if i < off {
			out[i] = math.NaN()
		} else {
			out[i] = xs[i-off]
		}
	}
	return out
}

func collect(cs ...<-chan float64) [][]float64 {
	res := make([][]float64, len(cs))
	done := make(chan int)
	for i, c := range cs {
		go func(i int, c <-chan float64) { res[i] = helper.ChanToSlice(c); done <- i }(i, c)
	}
	for range cs {
		<-done
	}
	return res
}

// positions replays raw strategy actions into a long/flat position per bar.
func positions(n int, acts []strategy.Action) []int {
	out := make([]int, n)
	off := n - len(acts)
	pos := 0
	for i, a := range acts {
		if a == strategy.Buy {
			pos = 1
		} else if a == strategy.Sell {
			pos = 0
		}
		out[off+i] = pos
	}
	return out
}

// Load reads a stock's history from the repository and computes its indicators.
func Load(repo asset.Repository, s Stock) (*Series, error) {
	if s.ProviderTicker == "" {
		return nil, ErrNoData
	}
	ch, err := repo.Get(s.ProviderTicker)
	if err != nil {
		return nil, ErrNoData
	}
	snaps := helper.ChanToSlice(ch)
	n := len(snaps)
	if n == 0 {
		return nil, ErrNoData
	}
	x := &Series{}
	for _, p := range snaps {
		x.Dates = append(x.Dates, p.Date)
		x.Open = append(x.Open, p.Open)
		x.High = append(x.High, p.High)
		x.Low = append(x.Low, p.Low)
		x.Close = append(x.Close, p.Close)
		x.Volume = append(x.Volume, p.Volume)
	}
	if n < 60 {
		return x, nil
	}
	src := func() <-chan *asset.Snapshot { return helper.SliceToChan(snaps) }
	cl := func() <-chan float64 { return helper.SliceToChan(x.Close) }
	sl := func(c <-chan float64) []float64 { return align(n, helper.ChanToSlice(c)) }

	x.SMA50 = sl(trend.NewSmaWithPeriod[float64](50).Compute(cl()))
	x.SMA200 = sl(trend.NewSmaWithPeriod[float64](200).Compute(cl()))
	x.RSI = sl(momentum.NewRsi[float64]().Compute(cl()))
	m, sg := trend.NewMacd[float64]().Compute(cl())
	ms := collect(m, sg)
	x.MACD, x.Sig = align(n, ms[0]), align(n, ms[1])
	u, mid, l := volatility.NewBollingerBands[float64]().Compute(cl())
	bb := collect(u, mid, l)
	x.BBUpper, x.BBLower = align(n, bb[0]), align(n, bb[2])
	x.ATR = sl(volatility.NewAtr[float64]().Compute(helper.SliceToChan(x.High), helper.SliceToChan(x.Low), cl()))
	x.OBV = sl(volume.NewObv[float64]().Compute(cl(), helper.SliceToChan(x.Volume)))
	logs := make([]float64, n)
	for i, c := range x.Close {
		logs[i] = math.Log(c)
	}
	x.HV = sl(volatility.NewMovingStdWithPeriod[float64](20).Compute(helper.Change(helper.SliceToChan(logs), 1)))
	x.GoldenCross = positions(n, helper.ChanToSlice(extrend.NewGoldenCrossStrategy().Compute(src())))
	x.SuperTrend = positions(n, helper.ChanToSlice(exvol.NewSuperTrendStrategy().Compute(src())))
	return x, nil
}

// MinBars is the history needed for 200-day averages and 12-month momentum.
const MinBars = 260

func ok(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }

// TrendRaw scores the long-term trend at bar j on a 0-100 scale:
// price above 200-day (35), 50-day above 200-day (25), 200-day rising over 20 bars (20), Super Trend long (20).
func (x *Series) TrendRaw(j int) float64 {
	if j < 220 || !ok(x.SMA200[j]) || !ok(x.SMA200[j-20]) {
		return math.NaN()
	}
	t := 0.0
	if x.Close[j] > x.SMA200[j] {
		t += 35
	}
	if x.SMA50[j] > x.SMA200[j] {
		t += 25
	}
	if x.SMA200[j] > x.SMA200[j-20] {
		t += 20
	}
	t += 20 * float64(x.SuperTrend[j])
	return t
}

// Momentum is the 12-month return excluding the most recent month (Jegadeesh & Titman, 1993).
func (x *Series) Momentum(j int) float64 {
	if j < 252 {
		return math.NaN()
	}
	return x.Close[j-21]/x.Close[j-252] - 1
}

// Since counts bars since the position series last changed at or before bar j.
func Since(pos []int, j int) int {
	k := j
	for k > 0 && pos[k-1] == pos[j] {
		k--
	}
	return j - k
}

// DaysAbove200 counts bars since the close moved above its 200-day average (-1 if below now).
func (x *Series) DaysAbove200(j int) int {
	if !(x.Close[j] > x.SMA200[j]) {
		return -1
	}
	k := j
	for k > 0 && x.Close[k-1] > x.SMA200[k-1] {
		k--
	}
	return j - k
}

// RealisedVol is annualised volatility of daily log returns over the last 252 bars ending at j.
func (x *Series) RealisedVol(j int) float64 {
	a := j - 252
	if a < 1 {
		a = 1
	}
	var s, s2 float64
	n := 0
	for i := a; i <= j; i++ {
		r := math.Log(x.Close[i] / x.Close[i-1])
		s += r
		s2 += r * r
		n++
	}
	if n < 2 {
		return math.NaN()
	}
	mean := s / float64(n)
	return math.Sqrt((s2/float64(n)-mean*mean)*float64(n)/float64(n-1)) * math.Sqrt(252)
}

// Percentiles converts raw values into 0-100 percentile ranks (ties share the average rank).
// NaN values receive NaN.
func Percentiles(vals []float64) []float64 {
	idx := []int{}
	for i, v := range vals {
		if ok(v) {
			idx = append(idx, i)
		}
	}
	out := make([]float64, len(vals))
	for i := range out {
		out[i] = math.NaN()
	}
	if len(idx) == 1 {
		out[idx[0]] = 50
		return out
	}
	sort.SliceStable(idx, func(a, b int) bool { return vals[idx[a]] < vals[idx[b]] })
	for i := 0; i < len(idx); {
		k := i
		for k+1 < len(idx) && vals[idx[k+1]] == vals[idx[i]] {
			k++
		}
		r := float64(i+k) / 2 / float64(len(idx)-1) * 100
		for m := i; m <= k; m++ {
			out[idx[m]] = r
		}
		i = k + 1
	}
	return out
}

// Weights of the composite score.
const (
	WTrend     = 0.4
	WMomentum  = 0.4
	WSentiment = 0.2
)
