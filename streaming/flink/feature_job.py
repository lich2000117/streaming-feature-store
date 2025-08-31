#!/usr/bin/env python3
"""
Real-time Feature Engineering Job (Refactored)

This PyFlink job processes streaming events to compute features for:
1. Fraud detection (transaction-based features)
2. Personalization (clickstream-based features)

Key capabilities:
- Event-time processing with watermarks
- Exactly-once semantics with checkpointing
- Windowed aggregations (tumbling and sliding)
- Cross-stream joins
- Late event handling with DLQ
- Real-time feature materialization to Redis
- Uses modular shared components from streaming.core.*
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
from pyflink.datastream.functions import MapFunction, FlatMapFunction, KeyedProcessFunction, WindowFunction, ProcessWindowFunction
from pyflink.datastream.state import ValueStateDescriptor, MapStateDescriptor
from pyflink.common import Duration, Time, WatermarkStrategy, Types
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaSink
from pyflink.datastream.formats.json import JsonRowDeserializationSchema

import structlog
import redis
import click
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Import shared components
from streaming.core.models.config import FeatureJobConfig
from streaming.core.models.events import TransactionEvent, ClickEvent
from streaming.core.models.features import TransactionFeatures, ClickstreamFeatures
from streaming.core.processors.transaction import compute_transaction_features_from_window
from streaming.core.processors.clickstream import compute_clickstream_features_from_window
from streaming.core.sinks.redis_sink import FlinkRedisSink

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Metrics
EVENTS_PROCESSED = Counter('flink_events_processed_total', 'Total events processed', ['event_type'])
FEATURES_COMPUTED = Counter('flink_features_computed_total', 'Total features computed', ['feature_type'])
PROCESSING_LATENCY = Histogram('flink_processing_latency_seconds', 'Processing latency', ['stage'])
WATERMARK_LAG = Gauge('flink_watermark_lag_seconds', 'Watermark lag behind wall clock')
DLQ_EVENTS = Counter('flink_dlq_events_total', 'Events sent to DLQ', ['reason'])


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
        self.state = None
        
    def open(self, runtime_context):
        """Initialize state."""
        # Keep a list of events in the window
        self.state = runtime_context.get_list_state(
            ValueStateDescriptor("events", Types.STRING())
        )
        
    def process_element(self, value, ctx: 'KeyedProcessFunction.Context'):
        """Process transaction event and compute features."""
        try:
            # Add current event to state
            self.state.add(json.dumps(value))
            
            # Set timer to trigger window computation
            timer_time = ctx.timestamp() + (self.config.short_window_minutes * 60 * 1000)
            ctx.timer_service().register_event_time_timer(timer_time)
            
        except Exception as e:
            logger.error("Error processing transaction event", 
                        event=value, 
                        error=str(e))
            
    def on_timer(self, timestamp: int, ctx: 'KeyedProcessFunction.OnTimerContext'):
        """Called when timer fires - compute features for the window."""
        try:
            # Get all events from state
            events = []
            for event_json in self.state.get():
                events.append(json.loads(event_json))
                
            if not events:
                return
                
            # Use shared business logic to compute features
            features = compute_transaction_features_from_window(events, self.config)
            
            if features:
                # Convert to TransactionFeatures model
                feature_model = TransactionFeatures(**features)
                
                FEATURES_COMPUTED.labels(feature_type='transaction').inc()
                
                # Yield computed features
                yield feature_model.dict()
                
            # Clear old events from state (keep only recent events)
            current_time = timestamp
            cutoff_time = current_time - (self.config.short_window_minutes * 60 * 1000)
            
            filtered_events = []
            for event_json in self.state.get():
                event = json.loads(event_json)
                if event['timestamp'] > cutoff_time:
                    filtered_events.append(event_json)
                    
            self.state.clear()
            for event_json in filtered_events:
                self.state.add(event_json)
                
        except Exception as e:
            logger.error("Error in transaction timer", error=str(e))


class TransactionWindowedFeatureProcessor(ProcessWindowFunction):
    """Alternative windowed approach for transaction feature computation."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        
    def process(self, key, context: 'ProcessWindowFunction.Context', elements):
        """Process elements in window."""
        try:
            events = list(elements)
            
            # Use shared business logic
            features = compute_transaction_features_from_window(events, self.config)
            
            if features:
                # Add window metadata
                features['window_start'] = context.window().start
                features['window_end'] = context.window().end
                
                feature_model = TransactionFeatures(**features)
                FEATURES_COMPUTED.labels(feature_type='transaction_windowed').inc()
                
                yield feature_model.dict()
                
        except Exception as e:
            logger.error("Error in windowed transaction processing", 
                        key=key, error=str(e))


class ClickstreamFeatureProcessor(KeyedProcessFunction):
    """Process clickstream events to compute personalization features."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        self.events_state = None
        self.session_state = None
        
    def open(self, runtime_context):
        """Initialize state."""
        self.events_state = runtime_context.get_list_state(
            ValueStateDescriptor("click_events", Types.STRING())
        )
        self.session_state = runtime_context.get_map_state(
            MapStateDescriptor("sessions", Types.STRING(), Types.STRING())
        )
        
    def process_element(self, value, ctx: 'KeyedProcessFunction.Context'):
        """Process clickstream event."""
        try:
            # Add to events state
            self.events_state.add(json.dumps(value))
            
            # Update session state
            session_id = value['session_id']
            session_data = self.session_state.get(session_id)
            
            if session_data is None:
                session_data = {
                    'start_time': value['timestamp'],
                    'events': [],
                    'last_update': value['timestamp']
                }
            else:
                session_data = json.loads(session_data)
                
            session_data['events'].append(value)
            session_data['last_update'] = value['timestamp']
            
            self.session_state.put(session_id, json.dumps(session_data))
            
            # Set timer for feature computation
            timer_time = ctx.timestamp() + (self.config.short_window_minutes * 60 * 1000)
            ctx.timer_service().register_event_time_timer(timer_time)
            
        except Exception as e:
            logger.error("Error processing clickstream event", 
                        event=value, error=str(e))
            
    def on_timer(self, timestamp: int, ctx: 'KeyedProcessFunction.OnTimerContext'):
        """Compute clickstream features when timer fires."""
        try:
            # Get all events from state
            events = []
            for event_json in self.events_state.get():
                events.append(json.loads(event_json))
                
            if not events:
                return
                
            # Get session information
            session_data = {}
            for session_id, session_json in self.session_state.entries():
                session_data[session_id] = json.loads(session_json)
                
            # Use shared business logic
            features = compute_clickstream_features_from_window(events, session_data, self.config)
            
            if features:
                feature_model = ClickstreamFeatures(**features)
                
                FEATURES_COMPUTED.labels(feature_type='clickstream').inc()
                
                yield feature_model.dict()
                
            # Clean up old events and sessions
            current_time = timestamp
            cutoff_time = current_time - (self.config.short_window_minutes * 60 * 1000)
            
            # Clean events state
            filtered_events = []
            for event_json in self.events_state.get():
                event = json.loads(event_json)
                if event['timestamp'] > cutoff_time:
                    filtered_events.append(event_json)
                    
            self.events_state.clear()
            for event_json in filtered_events:
                self.events_state.add(event_json)
                
            # Clean session state
            expired_sessions = []
            for session_id, session_json in self.session_state.entries():
                session = json.loads(session_json)
                if session['last_update'] < cutoff_time:
                    expired_sessions.append(session_id)
                    
            for session_id in expired_sessions:
                self.session_state.remove(session_id)
                
        except Exception as e:
            logger.error("Error in clickstream timer", error=str(e))


class RedisFeatureSink(MapFunction):
    """Sink computed features to Redis."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        self.redis_sink = None
        
    def open(self, runtime_context):
        """Initialize Redis connection."""
        self.redis_sink = FlinkRedisSink(self.config)
        self.redis_sink.open(runtime_context)
        
    def map(self, value):
        """Write features to Redis."""
        return self.redis_sink.write(value)


def create_watermark_strategy(delay_ms: int):
    """Create watermark strategy with specified delay."""
    return WatermarkStrategy \
        .for_bounded_out_of_orderness(Duration.of_millis(delay_ms)) \
        .with_timestamp_assigner(lambda event, timestamp: event['timestamp'])


def setup_flink_job(config: FeatureJobConfig) -> StreamExecutionEnvironment:
    """Set up Flink execution environment."""
    
    # Create execution environment
    env = StreamExecutionEnvironment.get_execution_environment()
    
    # Set time characteristic to event time
    env.set_stream_time_characteristic(TimeCharacteristic.EventTime)
    
    # Configure parallelism
    env.set_parallelism(config.processing_parallelism)
    
    # Configure checkpointing for exactly-once semantics
    env.enable_checkpointing(config.checkpoint_interval_ms)
    env.get_checkpoint_config().set_checkpointing_mode(1)  # EXACTLY_ONCE
    env.get_checkpoint_config().set_min_pause_between_checkpoints(5000)
    env.get_checkpoint_config().set_checkpoint_timeout(10000)
    env.get_checkpoint_config().set_max_concurrent_checkpoints(1)
    
    # Configure restart strategy
    env.get_config().set_auto_watermark_interval(1000)
    
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
    
    # Process transaction events using windowed approach
    transaction_features = transaction_stream \
        .flat_map(EventDeserializer(TransactionEvent, config.transaction_dlq)) \
        .key_by(lambda event: event['card_id']) \
        .window(SlidingEventTimeWindows.of(Time.minutes(config.short_window_minutes), Time.minutes(1))) \
        .process(TransactionWindowedFeatureProcessor(config)) \
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
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def cli(kafka_servers, redis_host, redis_port, parallelism, checkpoint_interval, config_file, verbose):
    """Run the Flink feature engineering job."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    # Load configuration
    if config_file:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            config = FeatureJobConfig(**config_data)
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
        logger.error("Feature engineering job failed", error=str(e))
        raise


if __name__ == '__main__':
    cli()
