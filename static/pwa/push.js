(() => {
  const button = document.getElementById('prontoar-push-toggle');
  const settingsButton = document.getElementById('prontoar-push-settings-toggle');
  const settingsStatus = document.getElementById('prontoar-push-settings-status');
  const userId = button?.dataset.userId || settingsButton?.dataset.userId || 'anonymous';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const request = (url, body) => fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    credentials: 'same-origin', body: JSON.stringify(body)
  });
  const decodeKey = (key) => {
    const padded = key + '='.repeat((4 - key.length % 4) % 4);
    const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  };
  const permission = () => window.Notification?.permission || 'default';
  const setPushState = (active) => {
    const selectedPermission = permission();
    if (button) {
      button.textContent = 'Ativar avisos de servi\u00e7o';
      button.hidden = active || selectedPermission !== 'default';
    }
    if (settingsButton) {
      settingsButton.textContent = active ? 'Desativar avisos neste navegador' : 'Ativar avisos neste navegador';
      settingsButton.hidden = false;
      settingsButton.disabled = selectedPermission === 'denied';
    }
    if (settingsStatus) {
      if (active) settingsStatus.textContent = 'Avisos ativados neste navegador.';
      else if (selectedPermission === 'denied') settingsStatus.textContent = 'Notifica\u00e7\u00f5es bloqueadas pelo navegador. Altere a permiss\u00e3o nas configura\u00e7\u00f5es do navegador.';
      else if (selectedPermission === 'granted') settingsStatus.textContent = 'Permiss\u00e3o concedida, mas a inscri\u00e7\u00e3o de avisos est\u00e1 desativada.';
      else settingsStatus.textContent = 'Avisos desativados neste navegador.';
    }
  };

  const showTodaySchedule = async () => {
    const response = await fetch('/notifications/today', { credentials: 'same-origin' });
    if (!response.ok) return;
    const data = await response.json();
    const key = `prontoar-agenda-${userId}-${data.date}`;
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, 'shown');
    if (!data.services.length) return;

    const toast = document.createElement('section');
    toast.setAttribute('role', 'status');
    toast.style.cssText = 'position:fixed;right:1rem;bottom:5rem;z-index:10000;width:min(24rem,calc(100vw - 2rem));max-height:60vh;overflow:auto;background:#fff;color:#172033;border:1px solid #cbd5e1;border-radius:1rem;padding:1rem;box-shadow:0 10px 30px rgba(0,0,0,.22);font:14px system-ui,sans-serif;';
    const heading = document.createElement('strong');
    heading.textContent = `Agenda de hoje - ${data.services.length} cliente(s)`;
    toast.appendChild(heading);
    const close = document.createElement('button');
    close.type = 'button'; close.textContent = 'Fechar';
    close.style.cssText = 'float:right;border:0;background:transparent;color:#0b4f8a;font-weight:600;cursor:pointer;';
    close.addEventListener('click', () => toast.remove());
    toast.appendChild(close);
    const list = document.createElement('ul');
    list.style.cssText = 'margin:.75rem 0 0;padding-left:1.1rem;';
    for (const service of data.services) {
      const item = document.createElement('li'); item.style.marginTop = '.45rem';
      const link = document.createElement('a'); link.href = service.url;
      link.textContent = `${service.time} - ${service.client} - ${service.service}`;
      link.style.cssText = 'color:#0b4f8a;text-decoration:underline;';
      item.appendChild(link); list.appendChild(item);
    }
    toast.appendChild(list);
    document.body.appendChild(toast);
  };

  showTodaySchedule().catch(() => {});
  const hasPushSupport = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && window.isSecureContext;
  if (!hasPushSupport) {
    if (settingsStatus) settingsStatus.textContent = 'Este navegador n\u00e3o oferece suporte a avisos push.';
    if (settingsButton) settingsButton.disabled = true;
    return;
  }

  navigator.serviceWorker.ready.then(async (registration) => {
    setPushState(Boolean(await registration.pushManager.getSubscription()));
  }).catch(() => {
    setPushState(false);
    if (settingsStatus) settingsStatus.textContent = 'N\u00e3o foi poss\u00edvel verificar os avisos neste navegador.';
  });

  const togglePush = async (control) => {
    control.disabled = true;
    try {
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe();
        const response = await request('/notifications/unsubscribe', { endpoint });
        if (!response.ok) throw new Error('N\u00e3o foi poss\u00edvel desativar os avisos neste navegador.');
        setPushState(false);
        return;
      }
      if (permission() === 'denied') throw new Error('Permita notifica\u00e7\u00f5es para este site nas configura\u00e7\u00f5es do navegador.');
      const keyResponse = await fetch('/notifications/vapid-public-key', { credentials: 'same-origin' });
      if (!keyResponse.ok) throw new Error('O servidor ainda n\u00e3o configurou as notifica\u00e7\u00f5es push.');
      const { publicKey } = await keyResponse.json();
      if (await Notification.requestPermission() !== 'granted') throw new Error('Permiss\u00e3o para notifica\u00e7\u00f5es n\u00e3o concedida.');
      subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodeKey(publicKey) });
      const response = await request('/notifications/subscribe', { subscription: subscription.toJSON() });
      if (!response.ok) throw new Error('N\u00e3o foi poss\u00edvel salvar sua inscri\u00e7\u00e3o de notifica\u00e7\u00f5es.');
      setPushState(true);
    } catch (error) {
      window.alert(error.message || 'N\u00e3o foi poss\u00edvel atualizar os avisos.');
    } finally {
      control.disabled = false;
    }
  };
  for (const control of [button, settingsButton].filter(Boolean)) {
    control.addEventListener('click', () => togglePush(control));
  }
})();
