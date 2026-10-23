/* Simple app-shell service worker for the mobile PWA.
 * Network-first for the HTML so firmware/UI updates show immediately, cache
 * fallback for offline. The WebSocket is never cached. */
const CACHE = 'drone-gs-v1';
const ASSETS = [
  './mobile.html', './controls.js', './craft.png', './icon-192.png', './icon-512.png', './manifest.webmanifest'
];
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS).catch(() => {})));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.endsWith('.html') || url.pathname.endsWith('/')) {
    e.respondWith(fetch(req).catch(() => caches.match(req).then(r => r || caches.match('./mobile.html'))));
  } else {
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(resp => {
      const cp = resp.clone();
      caches.open(CACHE).then(c => c.put(req, cp)).catch(() => {});
      return resp;
    }).catch(() => r)));
  }
});
