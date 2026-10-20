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

self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) { payload = { body: event.data?.text() || '' }; }
  event.waitUntil(self.registration.showNotification(payload.title || 'ProntoAr', {
    body: payload.body || 'Você tem um aviso sobre um serviço agendado.',
    icon: '/static/pwa/icon-192.png', badge: '/static/pwa/icon-192.png',
    tag: payload.tag || 'prontoar-service-reminder', data: { url: payload.url || '/' }, renotify: false
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(target);
        return client.focus();
      }
    }
    return self.clients.openWindow(target);
  })());
});
