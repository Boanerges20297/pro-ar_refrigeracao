/* Rollback: substituir a versao instalada por worker sem fetch e sem cache. */
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith('prontoar-pwa-')) await caches.delete(name);
    }
    await self.registration.unregister();
  })());
});
