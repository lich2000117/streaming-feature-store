# Streaming Feature Store - Project Structure

## Overview

This project follows a **centralized Docker Compose approach** with **distributed Dockerfiles** for optimal development and production deployment. All services are orchestrated through a single `docker-compose.yml` file using Docker Compose profiles.

## Architecture Decision

**✅ Chosen Approach: Centralized Compose + Distributed Dockerfiles**

```
Project Root/
├── infra/
│   └── docker-compose.yml          # 🎯 SINGLE SOURCE OF TRUTH
├── service1/
│   └── Dockerfile                  # Service-specific build
├── service2/
│   └── Dockerfile                  # Service-specific build
└── Makefile                        # Uses centralized compose
```

**Why This Approach:**
1. **Single source of truth** for service orchestration
2. **Service isolation** with individual Dockerfiles
3. **Profile-based deployment** for different environments
4. **Consistent with your existing Makefile** commands
5. **Production-ready** with proper dependencies and health checks

## Project Structure

```
streaming-feature-store/
├── 📁 infra/                       # Infrastructure & Orchestration
│   └── docker-compose.yml          # 🎯 All services defined here
│
├── 📁 generators/                  # Event Generation
│   ├── Dockerfile                  # Synthetic data generators
│   ├── requirements.txt
│   ├── txgen.py
│   └── clickgen.py
│
├── 📁 streaming/                   # Stream Processing
│   ├── Dockerfile                  # Feature engineering pipeline
│   ├── requirements.txt
│   └── stream_processor.py
│
├── 📁 inference/                   # ML Serving
│   ├── Dockerfile                  # FastAPI inference service
│   ├── requirements.txt
│   ├── app.py
│   ├── config.py
│   ├── schemas.py
│   ├── features.py
│   └── models.py
│
├── 📁 training/                    # ML Training
│   ├── Dockerfile                  # Training pipeline
│   ├── requirements.txt
│   ├── train.py
│   ├── config.py
│   ├── datasets.py
│   ├── models.py
│   └── outputs/                    # Model artifacts
│
├── 📁 feast/                       # Feature Store
│   ├── Dockerfile                  # Feast server
│   ├── requirements.txt
│   └── feature_store.yaml
│
├── 📁 monitoring/                  # Observability
│   ├── prometheus/                 # Metrics collection
│   │   ├── prometheus.yml
│   │   ├── alert_rules.yml
│   │   └── recording_rules.yml
│   ├── grafana/                    # Visualization
│   │   ├── dashboards/
│   │   └── provisioning/
│   └── blackbox/                   # Endpoint monitoring
│       └── config.yml
│
├── 📁 schemas/                     # Data Contracts
│   ├── transactions.v1.avsc
│   ├── clicks.v1.avsc
│   └── validate_schemas.py
│
├── Makefile                        # 🎯 Uses infra/docker-compose.yml
├── DesignDoc.md
└── README.md
```

## Docker Compose Profiles

All services use **Docker Compose profiles** for environment-specific deployments:

### Core Infrastructure (Always Running)
```yaml
services:
  kafka:           # Message broker
  schema-registry: # Schema management  
  redis:           # Feature store
  mlflow:          # ML lifecycle management
```

### Service Profiles
```yaml
profiles:
  - generators: [txn-generator, click-generator]
  - streaming:  [stream-processor]
  - inference:  [inference-api]
  - feast:      [feast-server]
  - training:   [training-job]
  - monitoring: [prometheus, grafana, redis-exporter, node-exporter, blackbox-exporter]
  - all:        [everything above]
```

## Makefile Commands

All commands use the **centralized compose file**:

```bash
# Infrastructure
make up              # Start core services
make down            # Stop all services

# Service Management  
make generate        # Start event generators
make stream          # Start stream processing
make serve           # Start inference API
make feast_up        # Start feature store
make train           # Run ML training
make monitor         # Start monitoring stack

# Complete Platform
make demo            # Start everything for demo
make up-all          # Start all profiles

# Operations
make health          # Check service health
make logs-api        # View API logs
make inspect         # View data flow
make test-api        # Test API endpoints
```

## Development Workflow

### 1. Local Development
```bash
# Start core infrastructure
make up

# Start specific services as needed
make serve           # For API development
make monitor         # For observability
make generate        # For data generation
```

### 2. Full System Testing
```bash
# Start everything
make demo

# Test end-to-end
make test-api
make inspect
make health
```

### 3. Production Deployment
```bash
# All services with monitoring
make up-all
```

## Service Dependencies

The compose file defines **proper dependency chains**:

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

monitoring:
  depends_on:
    - redis
    - prometheus
```

## Benefits of This Architecture

### ✅ Development Benefits
1. **Service Isolation**: Each service has its own Dockerfile
2. **Fast Iteration**: Only rebuild changed services
3. **Easy Testing**: Start individual services for testing
4. **Clear Boundaries**: Service responsibilities are well-defined

### ✅ Operations Benefits
1. **Single Orchestration**: One compose file to rule them all
2. **Profile-based Deployment**: Deploy only what you need
3. **Consistent Commands**: Makefile abstracts complexity
4. **Health Checks**: Proper service startup ordering
5. **Volume Management**: Persistent data across restarts

### ✅ Production Benefits
1. **Scalable**: Individual services can be scaled
2. **Monitored**: Complete observability stack
3. **Reliable**: Health checks and restart policies
4. **Maintainable**: Clear service boundaries and configs

## Configuration Management

### Environment Variables
```yaml
# Service-specific configs in docker-compose.yml
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

### Volume Mounts
```yaml
# Configuration files mounted from host
prometheus:
  volumes:
    - ../monitoring/prometheus:/etc/prometheus

# Persistent data volumes
grafana:
  volumes:
    - grafana_data:/var/lib/grafana
```

## Monitoring Integration

The monitoring stack is **fully integrated** into the main compose file:

```yaml
# Prometheus scrapes all services automatically
prometheus:
  # Scrapes: inference-api:8080/metrics
  # Scrapes: redis-exporter:9121/metrics
  # Scrapes: node-exporter:9100/metrics

grafana:
  # Auto-loads dashboards from monitoring/grafana/
  # Connects to Prometheus automatically
```

## Migration from Separate Compose Files

**✅ What Was Fixed:**
1. **Removed**: `monitoring/docker-compose.monitoring.yml` (duplicate)
2. **Enhanced**: `infra/docker-compose.yml` with complete monitoring stack
3. **Aligned**: All Makefile commands use centralized approach
4. **Added**: Missing exporters (redis-exporter, node-exporter, blackbox-exporter)
5. **Improved**: Prometheus configuration with alert/recording rules

**✅ Result:**
- **Single source of truth**: `infra/docker-compose.yml`
- **Consistent commands**: All Makefile targets work correctly
- **Complete monitoring**: All observability components included
- **Production-ready**: Health checks, dependencies, and volumes

## Best Practices Followed

1. **🎯 Centralized Orchestration**: Single compose file for all services
2. **📦 Service Isolation**: Individual Dockerfiles per service
3. **🔧 Profile-based Deployment**: Environment-specific service groups
4. **🏥 Health Checks**: Proper service startup ordering
5. **📊 Complete Observability**: Integrated monitoring stack
6. **🔒 Production Security**: Non-root containers and proper networking
7. **📚 Clear Documentation**: Comprehensive README and structure docs

This architecture provides the optimal balance of **development flexibility** and **production reliability** while maintaining clear service boundaries and operational simplicity.
