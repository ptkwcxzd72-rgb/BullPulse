// Package insider reads the permanent insider-dealing history written by
// scripts/insider_history.py (data/history/insiders/<quarter>.csv.gz).
package insider

import (
	"compress/gzip"
	"encoding/csv"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Tx is one open-market purchase (P) or sale (S) reported on Form 4.
type Tx struct {
	Filed, Trade time.Time
	Owner, Role  string
	Code         byte
	Value        float64
}

// Insider reports whether the filer is an officer or director (not only a large holder).
func (t Tx) Insider() bool {
	r := strings.ToUpper(t.Role)
	return strings.Contains(r, "OFFICER") || strings.Contains(r, "DIRECTOR")
}

// Load returns each stock's transactions sorted by filing date. A missing directory gives none.
func Load(dir string) map[string][]Tx {
	out := map[string][]Tx{}
	files, _ := filepath.Glob(filepath.Join(dir, "*.csv.gz"))
	sort.Strings(files)
	seen := map[string]bool{}
	for _, p := range files {
		f, err := os.Open(p)
		if err != nil {
			continue
		}
		z, err := gzip.NewReader(f)
		if err != nil {
			f.Close()
			continue
		}
		r := csv.NewReader(z)
		r.FieldsPerRecord = -1
		rows, _ := r.ReadAll()
		z.Close()
		f.Close()
		if len(rows) == 0 {
			continue
		}
		col := map[string]int{}
		for i, h := range rows[0] {
			col[h] = i
		}
		get := func(row []string, k string) string {
			if i, ok := col[k]; ok && i < len(row) {
				return row[i]
			}
			return ""
		}
		for _, row := range rows[1:] {
			key := get(row, "acc") + "|" + get(row, "trade") + "|" + get(row, "value") + "|" + get(row, "code")
			if seen[key] { // a refreshed quarter can repeat a late filing
				continue
			}
			seen[key] = true
			fd, err1 := time.Parse("2006-01-02", get(row, "filed"))
			td, err2 := time.Parse("2006-01-02", get(row, "trade"))
			v, _ := strconv.ParseFloat(get(row, "value"), 64)
			code := get(row, "code")
			if err1 != nil || code == "" {
				continue
			}
			if err2 != nil {
				td = fd
			}
			id := get(row, "id")
			out[id] = append(out[id], Tx{Filed: fd, Trade: td, Owner: get(row, "owner"), Role: get(row, "role"), Code: code[0], Value: v})
		}
	}
	for _, txs := range out {
		sort.SliceStable(txs, func(a, b int) bool { return txs[a].Filed.Before(txs[b].Filed) })
	}
	return out
}

// Buyers counts distinct officers and directors who bought in the open market with filings in
// (t - days, t].
func Buyers(txs []Tx, t time.Time, days int) int {
	from := t.AddDate(0, 0, -days)
	k := sort.Search(len(txs), func(i int) bool { return txs[i].Filed.After(from) })
	who := map[string]bool{}
	for ; k < len(txs) && !txs[k].Filed.After(t); k++ {
		if txs[k].Code == 'P' && txs[k].Insider() {
			who[txs[k].Owner] = true
		}
	}
	return len(who)
}
