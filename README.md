# lenta-mvp — AI personalized video recommendations

An end-to-end, **self-learning** video recommendation system for a digital media
platform, built as multiple services in one repo and deployable to a single
Railway project. It runs entirely on realistic **mock data** and ships with a
live **monitoring dashboard** that visualizes the whole workflow and shows how
recommendations change as the system learns.

Built for the AstanaHub tech task *“AI system for personalized video-content
recommendations”* (client: Azimut Tech). Optimized to **run locally with one
command**, **deploy to Railway cleanly**, and **demo well** — the model visibly
adapts when user behavior shifts.

## 🔗 Live demo, presentation & guides

- **Live dashboard** → https://lenta-mvp.xyz &nbsp;·&nbsp; **API + interactive docs** → https://api.lenta-mvp.xyz/docs
- **Presentation** → [`docs/Lenta-Presentation.pdf`](docs/Lenta-Presentation.pdf) &nbsp;·&nbsp; editable [`docs/Lenta-Presentation.pptx`](docs/Lenta-Presentation.pptx)
- **60-second reviewer quick-start** → [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- **Integrate Lenta into your platform** → [`docs/INTEGRATION.md`](docs/INTEGRATION.md)
- **Scale to thousands → millions of users** → [`docs/SCALING.md`](docs/SCALING.md)

---

## What it does (the funnel + two loops)

**Serving funnel:** `user events → candidate generation → ranking → re-rank → feed`

- **Candidate generation (retrieval):** ALS implicit-feedback collaborative
  filtering (`implicit`) narrows the catalog to a few hundred candidates, with a
  **content-based fallback** (genre similarity) for cold-start users and a
  **popularity** path for brand-new users.
- **Ranking:** a LightGBM model scores the shortlist by **predicted watch-time
  fraction** — *not* click probability. Ranking on clicks breeds clickbait;
  watch-time optimizes the retention goal in the brief.
- **Re-rank:** diversity + freshness rules (cap items per creator/genre, mix in
  recent uploads).

**Real-time loop:** per-session features (last-N genres, genre streak,
time-of-day) live in **Redis**, updated on every event, read by the ranker at
serving time.

**Self-learning loop:** every impression/play is logged to **Postgres** → a
scheduled + manually-triggerable **retrain** runs in the `trainer` → the new
model + eval metrics are written to a **Postgres-backed model registry** → the
`api` **hot-swaps** to the latest active version. Training is **recency-weighted**,
so when behavior shifts the model adapts within a retrain or two — visibly.

```
                       ┌────────────────────────── trainer (worker) ──────────────────────────┐
                       │  seed v1 · APScheduler retrain · /retrain jobs · live simulator       │
                       └───────────────┬───────────────────────────────────┬───────────────────┘
   browser / sim ──HTTP──▶  api (FastAPI)                                   │ writes model_versions (bytea)
        ▲                    │  /feed  → ALS → LightGBM → re-rank → feed     │ + metrics + pipeline_runs
        │ polls /metrics     │  /event → Redis session features             ▼
   dashboard (React)         │  hot-reload active model ◀──── Postgres model registry ────┐
                             └──── events ──▶ Postgres ◀── Redis (sessions + sim control) ─┘
```

---

## Repo structure

```
lenta-mvp/
├── packages/core/        # lenta_core: db schema, features, ALS+LightGBM, eval,
│                         #   registry, mock-data generators, CLI  (shared lib)
├── services/api/         # FastAPI: serving + ingestion + metrics + control plane
├── services/trainer/     # worker: seed, scheduled+manual retrain, live simulator
├── services/dashboard/   # Vite + React + TS + Tailwind + recharts (5 live panels)
├── docker-compose.yml    # postgres + redis + all 3 services for local dev
├── Makefile  .env.example  README.md
```

`core` is installed as an editable workspace dependency by `api` and `trainer`,
so there is one source of truth for models and features (and **train/serve
feature parity** is guaranteed by a single feature spec in
`core/features/ranking.py`).

---

## Quickstart (local, Docker)

Requires Docker + Docker Compose.

```bash
cp .env.example .env
make up        # postgres + redis + api + trainer + dashboard
               # trainer auto-seeds the catalog/users/backfill and trains v1 on
               # first boot (~30s). Watch progress with: make logs
```

Then open:

- **Dashboard** → http://localhost:8080
- **API docs** → http://localhost:8000/docs
- **Health**   → http://localhost:8000/health

### Run the demo (the centerpiece)

From the dashboard's **Scenario Controls** panel (or via curl):

1. **Start simulation** (rate ~20/s). Synthetic users start flowing through the
   real `/feed` + `/event` path. The **A/B panel** fills in: *treatment* (the
   recommender) vs *control* (popularity). Treatment shows a clear CTR /
   watch-time **lift**.
2. **Inject `genre_shift`** — a cohort swings toward a new genre.
3. **Trigger retrain.** Within seconds a new model version goes active (the api
   hot-reloads it).
4. Watch the **Model timeline**, the sample user's **feed**, and the headline
   **report** banner update — e.g. *“After retrain v2: action share of feeds rose
   3%, NDCG@10 +0.46.”*

`make demo` resets to a smaller, clean, demo-ready state at any time.

curl equivalent of the demo:

```bash
curl -X POST localhost:8000/sim/start    -H 'content-type: application/json' -d '{"rate":20}'
curl -X POST localhost:8000/sim/scenario -H 'content-type: application/json' -d '{"scenario":"genre_shift","intensity":4}'
curl -X POST localhost:8000/retrain
curl -s localhost:8000/report        # plain-English summary of what changed
curl -s "localhost:8000/metrics?window_minutes=10"   # per-variant CTR/watch + lift
```

## Quickstart (local, no Docker)

You need Postgres + Redis reachable at the URLs in `.env`, plus
[`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                                   # one venv with all workspace members
export DATABASE_URL=postgresql+psycopg://lenta:lenta@localhost:5432/lenta
export REDIS_URL=redis://localhost:6379/0

uv run python -m lenta_core.cli smoke     # seed → train → recommend → eval (one shot)

# or run the services in separate terminals:
make api          # uvicorn on $PORT (8000)
make trainer      # the worker (seeds on boot if empty, scheduler + simulator)
make dashboard    # vite dev server (http://localhost:5173)
```

The `lenta_core` CLI is handy on its own:

```bash
uv run python -m lenta_core.cli seed --demo        # reset + seed a demo dataset
uv run python -m lenta_core.cli train              # train + register next version
uv run python -m lenta_core.cli recommend --user 1 --k 10
uv run python -m lenta_core.cli recommend --user 1 --variant control
uv run python -m lenta_core.cli eval               # active model metrics
```

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET  | `/feed?user_id=&k=&variant=&session_id=` | Run the funnel (or popularity if `variant=control`); logs impressions; returns ranked videos + per-stage funnel debug. |
| POST | `/event` | Ingest an interaction; updates Redis session features; writes to `events`. |
| GET  | `/metrics?window_minutes=` | Online metrics (CTR, avg watch-time, session length) overall + per A/B variant, with lift. |
| GET  | `/models` | Registry: version history with offline metrics over time. |
| POST | `/retrain` | Queue a retrain job (trainer picks it up); returns `job_id`. |
| POST | `/reset` | Queue a full reset + reseed + retrain. |
| POST | `/sim/start` · `/sim/stop` · `/sim/scenario` | Control the live simulator. |
| GET  | `/sim/status` | Simulator state. |
| GET  | `/pipeline/status` | Last run + status of each stage (ingest / feature_update / retrain / deploy). |
| GET  | `/events/recent` · `/sessions/active` · `/users/sample` · `/report` · `/jobs/recent` | Dashboard feeds. |
| GET  | `/health` · `/` | Liveness + endpoint index. |

Scenarios: `genre_shift`, `new_content_surge`, `cold_start_wave`, `baseline`.

---

## The dashboard (5 live panels)

1. **Live workflow** — funnel counts (catalog → candidates → ranked → feed) for a
   sample user, that user's feed re-rendering live, an event ticker, and active
   sessions.
2. **Model timeline** — Recall@K, NDCG@K, coverage, diversity per model version.
3. **A/B panel** — recommender (treatment) vs popularity (control): CTR, avg
   watch-time, session length, with a clear **lift** readout.
4. **Scenario controls** — the demo cockpit: start/stop sim, set rate, inject a
   scenario, trigger retrain, reset DB.
5. **Pipeline status** — timeline of stage runs with timestamps + durations.

A banner shows a one-line plain-English summary from `/report` of what the latest
retrain changed.

---

## Configuration

All config is read from the environment (no secrets in code). See `.env.example`.

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local Postgres | `postgres://` is auto-normalized to psycopg3. |
| `REDIS_URL` | local Redis | sessions + sim control. |
| `LENTA_SEED` | `42` | deterministic mock data. |
| `LENTA_N_VIDEOS` / `LENTA_N_USERS` / `LENTA_BACKFILL_EVENTS` | 600 / 400 / 40000 | seed sizes. |
| `SEED_ON_BOOT` | `true` | trainer seeds + trains v1 if the DB is empty. |
| `RETRAIN_INTERVAL_MINUTES` | `5` | nightly in prod; **minutes** for a live demo. |
| `SIM_DEFAULT_RATE` | `6` | simulator events/sec. |
| `RECENCY_HALFLIFE_DAYS` | `3` | training recency weight — lower = faster adaptation. |
| `MODEL_RELOAD_SECONDS` | `5` | how often the api polls the registry for a newer model. |
| `PORT` | `8000` | every web service binds `$PORT`. |
| `VITE_API_URL` | `http://localhost:8000` | build-time api URL for the dashboard. |

---

## Railway deploy

One Railway **project** with services `api`, `trainer`, `dashboard`, plus the
**Postgres** and **Redis** plugins. The model registry lives in Postgres
precisely so services need **no shared volume** (Railway volumes attach to a
single service).

All three services build from the **repo root** (root directory `/`) and select
their Dockerfile via the `RAILWAY_DOCKERFILE_PATH` service variable, so the
shared `core` package is always in the build context.

1. **Create the project** and add the **PostgreSQL** and **Redis** plugins
   (`railway add -d postgres -d redis`, or New → Database in the UI).
2. **api** — service with root directory `/` and these variables:
   - `RAILWAY_DOCKERFILE_PATH=services/api/Dockerfile`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `REDIS_URL=redis://default:${{Redis.REDIS_PASSWORD}}@redis.railway.internal:6379`
   - `PORT=8000` (set **before** the first deploy so the generated domain maps to it)
   - Generate a public domain targeting port 8000.
3. **trainer** (worker, no domain) — root `/`, variables:
   - `RAILWAY_DOCKERFILE_PATH=services/trainer/Dockerfile`
   - `DATABASE_URL`, `REDIS_URL` (same as api)
   - `API_URL=http://api.railway.internal:8000` (private network — trainer → api)
   - `SEED_ON_BOOT=true`, `RETRAIN_INTERVAL_MINUTES=30`, `SIM_DEFAULT_RATE=6`
4. **dashboard** — root `/`, variables:
   - `RAILWAY_DOCKERFILE_PATH=services/dashboard/Dockerfile`
   - `PORT=8080`
   - `VITE_API_URL=https://<api-public-domain>` — the api's **public** URL, baked
     into the static build (the browser calls it, so it must be public).
   - Generate a public domain targeting port 8080.
5. **Deploy order:** Postgres + Redis → api (+ domain) → trainer (seeds + trains
   v1 on first boot) → dashboard (+ domain). Open the dashboard URL and run the demo.

Tip: setting `PORT` / `VITE_API_URL` **before** the first deploy avoids a redeploy
(those values are baked at build/boot time). CLI deploys: `railway up --service
<name> --detach` from the repo root.

> Optional upgrade: if model artifacts grow large, swap the Postgres `bytea`
> artifact store for Cloudflare R2 — only `core/registry.py` changes.

`make deploy-help` prints this checklist.
<!-- End Railway deploy -->

---

## Engineering notes

- **Watch-time target, not clicks.** The ranker predicts watch fraction (per
  impression, 0 if not played) so it optimizes retention rather than clickbait.
- **Train/serve parity.** The ranker feature vector is defined once in
  `core/features/ranking.py` and used by both the training-matrix builder and the
  serving funnel — they can't drift.
- **Model artifacts in Postgres.** ALS factors + LightGBM booster + encoders +
  feature snapshots are serialized into `model_versions.artifact` (`bytea`).
  Serving scores ALS with a plain dot product, so there's no `implicit`
  dependency at serve time.
- **Determinism.** All mock data is seeded (`LENTA_SEED`) for reproducible demos.
- **Lazy / fast cold start.** Models load lazily; the api caches the active
  bundle and hot-reloads on a poll.
- **Honest metrics.** The **online A/B lift** (treatment vs popularity control) is
  the unbiased measure of value — typically **+40–50% CTR** and **+35–40%
  watch-fraction** in the simulator, because simulated users engage by latent
  affinity and the recommender surfaces better-matched content. Offline
  Recall@K/NDCG@K naturally *rise* across retrains as the system and user behavior
  co-adapt (a real recommender feedback-loop effect); we report both and treat the
  online A/B as ground truth.

## Tests

```bash
make test       # uv run pytest
```

Targeted tests cover: the funnel returns `k` items, cold-start users still get a
feed, re-rank diversity caps hold, eval metrics are in valid ranges, the model
bundle round-trips through bytes (and predictions are preserved), mock data is
deterministic with a learnable signal, and the registry round-trips an artifact
through Postgres (skipped if no DB is reachable).
