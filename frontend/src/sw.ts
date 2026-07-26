/// <reference lib="webworker" />
/* decide service worker: app-shell precache, bounded artwork cache, and
 * Web Push for async match alerts. */

import { clientsClaim } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { CacheFirst } from "workbox-strategies";

declare let self: ServiceWorkerGlobalScope;

self.skipWaiting();
clientsClaim();

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// SPA navigations -> the precached shell; the API is never intercepted.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL("index.html"), {
    denylist: [/^\/api\//],
  }),
);

// Recently-served artwork (brief §6): cache-first, bounded.
registerRoute(
  ({ url }) => url.pathname.startsWith("/api/art/"),
  new CacheFirst({
    cacheName: "decide-art",
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 86400 })],
  }),
);

// Icons and the logo.
registerRoute(
  ({ url, sameOrigin }) => sameOrigin && url.pathname.endsWith(".png"),
  new CacheFirst({
    cacheName: "decide-static",
    plugins: [new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 30 * 86400 })],
  }),
);

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
  tag?: string;
}

self.addEventListener("push", (event) => {
  let payload: PushPayload = {};
  try {
    payload = event.data?.json() ?? {};
  } catch {
    /* non-JSON push — show something rather than nothing */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title ?? "decide", {
      body: payload.body ?? "Something happened in your session.",
      tag: payload.tag,
      icon: "/decide-icon-192.png",
      badge: "/decide-icon-192.png",
      data: { url: payload.url ?? "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data?.url as string) ?? "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          void client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
