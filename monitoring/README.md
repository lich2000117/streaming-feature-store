# Monitoring Setup

This directory contains monitoring and observability configurations for the streaming feature store.

## Structure

```
monitoring/
├── prometheus/
│   └── prometheus.yml          # Prometheus scraping configuration
├── grafana/
│   ├── dashboards/
│   │   └── streaming-overview.json  # Default dashboard
│   └── provisioning/
│       ├── datasources.yml     # Grafana datasource config
│       └── dashboards.yml      # Dashboard provisioning config
└── README.md                   # This file
```

## Usage

The monitoring stack is integrated with the main docker-compose.yml and can be started with:

```bash
# Start monitoring services
make monitoring

# Or start everything including monitoring
make all
```

## Services

- **Prometheus**: Metrics collection and storage (port 9090)
- **Grafana**: Metrics visualization and dashboards (port 3000)
  - Default credentials: admin/admin123

## Adding Metrics

To add metrics from your applications:

1. Expose a `/metrics` endpoint in your service
2. Add the service to `prometheus/prometheus.yml`
3. Create or update Grafana dashboards in `grafana/dashboards/`

## Dashboard Development

Dashboards can be:
- Created through the Grafana UI (will be persisted)
- Added as JSON files in `grafana/dashboards/`
- Imported from the Grafana dashboard library
