# Frontend — Classroom Schedule Generator

A minimal Svelte + Vite single-page app. Upload a schedule CSV, pick a
semester and academic year, and download the rendered PDF timetable
(produced by the Gateway via typst).

## Develop

```bash
npm install
npm run dev
```

The dev server proxies `/api/*` to `http://localhost:8000` (see
`vite.config.js`), so run `Backend/Gateway` locally alongside it.

## Build

```bash
npm run build
```

## Docker

```bash
docker build -t schedule-frontend .
```

Serves the built app via Nginx, which proxies `/api/*` to the `gateway`
container (see `nginx.conf`). Use the root `compose.yaml` to run both
services together.
