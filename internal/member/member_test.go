package member

import (
	"os"
	"path/filepath"
	"testing"
)

func TestMember(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "sp500_membership.csv"), []byte("ticker,start_date,end_date\nFB,2013-12-23,2022-06-09\nMETA,2022-06-09,\nAPP,2025-09-22,\nX,2000-01-01,2010-01-01\n"), 0o644)
	os.WriteFile(filepath.Join(dir, "sp500_aliases.csv"), []byte("ticker,previous,changed\nMETA,FB,2022-06-09\n"), 0o644)
	h := Load(dir)
	cases := []struct {
		m, t, d string
		want    bool
	}{
		{"US", "META", "2018-01-31", true}, {"US", "META", "2026-01-31", true}, {"US", "META", "2012-01-31", false},
		{"US", "APP", "2024-12-31", false}, {"US", "APP", "2025-10-31", true},
		{"US", "X", "2012-01-01", false}, {"US", "UNKNOWN", "2012-01-01", true}, {"UK", "BP", "2012-01-01", true},
	}
	for _, c := range cases {
		if got := h.Member(c.m, c.t, c.d); got != c.want {
			t.Errorf("%s %s %s = %v, want %v", c.m, c.t, c.d, got, c.want)
		}
	}
}
