(() => {
  const button = document.getElementById('prontoar-push-toggle');
  const userId = button?.dataset.userId || 'anonymous';
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
  const setLabel = (active) => {
    button.textContent = active ? 'Avisos de serviço ativos · Desativar' : 'Ativar avisos de serviço';
    button.hidden = false;
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
    heading.textContent = `Agenda de hoje · ${data.services.length} cliente(s)`;
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
      link.textContent = `${service.time} · ${service.client} — ${service.service}`;
      link.style.cssText = 'color:#0b4f8a;text-decoration:underline;';
      item.appendChild(link); list.appendChild(item);
    }
    toast.appendChild(list);
    document.body.appendChild(toast);
  };

  showTodaySchedule().catch(() => {});
  if (!button || !('serviceWorker' in navigator) || !('PushManager' in window) || !window.isSecureContext) return;

  navigator.serviceWorker.ready.then(async (registration) => {
    setLabel(Boolean(await registration.pushManager.getSubscription()));
  }).catch(() => setLabel(false));
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe();
        await request('/notifications/unsubscribe', { endpoint });
        setLabel(false);
        return;
      }
      const keyResponse = await fetch('/notifications/vapid-public-key', { credentials: 'same-origin' });
      if (!keyResponse.ok) throw new Error('O servidor ainda não configurou as notificações push.');
      const { publicKey } = await keyResponse.json();
      if (await Notification.requestPermission() !== 'granted') throw new Error('Permissão para notificações não concedida.');
      subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodeKey(publicKey) });
      const response = await request('/notifications/subscribe', { subscription: subscription.toJSON() });
      if (!response.ok) throw new Error('Não foi possível salvar sua inscrição de notificações.');
      setLabel(true);
    } catch (error) {
      window.alert(error.message || 'Não foi possível ativar os avisos.');
    } finally {
      button.disabled = false;
    }
  });
})();
