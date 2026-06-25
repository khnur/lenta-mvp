# Integrating Lenta into your platform

Lenta is **API-first**: a real media platform adopts it by pointing its app at
Lenta's REST API. There is no rip-and-replace — you keep your stack and call
Lenta for feeds, and send it user events. This guide shows exactly how.

Live reference API + interactive docs: **https://api.lenta-mvp.xyz/docs**

---

## The integration in one picture

```
        your apps / player                         Lenta
   ┌──────────────────────┐   GET /feed?user_id   ┌────────────────────────┐
   │  web / mobile / TV    │ ────────────────────▶ │  api  (FastAPI)         │
   │  home · browse · next │ ◀──────────────────── │  funnel → ranked feed   │
   │                       │     ranked videos      │                        │
   │  video player         │   POST /event          │  trainer (self-learns) │
   │  (impression/click/   │ ────────────────────▶ │  Postgres + Redis       │
   │   play + watch-time)  │                        │  model registry         │
   └──────────────────────┘                         └────────────────────────┘
```

You integrate at **two touch-points**: render feeds from `GET /feed`, and stream
behavior into `POST /event`. Everything else (training, model swaps, metrics) is
automatic.

---

## Step 1 — Bring your content and users

Map your domain objects onto Lenta's schema (one-time load, then keep in sync):

| Your data | Lenta field | Notes |
|---|---|---|
| Video id | `videos.id` | stable integer id |
| Title | `videos.title` | |
| Creator / channel | `videos.creator_id` | used for diversity caps |
| Genres / categories | `videos.genres` (list) | the core taste signal |
| Tags | `videos.tags` (list) | optional |
| Duration | `videos.duration_seconds` | drives watch-fraction |
| Publish time | `videos.upload_time` | drives the freshness boost |
| User id | `users.id` | stable integer id |

Replace the mock-data generators (`core/mock/*`) with a loader that reads your
catalog/CMS and user directory. On **publish** and **signup**, upsert the new
row so the catalog and audience stay current. (New videos/users are handled by
the cold-start fallbacks until the next retrain learns them.)

## Step 2 — Stream behavior (the fuel)

This is the most important integration. From your player/front-end/back-end,
send one event per interaction:

```http
POST /event
{
  "user_id": 12345,
  "video_id": 987,
  "event_type": "play",          // impression | click | play
  "session_id": "web-abc123",
  "watch_seconds": 142.0,
  "watch_fraction": 0.78          // how much of the video was watched
}
```

- **impression** — the video was shown (the `/feed` call logs these for you).
- **click** — the user opened it.
- **play** — the user watched it; include `watch_seconds` / `watch_fraction`.

Watch-time is what the ranker optimizes, so capturing `watch_fraction` accurately
is the single highest-leverage thing you can do.

## Step 3 — Render personalized feeds

Call the funnel wherever you show recommendations (home, browse rails, "up next"):

```http
GET /feed?user_id=12345&k=20
→ { "items": [ {id,title,genres,score,stage}, ... ],
    "funnel": { catalog, candidates, ranked, feed, retrieval } }
```

Render `items` in order. The `funnel` block is optional debug you can log or
ignore. For very high read volume, cache a user's feed for a short TTL (see
[SCALING.md](./SCALING.md)).

## Step 4 — Let it learn (automatic)

The `trainer` retrains on your accumulating events on a schedule
(`RETRAIN_INTERVAL_MINUTES`), evaluates each model, writes a new version to the
Postgres registry, and the API hot-swaps to it with **zero downtime**. You can
also trigger a retrain on demand (`POST /retrain`). No manual steps.

## Step 5 — Roll out safely with the built-in A/B test

Lenta assigns each user a **sticky** variant — `treatment` (recommender) or
`control` (popularity). Start with a small treatment share, watch the **lift**
on `GET /metrics` (CTR, watch-time, session length), and ramp up with confidence.
Force a variant per call with `&variant=treatment|control` for testing.

---

## Deployment patterns

**A) Sidecar microservice (recommended).** Deploy Lenta's `api` + `trainer` +
Postgres + Redis next to your platform (Docker Compose, Kubernetes, or Railway —
a one-project layout is provided). Your app talks to it over HTTP. Lowest
coupling, independent scaling, language-agnostic.

**B) Embedded library.** Import the `lenta_core` Python package directly into
your own Python services and call `recommend(...)` / the training functions in
process. Tighter coupling, no network hop.

## Security & operations

- **Auth:** Lenta's API is an internal service — put it behind your API gateway
  with API keys / JWT / mTLS and rate limits. Don't expose `/event` or the
  control plane (`/retrain`, `/sim/*`, `/reset`) publicly.
- **Health & metrics:** every service exposes `/health`; scrape `/metrics` and
  `/pipeline/status` for dashboards and alerting.
- **Bring your own models:** your data scientists can serialize a custom model
  into the same registry and get the same hot-swap + A/B machinery for free.

## Suggested phased migration

1. **Shadow mode** — log events and generate feeds, but don't display them.
   Validate quality offline against your held-out behavior.
2. **Canary A/B** — show Lenta feeds to 5–10% of users; compare watch-time vs
   your current system.
3. **Ramp** — 50/50, then full rollout, keeping a small permanent control
   holdout so you can always quantify Lenta's ongoing contribution.

---

See **[SCALING.md](./SCALING.md)** for taking this from thousands to millions of
users.
