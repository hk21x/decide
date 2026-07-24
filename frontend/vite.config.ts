import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "decide",
        short_name: "decide",
        description: "Swipe. Decide. Watch. A film picker for your Plex library.",
        theme_color: "#151021",
        background_color: "#151021",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/decide-icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/decide-icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/decide-icon-maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // App shell + fonts precached; pages work offline once visited.
        globPatterns: ["**/*.{js,css,html,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // Recently-served artwork (brief §6): cache-first, bounded.
            urlPattern: ({ url }) => url.pathname.startsWith("/api/art/"),
            handler: "CacheFirst",
            options: {
              cacheName: "decide-art",
              expiration: { maxEntries: 200, maxAgeSeconds: 7 * 86400 },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            // Icons and the logo — small, stable, nice offline.
            urlPattern: ({ url }) =>
              url.pathname.endsWith(".png") && url.origin === self.location.origin,
            handler: "CacheFirst",
            options: {
              cacheName: "decide-static",
              expiration: { maxEntries: 20, maxAgeSeconds: 30 * 86400 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        ws: true,
      },
    },
  },
});
