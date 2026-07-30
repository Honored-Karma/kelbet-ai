# KELBET Mini App

Telegram Mini App (Vite + React + TypeScript strict).

## Scripts

```bash
npm install
npm run dev
npm run build
```

## Env

Copy `.env.example`:

- `VITE_API_MODE=mock` — local UI against in-browser mock API (default DoD path)
- `VITE_API_MODE=live` — real `/api/v1` via `VITE_API_BASE_URL`

Prices always come from `POST /wallet/quote` (or mock quote). The client never invents credit costs.

## Pages

Home, Create, Generation, History, Plans (stub), Profile (ru/kk).
