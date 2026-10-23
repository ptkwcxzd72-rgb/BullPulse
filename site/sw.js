// BullPulse service worker: makes the site installable and usable offline.
// Pages and data are fetched from the network first (they change every night) and fall back to
// the last copy seen; static assets are served from the cache first.
const CACHE = "bullpulse-v3";
const SHELL = ["./", "index.html", "app.html", "portfolio.html", "alerts.html", "bp.css", "favicon.svg", "manifest.webmanifest", "brand/icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const fresh = url.origin === location.origin && (req.mode === "navigate" || /\/(data|feeds)\//.test(url.pathname) || /\.html$/.test(url.pathname));
  if (fresh) {
    e.respondWith(fetch(req).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(k => k.put(req, c)); } return r; })
      .catch(() => caches.match(req).then(r => r || caches.match("app.html"))));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
    if (r.ok && (url.origin === location.origin || /unpkg\.com|fonts\.(googleapis|gstatic)\.com/.test(url.host))) { const c = r.clone(); caches.open(CACHE).then(k => k.put(req, c)); }
    return r;
  })));
});
