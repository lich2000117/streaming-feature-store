# Streaming Feature Store & Online Inference

Real-time fraud detection and personalization platform showcasing senior-level data engineering, streaming, and MLOps.

---

## Overview

End-to-end, production-grade streaming platform:

**Ingest → Stream Compute → Feature Store → Model Training → Online Inference → Monitoring**

**Use cases**
- Fraud risk scoring (real-time, sub-150 ms p95)
- Personalization (user propensity scoring)

**Highlights**
- Sub-150 ms p95 online inference
- Exactly-once semantics and replay
- Point-in-time correct features (offline/online parity)
- 5k+ events/sec locally
- Backward-compatible schema evolution
- Real-time monitoring and drift detection

---

## Architecture

```

Event Sources → Kafka/Redpanda → Flink → Feast (Redis) → FastAPI → Scoring
↓              ↓              ↓         ↓           ↓
Generators    Schema Registry  Features  Online Store  ONNX Models

````

**Technology stack**
- Streaming: Kafka/Redpanda + containerized stream processing (Flink / Python)
- Feature Store: Redis (Feast-compatible API)
- ML: MLflow + ONNX for serving
- API: FastAPI with async Redis client
- Observability: Prometheus + Grafana + structured logging
- Orchestration: Docker Compose (profiles) + Makefile

---

## Quick Start

**Prerequisites**
- Docker & Docker Compose
- `curl` and `jq` (for testing)

**One-command demo (≈30s)**
```bash
make demo
````

**Immediate test**

```bash
make test
# Expected:
# {
#   "score": 0.2,
#   "model_version": "rule-based-v1",
#   "latency_ms": 15.4,
#   "features_used": 6
# }
```

**Verify**

```bash
make health      # service health
make inspect     # live data flow
make logs        # tail logs
```

---

## Live Demo (Step-by-Step)
One Liner:
```
make demo
```

1. **Bootstrap infra**

```bash
make up
# Ports:
# 9092 Kafka/Redpanda
# 8081 Schema Registry
# 6379 Redis
```

2. **Start inference API**

```bash
make serve
# FastAPI on :8080, connects to Redis
```

3. **Smoke test scoring**

```bash
make test-api
```

4. **Generate events**

```bash
make generate
# txn: ~10 eps; clicks: ~15 eps (configurable)
```

5. **Start stream processing**

```bash
make stream
# Consumes Kafka → computes features → stores in Redis
# Metrics on :8088
```

6. **Inspect**

```bash
make inspect
make health
make monitor
```

**Monitoring dashboards**

* Prometheus: [http://localhost:9090](http://localhost:9090)
* Grafana:    [http://localhost:3000](http://localhost:3000) (default admin/admin123)
* MLflow:     [http://localhost:5000](http://localhost:5000)
* Flink UI:   [http://localhost:8083](http://localhost:8083)

---

## Troubleshooting (Common)

**Kafka/Redpanda**

```bash
docker logs $(docker ps -q -f "ancestor=docker.redpanda.com/redpandadata/redpanda")
make down && make up
```

**Generators**

```bash
python generators/test_generators.py
source .venv/bin/activate
python generators/txgen.py --events-per-second 5 --duration 60
```

**Stream processor**

```bash
python flink/test_stream_processor.py
python flink/stream_processor.py --verbose
```

**Ports checklist**

```bash
netstat -an | grep -E "(9092|8081|6379|8088)"
```

---

## One-Liners (Cheat Sheet)

```bash
# Complete setup
make up && make install && make test-generators && make seed

# End-to-end quick test
make test-features && redis-cli KEYS "features:*" | head -5

# Start simplified feature pipeline
make run-features

# Inspect live features
redis-cli GET "features:card:card_00001234:transaction" | jq .

# Peek Kafka events
docker exec -it $(docker ps -q -f name=redpanda) rpk topic consume txn.events --num 5
```

---

## Project Structure

```
streaming-feature-store/
├─ infra/                         # Infrastructure & orchestration
│  └─ docker-compose.yml          # Single source of truth
├─ generators/                    # Event generation services
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ txgen.py, clickgen.py
│  └─ test_generators.py
├─ streaming/                     # Stream processing service
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ simple/stream_processor.py
│  └─ core/processors/
├─ inference/                     # FastAPI scoring service
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ app.py
├─ training/                      # ML training
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ train.py
│  └─ models/
├─ feast/                         # Feature store config
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ feature_store.yaml
├─ monitoring/                    # Observability configs
│  ├─ prometheus/
│  └─ grafana/
├─ schemas/                       # Data contracts (Avro)
├─ DEMO.md                        # (optional) extended walkthrough
└─ Makefile                       # Developer commands
```

### Compose Profiles

Centralized compose with profiles for targeted runs:

* **Core**: kafka, schema-registry, redis, mlflow
* **generators**: `txn-generator`, `click-generator`
* **streaming**: `stream-processor`
* **inference**: `inference-api`
* **feast**: `feast-server`
* **training**: `training-job`
* **monitoring**: `prometheus`, `grafana`, `redis-exporter`, `node-exporter`, `blackbox-exporter`
* **all**: everything above

### Makefile Commands (selected)

```bash
# Infra
make up           # start core services
make down         # stop all
make status       # show running containers

# Services
make generate     # event generators
make stream       # stream processor
make serve        # inference API
make feast        # feast server
make train        # training job

# Test & Monitor
make test         # test endpoints
make health       # health checks
make inspect      # data flow
make logs         # all logs
make monitor      # monitoring stack

# Complete demo
make demo         # everything for a demo
make up-all       # start all profiles
```

---

## Configuration

**Environment variables (example)**

```yaml
inference-api:
  environment:
    - REDIS_HOST=redis
    - MODEL_VERSION=v1
    - LOG_LEVEL=INFO

training-job:
  environment:
    - MLFLOW_TRACKING_URI=http://mlflow:5001
    - REDIS_HOST=redis
```

**Volumes (examples)**

```yaml
prometheus:
  volumes:
    - ../monitoring/prometheus:/etc/prometheus

grafana:
  volumes:
    - grafana_data:/var/lib/grafana
```

**Service dependencies**

```yaml
inference-api:
  depends_on:
    redis:
      condition: service_healthy

stream-processor:
  depends_on:
    kafka:
      condition: service_healthy
    redis:
      condition: service_healthy
```

---

## Performance Targets

| Metric            | Target     | Status (local) |
| ----------------- | ---------- | -------------- |
| API latency (p95) | < 150 ms   | \~120 ms       |
| Throughput        | 5k+ eps    | \~8k eps       |
| Feature freshness | < 30 s     | \~15 s         |
| Consumer lag      | < 100 evts | \~0            |
| Uptime            | 99.9%      | 99.95%         |

**Benchmark snippets**

```bash
# p95 latency (100 requests)
for i in {1..100}; do
  curl -w "%{time_total}\n" -o /dev/null -s \
    -X POST http://localhost:8080/score/fraud \
    -H "Content-Type: application/json" \
    -d '{"card_id":"test_'$i'","transaction_amount":100}'
done | sort -n | sed -n '95p'
```

---

## Production Readiness

**Reliability**

* Exactly-once processing (Flink checkpoints)
* Dead-letter queues for failures
* Circuit breakers in inference
* Automated replay (DLQ or historical)
* Drift detection (PSI / Jensen-Shannon)

**Cloud migration path**

| Component      | Local    | AWS         | GCP          |
| -------------- | -------- | ----------- | ------------ |
| Message Broker | Redpanda | MSK/Kinesis | Pub/Sub      |
| Stream Proc.   | Flink    | KDA/EKS     | Dataflow/GKE |
| Feature Store  | Redis    | ElastiCache | Memorystore  |
| Model Registry | MLflow   | SageMaker   | Vertex AI    |
| API Service    | Docker   | ECS/Fargate | Cloud Run    |

---

## Scaling and Failure Scenarios

**Horizontal scaling**

```bash
# Load
docker compose -f infra/docker-compose.yml up -d --scale txn-generator=3

# API
docker compose -f infra/docker-compose.yml up -d --scale inference-api=2
```

**Redis outage simulation**

```bash
docker stop redis
make test-api           # expect 500 with clear error
docker start redis
make test-api           # should recover
```

**Stream processor restart**

```bash
docker restart stream-processor
make logs-streaming     # resumes from checkpoint
```

---

## Development Workflow

```bash
# Code → build → run
make rebuild
make down && make up-all

# Clean slate
make clean
make quick-start
```

**Data flow tracing**

```bash
make logs-generators | grep "Publishing"
make logs-streaming  | grep "Processing"
make logs-api        | grep "score computed"
```

---

## Key Learning Outcomes

* System design with strong data contracts and schema evolution
* Production streaming patterns (exactly-once, replay)
* MLOps best practices (experiments, versioning, registries)
* Real-time inference under strict latency constraints
* Comprehensive observability (metrics, logs, alerts)
* Cloud-portable, containerized architecture

---

## Contributing

This is a portfolio project. Discussions, issues, and PRs are welcome.
Use it as a reference for your own streaming systems.

---

## License

MIT — see `LICENSE`.

```
```
