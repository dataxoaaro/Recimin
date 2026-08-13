import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      devOptions: { enabled: false },
      manifest: {
        name: "Recimin",
        short_name: "Recimin",
        description: "Every recipe you saved, in one place.",
        start_url: "/",
        scope: "/",
        display: "standalone",
        theme_color: "#a8502f",
        background_color: "#faf6ee",
        icons: [
          { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
        ],
        // A silent no-op on iOS — WebKit has never implemented share_target and
        // the bug has been open since 2019. Five lines, and it buys Android and
        // desktop Chrome for free.
        share_target: {
          action: "/import",
          method: "GET",
          params: { title: "title", text: "text", url: "url" },
        },
      },
      workbox: {
        globPatterns: ["**/*.{js,css,svg}"],
        navigateFallback: null,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === "navigate",
            handler: "NetworkFirst",
            options: { cacheName: "app-shell", networkTimeoutSeconds: 3 },
          },
          {
            // Offline reading is explicitly out of scope, so this is a short
            // timeout for flaky networks, not an offline cache.
            urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.startsWith("/api/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api",
              networkTimeoutSeconds: 5,
              expiration: { maxAgeSeconds: 60 * 5 },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: { "/api": "http://localhost:8850", "/health": "http://localhost:8850" },
  },
});
