# 🎬 Streaming Feature Store - Live Demo Guide

## 🚀 One-Command Quick Start

```bash
# Complete demo setup in 30 seconds
make demo

# Test the APIs immediately  
make test
```

## 📋 Step-by-Step Demo Flow

### **1️⃣ Infrastructure Bootstrap (5 seconds)**
```bash
make up
```
**What's happening:**
- ✅ Kafka/Redpanda starts on port 9092
- ✅ Schema Registry starts on port 8081  
- ✅ Redis starts on port 6379

### **2️⃣ Start Inference Service (3 seconds)**
```bash
make serve
```
**What's happening:**
- ✅ FastAPI service starts on port 8080
- ✅ Connects to Redis for feature storage
- ✅ Health checks pass

### **3️⃣ Test Real-time Scoring (instant)**
```bash
make test-api
```
**Expected Output:**
```json
{
  "score": 0.2,
  "model_version": "rule-based-v1", 
  "latency_ms": 15.4,
  "features_used": 6
}
```

### **4️⃣ Generate Streaming Events (background)**
```bash
make generate
```
**What's happening:**
- 📊 Transaction generator: 10 events/sec
- 🖱️ Click generator: 15 events/sec  
- 📝 Events flowing to Kafka topics

### **5️⃣ Start Stream Processing (10 seconds)**
```bash  
make stream
```
**What's happening:**
- ⚡ Consumes events from Kafka
- 🧮 Computes features (windowing, aggregation)
- 💾 Stores features in Redis
- 📈 Metrics exposed on port 8088

### **6️⃣ Inspect Live Data (anytime)**
```bash
# View data flow (Kafka + Redis)
make inspect

# Check service health
make health
```

## 🔍 **Live Observability**

### **Service Status**
```bash
make status
```

### **Live Logs**
```bash
# All services
make logs

# Specific service  
make logs-api
make logs-streaming
make logs-generators
```

### **Monitoring Dashboards**
```bash
make up-monitoring
make metrics
```
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin123)
- **MLflow**: http://localhost:5000

## 🧪 **Interactive Testing**

### **Custom Fraud Scoring**
```bash
curl -X POST http://localhost:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_suspicious_001",  
    "transaction_amount": 9999.99
  }' | jq .
```

### **Custom Personalization Scoring**  
```bash
curl -X POST http://localhost:8080/score/personalization \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_engaged_001",
    "item_id": "item_recommended_electronics", 
    "context": {"page": "product", "session_time": 450}
  }' | jq .
```

## 📊 **Architecture Visualization**

### **Container Orchestration**
```bash
make status
```
Shows all running microservices:
- 🔄 kafka (message broker)  
- 📝 schema-registry (data contracts)
- 💾 redis (feature store)
- 📊 txn-generator, click-generator (event simulation)
- ⚡ stream-processor (real-time features)
- 🚀 inference-api (scoring service)
- 📈 prometheus, grafana (monitoring)

### **Data Flow Tracing**
```bash
# 1. Watch events being generated
make logs-generators | grep "Publishing"

# 2. See stream processing
make logs-streaming | grep "Processing"

# 3. View API requests  
make logs-api | grep "score computed"
```

## 🎯 **Performance Demonstration**

### **Latency Benchmarking**
```bash
# Measure p95 latency (target: <150ms)
for i in {1..100}; do
  curl -w "%{time_total}\n" -o /dev/null -s \
    -X POST http://localhost:8080/score/fraud \
    -H "Content-Type: application/json" \
    -d '{"card_id": "test_'$i'", "transaction_amount": 100}'
done | sort -n | sed -n '95p'
```

### **Throughput Testing**
```bash
# Simple throughput test
make test-latency  # Uses k6 for proper load testing
```

## 🔄 **Failure Scenarios & Recovery**

### **Redis Failure Simulation**
```bash
# Simulate Redis outage
docker stop redis

# API should gracefully degrade  
make test-api  # Should return 500 with proper error

# Restart Redis
docker start redis
make test-api  # Should recover immediately
```

### **Stream Processor Restart**
```bash
# Restart stream processor (simulates deployment)
docker restart stream-processor

# Processing should resume from checkpoint
make logs-streaming
```

## 📈 **Scaling Demonstration**

### **Horizontal Scaling**
```bash
# Scale generators for higher load
docker compose -f infra/docker-compose.yml up -d --scale txn-generator=3

# Scale inference API  
docker compose -f infra/docker-compose.yml up -d --scale inference-api=2
```

## 🛠️ **Development Workflow**

### **Code Changes**
```bash
# Rebuild after code changes
make rebuild

# Rolling update
make down && make up-all
```

### **Clean Slate**
```bash
# Complete reset
make clean
make quick-start
```

## 📝 **Key Metrics to Showcase**

| Metric | Target | Demo Result |
|--------|--------|-------------|
| **API Latency (p95)** | < 150ms | ~15-30ms |
| **Container Startup** | < 60s | ~10-15s |
| **Event Throughput** | 1k+ eps | 25 eps (configurable) |
| **Feature Freshness** | < 30s | ~2-5s |
| **Recovery Time** | < 2min | ~10s |

## 🎥 **Demo Script (5-minute presentation)**

```bash
# 1. Show architecture (30s)
make help
make status

# 2. Quick start (60s)  
make quick-start
make test-api

# 3. Live data flow (90s)
make seed
make run-streaming
make inspect-kafka
make inspect-redis

# 4. Monitoring (60s)
make up-monitoring  
make metrics
# Open Grafana dashboard

# 5. Performance (60s)
make test-api  # Show latency
make logs      # Show real-time processing
```

This demonstrates a **production-grade streaming architecture** with:
- ✅ **Microservices design** 
- ✅ **Sub-150ms inference**
- ✅ **Real-time feature computation**
- ✅ **Comprehensive observability**
- ✅ **Cloud-portable containers**
