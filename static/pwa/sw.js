/* PWA v1: somente a pagina informativa offline e armazenada.
 * Nunca armazenar HTML autenticado, respostas de API, fotos, PDFs ou OS.
 */
const CACHE_PREFIX = 'prontoar-pwa-';
const CACHE_NAME = CACHE_PREFIX + 'offline-v1';
const OFFLINE_URL = '/static/pwa/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.add(new Request(OFFLINE_URL, { cache: 'reload' }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  // POST e recursos internos passam pelo navegador, sem interceptacao/caching.
  if (request.method !== 'GET' || request.mode !== 'navigate' ||
      new URL(request.url).origin !== self.location.origin) {
    return;
  }
  event.respondWith(
    fetch(request, { cache: 'no-store' }).catch(async () => {
      const cached = await caches.match(OFFLINE_URL);
      return cached || Response.error();
    })
  );
});
