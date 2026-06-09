self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(clients.claim()));

self.addEventListener('push', event => {
  if (!event.data) return;
  let payload;
  try { payload = event.data.json(); } catch(_) { return; }
  event.waitUntil(
    self.registration.showNotification(payload.title || 'VDD Rittatlas', {
      body: payload.body || '',
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      tag: payload.tag || payload.event_id || undefined,
      data: { url: payload.url || '/', doc_urls: payload.doc_urls || {} },
      actions: payload.actions || [],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {};
  const rawUrl = data.doc_urls[event.action] || data.url || '/';
  // Cross-origin URLs (e.g. PDFs on vdd-aktuell.de) go through a same-origin
  // redirect page so client.navigate() works and the existing tab gets focused.
  const url = rawUrl.startsWith(self.location.origin)
    ? rawUrl
    : `${self.registration.scope}redirect.html?url=${encodeURIComponent(rawUrl)}`;
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.navigate(url).then(c => c ? c.focus() : client.focus());
        }
      }
      return clients.openWindow(url);
    })
  );
});
