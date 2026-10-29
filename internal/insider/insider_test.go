package insider

import (
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadAndBuyers(t *testing.T) {
	dir := t.TempDir()
	f, _ := os.Create(filepath.Join(dir, "2024q1.csv.gz"))
	z := gzip.NewWriter(f)
	z.Write([]byte("filed,trade,id,owner,role,title,code,shares,price,value,acc\n" +
		"2024-01-10,2024-01-08,US-A,ANN,DIRECTOR,,P,10,10,100,a1\n" +
		"2024-02-10,2024-02-08,US-A,BOB,OFFICER,CFO,P,10,10,100,a2\n" +
		"2024-02-11,2024-02-08,US-A,BIG FUND,TENPERCENTOWNER,,P,10,10,100,a3\n" +
		"2024-02-12,2024-02-08,US-A,CAT,DIRECTOR,,S,10,10,100,a4\n" +
		"2024-02-12,2024-02-08,US-A,CAT,DIRECTOR,,S,10,10,100,a4\n"))
	z.Close()
	f.Close()
	m := Load(dir)
	if len(m["US-A"]) != 4 {
		t.Fatalf("got %d transactions, want 4 (one duplicate dropped)", len(m["US-A"]))
	}
	d := func(s string) time.Time { x, _ := time.Parse("2006-01-02", s); return x }
	if n := Buyers(m["US-A"], d("2024-02-29"), 90); n != 2 {
		t.Errorf("buyers = %d, want 2", n)
	}
	if n := Buyers(m["US-A"], d("2024-02-29"), 30); n != 1 {
		t.Errorf("30-day buyers = %d, want 1", n)
	}
}
