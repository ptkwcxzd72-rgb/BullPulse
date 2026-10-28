// Shared by every page: data-freshness strip, footer links and (optional) cookie-free visitor counts.
(() => {
  // Visitor counts: set this to your GoatCounter code (the part before .goatcounter.com) to switch them on.
  // GoatCounter sets no cookies and collects no personal data. Leave empty to count nothing.
  const GOATCOUNTER = "";
  const REPO = "https://github.com/ptkwcxzd72-rgb/BullPulse";
  const root = document.currentScript && document.currentScript.dataset.root || "";

  const st = document.createElement("style");
  st.textContent = `.freshbar{background:#15223a;color:#93a0b8;font:500 12.5px/1.4 var(--f-body,system-ui),system-ui,sans-serif;border-bottom:1px solid #22314a}
.freshbar .in{max-width:1320px;margin:0 auto;padding:6px 20px;display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap}
.freshbar b{color:#eef2f8;font-weight:600}.freshbar .gen{margin-left:auto}
.freshbar .dot{width:7px;height:7px;border-radius:50%;background:#3dbcab;flex:none}
.freshbar.late{background:#352812;color:#f3d9ad;border-bottom-color:#5a4220}.freshbar.late .dot{background:#eba648}.freshbar.late b{color:#fff}
.sitefoot{background:#0e1828;color:#93a0b8;font:14px/1.5 var(--f-body,system-ui),system-ui,sans-serif;margin-top:32px}
.sitefoot .in{max-width:1320px;margin:0 auto;padding:22px 20px;display:flex;flex-wrap:wrap;gap:10px 24px;align-items:center;justify-content:space-between}
.sitefoot nav{display:flex;flex-wrap:wrap;gap:8px 20px}.sitefoot a{color:#eef2f8;text-decoration:none}.sitefoot a:hover{color:#3dbcab}.sitefoot p{margin:0;font-size:12.5px}
@media (max-width:640px){.freshbar .gen{margin-left:0}}`;
  document.head.appendChild(st);

  if (GOATCOUNTER) {
    const s = document.createElement("script");
    s.async = true; s.src = "https://gc.zgo.at/count.js"; s.dataset.goatcounter = `https://${GOATCOUNTER}.goatcounter.com/count`;
    document.head.appendChild(s);
  }

  const londonParts = d => Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d).map(p => [p.type, p.value]));
  // weekdays strictly after a and up to and including b (ISO dates)
  const weekdaysBetween = (a, b) => { let n = 0; const d = new Date(a + "T12:00:00Z"), e = new Date(b + "T12:00:00Z"); while (d < e) { d.setUTCDate(d.getUTCDate() + 1); const w = d.getUTCDay(); if (w && w < 6) n++; } return n; };
  // the most recent weekday whose close should be ranked by now: the nightly run finishes by about 07:00 UK time
  function expectedClose(now){
    const p = londonParts(now); const d = new Date(`${p.year}-${p.month}-${p.day}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() - (+p.hour < 7 ? 2 : 1));
    while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0, 10);
  }
  function freshness(D){
    const head = document.querySelector("header"); if (!head || !D || D.demo) return;
    const fmt = iso => new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
    const gen = D.generated ? new Date(D.generated) : null;
    const genTxt = gen ? gen.toLocaleString("en-GB", { timeZone: "Europe/London", weekday: "short", hour: "2-digit", minute: "2-digit" }) : "";
    const behind = weekdaysBetween(D.asof, expectedClose(new Date()));
    const ageH = gen ? (Date.now() - gen) / 36e5 : 0;
    const late = behind >= 2 || (behind === 1 && ageH > 30); // one day behind with a fresh run is a market holiday
    const bar = document.createElement("div");
    bar.className = "freshbar" + (late ? " late" : "");
    bar.setAttribute("role", "status");
    bar.innerHTML = `<div class="in"><span class="dot" aria-hidden="true"></span>${late ? `<b>Today's update is late.</b> Figures are from the close on ${fmt(D.asof)}; the next run will catch up.` : `Prices to the close on <b>${fmt(D.asof)}</b>`}${genTxt ? `<span class="gen">Updated ${genTxt} UK time</span>` : ""}</div>`;
    head.insertAdjacentElement("afterend", bar);
  }
  function footer(){
    const links = `<a href="${root}score.html">Does the score work?</a><a href="${REPO}#readme" target="_blank" rel="noopener">Methodology</a><a href="${REPO}/issues/new?template=feedback.yml" target="_blank" rel="noopener">Send feedback</a>`;
    const nav = document.querySelector("footer nav");
    if (nav) { if (!nav.querySelector('a[href$="score.html"]')) nav.insertAdjacentHTML("beforeend", links); return; }
    const f = document.createElement("footer"); f.className = "sitefoot";
    f.innerHTML = `<div class="in"><nav aria-label="Footer"><a href="${root}./">Home</a><a href="${root}app.html">Screener</a><a href="${root}portfolio.html">Portfolio</a><a href="${root}alerts.html">Alerts</a>${links}</nav><p>BullPulse is a free research tool, not investment advice. US prices from Tiingo; UK prices from Yahoo Finance.</p></div>`;
    document.body.appendChild(f);
  }
  const start = () => {
    footer();
    fetch(root + "data/snapshot.json").then(r => r.ok ? r.json() : null).then(freshness).catch(() => {});
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
