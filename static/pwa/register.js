// PWA: botao de instalacao sem prompt intrusivo.
(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;

  const installed = () =>
    window.matchMedia('(display-mode: standalone)').matches ||
    navigator.standalone === true;

  const button = document.getElementById('prontoar-pwa-install');
  const isAppleMobile = /iPad|iPhone|iPod/i.test(navigator.userAgent);
  let pendingPrompt = null;

  const show = () => {
    if (button && !installed()) button.hidden = false;
  };
  const hide = () => {
    if (button) button.hidden = true;
  };

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    pendingPrompt = event;
    show();
  });

  window.addEventListener('appinstalled', () => {
    pendingPrompt = null;
    hide();
  });

  if (button) {
    button.addEventListener('click', async () => {
      if (pendingPrompt) {
        const promptEvent = pendingPrompt;
        pendingPrompt = null;
        hide();
        await promptEvent.prompt();
        await promptEvent.userChoice;
      } else if (isAppleMobile && !installed()) {
        window.alert('No Safari, toque em Compartilhar e depois em Adicionar a Tela de Início.');
      } else if (!installed()) {
        window.alert('Para instalar, use o ícone de instalação na barra de endereço ou o menu do navegador e escolha Instalar ProntoAr.');
      }
    });
  }

  if (button && !installed()) show();

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none'
    }).catch((error) => {
      console.warn('PWA nao disponivel:', error);
    });
  });
})();
