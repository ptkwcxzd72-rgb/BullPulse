package main

import (
	"bufio"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// Event is one alert-worthy change for a stock, kept in data/events.jsonl and published as
// RSS feeds (one for every stock, one for everything) so visitors can follow their watchlist
// in any feed reader without an account.
type Event struct {
	Date string `json:"date"`
	ID   string `json:"id"`
	Name string `json:"name"`
	Kind string `json:"kind"`
	Text string `json:"text"`
}

// detectEvents compares today's rows with the previous snapshot.
func detectEvents(day string, rows []*Row, prev map[string]Row) []Event {
	var out []Event
	add := func(r *Row, kind, text string) {
		out = append(out, Event{Date: day, ID: r.ID, Name: r.Name, Kind: kind, Text: text})
	}
	for _, r := range rows {
		p, ok := prev[r.ID]
		if !ok || p.Rank == 0 {
			continue
		}
		if mv := p.Rank - r.Rank; mv >= 20 || mv <= -20 {
			dir := "up"
			if mv < 0 {
				dir = "down"
			}
			add(r, "rank", fmt.Sprintf("Rank moved %s %d places to #%d (score %.0f).", dir, int(math.Abs(float64(mv))), r.Rank, r.Score))
		}
		if r.Above200 != p.Above200 {
			if r.Above200 {
				add(r, "trend", "Closed back above its 200-day average.")
			} else {
				add(r, "trend", "Closed below its 200-day average.")
			}
		}
		if r.GC.Long != p.GC.Long {
			if r.GC.Long == 1 {
				add(r, "cross", "Golden cross: the 50-day average moved above the 200-day.")
			} else {
				add(r, "cross", "The 50-day average fell below the 200-day.")
			}
		}
		if r.Early && !p.Early {
			add(r, "early", "Joined the early trend changes screen.")
		}
		if r.Grower && !p.Grower {
			add(r, "growth", "Joined the growing and turning up screen.")
		}
		if r.FundAsOf != "" && p.FundAsOf != "" && r.FundAsOf != p.FundAsOf {
			t := "New results filed"
			if r.RevGrowth != nil {
				t += fmt.Sprintf(": revenue %+.1f%% year on year", *r.RevGrowth*100)
			}
			add(r, "results", t+".")
		}
		if r.Ins != nil && r.Ins.Cluster && (p.Ins == nil || !p.Ins.Cluster) {
			add(r, "insider", fmt.Sprintf("Cluster buying: %d insiders bought shares in the open market in the last 90 days.", r.Ins.Buyers))
		}
		if r.Event && !p.Event {
			add(r, "news", fmt.Sprintf("Unusual burst of news coverage (30-day tone %+.2f).", r.Tone30))
		}
	}
	return out
}

// loadEvents reads the log, drops anything older than keepDays and replaces today's entries.
func loadEvents(path, day string, keepDays int, today []Event) []Event {
	cut := ""
	if t, err := time.Parse("2006-01-02", day); err == nil {
		cut = t.AddDate(0, 0, -keepDays).Format("2006-01-02")
	}
	var all []Event
	if f, err := os.Open(path); err == nil {
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			var e Event
			if json.Unmarshal(sc.Bytes(), &e) == nil && e.Date >= cut && e.Date != day {
				all = append(all, e)
			}
		}
		f.Close()
	}
	all = append(all, today...)
	sort.SliceStable(all, func(a, b int) bool { return all[a].Date > all[b].Date })
	return all
}

func saveEvents(path string, all []Event) error {
	os.MkdirAll(filepath.Dir(path), 0o755)
	var b strings.Builder
	for i := len(all) - 1; i >= 0; i-- { // oldest first on disk
		j, _ := json.Marshal(all[i])
		b.Write(j)
		b.WriteByte('\n')
	}
	return os.WriteFile(path, []byte(b.String()), 0o644)
}

type rssGUID struct {
	Perma bool   `xml:"isPermaLink,attr"`
	Value string `xml:",chardata"`
}

type atomLink struct {
	XMLName xml.Name `xml:"atom:link"`
	Href    string   `xml:"href,attr"`
	Rel     string   `xml:"rel,attr"`
	Type    string   `xml:"type,attr"`
}

type rssItem struct {
	Title   string  `xml:"title"`
	Link    string  `xml:"link"`
	GUID    rssGUID `xml:"guid"`
	PubDate string  `xml:"pubDate"`
	Desc    string  `xml:"description"`
}

type rssDoc struct {
	XMLName xml.Name `xml:"rss"`
	Version string   `xml:"version,attr"`
	Atom    string   `xml:"xmlns:atom,attr"`
	Channel struct {
		Self  atomLink  `xml:"atom:link"`
		Title string    `xml:"title"`
		Link  string    `xml:"link"`
		Desc  string    `xml:"description"`
		TTL   int       `xml:"ttl"`
		Items []rssItem `xml:"item"`
	} `xml:"channel"`
}

// writeFeeds publishes site/feeds/all.xml and site/feeds/<id>.xml for every ranked stock.
func writeFeeds(dir, base string, rows []*Row, all []Event) error {
	os.MkdirAll(dir, 0o755)
	byID := map[string][]Event{}
	for _, e := range all {
		byID[e.ID] = append(byID[e.ID], e)
	}
	feed := func(file, title, link, desc string, evs []Event, limit int) []byte {
		var d rssDoc
		d.Version, d.Atom = "2.0", "http://www.w3.org/2005/Atom"
		d.Channel.Self = atomLink{Href: base + "feeds/" + file, Rel: "self", Type: "application/rss+xml"}
		d.Channel.Title, d.Channel.Link, d.Channel.Desc, d.Channel.TTL = title, link, desc, 720
		for i, e := range evs {
			if i >= limit {
				break
			}
			t, _ := time.Parse("2006-01-02", e.Date)
			d.Channel.Items = append(d.Channel.Items, rssItem{
				Title: e.Name + ": " + strings.TrimSuffix(e.Text, "."), Link: base + "app.html#" + e.ID,
				GUID: rssGUID{Value: e.Date + "-" + e.ID + "-" + e.Kind}, PubDate: t.Add(22 * time.Hour).Format(time.RFC1123Z),
				Desc: e.Text + " BullPulse is a research screen, not investment advice.",
			})
		}
		b, _ := xml.MarshalIndent(d, "", " ")
		return append([]byte(xml.Header), b...)
	}
	if err := os.WriteFile(filepath.Join(dir, "all.xml"), feed("all.xml", "BullPulse: all alerts", base+"app.html",
		"Rank moves, trend changes, new results and insider buying across the BullPulse universe.", all, 200), 0o644); err != nil {
		return err
	}
	for _, r := range rows {
		b := feed(r.ID+".xml", "BullPulse: "+r.Name+" ("+r.T+")", base+"app.html#"+r.ID,
			"Alerts for "+r.Name+" from the BullPulse nightly screen.", byID[r.ID], 50)
		if err := os.WriteFile(filepath.Join(dir, r.ID+".xml"), b, 0o644); err != nil {
			return err
		}
	}
	return nil
}

// writeEventsJSON publishes the alert log for the website's Alerts page.
func writeEventsJSON(path string, all []Event, limit int) error {
	if len(all) > limit {
		all = all[:limit]
	}
	if all == nil {
		all = []Event{}
	}
	b, err := json.Marshal(map[string]any{"events": all})
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o644)
}
