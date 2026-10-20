// PWA: botao de instalacao sem prompt intrusivo.
(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;

  const installed = () => {
    let installedOnDevice = false;
    try {
      installedOnDevice = window.localStorage.getItem('prontoar-pwa-installed') === '1';
    } catch (_) {}
    return window.matchMedia('(display-mode: standalone)').matches ||
      navigator.standalone === true || installedOnDevice;
  };
  const status = document.getElementById('prontoar-pwa-install-status');
  const updateStatus = () => {
    if (!status) return;
    status.textContent = installed()
      ? 'ProntoAr est\u00e1 instalado neste dispositivo.'
      : 'ProntoAr ainda n\u00e3o est\u00e1 instalado. Use o bot\u00e3o de instala\u00e7\u00e3o.';
  };

  const buttons = [
    document.getElementById('prontoar-pwa-install'),
    document.getElementById('prontoar-pwa-settings-install')
  ].filter(Boolean);
  const isAppleMobile = /iPad|iPhone|iPod/i.test(navigator.userAgent);
  let pendingPrompt = null;

  const show = () => {
    if (!installed()) buttons.forEach((button) => { button.hidden = false; });
    updateStatus();
  };
  const hide = () => {
    buttons.forEach((button) => { button.hidden = true; });
    updateStatus();
  };

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    pendingPrompt = event;
    show();
  });

  window.addEventListener('appinstalled', () => {
    pendingPrompt = null;
    try {
      window.localStorage.setItem('prontoar-pwa-installed', '1');
    } catch (_) {}
    hide();
  });

  for (const button of buttons) {
    button.addEventListener('click', async () => {
      if (pendingPrompt) {
        const promptEvent = pendingPrompt;
        pendingPrompt = null;
        hide();
        await promptEvent.prompt();
        const choice = await promptEvent.userChoice;
        if (choice.outcome === 'dismissed') show();
      } else if (isAppleMobile && !installed()) {
        window.alert('No Safari, toque em Compartilhar e depois em Adicionar a Tela de Início.');
      } else if (!installed()) {
        window.alert('Para instalar, use o ícone de instalação na barra de endereço ou o menu do navegador e escolha Instalar ProntoAr.');
      }
    });
  }

  if (buttons.length && !installed()) show();
  updateStatus();

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', {
      scope: '/',
      updateViaCache: 'none'
    }).catch((error) => {
      console.warn('PWA nao disponivel:', error);
    });
  });
})();
