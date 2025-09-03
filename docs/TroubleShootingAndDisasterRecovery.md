
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

**Data flow tracing**

```bash
make logs-generators | grep "Publishing"
make logs-streaming  | grep "Processing"
make logs-api        | grep "score computed"
```