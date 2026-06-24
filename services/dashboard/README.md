# Lenta — Dashboard

Live monitoring UI for the Lenta AI video-recommendation system. A static
Vite + React + TypeScript app (TailwindCSS + recharts) that polls the API every
~2 seconds.

## Panels

1. **Live workflow** — per-user funnel (catalog → candidates → ranked → feed),
   the user's current feed, an event ticker, and active sessions.
2. **Model timeline** — recall@k / ndcg@k / coverage / diversity per model
   version.
3. **A/B test** — treatment (recommender) vs control (popularity): CTR, watch
   seconds, session length, and lift.
4. **Scenario controls** — the demo cockpit: start/stop the sim, switch
   scenarios with an intensity slider, retrain, and reset.
5. **Pipeline status** — ingest / feature_update / retrain / deploy stages,
   recent runs, and recent jobs.

## Configuration

The API base URL is read from `VITE_API_URL` (default `http://localhost:8000`).
For local dev create a `.env` (or `.env.local`):

```
VITE_API_URL=http://localhost:8000
```

## Develop

```bash
npm install
npm run dev
```

Open the printed local URL (default http://localhost:5173).

## Build

```bash
npm run build      # type-checks then builds static assets into dist/
npm run preview    # serve the production build locally
```

## Docker

`VITE_API_URL` is baked in at build time, so pass it as a build arg:

```bash
docker build --build-arg VITE_API_URL=http://localhost:8000 -t lenta-dashboard .
docker run -p 8080:8080 lenta-dashboard
```

The container serves the static `dist/` on `$PORT` (default `8080`) via `serve`.
