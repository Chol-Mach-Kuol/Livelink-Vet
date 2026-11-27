// LiveLink Vet service worker: keeps the field app usable with no signal.
// Only the app shell is cached. API calls are never cached (reports queue in the page itself).
const CACHE = "livelink-shell-v1";
const SHELL = ["/report", "/static/theme.css", "/static/common.js", "/static/logo.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate" && url.pathname === "/report") {
    // Network first so updates arrive; cached copy when offline.
    event.respondWith(
      fetch(req)
        .then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put("/report", copy)); return res; })
        .catch(() => caches.match("/report"))
    );
    return;
  }

  if (SHELL.includes(url.pathname)) {
    // Stale-while-revalidate for the shell assets.
    event.respondWith(
      caches.match(req).then((cached) => {
        const fresh = fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        }).catch(() => cached);
        return cached || fresh;
      })
    );
  }
});
