/* Push handlers, imported into the Workbox-generated service worker.
 *
 * Kept as a separate file rather than switching the plugin to injectManifest:
 * generateSW handles the precache manifest well and this is the only custom
 * behaviour we need.
 */

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "Recimin", body: event.data.text(), url: "/" };
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "Recimin", {
      body: payload.body || "",
      icon: "/icon.svg",
      badge: "/icon.svg",
      data: { url: payload.url || "/" },
      tag: payload.url || "recimin",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      // Focus an existing window rather than opening a second copy of the app.
      for (const client of windows) {
        if ("focus" in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
