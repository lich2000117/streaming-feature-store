
# Project: Streaming Feature Store & Online Inference (Fraud + Personalisation)


## 0) Why this wins (ROI)

* Shows **end-to-end ownership**: ingest → stream compute → feature store → model train → online inference → monitoring.
* Signals **senior judgement**: data contracts, schema evolution, exactly-once, replay, SLAs, drift, A/B rollout.
* Maps cleanly to **big-tech system design** and to product teams (risk, growth, recsys).

---

## 1) Business framing

* **Use cases**:

  1. **Fraud risk** for payments (score = probability of fraud).
  2. **Personalisation** (propensity/re-ranking for banners or products).
* **Goal**: sub-150 ms p95 online scoring, **exactly-once** stream features, and **replayable** history.
* **KPIs**: latency p95, feature freshness, drift alerts, A/B deltas.

---

## 2) Success criteria

* **Throughput**: ≥ 5k events/sec locally; document how to scale to 50k+.
* **Latency**: end-to-end (event → score) **p95 ≤ 150 ms**.
* **Correctness**: point-in-time feature reads; **exactly-once** writes to online store.
* **Ops**: replay in < 10 min for 1 hour of data; consumer lag alerting; DLQ < 0.1%.

---

## 3) High-level architecture (local first, cloud-ready)

* **Producers**: synthetic **transactions** + **clickstream** generators.
* **Broker**: Kafka or Redpanda (local), Schema Registry.
* **Stream compute**: **Flink** (features, joins, windows, DLQ handling).
* **Feature store**: **Feast** (offline: Parquet/BigQuery; online: **Redis**).
* **Model**: trained offline (scikit-learn/XGBoost), tracked in **MLflow**, exported to **ONNX**.
* **Online inference**: **FastAPI** microservice → fetch features from Redis → run model → return score.
* **Observability**: Prometheus + Grafana; Flink metrics; consumer-lag exporter; drift monitors.
* **Control plane**: Makefile + `docker-compose` for local; k8s manifests optional.

Cloud mapping (documented):

* **GCP**: Pub/Sub ↔ Kafka, Dataflow/Beam ↔ Flink, BigQuery, Cloud Run, Vertex AI, Memorystore.
* **AWS**: MSK/Kinesis, Glue/KDA ↔ Flink, DynamoDB/S3, Lambda/Fargate, SageMaker, ElastiCache.

---

## 4) Data contracts & topics 

**Contracts (Avro/Protobuf)** with backward-compatible evolution:

* `transactions.v1` (key = `card_id`): `txn_id`, `card_id`, `user_id`, `amount`, `currency`, `mcc`, `device_id`, `ip`, `geo`, `timestamp`.
* `clicks.v1` (key = `user_id`): `event_id`, `user_id`, `page`, `item_id`, `referrer`, `device_id`, `timestamp`.
* `devices.v1` (key = `device_id`): fingerprint hash, os, browser, `timestamp`.

**Topic design**

* `txn.events` (12–24 partitions; key by `card_id` for state locality).
* `click.events` (12–24 partitions; key by `user_id`).
* `device.enrich` (6–12 partitions; key by `device_id`).
* `*_dlq` for each stream.
* Retention: hot (7 days), compacted snapshots for upsert topics where needed.

---

## 5) Streaming features (Flink job design)

**Operators (per keyed stream):**

* Event-time + **watermarks** (bounded out-of-orderness, e.g. 2 minutes).
* **Windows**:

  * Count of txns in last **5m/30m/24h** (tumbling + sliding).
  * Sum/avg amount in last **5m**.
  * **Geo/device mismatch rate** in last **N** events.
  * **Time since last txn** (stateful timer).
  * Clickstream session features: pages/session, dwell time.
* **Joins**: `transactions` ⟵(`device_id`)⟶ `devices` (interval join with state TTL).
* **Late events**: allowed lateness (e.g., 1 minute). Very late → **DLQ**.
* **State backend**: RocksDB; checkpoints every 30s; exactly-once sinks; externalized checkpoints for replay.
* **Upserts** to **Feast online** via Redis sink; idempotent writes (feature row key = entity + feature set + event\_time).

**Feature definitions (Feast)**

* Entities: `card_id`, `user_id`, `device_id`.
* Example feature view: `txn_stats_5m` (`count_5m`, `sum_5m`, `avg_5m`, `geo_mismatch_ratio_5m`).

---

## 6) Offline training & parity

* **Backfill**: use the same Flink codepath to write **offline feature logs** (Parquet) to `/data/offline_features/…` (or BigQuery).
* **Training notebook**:

  * Label fraud with simple rules or injected anomalies.
  * Train LR/XGB; calibrate; evaluate (PR/AUC).
  * Log to **MLflow** (`v1` baseline, `v2` improved).
* **Feature parity test**: point-in-time correctness join (Feast `get_historical_features`) vs online Redis snapshot for an entity/time—assert differences < threshold.

---

## 7) Online inference service (FastAPI)

* **Endpoint**: `POST /score` with `card_id` (fraud) **or** `user_id` + `context` (recs).
* **Flow**: fetch latest features from Redis (TTL-aware) → load ONNX model (on startup; version via env) → score → return `{score, model_version, latency_ms}`.
* **A/B or canary**: header `X-Model-Version` or 90/10 traffic split internally.
* **Budgets**: enforce max qps & timeout; circuit break to baseline rules if feature fetch fails.

---

## 8) Observability & governance

* **Metrics**:

  * Flink: checkpoint duration/failures, busy time, backpressure, records/sec, watermark lag.
  * Kafka: consumer lag per group/partition.
  * API: p50/p95 latency, RPS, error rate.
* **Drift**: PSI/JS divergence daily on key features; alert if > threshold.
* **DLQ workflow**: sample + reason code; `make replay` to re-ingest fixed payloads.
* **Schema evolution**: demo `transactions.v2` adding `merchant_id`; prove compatibility + codepath that ignores unknown fields.

---

## 9) Reliability & replay story

* **Exactly-once**: Flink checkpoints + transactional/commit sinks to Feast/Redis (or idempotent `SET` with versioned timestamps).
* **Backfill**: From Parquet to online store with time fences so you don’t pollute freshness.
* **Disaster drill**: nuke Redis; **rebuild features** from compacted topics + offline logs with a single command.


---

## 11) Commands (make it one-click runnable)

* `make up` → bring up infra.
* `make seed` → start generators.
* `make run-features` → submit Flink job.
* `make train` → train + log model to MLflow.
* `make serve` → run FastAPI.
* `make test-latency` → k6/locust tests.
* `make drift-check` → compute PSI.
* `make replay file=…` → DLQ replay.

---

## 12) What screenshot in the README

* Grafana panel: **consumer lag \~0**, **Flink p95 < 50 ms**, API **p95 < 150 ms**.
* Feast materialization logs + point-in-time validation output.
* MLflow UI with `v1` vs `v2`.
* Example `POST /score` result.
* Drift chart before/after simulated shift.

---



It’s:

* **Pure local + easy to run** (Docker Compose): Redpanda/Kafka, Schema Registry, Flink, Redis/Feast, MLflow, FastAPI, Prometheus/Grafana. One command to bring it up, one to seed events, one to submit the Flink job.
* **Deep-under-the-hood learning**: you’ll touch partitions/keys, watermarks, state (RocksDB), checkpointing, exactly-once sinks, schema evolution, DLQs, replay, feature freshness—the real machinery senior interviews probe on.
* **Cloud-portable**: the same abstractions map cleanly to AWS/GCP. You swap infra, keep contracts and jobs.

### Local → Cloud mapping (drop-in mental model)

| Capability           | Local (Compose)      | AWS                                                                 | GCP                                      |
| -------------------- | -------------------- | ------------------------------------------------------------------- | ---------------------------------------- |
| Event bus            | Redpanda/Kafka       | MSK (or Kinesis\*)                                                  | Pub/Sub                                  |
| Schema registry      | Confluent SR         | Glue Schema Registry                                                | Pub/Sub schemas / SR on Confluent Cloud  |
| Stream compute       | Flink                | Kinesis Data Analytics for Apache Flink / self-managed Flink on EKS | Dataflow (Beam) or Flink on GKE          |
| Online features (KV) | Redis                | ElastiCache (Redis) / DynamoDB                                      | Memorystore (Redis) / Firestore          |
| Offline store        | Parquet on disk      | S3                                                                  | GCS                                      |
| Model registry       | MLflow (local)       | SageMaker Model Registry / MLflow on EC2/EKS                        | Vertex AI Model Registry / MLflow on GKE |
| Inference service    | FastAPI (Docker)     | ECS/Fargate or Lambda + API Gateway                                 | Cloud Run / GKE + Serverless NEG         |
| Metrics              | Prometheus + Grafana | CloudWatch + Managed Grafana                                        | Cloud Monitoring + Managed Grafana       |

\*If you choose Kinesis instead of Kafka: re-think partitioning/consumer groups, but the concepts transfer.

### Make cloud moves trivial (bake these in now)

* **12-factor everything**: all endpoints/creds as env vars; no hardcoded hosts.
* **Contracts first**: Avro/Proto in `/schemas` + compatibility rules—portable to Glue/Confluent/Vertex.
* **Idempotent sinks**: versioned feature timestamps or transactional sinks → makes exactly-once portable.
* **Replay tooling**: a `make replay` that reads from DLQ/Parquet → works on S3/GCS with the same code path.
* **IaC-ready**: keep k8s manifests and a minimal Terraform skeleton so you can show “here’s how I’d lift-and-shift”.

### Use it for “literally anything” (a few quick remixes)

* **Real-time log analytics**: ship app logs → Kafka; Flink parses and aggregates; store features like error-rate(1m/5m); alerts via webhook; optional LLM to summarise incidents.
* **Clickstream personalisation**: same framework; change schemas + feature views; add re-ranker service.
* **IoT anomaly detection**: MQTT/HTTP ingest → Kafka; Flink rolling z-scores/isolation forest; push alerts; store device features online.
* **Ops telemetry**: Kafka → Flink → Prometheus remote-write or Elasticsearch; dedupe + incident bucketing.

It’s the **same bones**: contracts → streaming features → online store → inference → monitoring → replay.

### “I really get it” checklist (what to focus on while building)

* **Keys/partitions**: choose keys for state locality (e.g., `card_id`); size partitions; rebalancing impact.
* **Event time vs processing time**: watermarks, late data strategy, allowed lateness → DLQ.
* **State & exactly-once**: RocksDB state backend, checkpoints, externalized checkpoints; idempotent upserts.
* **Schema evolution**: add `merchant_id` in `transactions.v2` with backward compatibility; prove consumers survive.
* **Feature freshness & point-in-time**: prove parity between offline historical features and online Redis for the same timestamp.
* **Replay**: wipe Redis, rebuild from compacted topics + offline logs; measure time to recovery.
* **SLOs**: document p95 for API, consumer lag, end-to-end latency; show dashboards.

### Minimal conversion steps

1. **Lift compute**: containerize Flink job and inference service → deploy to Cloud Run/ECS/Fargate first (simplest).
2. **Swap data plane**: Kafka → Pub/Sub/MSK; update client libs + credentials; keep schemas.
3. **Swap stores**: local Parquet → S3/GCS; Redis → ElastiCache/Memorystore.
4. **Plug observability**: export Prometheus metrics to Managed Grafana/CloudWatch/Cloud Monitoring.

