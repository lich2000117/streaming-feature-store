# 🚀 Stream Processing Module

Real-time feature engineering for fraud detection and personalization.

## 📁 Structure

```
flink/
├── jobs/               # Production Flink jobs
│   └── feature_job.py  # Full PyFlink implementation 
├── utils/              # Shared utilities
│   └── watermarks.py   # Event-time processing
├── stream_processor.py # Simplified development version
├── test_stream_processor.py  # Unit tests
└── requirements.txt    # Dependencies
```

## 🎯 Two Approaches

### Development: `stream_processor.py`
- **Use for**: Local development, testing, learning
- **Tech**: Pure Python + Kafka consumers
- **Pros**: Simple setup, fast iteration, easy debugging
- **Cons**: In-memory state, at-least-once semantics

```bash
# Run simplified processor
make run-features
# OR
python flink/stream_processor.py --kafka-servers localhost:9092
```

### Production: `jobs/feature_job.py` 
- **Use for**: Production deployment
- **Tech**: PyFlink + distributed processing
- **Pros**: Exactly-once semantics, fault tolerance, scalability
- **Cons**: Complex setup, requires Flink cluster

```bash
# Run Flink job (requires PyFlink setup)
make run-flink
```

## ⚡ Key Concepts

### Event-Time Processing
- **Watermarks**: Handle out-of-order events
- **Late events**: Send to Dead Letter Queue
- **Event timestamps**: Use event creation time, not processing time

### Stateful Processing
- **Partitioning**: `card_id` for fraud, `user_id` for personalization  
- **State management**: Per-key aggregations and windows
- **Fault tolerance**: Checkpointed state in Flink

### Feature Engineering
- **Transaction features**: Velocity, geo patterns, risk scoring
- **Clickstream features**: Engagement, conversion, session behavior
- **Real-time aggregations**: 5-minute sliding windows

## 🧪 Testing

```bash
# Test without Kafka infrastructure
python flink/test_stream_processor.py

# Test with mocked components
make test-features
```

## 📊 Monitoring

- **Metrics**: Prometheus metrics on port 8088
- **Logs**: Structured logging with context
- **Health**: Consumer lag and processing rates

## 🔧 Configuration

Key environment variables:
- `KAFKA_SERVERS`: Kafka bootstrap servers
- `REDIS_HOST`: Feature store location  
- `WINDOW_SIZE_MINUTES`: Aggregation window (default: 5)
- `CHECKPOINT_INTERVAL_MS`: Fault tolerance frequency (default: 30000)

## 🚀 Quick Start

1. **Start infrastructure**: `make up`
2. **Generate data**: `make seed` 
3. **Run processor**: `make run-features`
4. **Check features**: `redis-cli KEYS "features:*"`

## 💡 Next Steps

- Explore `/utils/watermarks.py` for event-time concepts
- Read `/jobs/feature_job.py` for production patterns
- Study the test files for mocking strategies
- Check the main StudyDoc.md for detailed explanations
