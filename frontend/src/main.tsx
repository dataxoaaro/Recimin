import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
import { initTheme } from "@/lib/theme";
import "@/index.css";

initTheme();

/**
 * In production vite-plugin-pwa injects registerSW.js, which registers the
 * generated Workbox worker (and that worker importScripts the push handlers).
 * The dev server has no such worker, so navigator.serviceWorker.ready never
 * resolved and enablePush() hung forever. Register the push handlers directly
 * here; .ready resolves once either registration completes.
 */
if ("serviceWorker" in navigator && import.meta.env.DEV) {
  void navigator.serviceWorker.register("/push-sw.js");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
