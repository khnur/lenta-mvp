# Lenta — 60-second reviewer quick-start

**Lenta is a working, deployed AI video-recommendation system.** You can operate
it yourself right now — no setup.

## Open these

- **Dashboard (live monitoring UI):** https://lenta-mvp.xyz
- **API + interactive docs:** https://api.lenta-mvp.xyz/docs
- **Source code:** https://github.com/khnur/lenta-mvp

## The 5-click demo (≈1 minute)

On the dashboard, use the **Scenario Controls** panel:

1. **Start** the simulation (rate ≈ 10) — synthetic users start flowing through
   the real recommender; the whole dashboard comes alive.
2. Look at the **A/B test** panel — the recommender (treatment) beats the
   "most-popular" baseline (control), most visibly on **watch-time**.
3. Click **genre_shift** (intensity 3–4) — a group of users suddenly prefers a
   new genre.
4. Click **Trigger retrain** — a new model trains and goes live in ~10 seconds.
5. Watch the **banner**, the **Model timeline**, and the **sample user's feed**
   all update — the system just learned and adapted, live.

## What you're looking at (5 panels)

1. **Live workflow** — the funnel (catalog → candidates → ranked → feed), a live
   feed, and an event ticker.
2. **Model timeline** — model quality across versions as it learns.
3. **A/B test** — recommender vs popularity, with the lift.
4. **Scenario controls** — the demo cockpit (used above).
5. **Pipeline status** — the backend stages running in real time.

## What makes it credible

- The complete production-shape funnel: collaborative-filtering retrieval →
  watch-time ranking → diversity/freshness re-rank.
- Real-time (Redis) + self-learning (retrain → registry → hot-swap) loops.
- Proven with a built-in A/B test; runs continuously with bounded resources.

See the full presentation and `docs/` for architecture, integration, and scaling.
