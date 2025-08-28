# Data Contracts & Schema Evolution

## Overview

This directory contains **Avro schemas** that define our data contracts for all streaming events. These schemas ensure:

- **Type safety** across producers and consumers
- **Backward compatibility** for schema evolution
- **Automatic serialization/deserialization**
- **Schema validation** at ingestion time

## Schema Design Principles

### 1. **Partitioning Strategy**
- `transactions.v1`: Partitioned by `card_id` for fraud detection locality
- `clicks.v1`: Partitioned by `user_id` for personalization features
- `devices.v1`: Partitioned by `device_id` for device fingerprinting

### 2. **Backward Compatibility Rules**
- ✅ **Adding optional fields** (with defaults)
- ✅ **Adding new enum values**
- ❌ **Removing fields** (deprecate instead)
- ❌ **Changing field types**
- ❌ **Renaming fields**

### 3. **Evolution Strategy**
```
transactions.v1 → transactions.v2
- Add `merchant_id` field (optional, default: null)
- Add `risk_score` field (optional, default: 0.0)
- Deprecate `mcc` (keep for compatibility)
```

## Topic Configuration

| Topic | Partitions | Key | Retention |
|-------|------------|-----|-----------|
| `txn.events` | 24 | `card_id` | 7 days |
| `click.events` | 24 | `user_id` | 7 days |
| `device.events` | 12 | `device_id` | 7 days |
| `*_dlq` | 6 | original_key | 30 days |

## Usage Examples

### Python Producer
```python
from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer

# Load schema
with open('schemas/transactions.v1.avsc', 'r') as f:
    schema = avro.loads(f.read())

# Configure producer
producer = AvroProducer({
    'bootstrap.servers': 'localhost:9092',
    'schema.registry.url': 'http://localhost:8081'
})

# Send event
event = {
    "txn_id": "txn_12345",
    "card_id": "card_67890",
    "user_id": "user_456",
    "amount": 129.99,
    "currency": "USD",
    # ... other fields
}

producer.produce(
    topic='txn.events',
    key=event['card_id'],
    value=event,
    value_schema=schema
)
```

### Flink Consumer
```python
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors import FlinkKafkaConsumer

# Flink will automatically deserialize using schema registry
kafka_source = FlinkKafkaConsumer(
    topics=['txn.events'],
    deserialization_schema=AvroDeserializationSchema.for_specific(
        'schemas/transactions.v1.avsc'
    ),
    properties={
        'bootstrap.servers': 'localhost:9092',
        'group.id': 'flink-feature-job'
    }
)
```

## Schema Validation

Use the provided validation script:
```bash
python schemas/validate_schemas.py
```

This checks:
- ✅ Avro schema syntax
- ✅ Backward compatibility with previous versions
- ✅ Required field presence
- ✅ Default value validity
