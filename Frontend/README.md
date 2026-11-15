# Frontend — Classroom Schedule Generator

A minimal Svelte + Vite single-page app for the ECC building's 8th floor.
Upload a schedule CSV and a config JSON (semester, academic year, room
capacities); the app shows the floor plan (`src/lib/ecc-8th-floor.svg`)
with each of the ten classrooms (ECC-801 … ECC-810) clickable — click one
to see its weekly timetable. **Download summary PDF** fetches the rendered PDF (one page per
room, produced by the Gateway via typst).

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
