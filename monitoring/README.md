# Production Monitoring & Observability Stack

Enterprise-grade monitoring solution for the Streaming Feature Store providing comprehensive observability across the entire ML pipeline with real-time alerts, performance tracking, and business metrics.

## 🎯 Monitoring Philosophy

Our monitoring approach follows the **Three Pillars of Observability**:
- **Metrics**: Quantitative measurements of system behavior
- **Logs**: Event records for debugging and audit trails  
- **Traces**: Request flow across distributed services

### SLI/SLO Framework

We monitor **Service Level Indicators (SLIs)** against **Service Level Objectives (SLOs)**:

| Service | SLI | SLO Target | Alert Threshold |
|---------|-----|------------|----------------|
| Inference API | P95 Latency | < 150ms | > 200ms |
| Inference API | Availability | > 99.9% | < 99.5% |
| Feature Store | Cache Hit Rate | > 90% | < 70% |
| Stream Processing | Lag | < 1000 msgs | > 10000 msgs |
| Model Performance | Confidence | > 80% | < 70% |

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Applications  │───▶│   Prometheus    │───▶│     Grafana     │
│                 │    │  (Metrics DB)   │    │  (Visualization)│
│ • Inference API │    │                 │    │                 │
│ • Stream Proc   │    │ • Recording     │    │ • Dashboards    │
│ • Feature Store │    │ • Alert Rules   │    │ • Alerting      │
│ • ML Pipeline   │    │ • Scraping      │    │ • Analysis      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │   Exporters     │              │
         │              │                 │              │
         └──────────────│ • Redis         │──────────────┘
                        │ • Node          │
                        │ • Blackbox      │
                        └─────────────────┘
```

## 📊 Monitoring Stack Components

### Core Monitoring Services

#### Prometheus (Port 9090)
- **Role**: Metrics collection, storage, and alerting engine
- **Retention**: 30 days, 10GB storage limit
- **Features**:
  - 15s scrape interval for real-time monitoring
  - Recording rules for pre-computed metrics
  - Alert rules for production incidents
  - Service discovery and health checks

#### Grafana (Port 3000)
- **Role**: Metrics visualization and dashboard platform
- **Credentials**: `admin` / `admin123`
- **Features**:
  - Auto-provisioned dashboards
  - Unified alerting with Prometheus
  - Business metrics visualization
  - SLI/SLO compliance tracking

### Specialized Exporters

#### Redis Exporter (Port 9121)
- **Metrics**: Redis performance, memory usage, connection stats
- **Key Metrics**:
  - `redis_connected_clients` - Active connections
  - `redis_memory_used_bytes` - Memory utilization
  - `redis_commands_processed_total` - Operation throughput

#### Node Exporter (Port 9100)
- **Metrics**: System-level metrics (CPU, memory, disk, network)
- **Key Metrics**:
  - `node_cpu_seconds_total` - CPU utilization
  - `node_memory_*` - Memory statistics
  - `node_filesystem_*` - Disk usage

#### Blackbox Exporter (Port 9115)
- **Metrics**: External endpoint monitoring and synthetic checks
- **Probes**:
  - HTTP health checks for all services
  - TCP connectivity tests
  - DNS resolution monitoring

## 📈 Dashboard Portfolio

### 1. System Overview Dashboard
**Purpose**: High-level system health and performance
**Key Panels**:
- Service health status matrix
- Request rate and error distribution
- API latency percentiles (P50, P95, P99)
- System throughput metrics
- Resource utilization overview

### 2. Inference API Dashboard  
**Purpose**: Real-time ML serving performance
**Key Panels**:
- Fraud detection vs personalization latency
- Model inference performance breakdown
- Feature fetch latency and cache performance
- Prediction score distributions
- Error rates by endpoint and status code

### 3. Feature Store Dashboard
**Purpose**: Feature pipeline and Redis monitoring
**Key Panels**:
- Feature freshness tracking
- Cache hit/miss ratios
- Redis performance metrics
- Feature computation latency
- Data quality indicators

### 4. Stream Processing Dashboard
**Purpose**: Real-time data pipeline monitoring
**Key Panels**:
- Kafka consumer lag by topic
- Event processing throughput
- Stream processing latency
- Dead letter queue monitoring
- Watermark progression

### 5. ML Pipeline Dashboard
**Purpose**: Model training and lifecycle monitoring
**Key Panels**:
- Training job success/failure rates
- Model performance drift detection
- MLflow experiment tracking
- Model registry statistics
- A/B testing metrics

### 6. Business Metrics Dashboard
**Purpose**: Business KPIs and operational insights
**Key Panels**:
- Fraud detection rates and trends
- Transaction volume and patterns
- Model confidence distributions
- Feature importance tracking
- Revenue impact metrics

## 🚨 Alert Management

### Alert Severity Levels

#### Critical (Immediate Response Required)
- API service down
- Error rate > 1%
- P95 latency > 150ms
- Redis/Kafka unavailable
- System health score < 90%

#### Warning (Investigation Required)
- High load conditions
- Cache hit rate < 70%
- Feature staleness > 5 minutes
- Model confidence < 70%
- Resource utilization > 80%

#### Info (Awareness Only)
- Deployment events
- Configuration changes
- Scheduled maintenance
- Performance optimizations

### Alert Rules Configuration

```yaml
# Example: High API Latency Alert
- alert: InferenceAPIHighLatency
  expr: histogram_quantile(0.95, sum(rate(inference_request_duration_seconds_bucket[5m])) by (le, endpoint)) > 0.15
  for: 2m
  labels:
    severity: critical
    service: inference-api
  annotations:
    summary: "API latency exceeds SLA"
    description: "P95 latency is {{ $value | humanizeDuration }} for {{ $labels.endpoint }}"
    runbook_url: "https://runbook.company.com/api-latency"
```

## 🚀 Quick Start

### 1. Start Monitoring Stack
```bash
# Start core infrastructure first
make up

# Start monitoring services (uses centralized docker-compose.yml)
make monitor

# Verify services are healthy
make health
```

### 2. Monitoring Architecture
The monitoring stack is **integrated into the main docker-compose.yml** using Docker Compose profiles:

```bash
# All monitoring services are defined in:
infra/docker-compose.yml

# Configuration files are in:
monitoring/
├── prometheus/          # Prometheus config and rules
├── grafana/            # Dashboards and provisioning
└── blackbox/           # Endpoint monitoring config
```

### 3. Access Dashboards
```bash
# View service URLs
make urls

# Direct access:
# Grafana: http://localhost:3000 (admin/admin123)
# Prometheus: http://localhost:9090
# Alertmanager: http://localhost:9093
```

### 3. Import Additional Dashboards
```bash
# Pre-built dashboards are auto-loaded
# Custom dashboards can be added to:
monitoring/grafana/dashboards/
```

## 📋 Monitoring Checklist

### Daily Operations
- [ ] Check system overview dashboard for anomalies
- [ ] Review error rates and latency trends
- [ ] Validate feature freshness and cache performance
- [ ] Monitor model prediction distributions
- [ ] Check stream processing lag

### Weekly Reviews
- [ ] Analyze performance trends and capacity planning
- [ ] Review alert fatigue and tune thresholds
- [ ] Update dashboards based on operational needs
- [ ] Performance optimization opportunities
- [ ] Business metrics correlation analysis

### Monthly Health Checks
- [ ] SLO compliance review and reporting
- [ ] Dashboard effectiveness evaluation
- [ ] Alert rule accuracy assessment
- [ ] Capacity planning and scaling decisions
- [ ] Monitoring stack performance optimization

## 🔧 Configuration Management

### Prometheus Configuration
```yaml
# monitoring/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'inference-api'
    static_configs:
      - targets: ['inference-api:8080']
    metrics_path: /metrics
    scrape_interval: 10s
```

### Grafana Provisioning
```yaml
# monitoring/grafana/provisioning/datasources.yml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
```

### Custom Metrics Implementation
```python
# Example: Adding custom metrics to inference service
from prometheus_client import Counter, Histogram

PREDICTION_COUNTER = Counter(
    'model_predictions_total',
    'Total model predictions',
    ['model_type', 'prediction_class']
)

FEATURE_LATENCY = Histogram(
    'feature_fetch_duration_seconds',
    'Feature fetch latency'
)
```

## 🎛️ Advanced Features

### Service Discovery
- Kubernetes service discovery support
- Docker Swarm integration
- Consul service discovery
- Custom target discovery

### Long-term Storage
- Remote write to InfluxDB/VictoriaMetrics
- Data retention policies
- Compaction and downsampling
- Cross-region replication

### Security
- RBAC for Grafana dashboards
- Prometheus authentication
- TLS/SSL encryption
- Network security policies

## 🔍 Troubleshooting

### Common Issues

#### High Memory Usage in Prometheus
```bash
# Check retention settings
docker exec prometheus cat /etc/prometheus/prometheus.yml | grep retention

# Optimize scrape intervals
# Reduce metric cardinality
# Implement recording rules
```

#### Grafana Dashboard Not Loading
```bash
# Check datasource connectivity
curl http://localhost:9090/api/v1/query?query=up

# Verify dashboard provisioning
docker exec grafana ls -la /etc/grafana/provisioning/dashboards/
```

#### Missing Metrics
```bash
# Verify service is exposing metrics
curl http://inference-api:8080/metrics

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets
```

### Performance Optimization

#### Prometheus Performance
- Use recording rules for expensive queries
- Optimize label cardinality
- Configure appropriate retention
- Use federation for scaling

#### Grafana Performance  
- Limit time ranges for heavy queries
- Use template variables effectively
- Cache dashboard queries
- Optimize panel refresh rates

## 📚 Best Practices

### Metric Design
- Use consistent naming conventions
- Include relevant labels for filtering
- Avoid high-cardinality labels
- Document metric meanings

### Dashboard Design
- Start with business metrics
- Include SLI/SLO indicators
- Use consistent time ranges
- Add context and annotations

### Alert Design
- Make alerts actionable
- Include runbook links
- Use appropriate severity levels
- Test alert fatigue regularly

## 🔗 Integration Examples

### Slack Notifications
```yaml
# alertmanager/config.yml
route:
  group_by: ['alertname']
  receiver: 'slack-notifications'

receivers:
- name: 'slack-notifications'
  slack_configs:
  - api_url: 'YOUR_SLACK_WEBHOOK_URL'
    channel: '#alerts'
    title: 'Streaming Feature Store Alert'
```

### PagerDuty Integration
```yaml
receivers:
- name: 'pagerduty'
  pagerduty_configs:
  - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
    description: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
```

## 📊 Metrics Reference

### Application Metrics

#### Inference API
- `inference_requests_total` - Total API requests
- `inference_request_duration_seconds` - Request latency histogram
- `inference_active_requests` - Current active requests
- `model_inference_duration_seconds` - Model execution time
- `feature_fetch_duration_seconds` - Feature retrieval time

#### Feature Store
- `feature_cache_hits_total` - Cache hit counter
- `feature_cache_misses_total` - Cache miss counter
- `feature_freshness_seconds` - Age of features
- `redis_connected_clients` - Redis connections

#### Stream Processing  
- `stream_events_processed_total` - Events processed
- `stream_processing_duration_seconds` - Processing latency
- `kafka_consumer_lag_sum` - Consumer lag

### Infrastructure Metrics
- `node_cpu_seconds_total` - CPU usage
- `node_memory_*` - Memory statistics
- `node_filesystem_*` - Disk usage
- `up` - Service availability

This monitoring stack provides production-grade observability for your streaming feature store, enabling proactive issue detection, performance optimization, and business insight generation.