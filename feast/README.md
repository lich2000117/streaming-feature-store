# 🏪 Feast Feature Store Configuration

This directory contains the **Feast feature store configuration** for real-time ML feature serving and management.

## 📋 Overview

The feature store provides:
- **Centralized feature registry** with metadata and lineage
- **Online feature serving** from Redis for low-latency inference  
- **Offline feature access** for model training and backtesting
- **Point-in-time correctness** for consistent training/serving
- **Feature validation** and data quality monitoring

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Stream Pipeline│    │  Feast Registry │    │ Online Inference│
│     (Flink)     │───▶│   (Metadata)    │◀───│   (FastAPI)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Redis Online    │    │ File Offline    │    │ Model Training  │
│ Feature Store   │    │ Feature Store   │    │   (MLflow)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 Directory Structure

```
feast/
├── feature_store.yaml          # Main Feast configuration
├── entities.py                 # Entity definitions (card, user, device)
├── feature_views.py           # Feature view definitions and schemas
├── feature_store_definition.py # Main feature store registry
├── feature_utils.py           # Utilities and CLI tools
├── test_feast_integration.py  # Integration tests
└── requirements.txt           # Feast dependencies
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
source .venv/bin/activate
pip install -r feast/requirements.txt
```

### 2. Initialize Feature Store
```bash
cd feast/
feast plan                    # Preview changes
feast apply                   # Apply feature definitions to registry
```

### 3. Validate Setup
```bash
python feature_utils.py validate
python test_feast_integration.py
```

### 4. Start Feature Server (Optional)
```bash
feast serve                   # Start feature serving API on :6566
```

## 📊 Feature Definitions

### Entities
- **Card**: Payment card entity (`card_id`)
- **User**: User entity for personalization (`user_id`)  
- **Device**: Device fingerprint entity (`device_id`)
- **Session**: User session entity (`session_id`)

### Feature Views

#### Transaction Features (Fraud Detection)
**Feature View**: `transaction_stats_5m`
- **Count Features**: `txn_count_5m`, `txn_count_30m`, `txn_count_24h`
- **Amount Features**: `amount_sum_5m`, `amount_avg_5m`, `amount_max_5m`
- **Geographic**: `unique_countries_5m`, `geo_diversity_score`
- **Temporal**: `time_since_last_txn_min`, `is_weekend`
- **Risk**: `velocity_score`, `high_risk_txn_ratio`, `is_high_velocity`

#### User Engagement Features (Personalization)  
**Feature View**: `user_engagement_5m`
- **Session**: `session_duration_min`, `pages_per_session`
- **Engagement**: `avg_dwell_time_sec`, `avg_scroll_depth`, `click_rate_5m`
- **Funnel**: `cart_adds_session`, `conversion_rate_session`
- **Behavioral**: `engagement_score`, `is_likely_purchaser`

### Feature Services
- **Fraud Detection Service**: Real-time fraud scoring features
- **Personalization Service**: User behavior and preference features

## 🔧 Usage Examples

### Online Feature Serving
```python
from feast import FeatureStore

# Initialize feature store
fs = FeatureStore(repo_path="feast/")

# Get features for fraud detection
fraud_features = fs.get_online_features(
    features=[
        "transaction_stats_5m:txn_count_5m",
        "transaction_stats_5m:amount_avg_5m", 
        "transaction_stats_5m:velocity_score"
    ],
    entity_rows=[{"card_id": "card_12345"}]
).to_dict()

print(f"Fraud features: {fraud_features}")
```

### Historical Features for Training
```python
import pandas as pd
from datetime import datetime, timedelta

# Training data with entity IDs and timestamps
entity_df = pd.DataFrame([
    {
        "card_id": "card_12345",
        "event_timestamp": datetime.now() - timedelta(hours=1)
    },
    {
        "card_id": "card_67890", 
        "event_timestamp": datetime.now() - timedelta(hours=2)
    }
])

# Get historical features
training_data = fs.get_historical_features(
    entity_df=entity_df,
    features=[
        "transaction_stats_5m:txn_count_5m",
        "transaction_stats_5m:velocity_score"
    ]
).to_df()

print(f"Training data shape: {training_data.shape}")
```

### Feature Server API
```bash
# Start feature server
feast serve

# Get online features via HTTP
curl -X POST http://localhost:6566/get-online-features \
  -H "Content-Type: application/json" \
  -d '{
    "features": [
      "transaction_stats_5m:txn_count_5m",
      "transaction_stats_5m:velocity_score"
    ],
    "entities": {
      "card_id": ["card_12345"]
    }
  }'
```

## 🔍 Validation and Monitoring

### Feature Store Validation
```bash
python feature_utils.py validate
```
Checks:
- ✅ Registry connectivity
- ✅ Online store (Redis) connectivity  
- ✅ Feature view registration
- ✅ Entity definitions

### Point-in-time Correctness
```bash
python feature_utils.py validate-pit --entity-id card_12345 --entity-type card
```
Validates consistency between online and offline features.

### Feature Documentation
```bash
python feature_utils.py docs --output-file docs/FEATURES.md
```
Generates comprehensive feature documentation.

## 🔄 Integration with Stream Processing

Our streaming pipeline (Flink) writes features to Redis using the format:
```
Key: features:{entity_type}:{entity_id}:{feature_type}
Value: {feature_name: feature_value, ...}
```

Feast reads from this same Redis instance for online serving, ensuring consistency.

## 📈 Production Deployment

### Local Development
```bash
# File-based offline store, Redis online store
export FEAST_CONFIG="feast/feature_store.yaml"
feast apply
```

### Production (Cloud)
```yaml
# Update feature_store.yaml for production
offline_store:
  type: bigquery
  project_id: "my-project"
  dataset: "feast_features"

online_store:
  type: redis
  connection_string: "redis-cluster.prod.com:6379"
```

### CI/CD Integration
```bash
# Validate features in CI
pytest feast/test_feast_integration.py

# Deploy feature definitions
feast plan --diff
feast apply

# Run feature validation
python feast/feature_utils.py validate
```

## 🚨 Troubleshooting

### Common Issues

**Registry not found**
```bash
# Initialize registry
feast init
feast apply
```

**Redis connection failed**
```bash
# Check Redis connectivity
redis-cli ping

# Update connection in feature_store.yaml
```

**Feature not found**
```bash
# List registered features
feast feature-views list
feast entities list

# Re-apply feature definitions
feast apply
```

### Debug Commands
```bash
# Check feature store status
feast registry-dump

# Validate configuration
python -c "from feast import FeatureStore; fs = FeatureStore(); print('OK')"

# Test online features
python feast/feature_utils.py validate-pit --entity-id test_card --entity-type card
```

## 🔗 Integration Points

- **Stream Processing**: Flink jobs write to Redis online store
- **ML Training**: Historical features from offline store  
- **Inference API**: Online features via Feast client or HTTP API
- **Monitoring**: Feature drift detection and data quality
- **MLflow**: Model metadata includes feature specifications

## 📚 Additional Resources

- [Feast Documentation](https://docs.feast.dev/)
- [Feature Store Concepts](https://docs.feast.dev/getting-started/concepts)
- [Production Deployment Guide](https://docs.feast.dev/how-to-guides/running-feast-in-production)
