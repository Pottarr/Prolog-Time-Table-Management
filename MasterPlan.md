# Master Plan — Frontend & Gateway Implementation

This plan picks up where `Prolog-Time-Table-Management-Setup.md` left off. The
Prolog reasoning engine is proven end-to-end (`main.pl` + `scheduler.pl`
serve HTTP/JSON on port 8080 inside a container). The **Gateway** and
**Frontend** directories currently contain only empty `Dockerfile` stubs —
this document defines how to fill them in.

## 1. Target architecture

```text
Browser
   |
   v
Frontend (React SPA, static files served by Nginx)
   |
   | HTTPS/JSON  (fetch to /api/*)
   v
Gateway (Node.js/Express API)
   |  - auth, validation, request shaping
   |  - the ONLY service exposed to the internet
   |
   | internal HTTP/JSON  (docker network, not exposed publicly)
   v
Prolog Service (SWI-Prolog, current Backend/Prolog)
   |  - facts, rules, CLP(FD) constraints, optimization
   v
Timetable / room assignment result
```

Three containers, one Docker Compose network:

| Service  | Folder            | Language           | Exposed port |
|----------|-------------------|--------------------|--------------|
| frontend | `Frontend/`       | React + TypeScript | 80 (public)  |
| gateway  | `Backend/Gateway/`| Node.js + Express + TypeScript | 3000 (public) |
| prolog   | `Backend/Prolog/` | SWI-Prolog          | 8081 (internal only) |

The Prolog container should **not** be published to the host in production —
only `gateway` talks to it, over the Compose network name `prolog`.

## 2. Gateway (`Backend/Gateway`)

### 2.1 Why Node.js + Express + TypeScript

- JSON in, JSON out on both sides (browser and Prolog's `reply_json_dict`) —
  no serialization impedance mismatch.
- Lightweight enough to justify being a thin gateway rather than a heavy
  framework; TypeScript gives request/response typing that documents the
  contract with both the frontend and Prolog.
- First-class `fetch`/`axios` HTTP client story for calling the internal
  Prolog service.

### 2.2 Responsibilities

- The **only** service reachable from the public internet in production.
- Validates and shapes all incoming requests before they ever reach Prolog
  (per §10 of the setup doc: never expose a raw query endpoint).
- Translates HTTP requests into calls against a fixed, known set of Prolog
  predicates/endpoints — one gateway route per allowed operation.
- Normalizes Prolog's responses (and its failure modes — a predicate that
  fails, times out, or the container being unreachable) into consistent
  HTTP status codes and JSON error bodies for the frontend.
- Owns cross-cutting concerns Prolog shouldn't: CORS, request logging,
  input validation, rate limiting, and (once needed) auth/session handling
  and persistence (course/room data, saved timetables) in a real database.

### 2.3 Folder structure

```text
Backend/Gateway/
├── Dockerfile
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # entrypoint: create app, listen
│   ├── app.ts                # express app, middleware wiring
│   ├── config.ts             # env vars (PORT, PROLOG_URL, ...)
│   ├── routes/
│   │   ├── health.ts         # GET /api/health
│   │   ├── rooms.ts          # /api/rooms
│   │   ├── courses.ts        # /api/courses
│   │   └── timetable.ts      # /api/timetable/generate
│   ├── services/
│   │   └── prologClient.ts   # wraps HTTP calls to the Prolog container
│   ├── schemas/              # request/response validation (zod)
│   └── middleware/
│       ├── errorHandler.ts
│       └── requestLogger.ts
└── test/
    └── routes/*.test.ts
```

### 2.4 API surface (mirrors, never bypasses, Prolog's own endpoints)

| Method | Path                      | Calls into Prolog      | Notes |
|--------|---------------------------|-------------------------|-------|
| GET    | `/api/health`             | —                        | Gateway + Prolog liveness |
| GET    | `/api/rooms`              | `room/2` facts           | List rooms + capacity |
| GET    | `/api/courses`            | `course/2` facts         | List courses + enrollment |
| POST   | `/api/timetable/generate` | `generate_timetable/…`   | Body: courses, rooms, constraints. Returns assignment or 422 with the unsatisfiable constraint |
| GET    | `/api/timetable/:id`      | (DB, not Prolog)         | Fetch a previously generated/saved timetable |

Each route does: **validate → call `prologClient` → map result → respond**.
No route should accept a free-form Prolog expression from the client.

### 2.5 Talking to Prolog

`services/prologClient.ts` centralizes the internal HTTP calls:

```ts
const PROLOG_URL = process.env.PROLOG_URL ?? "http://prolog:8081";

export async function generateTimetable(payload: TimetableRequest) {
  const res = await fetch(`${PROLOG_URL}/generate-timetable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10_000), // solver can be slow — bound it
  });
  if (!res.ok) throw new PrologError(res.status, await res.text());
  return res.json();
}
```

Key points:
- Timeouts matter — constraint solving can be slow or hang; the gateway
  must not let a client request block forever.
- One typed function per Prolog endpoint, matching the "known predicates
  only" rule from the setup doc.
- Map Prolog-side failures (`result: false`, HTTP 4xx/5xx, connection
  refused) to meaningful gateway responses (`404`, `422 Unprocessable`,
  `503 Service Unavailable`) rather than leaking raw Prolog errors.

### 2.6 Dockerfile

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

## 3. Frontend (`Frontend/`)

### 3.1 Why React + TypeScript + Vite

- Fast dev server, small production build, easy static-file Docker image
  (matches the "SPA behind Nginx" deployment shape).
- TypeScript types for the gateway's JSON contracts catch mismatches at
  build time instead of in the browser console.

### 3.2 Pages / views

| Route          | Purpose |
|----------------|---------|
| `/`            | Dashboard — summary of rooms, courses, latest timetable |
| `/courses`     | CRUD for courses (name, size, required room type) |
| `/rooms`       | CRUD for rooms (name, capacity, type/availability) |
| `/timetable`   | Trigger generation, show progress, render the resulting grid |
| `/timetable/:id` | View a previously generated timetable |

### 3.3 Folder structure

```text
Frontend/
├── Dockerfile
├── package.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts         # thin wrapper around fetch to the gateway
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── Courses.tsx
│   │   ├── Rooms.tsx
│   │   └── Timetable.tsx
│   ├── components/
│   │   ├── TimetableGrid.tsx
│   │   └── forms/...
│   └── types/                # mirrors Gateway's schemas/ types
└── nginx.conf                # SPA fallback + /api proxy (optional)
```

### 3.4 Talking to the Gateway

- All calls go through `src/api/client.ts`, hitting relative paths like
  `/api/timetable/generate` — never the Prolog service directly, and never
  a hardcoded absolute host (so the same build works in dev and prod).
- In production, Nginx serves the built static files and reverse-proxies
  `/api/*` to the `gateway` container, so the browser never needs to know
  the gateway's internal address:

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  location /api/ {
    proxy_pass http://gateway:3000/api/;
  }
  location / {
    try_files $uri /index.html;
  }
}
```

- In local dev, Vite's dev-server proxy (`vite.config.ts`) forwards `/api`
  to `http://localhost:3000` so `npm run dev` works without CORS setup.

### 3.5 Dockerfile

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

## 4. Example contract: generating a timetable

`POST /api/timetable/generate` (Frontend → Gateway):

```json
{
  "courses": [
    { "id": "coa", "enrollment": 40, "type": "lecture" },
    { "id": "dsa", "enrollment": 25, "type": "lecture" }
  ],
  "rooms": [
    { "id": "r101", "capacity": 30 },
    { "id": "r102", "capacity": 50 }
  ]
}
```

Gateway → Prolog (`POST /generate-timetable` on the internal service),
same shape, forwarded after validation.

Success response (Prolog → Gateway → Frontend):

```json
{
  "status": "ok",
  "assignments": [
    { "course": "coa", "room": "r102", "slot": "mon-09-11" },
    { "course": "dsa", "room": "r102", "slot": "mon-11-13" }
  ],
  "roomsUsed": 1
}
```

Unsatisfiable case → Gateway returns `422` with:

```json
{ "status": "unsatisfiable", "reason": "no room fits course 'coa'" }
```

## 5. Docker Compose

```yaml
services:
  frontend:
    build: ./Frontend
    ports:
      - "80:80"
    depends_on:
      - gateway

  gateway:
    build: ./Backend/Gateway
    ports:
      - "3000:3000"
    environment:
      - PROLOG_URL=http://prolog:8081
    depends_on:
      - prolog

  prolog:
    build: ./Backend/Prolog
    expose:
      - "8081"
```

Note: the existing `Backend/Prolog/Dockerfile` and `main.pl` currently use
port 8080; align them to `8081` (or update this compose file to match)
before wiring the gateway in, so the "internal-only" port is unambiguous.

## 6. Suggested build order

1. **Gateway skeleton**: Express app, `/api/health`, Dockerfile, compose
   wiring to the existing Prolog container. Confirms the network path
   Frontend → Gateway → Prolog works end-to-end, replacing the manual
   `curl` test from the setup doc.
2. **Real timetable predicates in Prolog** (`rooms.pl`, `constraints.pl`,
   CLP(FD) solver) exposed via `/generate-timetable`, per §11 of the setup
   doc — independent of gateway/frontend work, can proceed in parallel.
3. **Gateway routes** for rooms/courses/timetable, with validation schemas
   and the Prolog-error-mapping described in §2.5.
4. **Frontend skeleton**: Vite app, routing, API client, Dockerfile +
   Nginx proxy, pointed at the gateway's `/api/health`.
5. **Frontend pages**: courses/rooms CRUD, then the timetable generation
   flow and grid view, wired to the real gateway endpoints.
6. **Hardening**: auth (if multiple users need distinct access), request
   rate limiting on `/api/timetable/generate` (solver calls are expensive),
   persistence for courses/rooms/saved timetables (currently only living
   as Prolog facts — a real database belongs in the gateway, per the
   two-container architecture in §12 of the setup doc).

## 7. Open decisions

- **Persistence**: courses/rooms currently only exist as Prolog facts.
  Decide whether the gateway owns a database (Postgres/SQLite) as the
  source of truth and pushes facts into Prolog per request, or whether
  Prolog's fact base stays authoritative for now (fine for a prototype,
  not for multi-user production).
- **Auth**: none exists yet. If this is multi-user, decide where sessions
  live (gateway) before building CRUD pages that assume a current user.
- **Language choice**: this plan assumes Node/Express + React because they
  share JSON naturally with SWI-Prolog's `http/json` libraries and keep
  the whole stack in TypeScript. If there's a reason to prefer Go/Java/Rust
  for the gateway (per the "Rust / Java / Go" placeholder in the setup
  doc) or Vue/Svelte for the frontend, swap the stack — the routes,
  contracts, and Docker Compose topology above stay the same either way.
