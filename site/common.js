// Shared by every page: the site navigation (top bar, and a tab bar on phones), the data-freshness
// strip, footer links and (optional) cookie-free visitor counts.
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
.freshbar .short{display:none}
@media (max-width:640px){.freshbar .gen{margin-left:0}.freshbar .long,.freshbar .gen{display:none}.freshbar .short{display:inline}.freshbar .in{padding:5px 16px;flex-wrap:nowrap}}
.skip{position:absolute;left:12px;top:-60px;z-index:100;background:#3dbcab;color:#06231f;font:600 14px var(--f-body,system-ui),sans-serif;padding:8px 14px;border-radius:8px;text-decoration:none}
.skip:focus{top:10px}
:focus-visible{outline:2px solid #3dbcab;outline-offset:2px}
.tabbar{display:none}
.moresheet{display:none}
@media (max-width:760px){
  nav.nav{display:none!important}
  body{padding-bottom:calc(64px + env(safe-area-inset-bottom))}
  .tabbar{display:grid;grid-template-columns:repeat(5,1fr);position:fixed;left:0;right:0;bottom:0;z-index:60;background:rgba(14,24,40,.97);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-top:1px solid #22314a;padding:4px 4px calc(4px + env(safe-area-inset-bottom))}
  .tabbar a,.tabbar button{display:grid;justify-items:center;gap:3px;padding:6px 0 4px;color:#93a0b8;text-decoration:none;font:600 11px/1 var(--f-body,system-ui),system-ui,sans-serif;background:none;border:0;border-radius:10px;cursor:pointer}
  .tabbar svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  .tabbar [aria-current="page"],.tabbar button[aria-expanded="true"]{color:#3dbcab}
  .moresheet{position:fixed;left:8px;right:8px;bottom:calc(70px + env(safe-area-inset-bottom));z-index:61;background:#15223a;border:1px solid #22314a;border-radius:16px;padding:6px;box-shadow:0 12px 40px rgba(0,0,0,.45)}
  .moresheet.open{display:grid}
  .moresheet a{display:flex;justify-content:space-between;align-items:center;gap:10px;color:#eef2f8;text-decoration:none;font:500 15px var(--f-body,system-ui),system-ui,sans-serif;padding:13px 14px;border-radius:10px}
  .moresheet a span{color:#93a0b8;font-size:12.5px}
  .moresheet a[aria-current="page"]{background:#1b2942;color:#3dbcab}
}
@media (max-width:760px){.pagehead > p.clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.pagehead .lmore{display:none;background:none;border:0;padding:4px 0 0;color:#3dbcab;font:600 13px var(--f-body,system-ui),sans-serif;cursor:pointer}
@media (max-width:760px){.pagehead .lmore{display:inline-block}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}`;
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
    bar.innerHTML = `<div class="in"><span class="dot" aria-hidden="true"></span><span class="long">${late ? `<b>Today's update is late.</b> Figures are from the close on ${fmt(D.asof)}; the next run will catch up.` : `Prices to the close on <b>${fmt(D.asof)}</b>`}</span><span class="short">${late ? `<b>Update late:</b> prices to ${fmt(D.asof)}` : `Prices to the close on <b>${fmt(D.asof)}</b>`}</span>${genTxt ? `<span class="gen">Updated ${genTxt} UK time</span>` : ""}</div>`;
    head.insertAdjacentElement("afterend", bar);
  }
  const here = root ? "" : (location.pathname.split("/").pop() || "index.html");
  const IC = {
    screener: '<path d="M4 6h16M4 12h10M4 18h6"/><path d="M17 15l2 2 3-4"/>',
    news: '<rect x="3" y="4" width="15" height="16" rx="2"/><path d="M18 8h2a1 1 0 0 1 1 1v9a2 2 0 0 1-2 2"/><path d="M7 8h7M7 12h7M7 16h4"/>',
    investors: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="17" cy="9" r="2.4"/><path d="M15.5 14.2c2.6-.3 4.5 1.4 5 4.3"/>',
    portfolio: '<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
    models: '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
    more: '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>'
  };
  const MAIN = [["app.html", "Screener"], ["models.html", "Models"], ["news.html", "News"], ["investors.html", "Investors"], ["portfolio.html", "Portfolio"], ["lab.html", "Lab"], ["alerts.html", "Alerts"]];
  function nav(){
    // one navigation for every page: the page's own markup is replaced so new sections appear everywhere
    document.querySelectorAll("nav.nav").forEach(n => {
      n.innerHTML = MAIN.map(([h, t]) => `<a href="${root}${h}"${here === h ? ' aria-current="page"' : ""}>${t}</a>`).join("");
    });
    const main = document.querySelector("main");
    if (main && !document.querySelector(".skip")) {
      if (!main.id) main.id = "main";
      document.body.insertAdjacentHTML("afterbegin", `<a class="skip" href="#${main.id}">Skip to content</a>`);
    }
    const tab = (h, t, ic) => `<a href="${root}${h}"${here === h ? ' aria-current="page"' : ""}><svg viewBox="0 0 24 24" aria-hidden="true">${IC[ic]}</svg>${t}</a>`;
    const more = [["portfolio.html", "Portfolio", "Your holdings and a model portfolio"], ["lab.html", "Strategy Lab", "Test a strategy on ten years of data"], ["alerts.html", "Alerts", "What changed overnight"], ["score.html", "Does the score work?", "The evidence, updated monthly"], ["./", "Home", "About BullPulse"]];
    const inMore = more.some(([h]) => h === here);
    const bar = document.createElement("nav");
    bar.className = "tabbar"; bar.setAttribute("aria-label", "Sections");
    bar.innerHTML = tab("app.html", "Screener", "screener") + tab("models.html", "Models", "models") + tab("news.html", "News", "news") + tab("investors.html", "Investors", "investors") +
      `<button type="button" aria-expanded="false" aria-controls="moresheet"${inMore ? ' style="color:#3dbcab"' : ""}><svg viewBox="0 0 24 24" aria-hidden="true">${IC.more}</svg>More</button>`;
    const sheet = document.createElement("div");
    sheet.className = "moresheet"; sheet.id = "moresheet";
    sheet.innerHTML = more.map(([h, t, d]) => `<a href="${root}${h}"${here === h || (h === "./" && here === "index.html") ? ' aria-current="page"' : ""}>${t}<span>${d}</span></a>`).join("") +
      `<a href="${REPO}/issues/new?template=feedback.yml" target="_blank" rel="noopener">Send feedback<span>Ideas and problems</span></a>`;
    document.body.append(sheet, bar);
    const btn = bar.querySelector("button");
    const toggle = open => { sheet.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); };
    btn.onclick = e => { e.stopPropagation(); toggle(!sheet.classList.contains("open")); };
    document.addEventListener("click", e => { if (!sheet.contains(e.target)) toggle(false); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") toggle(false); });
  }
  // long page introductions: three lines on phones, with a button to read the rest
  function intros(){
    document.querySelectorAll(".pagehead > p").forEach(p => {
      if (p.textContent.length < 160 || p.classList.contains("clamp")) return;
      p.classList.add("clamp");
      const b = document.createElement("button"); b.type = "button"; b.className = "lmore"; b.textContent = "More";
      b.onclick = () => { const open = p.classList.toggle("clamp"); b.textContent = open ? "More" : "Less"; };
      p.after(b);
    });
  }
  function footer(){
    const links = `<a href="${root}score.html">Does the score work?</a><a href="${REPO}#readme" target="_blank" rel="noopener">Methodology</a><a href="${REPO}/issues/new?template=feedback.yml" target="_blank" rel="noopener">Send feedback</a>`;
    const nav = document.querySelector("footer nav");
    if (nav) { if (!nav.querySelector('a[href$="score.html"]')) nav.insertAdjacentHTML("beforeend", links); return; }
    const f = document.createElement("footer"); f.className = "sitefoot";
    f.innerHTML = `<div class="in"><nav aria-label="Footer"><a href="${root}./">Home</a><a href="${root}app.html">Screener</a><a href="${root}models.html">Model portfolios</a><a href="${root}news.html">News</a><a href="${root}portfolio.html">Portfolio</a><a href="${root}lab.html">Strategy Lab</a><a href="${root}investors.html">Investors</a><a href="${root}alerts.html">Alerts</a>${links}</nav><p>BullPulse is a free research tool, not investment advice. US prices from Tiingo; UK prices, and investors’ holdings outside the S&amp;P 500, from Yahoo Finance; investor holdings from SEC filings.</p></div>`;
    document.body.appendChild(f);
  }
  const start = () => {
    nav();
    intros();
    footer();
    fetch(root + "data/snapshot.json").then(r => r.ok ? r.json() : null).then(freshness).catch(() => {});
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
