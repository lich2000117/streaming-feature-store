# FastAPI Inference Service

Production-grade real-time ML inference service for fraud detection and personalization with sub-150ms latency targets.

## Architecture Overview

The inference service is built with a modular, senior-level architecture:

```
├── config.py          # Configuration management with environment support
├── schemas.py          # Pydantic request/response models with validation
├── features.py         # Redis feature store client with caching
├── models.py           # ML model loading and inference (sklearn/ONNX)
├── app.py             # FastAPI application with monitoring
├── Dockerfile         # Production container build
├── requirements.txt   # Python dependencies
└── README.md          # This documentation
```

## Key Features

### 🚀 Performance
- **Sub-150ms p95 latency** for real-time scoring
- **Batch inference** support for high-throughput scenarios
- **Feature caching** with Redis client-side caching
- **ONNX runtime** support for optimized inference
- **Connection pooling** for Redis feature store

### 🔒 Production Ready
- **Comprehensive monitoring** with Prometheus metrics
- **Health checks** for load balancer integration
- **Structured logging** with request tracing
- **Error handling** with proper HTTP status codes
- **Input validation** with Pydantic schemas
- **Security** with non-root Docker user

### 🧠 ML Integration
- **Multiple model types** (XGBoost, LightGBM, scikit-learn)
- **Model versioning** and A/B testing support
- **Feature importance** and model explainability
- **Automatic fallbacks** for missing features
- **Model hot-swapping** capabilities

### 📊 Observability
- **Request tracing** with unique request IDs
- **Performance metrics** (latency, throughput, errors)
- **Feature freshness** monitoring
- **Cache hit rates** and Redis health
- **Model prediction distributions**

## API Endpoints

### Core Scoring Endpoints

#### POST `/score/fraud`
Real-time fraud detection scoring.

**Request:**
```json
{
  "card_id": "card_00001234",
  "transaction_amount": 150.0,
  "merchant_id": "merchant_12345",
  "mcc_code": "5411",
  "country_code": "US"
}
```

**Response:**
```json
{
  "fraud_score": 0.15,
  "risk_level": "low",
  "confidence": 0.85,
  "recommended_action": "approve",
  "explanation": "Transaction appears legitimate with low risk indicators",
  "top_risk_factors": ["velocity_check", "geo_pattern"],
  "features_used": 16,
  "latency_ms": 45.2,
  "model_version": "v1.0",
  "feature_freshness_sec": 12
}
```

#### POST `/score/personalization`
Real-time personalization and recommendation scoring.

**Request:**
```json
{
  "user_id": "user_00005678",
  "item_id": "item_electronics_001",
  "item_category": "electronics",
  "item_price": 299.99,
  "session_id": "session_abc123"
}
```

**Response:**
```json
{
  "relevance_score": 0.78,
  "conversion_probability": 0.12,
  "engagement_score": 0.85,
  "user_segment": "high_value_engaged",
  "behavioral_signals": ["high_engagement_session", "multi_page_session"],
  "features_used": 12,
  "latency_ms": 38.5,
  "model_version": "v1.0"
}
```

#### POST `/score/batch`
Batch scoring for multiple requests.

**Request:**
```json
{
  "model_type": "fraud_detection",
  "requests": [
    {"card_id": "card_1", "transaction_amount": 100},
    {"card_id": "card_2", "transaction_amount": 500}
  ],
  "batch_id": "batch_20240902_001"
}
```

### Monitoring Endpoints

#### GET `/health`
Comprehensive health check with component status.

#### GET `/ready`
Kubernetes readiness probe endpoint.

#### GET `/metrics`
Prometheus metrics in standard format.

#### GET `/models`
List available models and their metadata.

## Configuration

The service uses environment-based configuration with sensible defaults:

### Core Configuration
```bash
# Model paths
MODEL_PATH=training/outputs/model.pkl
FEATURE_NAMES_PATH=training/outputs/feature_names.json
ONNX_MODEL_PATH=training/outputs/model.onnx

# Redis feature store
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

# API settings
API_HOST=0.0.0.0
API_PORT=8080
LOG_LEVEL=INFO

# Performance
USE_ONNX=false
FEATURE_CACHE_TTL=300
```

### Advanced Configuration
All configuration is managed through the `InferenceConfig` class with validation:

- **Redis settings**: Connection pooling, timeouts, health checks
- **Model settings**: ONNX runtime, batch sizes, thresholds
- **API settings**: CORS, rate limiting, request timeouts
- **Monitoring**: Metrics collection, alerting thresholds

## Metrics and Monitoring

### Prometheus Metrics

The service exposes comprehensive metrics for production monitoring:

#### Request Metrics
- `inference_requests_total` - Total requests by endpoint and status
- `inference_request_duration_seconds` - Request latency distribution
- `inference_active_requests` - Current active requests

#### Feature Store Metrics
- `feature_fetch_duration_seconds` - Feature retrieval latency
- Cache hit rates and Redis connection health

#### Model Metrics
- `model_inference_duration_seconds` - Model inference time
- `prediction_scores` - Distribution of prediction scores
- Feature importance and model confidence scores

#### Error Metrics
- `inference_errors_total` - Error counts by type and endpoint

### Alerting Thresholds

**Production SLAs:**
- p95 latency < 150ms
- p99 latency < 300ms
- Error rate < 1%
- Feature freshness < 5 minutes

## Deployment

### Docker Build
```bash
docker build -f inference/Dockerfile -t inference-api:latest .
```

### Docker Run
```bash
docker run -p 8080:8080 \
  -e REDIS_HOST=localhost \
  -e MODEL_PATH=training/outputs/model.pkl \
  inference-api:latest
```

### Docker Compose (Production)
```yaml
services:
  inference-api:
    build:
      context: .
      dockerfile: inference/Dockerfile
    ports:
      - "8080:8080"
    environment:
      - REDIS_HOST=redis
      - LOG_LEVEL=INFO
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inference-api
  template:
    metadata:
      labels:
        app: inference-api
    spec:
      containers:
      - name: inference-api
        image: inference-api:latest
        ports:
        - containerPort: 8080
        env:
        - name: REDIS_HOST
          value: "redis-service"
        - name: LOG_LEVEL
          value: "INFO"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot reload
uvicorn app:app --host 0.0.0.0 --port 8080 --reload

# Test API
curl -X POST http://localhost:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{"card_id": "card_00001234", "transaction_amount": 150.0}'
```

### Testing
```bash
# Unit tests
python -m pytest tests/

# Load testing
k6 run loadtest/inference_load_test.js

# Performance profiling
python -m cProfile -o inference.prof app.py
```

## Performance Optimization

### Latency Optimization
1. **Feature Caching**: Client-side Redis caching with TTL
2. **Connection Pooling**: Persistent Redis connections
3. **ONNX Runtime**: Optimized model inference
4. **Batch Processing**: Vectorized operations where possible
5. **Async Operations**: Non-blocking I/O for concurrent requests

### Scaling Strategies
1. **Horizontal Scaling**: Multiple API instances behind load balancer
2. **Model Sharding**: Different models for different traffic patterns
3. **Feature Precomputation**: Reduce real-time computation
4. **CDN Integration**: Cache responses for deterministic inputs
5. **Auto-scaling**: Kubernetes HPA based on latency/CPU metrics

## Security Considerations

### Production Security
- **Non-root containers** with minimal attack surface
- **Input validation** with Pydantic schemas
- **Rate limiting** to prevent abuse
- **CORS configuration** for web integration
- **Health check endpoints** without sensitive data
- **Structured logging** without PII exposure

### Network Security
- **TLS termination** at load balancer
- **VPC isolation** for Redis and model storage
- **IAM roles** for cloud resource access
- **Secret management** for Redis passwords
- **Firewall rules** restricting port access

## Troubleshooting

### Common Issues

#### High Latency
```bash
# Check feature store latency
curl http://localhost:8080/metrics | grep feature_fetch_duration

# Check model inference time
curl http://localhost:8080/metrics | grep model_inference_duration

# Check Redis connection
redis-cli -h $REDIS_HOST ping
```

#### Model Loading Errors
```bash
# Check model files exist
ls -la training/outputs/

# Check feature names compatibility
python -c "import json; print(json.load(open('training/outputs/feature_names.json')))"

# Check model format
python -c "import pickle; m = pickle.load(open('training/outputs/model.pkl', 'rb')); print(type(m))"
```

#### Redis Connection Issues
```bash
# Test Redis connectivity
redis-cli -h $REDIS_HOST -p $REDIS_PORT ping

# Check feature keys
redis-cli -h $REDIS_HOST --scan --pattern "features:*" | head -10

# Monitor Redis performance
redis-cli -h $REDIS_HOST --latency-history
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with verbose output
uvicorn app:app --log-level debug --access-log

# Profile performance
python -m cProfile -s tottime app.py
```

## Integration Examples

### cURL Examples
```bash
# Fraud detection
curl -X POST http://localhost:8080/score/fraud \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_00001234",
    "transaction_amount": 150.0,
    "merchant_id": "merchant_high_risk",
    "mcc_code": "5816"
  }'

# Personalization
curl -X POST http://localhost:8080/score/personalization \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_00005678",
    "item_id": "item_electronics_001",
    "item_category": "electronics"
  }'

# Health check
curl http://localhost:8080/health | jq .

# Metrics
curl http://localhost:8080/metrics
```

### Python Client
```python
import requests

class InferenceClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def score_fraud(self, card_id: str, amount: float) -> dict:
        response = requests.post(
            f"{self.base_url}/score/fraud",
            json={"card_id": card_id, "transaction_amount": amount}
        )
        return response.json()
    
    def score_personalization(self, user_id: str, item_id: str) -> dict:
        response = requests.post(
            f"{self.base_url}/score/personalization", 
            json={"user_id": user_id, "item_id": item_id}
        )
        return response.json()

# Usage
client = InferenceClient("http://localhost:8080")
fraud_result = client.score_fraud("card_123", 150.0)
print(f"Fraud score: {fraud_result['fraud_score']}")
```

```
graph LR
    A[Event Generators] --> B[Kafka]
    B --> C[Stream Processor]
    C --> D[Redis Features]
    D --> E[**FastAPI Inference**]
    E --> F[Real-time Predictions]
    
    G[Training Pipeline] --> H[Trained Models]
    H --> E
    
    I[MLflow] --> E
    E --> J[Prometheus Metrics]
```

## Production Checklist

### Pre-deployment
- [ ] Model validation with test dataset
- [ ] Load testing with expected traffic
- [ ] Security scan of container image
- [ ] Configuration review and secrets setup
- [ ] Monitoring and alerting configuration

### Post-deployment
- [ ] Health check verification
- [ ] Latency SLA validation
- [ ] Error rate monitoring
- [ ] Feature store connectivity
- [ ] Model performance validation
- [ ] Log aggregation setup

This inference service provides enterprise-grade real-time ML serving with the performance, reliability, and observability required for production fraud detection and personalization systems.
