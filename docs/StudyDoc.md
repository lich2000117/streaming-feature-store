
# 📚 Streaming Schemas Study Guide


## From Batch to Streaming: A Complete Reference

---

## 🎯 **Core Concept: Schema-on-Write vs Schema-on-Read**

### **Batch Processing (What You Know)**
```
Data Files → Process → Discover Schema → Transform
```
- **Schema-on-Read**: Figure out structure when processing
- **Immutable files**: Schema changes = new files
- **Flexible**: Can reprocess everything if needed
- **Late validation**: Discover issues during processing

### **Streaming Processing (What You're Learning)**
```
Schema Definition → Validate → Stream → Process
```
- **Schema-on-Write**: Define structure before data flows
- **Continuous streams**: Can't "restart" everything
- **Rigid contracts**: Must handle evolution gracefully
- **Early validation**: Catch issues at ingestion

---

## 📋 **What Are Avro Schemas?**

**Avro schemas** = **Data contracts** for streaming systems

```json
{
  "type": "record",
  "name": "Transaction", 
  "namespace": "com.streamingfs.events",
  "fields": [
    {"name": "txn_id", "type": "string"},
    {"name": "amount", "type": "double"},
    {"name": "currency", "type": "enum", "symbols": ["USD", "EUR"]}
  ]
}
```

### **They Provide:**
- ✅ **Type Safety**: All systems agree on data structure
- ✅ **Backward Compatibility**: New versions read old data
- ✅ **Automatic Serialization**: No manual JSON parsing
- ✅ **Schema Validation**: Catch errors at write time

---

## 🏗️ **Schema Registry Architecture**

```
Producer → Schema Registry (HTTP API) → Register schema, get ID
Producer → Kafka Topic → Send data + embedded schema ID

Consumer → Kafka Topic → Read data + extract schema ID  
Consumer → Schema Registry → Fetch schema by ID
Consumer → Deserialize data using schema
```

### **Wire Protocol Magic:**
```
Kafka Message Format:
[0x00][schema_id: 4 bytes][avro_binary_data...]
```

### **Developer Experience:**
```python
# You write simple code:
producer.produce(value=event, value_schema=schema)

# AvroProducer automatically:
# 1. Registers schema → gets ID
# 2. Embeds ID in message  
# 3. Serializes data efficiently
```

---

## 🎯 **Real-World Example: Feature Store Schemas**

### **Business Context: 3 Event Streams**

| Stream | Partition Key | Use Case | Partitions |
|--------|--------------|----------|------------|
| `txn.events` | `card_id` | Fraud Detection | 24 |
| `click.events` | `user_id` | Personalization | 24 |
| `device.events` | `device_id` | Device Fingerprinting | 12 |

### **Why Partitioning Matters:**
```python
# Fraud detection needs related transactions together
txn1: card_id="card_123" → Partition 5
txn2: card_id="card_123" → Partition 5  # Same partition!
# → Efficient fraud pattern detection

# Personalization needs user events together  
click1: user_id="user_456" → Partition 8
click2: user_id="user_456" → Partition 8  # Same partition!
# → Efficient user behavior analysis
```

---

## 🔄 **Schema Evolution: v1 → v2**

### **Evolution Example: transactions.v1 → transactions.v2**

**✅ SAFE Changes (Backward Compatible):**
```json
// v2 adds optional fields with defaults
"merchant_id": {"type": ["null", "string"], "default": null}
"risk_score": {"type": "double", "default": 0.0}
"currency": {"symbols": ["USD", "EUR", "JPY", "CHF"]}  // Added JPY, CHF
```

**❌ BREAKING Changes (Will Crash Consumers):**
```json
// DON'T DO THESE:
- Remove "amount" field
- Change "amount" from double → string  
- Rename "txn_id" → "transaction_id"
```

### **Evolution Strategy:**
```
1. Deploy new schema (consumers ignore new fields)
2. Deploy updated consumers (handle new fields)
3. Deploy updated producers (send new fields)
4. Deprecate old fields (but keep for compatibility)
```

---

## 🔧 **Producer/Consumer Workflow**

### **Producer Side:**
```python
from confluent_kafka.avro import AvroProducer

# Load schema
with open('schemas/transactions.v1.avsc') as f:
    schema = avro.loads(f.read())

# Configure producer
producer = AvroProducer({
    'bootstrap.servers': 'localhost:9092',
    'schema.registry.url': 'http://localhost:8081'
})

# Send event (with automatic validation)
event = {
    "txn_id": "txn_12345",
    "card_id": "card_67890",  # Becomes partition key
    "amount": 129.99,
    "currency": "USD"
}

producer.produce(
    topic='txn.events',
    key=event['card_id'],    # Partition by card_id
    value=event,             # Data
    value_schema=schema      # Schema for validation
)
```

### **Consumer Side (Flink):**
```python
from pyflink.datastream.connectors import FlinkKafkaConsumer

# Consumer automatically deserializes using schema registry
kafka_source = FlinkKafkaConsumer(
    topics=['txn.events'],
    deserialization_schema=AvroDeserializationSchema.for_specific(
        'schemas/transactions.v1.avsc'
    ),
    properties={
        'bootstrap.servers': 'localhost:9092',
        'group.id': 'fraud-detection-job'
    }
)
```

---

## ⚠️ **Schema Testing & Validation**

### **Before Deploying Schema Changes:**
```bash
# 1. Validate syntax & compatibility
python schemas/validate_schemas.py

# 2. Test in staging environment
docker-compose up schema-registry
make register-schemas

# 3. Integration testing
# - Deploy new schema
# - Run old consumers against new data
# - Verify no crashes/data loss

# 4. Gradual production rollout
```

### **Validation Checks:**
- ✅ Avro syntax correctness
- ✅ Backward compatibility between versions
- ✅ Required fields have defaults
- ✅ Optional fields are properly nullable

---

## 💡 **Key Differences from Batch**

| Aspect | Batch | Streaming |
|--------|-------|-----------|
| **Schema Discovery** | Runtime (flexible) | Compile-time (rigid) |
| **Error Handling** | Reprocess files | Must handle in-stream |
| **Schema Changes** | New files | Backward-compatible evolution |
| **Validation** | During processing | At ingestion |
| **Performance** | Can reshuffle data | Partitioning is permanent |
| **Debugging** | Easy to replay | Complex state management |

---

## 🚀 **Why This Architecture Wins**

### **1. Performance:**
- **Efficient serialization**: Binary Avro vs JSON text
- **Smart partitioning**: Related events co-located
- **Schema caching**: Fetch schema once, reuse for millions of messages

### **2. Reliability:**
- **Type safety**: Catch errors before they propagate
- **Graceful evolution**: Add features without downtime
- **Cross-team contracts**: Clear data interfaces

### **3. Developer Experience:**
- **Auto-serialization**: No manual parsing code
- **IDE support**: Schema-aware tooling
- **Documentation**: Schema IS the documentation

---

# 📘 Chapter 2: Streaming Data Generators
## From Schema Contracts to Real Data Production

---

## 🏗️ **The Producer Pattern: BaseEventGenerator**

### **Foundation Architecture**
```python
class BaseEventGenerator(ABC):
    def __init__(self, topic, schema_file, events_per_second=10.0):
        # 1. Load Avro schema (connects to Chapter 1!)
        self.schema = self._load_schema(schema_file)
        
        # 2. Configure production-grade Kafka producer
        self.producer = KafkaProducer(
            value_serializer=self._serialize_avro,  # Schema-based validation!
            acks='all',                             # Durability
            retries=3,                             # Reliability
            max_in_flight_requests_per_connection=1, # Ordering
            compression_type='snappy',              # Performance
            batch_size=16384,                      # Throughput
            linger_ms=10                           # Latency optimization
        )
```

### **Key Streaming Concepts:**
- ✅ **Schema-Driven Serialization**: Every event validated against Avro schema
- ✅ **Production Configuration**: Durability + ordering + performance tuned
- ✅ **Rate Limiting**: `events_per_second` prevents downstream overwhelm
- ✅ **Template Pattern**: Abstract methods force business logic implementation

### **The Streaming Loop:**
```python
def run(self):
    delay = 1.0 / self.events_per_second  # Rate limiting calculation
    
    while True:
        event = self.generate_event()        # Business logic (abstract)
        key = self.get_partition_key(event)  # Partitioning strategy (abstract)
        self.producer.send(topic, key=key, value=event)
        time.sleep(delay)                    # Backpressure protection
```

---

## 🧪 **Advanced Testing: Dependency Injection & Mocking**

### **The Testing Problem:**
How do you test streaming producers without Kafka infrastructure?

### **Solution: Monkey Patching + Mock Objects**
```python
class MockKafkaProducer:
    """Replace real Kafka with in-memory storage."""
    def __init__(self, **kwargs):
        self.events: List[Dict[str, Any]] = []  # Collect events locally
        
    def send(self, topic, key=None, value=None):
        self.events.append({
            'topic': topic, 'key': key, 'value': value,
            'timestamp': time.time()
        })
        return MockFuture()  # Callback compatibility

# Dependency injection via monkey patching
import generators.base_generator as bg
original_producer = bg.KafkaProducer
bg.KafkaProducer = MockKafkaProducer  # Replace globally

# Now all generators use mock automatically!
generator = TransactionGenerator(events_per_second=100)
```

### **Multi-Level Validation:**
```python
# 1. Schema Compliance
required_fields = ['txn_id', 'card_id', 'user_id', 'amount']
for event in events:
    for field in required_fields:
        assert field in event, f"Missing field: {field}"

# 2. Data Quality  
amounts = [e['amount'] for e in events]
assert min(amounts) > 0, "Negative amounts found"
assert max(amounts) < 10000, "Unrealistic amounts found"

# 3. Business Logic
fraud_events = [e for e in events if 'risk_flags' in e.get('metadata', {})]
fraud_rate = len(fraud_events) / len(events)
assert 0.08 <= fraud_rate <= 0.12, f"Fraud rate {fraud_rate:.2%} outside expected range"

# 4. Referential Integrity  
unique_users = len(set(e['user_id'] for e in events))
assert unique_users > 1, "Should have multiple users per batch"
```

---

## 💼 **Real-World Business Logic: Transaction Generator**

### **Fraud Injection Patterns:**
```python
def generate_event(self):
    # Realistic fraud modeling
    is_fraud = random.random() < self.fraud_rate
    
    if is_fraud:
        # Fraudulent transactions have different patterns:
        if random.random() < 0.3:  # 30% test transactions
            amount = random.uniform(1.0, 5.0)
        elif random.random() < 0.4:  # 40% large fraud
            amount *= random.uniform(5.0, 20.0)
        
        # Geographic anomalies
        country = random.choice(['CN', 'RU'])  # High-risk countries
        ip_prefix = random.choice(['tor_exit_', 'proxy_'])  # Suspicious IPs
```

### **Merchant Category Modeling:**
```python
merchant_categories = {
    'grocery': {'mcc': '5411', 'avg_amount': 85.0, 'fraud_likelihood': 0.1},
    'online': {'mcc': '5967', 'avg_amount': 75.0, 'fraud_likelihood': 0.3},
    'atm': {'mcc': '6011', 'avg_amount': 100.0, 'fraud_likelihood': 0.4}
}
```

### **Critical Partitioning Strategy:**
```python
def get_partition_key(self, event: Dict[str, Any]) -> str:
    return event['card_id']  # Fraud detection locality!
```
**Why `card_id`?** All transactions for a card go to same partition → efficient fraud pattern detection

---

## 🔗 **Cross-Stream Referential Integrity**

### **Session Management Across Generators:**
```python
class UserSessionManager:
    """Ensures consistency across transaction, click, and device events."""
    
    def get_user_session(self):
        # Returns consistent user_id, session_id, device_id
        return {
            'user_id': 'user_123',     # Links transactions ↔ clicks
            'session_id': 'sess_456',  # Session-based features
            'device_id': 'dev_789'     # Device fingerprinting
        }

# Used by ALL generators
session = session_manager.get_user_session()

# Transaction event
txn_event = {
    'user_id': session['user_id'],    # Same user
    'device_id': session['device_id'] # Same device
}

# Click event (different generator!)
click_event = {
    'user_id': session['user_id'],    # Same user!
    'device_id': session['device_id'] # Same device!
}
```

**This enables powerful cross-stream joins in feature engineering!**

---

## 🎯 **Senior-Level Testing Patterns**

### **1. Test-Driven Development for Streaming:**
- ✅ **Mock external dependencies** (Kafka, Schema Registry)
- ✅ **Test business logic independently** of infrastructure
- ✅ **Validate realistic data distributions**
- ✅ **Ensure cross-stream consistency**

### **2. Production-Ready Validation:**
```python
def validate_transaction_realism(events):
    """Production data quality checks."""
    
    # Geographic consistency
    for event in events:
        if event['geo_country'] == 'US':
            assert event['currency'] == 'USD'
            assert event['ip_address'].startswith(('192.168.', '10.0.'))
    
    # Temporal patterns
    timestamps = [e['timestamp'] for e in events]
    assert timestamps == sorted(timestamps), "Events should be time-ordered"
    
    # Business rules
    high_value_txns = [e for e in events if e['amount'] > 1000]
    for txn in high_value_txns:
        assert 'risk_flags' in txn.get('metadata', {}), "High-value transactions should be flagged"
```

### **3. Dependency Injection Benefits:**
- **Fast iteration**: Test without infrastructure setup
- **Deterministic results**: Controlled data generation
- **Parallel development**: Multiple teams can work independently
- **CI/CD friendly**: Tests run anywhere without external dependencies

---

## 💡 **Key Learning: Advanced Testing Techniques**

### **Monkey Patching:**
```python
# Replace dependencies at module level
import module
original_class = module.ExternalDependency
module.ExternalDependency = MockDependency
# All code using module.ExternalDependency now uses mock!
```

### **Dependency Injection:**
```python
# Make dependencies configurable
class Producer:
    def __init__(self, kafka_client=None):
        self.kafka = kafka_client or RealKafkaProducer()
        
# Test with mock
producer = Producer(kafka_client=MockKafkaProducer())
```

### **Mock Object Design:**
```python
class MockKafkaProducer:
    def __init__(self):
        self.events = []  # State tracking
        
    def send(self, topic, value):
        self.events.append(value)
        return MockFuture()  # Interface compatibility
        
    def flush(self): pass    # No-op implementations
    def close(self): pass
```

---

## 🚀 **Interview Gold: Testing Streaming Systems**

**Junior Answer:** "I test with a local Kafka cluster"  
**Senior Answer:** "I use dependency injection to mock external systems, validate business logic independently with comprehensive data quality checks, then integration test with real infrastructure"

**You Now Understand:**
- ✅ **Monkey patching** for test isolation
- ✅ **Mock objects** with interface compatibility  
- ✅ **Multi-level validation** (schema, data quality, business rules)
- ✅ **Realistic data generation** for meaningful tests
- ✅ **Cross-stream consistency** testing

---

## 📖 **Next Steps in Your Streaming Journey**

1. **Practice schema evolution** with the validation scripts
2. **Understand stream joins** (how device_id links transactions ↔ clicks)
3. **Learn windowed aggregations** (fraud detection patterns)
4. **Explore state management** (how Flink handles stateful processing)
5. **Study backpressure** (what happens when consumers can't keep up)

---

# 📊 Chapter 3: Stream Processing & Feature Engineering
## From Raw Events to ML-Ready Features

---

## 🎯 **Two Approaches: Production vs Development**

### **Production: Flink Job (`jobs/feature_job.py`)**
```python
# Full PyFlink with exactly-once semantics
transaction_stream = env.from_source(kafka_source, watermark_strategy)
features = transaction_stream.process(TransactionFeatureProcessor())
features.map(RedisFeatureSink()).execute()
```

### **Development: Simplified Processor (`stream_processor.py`)**
```python
# Pure Python for rapid iteration
consumer = KafkaConsumer('txn.events')
for message in consumer:
    features = tx_computer.process_event(message.value)
    redis_client.set(feature_key, features)
```

---

## ⚡ **Key Streaming Concepts**

### **1. Event-Time Processing**
```python
# Events arrive out-of-order, but we process by event timestamp
watermark = max_timestamp - allowed_lateness  # 5 seconds behind latest
if event.timestamp < watermark:
    send_to_dlq(event)  # Too late!
```

### **2. Stateful Processing & Partitioning**
```python
# All events for same key → same processor instance  
.key_by(lambda event: event['card_id'])     # Fraud detection
.key_by(lambda event: event['user_id'])     # Personalization

# Each processor maintains state per key
state = {
    'card_123': {'txn_count': 5, 'amount_sum': 1250.0},
    'card_456': {'txn_count': 2, 'amount_sum': 300.0}
}
```

### **3. Windowed Aggregations**
```python
# Sliding 5-minute windows for real-time features
window = SlidingWindow(window_size_ms=5*60*1000)
window.add_event(timestamp, event)

# Compute features over window
features = {
    'txn_count_5m': len(window.events),
    'amount_avg_5m': sum(amounts) / len(amounts),
    'velocity_score': len(events) / time_span_hours
}
```

---

## 🚨 **Fraud Detection Features**
```python
# Real-time risk indicators
features = {
    'txn_count_5m': 8,                    # High frequency
    'unique_countries_5m': 3,             # Geographic spread  
    'velocity_score': 0.9,               # Very fast transactions
    'high_risk_txn_ratio': 0.4,          # 40% high-risk merchants
    'time_since_last_txn_min': 0.5       # 30 seconds apart
}

# Risk flags for immediate alerting
if features['velocity_score'] > 0.7 and features['unique_countries_5m'] > 2:
    metadata['risk_flags'] = 'high_velocity_geo_anomaly'
```

## 🎯 **Personalization Features**
```python
# User engagement patterns
features = {
    'session_duration_min': 12.5,        # Active session
    'page_views_5m': 15,                 # High engagement
    'cart_conversion_rate': 0.3,         # Strong purchase intent
    'category_affinity': 'electronics',   # Primary interest
    'engagement_score': 0.85             # Highly engaged user
}
```

---

## 🔄 **Exactly-Once vs At-Least-Once**

### **Exactly-Once (Flink Production)**
```python
# Coordinated checkpointing every 30 seconds
env.enable_checkpointing(30000)
env.get_checkpoint_config().set_checkpointing_mode(EXACTLY_ONCE)

# On failure: restore state + replay from last checkpoint
# Result: No duplicates, no data loss
```

### **At-Least-Once (Simplified)**
```python
# Auto-commit every 5 seconds
consumer = KafkaConsumer(enable_auto_commit=True)

# On failure: may reprocess some events
# Result: Possible duplicates, but simpler to implement
```

---

## 🎛️ **Feature Sink: Redis Storage**
```python
# Multi-layer storage strategy
feature_key = f"features:card:{card_id}:transaction"      # Current features
latest_key = f"features:latest:card:{card_id}"           # Quick lookup
ts_key = f"features:ts:card:{card_id}:transaction"       # Time series

# TTL for automatic cleanup
redis.set(feature_key, features, ex=24*3600)  # 24-hour TTL
```

---

## 🧪 **Testing Without Infrastructure**
```python
# Mock Kafka for unit testing
class MockKafkaConsumer:
    def __init__(self, events):
        self.events = iter(events)
    def __iter__(self):
        return self.events

# Test feature computation logic
test_events = [generate_test_transaction()]
processor = TransactionFeatureComputer(config)
features = processor.process_event(test_events[0])
assert features['txn_count_5m'] == 1
```

---

## 💡 **Key Architectural Decisions**

| Aspect | Flink Job | Simplified |
|--------|-----------|------------|
| **Deployment** | Distributed cluster | Single process |
| **State** | RocksDB + checkpoints | In-memory dictionaries |
| **Fault Tolerance** | Exactly-once | Manual restart |
| **Throughput** | 50k+ events/sec | 1k events/sec |
| **Development** | Complex setup | Simple Python |
| **Use Case** | Production | Development/Testing |

---

## 🚀 **Interview Talking Points**

**"I built both approaches to understand trade-offs:**
- **Flink for production**: Exactly-once semantics, fault tolerance, scale
- **Simplified for development**: Fast iteration, easy debugging, local testing
- **Same business logic**: Fraud detection algorithms work identically
- **Progressive enhancement**: Start simple, add complexity when needed"

---

## Python Abstract Learnt

python can have two classes inherited, the order matters (both define functions, the one goes first gets executed)


Interview Story:
> "I designed this as a microservices platform from day one. Each service - event generation, stream processing, inference, and training - runs in its own container with isolated dependencies. The architecture maps directly to cloud services like ECS or Cloud Run, and I can scale each component independently based on load."
Key Differentiators:
🔥 Sub-150ms inference with real-time features
🔥 Production-grade observability (Prometheus, Grafana)
🔥 One-command demo showing complete workflow
🔥 Cloud-portable containers ready for any platform



## Microservices

Each service has theri own dockerfile and requirements, use docker compose and make file to orchestrate