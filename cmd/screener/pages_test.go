package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestWritePages(t *testing.T) {
	dir := t.TempDir()
	mc := 10.0
	rows := []*Row{
		{ID: "LSE-ULVR", T: "ULVR", Ex: "LSE", Name: "Unilever & Co <test>", Sector: "Consumer Staples", Ccy: "GBX", Price: 4892.5, Score: 53, Rank: 2, Ret1y: -0.012, McapBn: &mc},
		{ID: "LSE-TSCO", T: "TSCO", Ex: "LSE", Name: "Tesco", Sector: "Consumer Staples", Ccy: "GBX", Price: 450, Score: 61, Rank: 1, Ret1y: 0.17, McapBn: &mc},
		{ID: "LSE-SMT", T: "SMT", Ex: "LSE", Name: "Scottish Mortgage", Sector: "Financials", Ccy: "GBX", Price: 1000, Score: 67, Rank: 3, Trust: true},
	}
	os.MkdirAll(filepath.Join(dir, "stock", "lse-gone"), 0o755)
	if err := writePages(dir, "https://bullpulse.co.uk", rows, time.Date(2026, 10, 27, 0, 0, 0, 0, time.UTC)); err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(filepath.Join(dir, "stock", "lse-ulvr", "index.html"))
	if err != nil {
		t.Fatal(err)
	}
	page := string(b)
	for _, want := range []string{"Unilever &amp; Co &lt;test&gt;", "4892.5p", `href="../lse-tsco/"`, "https://bullpulse.co.uk/stock/lse-ulvr/", "#2 of 3 UK stocks"} {
		if !strings.Contains(page, want) {
			t.Errorf("page lacks %q", want)
		}
	}
	trust, _ := os.ReadFile(filepath.Join(dir, "stock", "lse-smt", "index.html"))
	if !strings.Contains(string(trust), "investment trust") {
		t.Error("trust page should say it is an investment trust")
	}
	if _, err := os.Stat(filepath.Join(dir, "stock", "lse-gone")); !os.IsNotExist(err) {
		t.Error("page for a stock no longer ranked should be removed")
	}
	sm, _ := os.ReadFile(filepath.Join(dir, "sitemap.xml"))
	if !strings.Contains(string(sm), "<loc>https://bullpulse.co.uk/stock/lse-smt/</loc>") || !strings.Contains(string(sm), "score.html") {
		t.Errorf("sitemap incomplete:\n%s", sm)
	}
}

func TestPeersOfSkipsTrustsAndOtherMarkets(t *testing.T) {
	a, b, c, d := &Row{ID: "a", Ex: "LSE", Sector: "X"}, &Row{ID: "b", Ex: "LSE", Sector: "X"}, &Row{ID: "c", Ex: "US", Sector: "X"}, &Row{ID: "d", Ex: "LSE", Sector: "X", Trust: true}
	ps := peersOf(a, []*Row{a, b, c, d}, 5)
	if len(ps) != 1 || ps[0] != b {
		t.Fatalf("peers = %v", ps)
	}
}
