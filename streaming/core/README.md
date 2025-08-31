# 🎯 Core Shared Components

Framework-agnostic components for streaming feature engineering. Used by both simplified Kafka consumers and production PyFlink jobs.

## 📋 Components Overview

### **Models** (`models/`)
```python
# Event schemas with validation
from streaming.core.models.events import TransactionEvent, ClickEvent

# Feature output schemas  
from streaming.core.models.features import TransactionFeatures, ClickstreamFeatures

# Configuration management
from streaming.core.models.config import ProcessorConfig, FeatureJobConfig
```

### **Processors** (`processors/`)
```python
# Business logic for feature computation
from streaming.core.processors.transaction import TransactionFeatureComputer
from streaming.core.processors.clickstream import ClickstreamFeatureComputer

# Shared utility functions for windowed aggregations
from streaming.core.processors.transaction import compute_transaction_features_from_window
```

### **Sinks** (`sinks/`)  
```python
# Redis feature storage with proper serialization
from streaming.core.sinks.redis_sink import FeatureSink, FlinkRedisSink
```

### **Utils** (`utils/`)
```python
# Avro schema management and deserialization
from streaming.core.utils.avro import AvroDeserializer, AvroSerializer

# Time-based windowing for aggregations
from streaming.core.utils.windowing import SlidingWindow

# Event-time processing and watermarking  
from streaming.core.utils.watermarks import WatermarkGenerator, LateEventHandler
```

## 🏗️ Design Principles

### **Framework Agnostic**
- Core business logic works with any streaming framework
- No dependencies on Kafka or Flink specifics
- Testable without infrastructure

### **Type Safety**
- Pydantic models ensure data validation
- Clear interfaces between components
- Runtime type checking for debugging

### **Reusability**
- Feature computation logic shared across implementations
- Configuration management centralized
- Utilities work with different window types

## 🔧 Usage Examples

### **Feature Computation**
```python
from streaming.core.processors.transaction import compute_transaction_features_from_window
from streaming.core.models.config import ProcessorConfig

# Configure processor
config = ProcessorConfig(window_size_minutes=5)

# Process events in window
events = [{'card_id': '123', 'amount': 100.0, 'timestamp': 1640995200000}]
features = compute_transaction_features_from_window(events, config)

# Output: {'txn_count': 1, 'amount_sum': 100.0, 'velocity_score': 0.1, ...}
```

### **Avro Deserialization**
```python
from streaming.core.utils.avro import AvroDeserializer
from streaming.core.models.config import ProcessorConfig

# Initialize with schema directory
config = ProcessorConfig(schema_dir="schemas")
deserializer = AvroDeserializer(config)

# Deserialize binary Avro message
event = deserializer.deserialize_message("txn.events", avro_bytes)
```

### **Redis Storage**  
```python
from streaming.core.sinks.redis_sink import FeatureSink
from streaming.core.models.config import ProcessorConfig

# Initialize Redis sink
config = ProcessorConfig(redis_host="localhost", redis_port=6379)
sink = FeatureSink(config)

# Store computed features
features = {'entity_id': 'card_123', 'txn_count_5m': 5}
success = sink.write_features(features)
```

## 🧪 Testing

Each component is designed for independent testing:

```python
# Test feature computation
def test_transaction_features():
    events = [mock_transaction_event()]
    features = compute_transaction_features_from_window(events, config)
    
    assert features['txn_count'] == 1
    assert features['amount_sum'] == 100.0

# Test windowing
def test_sliding_window():
    window = SlidingWindow(window_size_ms=5000, slide_size_ms=1000)
    window.add_event(timestamp, event)
    
    assert window.size() == 1
    assert len(window.get_events()) == 1
```

## 📊 Metrics & Observability

Components expose metrics for monitoring:

```python
# Feature computation metrics
FEATURES_COMPUTED.labels(feature_type='transaction').inc()

# Redis write metrics  
REDIS_WRITES.labels(status='success').inc()

# Window size metrics
WINDOW_SIZE.labels(window_type='transaction').set(event_count)
```

## 🔄 Extension Points

### **Adding New Event Types**
1. Define model in `models/events.py`
2. Add processor in `processors/new_type.py`  
3. Update deserializer in `utils/avro.py`

### **New Feature Types**
1. Add feature model in `models/features.py`
2. Implement computation logic in appropriate processor
3. Update sink serialization if needed

### **New Storage Backends**
1. Create sink in `sinks/new_backend.py`
2. Implement write methods with error handling
3. Add configuration to `models/config.py`

---

**🎯 These shared components enable consistent, maintainable feature engineering across different streaming frameworks while maximizing code reuse and testability.**
