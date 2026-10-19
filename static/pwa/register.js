// Somente registra em contexto seguro e quando o template habilitou o PWA.
(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none'
    }).catch((error) => {
      console.warn('PWA indisponivel neste navegador:', error);
    });
  });
})();
