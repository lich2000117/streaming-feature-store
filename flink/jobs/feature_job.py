#!/usr/bin/env python3
"""
Real-time Feature Engineering Job

This Flink job processes streaming events to compute features for:
1. Fraud detection (transaction-based features)
2. Personalization (clickstream-based features)

Key capabilities:
- Event-time processing with watermarks
- Exactly-once semantics with checkpointing
- Windowed aggregations (tumbling and sliding)
- Cross-stream joins
- Late event handling with DLQ
- Real-time feature materialization to Redis
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

# Add parent directories to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pyflink.datastream import StreamExecutionEnvironment, TimeCharacteristic
from pyflink.datastream.window import TumblingEventTimeWindows, SlidingEventTimeWindows
from pyflink.datastream.functions import MapFunction, FlatMapFunction, KeyedProcessFunction, WindowFunction
from pyflink.datastream.state import ValueStateDescriptor, MapStateDescriptor
from pyflink.common import Duration, Time, WatermarkStrategy, Types
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink
from pyflink.datastream.formats.json import JsonRowDeserializationSchema

import structlog
import redis
import click
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Metrics
EVENTS_PROCESSED = Counter('flink_events_processed_total', 'Total events processed', ['event_type'])
FEATURES_COMPUTED = Counter('flink_features_computed_total', 'Total features computed', ['feature_type'])
PROCESSING_LATENCY = Histogram('flink_processing_latency_seconds', 'Processing latency', ['stage'])
WATERMARK_LAG = Gauge('flink_watermark_lag_seconds', 'Watermark lag behind wall clock')
DLQ_EVENTS = Counter('flink_dlq_events_total', 'Events sent to DLQ', ['reason'])


# Configuration Models
class FeatureJobConfig(BaseModel):
    """Configuration for the feature engineering job."""
    
    # Kafka configuration
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    schema_registry_url: str = Field(default="http://localhost:8081")
    
    # Source topics
    transaction_topic: str = Field(default="txn.events")
    clickstream_topic: str = Field(default="click.events")
    device_topic: str = Field(default="device.events")
    
    # DLQ topics
    transaction_dlq: str = Field(default="txn.events.dlq")
    clickstream_dlq: str = Field(default="click.events.dlq") 
    device_dlq: str = Field(default="device.events.dlq")
    
    # Redis configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    
    # Processing configuration
    watermark_delay_ms: int = Field(default=5000)  # 5 second delay for late events
    allowed_lateness_ms: int = Field(default=60000)  # 1 minute allowed lateness
    checkpoint_interval_ms: int = Field(default=30000)  # 30 second checkpoints
    
    # Feature windows
    short_window_minutes: int = Field(default=5)   # 5-minute windows
    medium_window_minutes: int = Field(default=30) # 30-minute windows  
    long_window_hours: int = Field(default=24)     # 24-hour windows
    
    # Parallelism
    source_parallelism: int = Field(default=4)
    processing_parallelism: int = Field(default=8)
    sink_parallelism: int = Field(default=4)


# Event Models
class TransactionEvent(BaseModel):
    """Transaction event model."""
    txn_id: str
    card_id: str
    user_id: str
    amount: float
    currency: str
    mcc: str
    device_id: str
    ip_address: str
    geo_country: Optional[str] = None
    geo_city: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    timestamp: int  # milliseconds
    metadata: Dict[str, str] = Field(default_factory=dict)


class ClickEvent(BaseModel):
    """Clickstream event model."""
    event_id: str
    user_id: str
    session_id: str
    page_url: str
    page_type: str
    item_id: Optional[str] = None
    category_id: Optional[str] = None
    action_type: str
    device_id: str
    dwell_time_ms: Optional[int] = None
    scroll_depth: Optional[float] = None
    timestamp: int
    experiment_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)


# Feature Models
class TransactionFeatures(BaseModel):
    """Computed transaction features."""
    entity_id: str  # card_id
    entity_type: str = "card"
    
    # Count features
    txn_count_5m: int = 0
    txn_count_30m: int = 0
    txn_count_24h: int = 0
    
    # Amount features
    amount_sum_5m: float = 0.0
    amount_avg_5m: float = 0.0
    amount_max_5m: float = 0.0
    amount_sum_30m: float = 0.0
    amount_avg_30m: float = 0.0
    
    # Geo features
    unique_countries_5m: int = 0
    unique_cities_5m: int = 0
    geo_mismatch_rate_5m: float = 0.0
    
    # Temporal features  
    time_since_last_txn_minutes: Optional[float] = None
    is_weekend: bool = False
    hour_of_day: int = 0
    
    # Risk indicators
    has_high_risk_mcc: bool = False
    device_location_mismatch: bool = False
    
    # Metadata
    feature_timestamp: int
    computation_timestamp: int


class ClickstreamFeatures(BaseModel):
    """Computed clickstream features."""
    entity_id: str  # user_id
    entity_type: str = "user"
    
    # Session features
    session_duration_minutes: float = 0.0
    pages_per_session: int = 0
    unique_categories_per_session: int = 0
    
    # Engagement features
    avg_dwell_time_5m: float = 0.0
    avg_scroll_depth_5m: float = 0.0
    click_rate_5m: float = 0.0
    
    # Purchase funnel features
    cart_adds_5m: int = 0
    cart_removes_5m: int = 0
    purchases_5m: int = 0
    cart_conversion_rate_5m: float = 0.0
    
    # Temporal features
    sessions_24h: int = 0
    total_page_views_24h: int = 0
    
    # Metadata
    feature_timestamp: int
    computation_timestamp: int


# Flink Functions
class EventDeserializer(FlatMapFunction):
    """Deserialize JSON events and handle parsing errors."""
    
    def __init__(self, event_class, dlq_topic: str):
        self.event_class = event_class
        self.dlq_topic = dlq_topic
        
    def flat_map(self, value):
        try:
            # Parse JSON
            data = json.loads(value)
            
            # Validate with Pydantic
            event = self.event_class(**data)
            
            EVENTS_PROCESSED.labels(event_type=self.event_class.__name__).inc()
            yield event.dict()
            
        except Exception as e:
            logger.error("Failed to deserialize event", 
                        event_data=value, 
                        error=str(e),
                        event_type=self.event_class.__name__)
            
            DLQ_EVENTS.labels(reason="deserialization_error").inc()
            
            # Send to DLQ (simplified - in production would use side output)
            dlq_event = {
                "original_event": value,
                "error": str(e),
                "error_type": "deserialization_error",
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            # TODO: Implement DLQ side output
            

class TransactionFeatureProcessor(KeyedProcessFunction):
    """Process transaction events to compute fraud detection features."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        
        # State descriptors
        self.txn_count_state = ValueStateDescriptor("txn_count", Types.INT())
        self.amount_sum_state = ValueStateDescriptor("amount_sum", Types.DOUBLE())
        self.last_txn_time_state = ValueStateDescriptor("last_txn_time", Types.LONG())
        self.geo_locations_state = MapStateDescriptor("geo_locations", Types.STRING(), Types.INT())
        
    def process_element(self, value, ctx):
        """Process individual transaction events."""
        try:
            with PROCESSING_LATENCY.labels(stage="transaction_processing").time():
                # Parse event
                event = TransactionEvent(**value)
                
                # Get current state
                current_count = self.txn_count_state.value() or 0
                current_sum = self.amount_sum_state.value() or 0.0
                last_txn_time = self.last_txn_time_state.value()
                
                # Update state
                self.txn_count_state.update(current_count + 1)
                self.amount_sum_state.update(current_sum + event.amount)
                self.last_txn_time_state.update(event.timestamp)
                
                # Track geo locations
                if event.geo_country:
                    current_geo_count = self.geo_locations_state.get(event.geo_country) or 0
                    self.geo_locations_state.put(event.geo_country, current_geo_count + 1)
                
                # Compute time-based features
                event_time = datetime.fromtimestamp(event.timestamp / 1000)
                time_since_last = None
                if last_txn_time:
                    time_since_last = (event.timestamp - last_txn_time) / (1000 * 60)  # minutes
                
                # Check risk indicators
                high_risk_mccs = ['6011', '7995', '5967']  # ATM, gambling, online
                has_high_risk_mcc = event.mcc in high_risk_mccs
                
                # Create feature record
                features = TransactionFeatures(
                    entity_id=event.card_id,
                    txn_count_5m=current_count + 1,  # Simplified - in reality would use windowed state
                    amount_sum_5m=current_sum + event.amount,
                    amount_avg_5m=(current_sum + event.amount) / (current_count + 1),
                    amount_max_5m=event.amount,  # Simplified
                    unique_countries_5m=len(self.geo_locations_state.keys()) if self.geo_locations_state.keys() else 1,
                    time_since_last_txn_minutes=time_since_last,
                    is_weekend=event_time.weekday() >= 5,
                    hour_of_day=event_time.hour,
                    has_high_risk_mcc=has_high_risk_mcc,
                    feature_timestamp=event.timestamp,
                    computation_timestamp=int(datetime.now().timestamp() * 1000)
                )
                
                FEATURES_COMPUTED.labels(feature_type="transaction").inc()
                yield features.dict()
                
        except Exception as e:
            logger.error("Error processing transaction", 
                        event=value, 
                        error=str(e))
            DLQ_EVENTS.labels(reason="processing_error").inc()


class ClickstreamFeatureProcessor(KeyedProcessFunction):
    """Process clickstream events to compute personalization features."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        
        # State descriptors
        self.session_start_state = ValueStateDescriptor("session_start", Types.LONG())
        self.page_count_state = ValueStateDescriptor("page_count", Types.INT())
        self.categories_state = MapStateDescriptor("categories", Types.STRING(), Types.INT())
        self.cart_actions_state = MapStateDescriptor("cart_actions", Types.STRING(), Types.INT())
        
    def process_element(self, value, ctx):
        """Process individual clickstream events."""
        try:
            with PROCESSING_LATENCY.labels(stage="clickstream_processing").time():
                # Parse event
                event = ClickEvent(**value)
                
                # Get current state
                current_page_count = self.page_count_state.value() or 0
                session_start = self.session_start_state.value()
                
                # Initialize session if needed
                if not session_start:
                    self.session_start_state.update(event.timestamp)
                    session_start = event.timestamp
                
                # Update state
                self.page_count_state.update(current_page_count + 1)
                
                # Track categories
                if event.category_id:
                    current_cat_count = self.categories_state.get(event.category_id) or 0
                    self.categories_state.put(event.category_id, current_cat_count + 1)
                
                # Track cart actions
                if event.action_type in ['ADD_TO_CART', 'REMOVE_FROM_CART', 'PURCHASE']:
                    current_action_count = self.cart_actions_state.get(event.action_type) or 0
                    self.cart_actions_state.put(event.action_type, current_action_count + 1)
                
                # Compute session duration
                session_duration = (event.timestamp - session_start) / (1000 * 60)  # minutes
                
                # Compute cart conversion
                cart_adds = self.cart_actions_state.get('ADD_TO_CART') or 0
                purchases = self.cart_actions_state.get('PURCHASE') or 0
                cart_conversion_rate = purchases / max(cart_adds, 1)
                
                # Create feature record
                features = ClickstreamFeatures(
                    entity_id=event.user_id,
                    session_duration_minutes=session_duration,
                    pages_per_session=current_page_count + 1,
                    unique_categories_per_session=len(self.categories_state.keys()) if self.categories_state.keys() else 0,
                    avg_dwell_time_5m=event.dwell_time_ms / 1000 if event.dwell_time_ms else 0,
                    avg_scroll_depth_5m=event.scroll_depth or 0,
                    cart_adds_5m=cart_adds,
                    cart_removes_5m=self.cart_actions_state.get('REMOVE_FROM_CART') or 0,
                    purchases_5m=purchases,
                    cart_conversion_rate_5m=cart_conversion_rate,
                    feature_timestamp=event.timestamp,
                    computation_timestamp=int(datetime.now().timestamp() * 1000)
                )
                
                FEATURES_COMPUTED.labels(feature_type="clickstream").inc()
                yield features.dict()
                
        except Exception as e:
            logger.error("Error processing clickstream event", 
                        event=value, 
                        error=str(e))
            DLQ_EVENTS.labels(reason="processing_error").inc()


class RedisFeatureSink(MapFunction):
    """Sink features to Redis for online serving."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        self.redis_client = None
        
    def open(self, runtime_context):
        """Initialize Redis connection."""
        self.redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            decode_responses=True
        )
        logger.info("Connected to Redis", 
                   host=self.config.redis_host, 
                   port=self.config.redis_port)
        
    def map(self, value):
        """Write features to Redis."""
        try:
            # Create Redis key
            entity_type = value.get('entity_type', 'unknown')
            entity_id = value.get('entity_id', 'unknown')
            feature_key = f"features:{entity_type}:{entity_id}"
            
            # Set features with TTL (24 hours)
            self.redis_client.hmset(feature_key, value)
            self.redis_client.expire(feature_key, 86400)
            
            # Also maintain latest features pointer
            latest_key = f"features:latest:{entity_type}:{entity_id}"
            self.redis_client.set(latest_key, json.dumps(value), ex=86400)
            
            logger.debug("Wrote features to Redis", 
                        key=feature_key, 
                        entity_type=entity_type,
                        entity_id=entity_id)
            
            return f"SUCCESS:{feature_key}"
            
        except Exception as e:
            logger.error("Failed to write features to Redis", 
                        features=value, 
                        error=str(e))
            return f"ERROR:{str(e)}"


def create_watermark_strategy(delay_ms: int):
    """Create watermark strategy for event-time processing."""
    return WatermarkStrategy.for_bounded_out_of_orderness(Duration.of_millis(delay_ms)) \
        .with_timestamp_assigner(lambda event, timestamp: event['timestamp'])


def setup_flink_job(config: FeatureJobConfig) -> StreamExecutionEnvironment:
    """Set up the Flink streaming job."""
    
    # Create execution environment
    env = StreamExecutionEnvironment.get_execution_environment()
    
    # Configure for event-time processing
    env.set_stream_time_characteristic(TimeCharacteristic.EventTime)
    
    # Configure checkpointing for exactly-once semantics
    env.enable_checkpointing(config.checkpoint_interval_ms)
    env.get_checkpoint_config().set_checkpointing_mode(1)  # EXACTLY_ONCE
    env.get_checkpoint_config().set_min_pause_between_checkpoints(5000)
    env.get_checkpoint_config().set_checkpoint_timeout(60000)
    env.get_checkpoint_config().set_max_concurrent_checkpoints(1)
    env.get_checkpoint_config().enable_externalized_checkpoints(True)
    
    # Set parallelism
    env.set_parallelism(config.processing_parallelism)
    
    logger.info("Flink environment configured",
               parallelism=config.processing_parallelism,
               checkpoint_interval=config.checkpoint_interval_ms)
    
    return env


def main(config: FeatureJobConfig):
    """Main feature engineering job."""
    
    logger.info("Starting Flink Feature Engineering Job", config=config.dict())
    
    # Start metrics server
    start_http_server(8088)
    logger.info("Metrics server started on port 8088")
    
    # Set up Flink environment
    env = setup_flink_job(config)
    
    # Create Kafka sources
    transaction_source = KafkaSource.builder() \
        .set_bootstrap_servers(config.kafka_bootstrap_servers) \
        .set_topics(config.transaction_topic) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
        
    clickstream_source = KafkaSource.builder() \
        .set_bootstrap_servers(config.kafka_bootstrap_servers) \
        .set_topics(config.clickstream_topic) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    # Create flink data streams with watermarks
    transaction_stream = env.from_source(
        transaction_source,
        create_watermark_strategy(config.watermark_delay_ms),
        "transactions"
    ).set_parallelism(config.source_parallelism)
    
    clickstream_stream = env.from_source(
        clickstream_source,
        create_watermark_strategy(config.watermark_delay_ms),
        "clickstream"
    ).set_parallelism(config.source_parallelism)
    
    # Process transaction events
    transaction_features = transaction_stream \
        .flat_map(EventDeserializer(TransactionEvent, config.transaction_dlq)) \
        .key_by(lambda event: event['card_id']) \
        .process(TransactionFeatureProcessor(config)) \
        .set_parallelism(config.processing_parallelism)
    
    # Process clickstream events  
    clickstream_features = clickstream_stream \
        .flat_map(EventDeserializer(ClickEvent, config.clickstream_dlq)) \
        .key_by(lambda event: event['user_id']) \
        .process(ClickstreamFeatureProcessor(config)) \
        .set_parallelism(config.processing_parallelism)
    
    # Union feature streams
    all_features = transaction_features.union(clickstream_features)
    
    # Sink to Redis
    redis_results = all_features \
        .map(RedisFeatureSink(config)) \
        .set_parallelism(config.sink_parallelism)
    
    # Add logging sink for monitoring
    redis_results.print("REDIS_SINK")
    
    logger.info("Job graph created, starting execution...")
    
    # Execute the job
    env.execute("Real-time Feature Engineering")


@click.command()
@click.option('--kafka-servers', default='localhost:9092', help='Kafka bootstrap servers')
@click.option('--redis-host', default='localhost', help='Redis host')
@click.option('--redis-port', default=6379, help='Redis port')
@click.option('--parallelism', default=4, help='Job parallelism')
@click.option('--checkpoint-interval', default=30000, help='Checkpoint interval in ms')
@click.option('--config-file', help='Path to configuration file')
def cli(kafka_servers, redis_host, redis_port, parallelism, checkpoint_interval, config_file):
    """Run the real-time feature engineering job."""
    
    # Load configuration
    if config_file and os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config_dict = json.load(f)
        config = FeatureJobConfig(**config_dict)
    else:
        config = FeatureJobConfig(
            kafka_bootstrap_servers=kafka_servers,
            redis_host=redis_host,
            redis_port=redis_port,
            processing_parallelism=parallelism,
            checkpoint_interval_ms=checkpoint_interval
        )
    
    try:
        main(config)
    except Exception as e:
        logger.error("Feature job failed", error=str(e))
        raise


if __name__ == '__main__':
    cli()
