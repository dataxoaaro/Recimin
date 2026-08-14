# Recimin frontend

React 19 + TypeScript + Vite + Tailwind v4, built as an installable PWA. See
the repository root README for the full picture.

```bash
pnpm install
pnpm dev              # Vite dev server, proxies /api to the backend
pnpm exec tsc --noEmit
npx vitest run
pnpm build            # output in dist/, served by the api container
```
