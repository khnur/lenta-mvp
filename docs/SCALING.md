# Scaling Lenta to thousands → millions of users

The MVP runs as a single instance, but its architecture is the **same
multi-stage funnel** (candidate generation → ranking → re-rank) that Netflix,
YouTube and Amazon use to serve billions of recommendations a day. That means
scaling follows well-trodden, low-risk paths — each stage upgrades independently
without touching the others.

This guide maps **where Lenta is today → what changes at scale**, in priority
order.

---

## At a glance

| Component | MVP today | At scale (10k → 10M+ users) |
|---|---|---|
| **API serving** | single instance, in-process model cache | N stateless replicas behind a load balancer + autoscaling |
| **Candidate generation** | ALS scored over the full catalog per request | Two-tower embeddings + **ANN index** (FAISS / ScaNN / HNSW / pgvector) — top-K in <10 ms over 100M+ items |
| **Ranking** | LightGBM over a few hundred candidates (sub-ms) | same, batched; optional GPU L2 ranker for depth |
| **Session features** | Redis, updated per event | Redis cluster / managed feature store (Feast, ElastiCache) |
| **Event ingestion** | synchronous `POST /event` → Postgres insert | **Kafka / Redpanda / Kinesis** stream → consumers update Redis + batch-write store |
| **Event store** | Postgres (auto-pruned) | time-partitioned Postgres + read replicas, or ClickHouse / BigQuery for analytics |
| **Model artifacts** | Postgres `bytea` | object storage (S3 / Cloudflare R2) — the registry already abstracts the store |
| **Training** | single worker, recency-weighted, event-capped | scheduled / distributed training box; incremental updates for freshness |
| **Feeds** | computed per request | short-TTL feed cache + precompute for power users |

---

## 1. Scale serving horizontally (easiest, biggest win)

The `api` is **stateless** — all session state lives in Redis, the model lives in
the registry. So you simply run **N replicas behind a load balancer**; each
caches the active model and hot-reloads when a new version is published. Add
autoscaling on CPU/RPS (Kubernetes HPA, or Railway replicas). Throughput scales
roughly linearly with replicas.

## 2. Candidate generation: full-scan → ANN index

Today ALS computes a dot product against every catalog item per request — fine
for thousands of items, too slow for tens of millions. The industry-standard
upgrade:

- Precompute **item embeddings** (evolve ALS → a **two-tower** model so the user
  and item encoders share an embedding space — the user tower runs online, items
  are precomputed).
- Serve candidate retrieval from an **approximate-nearest-neighbor index**
  (FAISS with IVF+PQ, ScaNN, HNSW, `pgvector`, or a managed vector DB). Top-K
  retrieval drops to **sub-10 ms over 100M+ items**.

This is a drop-in replacement for the retrieval stage; ranking and re-rank are
untouched. Keep ALS/content/popularity as fallbacks.

## 3. Ranking already scales

LightGBM scores a few hundred candidates in **sub-millisecond** time; batch the
scoring and cap the candidate count to bound tail latency. When you want a
heavier model, add it as an **L2 re-ranker** on the top-N only (the classic
cheap-L1 → expensive-L2 cascade), optionally on GPU.

## 4. Cache the read path

- **Feed cache:** cache each user's feed in Redis with a short TTL; serve from
  cache, recompute on expiry or on a strong real-time signal. Precompute feeds
  for the most active users off the request path.
- **Popularity / trending** is cheap to precompute and cache globally.

## 5. Ingest events as a stream, not synchronous inserts

Replace synchronous `POST /event` → Postgres with a **streaming pipeline**
(Kafka / Redpanda / Kinesis). Consumers:

1. update **Redis session features** in real time (the online loop), and
2. **batch-write** to the durable event store.

This decouples traffic spikes from serving latency and gives you a replayable
log for backfills and new features.

## 6. Data tier

- **Online features:** keep them in Redis / a feature store (Feast) so serving is
  a fast lookup, not a recompute.
- **Event log:** time-partition the Postgres `events` table and add read
  replicas; for heavy analytics, ship events to a columnar store (ClickHouse /
  BigQuery). Lenta already auto-prunes the operational tables so the serving DB
  stays lean.

## 7. Model artifacts & training

- Move large artifacts from Postgres `bytea` to **object storage (S3 / R2)** —
  the registry (`core/registry.py`) is the only thing that changes.
- Run training on a dedicated box (or distributed) on a schedule; the
  recency-weighting + event cap keep each retrain bounded regardless of volume.
  Add **incremental / online updates** when you need minute-level freshness.
- The `trainer` is a **singleton** (leader-elected) — serving scales out
  independently of training.

## 8. Reliability & observability

- Export Prometheus metrics + traces; alert on the **A/B lift** and pipeline
  stage health.
- **Canary every model** through the built-in A/B before full rollout — bad
  models are caught by the lift metric, not by users.
- Keep a permanent small **control holdout** to continuously quantify value.

---

## Rough capacity model

- A single `api` replica serves on the order of **hundreds of feed requests/sec**
  today (retrieval + rank ≈ 10 ms each); replicas scale that linearly into the
  thousands/sec.
- With ANN retrieval + feed caching, p99 feed latency stays in the low tens of
  milliseconds at millions of users.
- Postgres/Redis are sized to event throughput; the streaming + pruning design
  keeps the serving database small and fast regardless of total history.

The point: **none of these are rewrites.** Each is a localized upgrade to one
stage of a funnel that is already the production-standard shape.

## Sources / further reading

- Two-tower retrieval at scale — Google Cloud Architecture Center
- FAISS (Meta), ScaNN (Google), HNSW — ANN libraries for candidate retrieval
- Streaming recommendation pipelines with Kafka
- Feature stores (Feast) for online serving
