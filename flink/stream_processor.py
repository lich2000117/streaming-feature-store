#!/usr/bin/env python3
"""
Simplified Stream Processor for Feature Engineering

This is a simplified version of the Flink job that can run without PyFlink.
It demonstrates the same streaming patterns using Kafka consumers directly.

Features:
- Real-time event processing
- Windowed aggregations
- Feature computation
- Redis sink
- Metrics and monitoring

Use this for development and testing before deploying to Flink.
"""

import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging

# Add parent directories to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kafka import KafkaConsumer
import redis
import click
import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Import our utilities
from flink.utils.watermarks import WatermarkGenerator, WatermarkConfig, LateEventHandler

# Import our generators for event models
from generators.txgen import TransactionGenerator
from generators.clickgen import ClickstreamGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)

# Metrics
EVENTS_PROCESSED = Counter('stream_events_processed_total', 'Total events processed', ['topic', 'status'])
FEATURES_COMPUTED = Counter('stream_features_computed_total', 'Total features computed', ['feature_type'])
PROCESSING_LATENCY = Histogram('stream_processing_latency_seconds', 'Processing latency')
WINDOW_SIZE = Gauge('stream_window_size', 'Current window size', ['window_type'])
REDIS_WRITES = Counter('stream_redis_writes_total', 'Redis write operations', ['status'])


@dataclass
class ProcessorConfig:
    """Configuration for the stream processor."""
    
    # Kafka settings
    kafka_bootstrap_servers: str = "localhost:9092"
    consumer_group: str = "feature-processor"
    topics: List[str] = field(default_factory=lambda: ["txn.events", "click.events"])
    
    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Processing settings
    window_size_minutes: int = 5
    window_slide_minutes: int = 1
    max_out_of_order_seconds: int = 30
    batch_size: int = 100
    
    # Feature settings
    feature_ttl_hours: int = 24
    enable_late_events: bool = True
    
    # Monitoring
    metrics_port: int = 8088


class SlidingWindow:
    """Sliding window implementation for aggregations."""
    
    def __init__(self, window_size_ms: int, slide_size_ms: int):
        self.window_size_ms = window_size_ms
        self.slide_size_ms = slide_size_ms
        self.events = deque()
        
    def add_event(self, timestamp: int, event: Dict[str, Any]):
        """Add event to window."""
        self.events.append((timestamp, event))
        self._cleanup_old_events(timestamp)
        
    def _cleanup_old_events(self, current_timestamp: int):
        """Remove events outside the window."""
        cutoff = current_timestamp - self.window_size_ms
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
            
    def get_events(self) -> List[tuple]:
        """Get all events in current window."""
        return list(self.events)
        
    def size(self) -> int:
        """Get number of events in window."""
        return len(self.events)


class TransactionFeatureComputer:
    """Compute features from transaction events."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.windows = defaultdict(lambda: SlidingWindow(
            config.window_size_minutes * 60 * 1000,
            config.window_slide_minutes * 60 * 1000
        ))
        
    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a transaction event and compute features."""
        try:
            card_id = event['card_id']
            timestamp = event['timestamp']
            amount = event['amount']
            
            # Add to sliding window
            window = self.windows[card_id]
            window.add_event(timestamp, event)
            
            # Compute windowed features
            window_events = window.get_events()
            
            if not window_events:
                return None
                
            # Count features
            txn_count = len(window_events)
            
            # Amount features
            amounts = [e[1]['amount'] for e in window_events]
            amount_sum = sum(amounts)
            amount_avg = amount_sum / len(amounts)
            amount_max = max(amounts)
            amount_min = min(amounts)
            
            # Geographic features
            countries = set(e[1].get('geo_country') for e in window_events if e[1].get('geo_country'))
            unique_countries = len(countries)
            
            # Time-based features
            timestamps = [e[0] for e in window_events]
            if len(timestamps) > 1:
                timestamps.sort()
                time_since_last = (timestamps[-1] - timestamps[-2]) / (1000 * 60)  # minutes
                avg_time_between = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1) / (1000 * 60)
            else:
                time_since_last = None
                avg_time_between = None
                
            # Risk indicators
            high_risk_mccs = ['6011', '7995', '5967']
            high_risk_txns = sum(1 for e in window_events if e[1].get('mcc') in high_risk_mccs)
            risk_ratio = high_risk_txns / len(window_events)
            
            # Velocity features
            velocity_score = 0.0
            if len(window_events) > 1:
                time_span_hours = (timestamps[-1] - timestamps[0]) / (1000 * 3600)
                if time_span_hours > 0:
                    txn_per_hour = len(window_events) / time_span_hours
                    velocity_score = min(txn_per_hour / 10.0, 1.0)  # Normalize to 0-1
            
            # Create feature record
            features = {
                'entity_id': card_id,
                'entity_type': 'card',
                'feature_type': 'transaction',
                
                # Count features
                'txn_count_5m': txn_count,
                
                # Amount features
                'amount_sum_5m': round(amount_sum, 2),
                'amount_avg_5m': round(amount_avg, 2),
                'amount_max_5m': round(amount_max, 2),
                'amount_min_5m': round(amount_min, 2),
                'amount_std_5m': round(float(np.std(amounts)) if len(amounts) > 1 else 0.0, 2),
                
                # Geographic features
                'unique_countries_5m': unique_countries,
                'geo_diversity_score': min(unique_countries / 3.0, 1.0),
                
                # Temporal features
                'time_since_last_txn_min': round(time_since_last, 2) if time_since_last else None,
                'avg_time_between_txns_min': round(avg_time_between, 2) if avg_time_between else None,
                'velocity_score': round(velocity_score, 3),
                
                # Risk features
                'high_risk_txn_ratio': round(risk_ratio, 3),
                'is_high_velocity': velocity_score > 0.7,
                'is_geo_diverse': unique_countries > 2,
                
                # Metadata
                'window_size_minutes': self.config.window_size_minutes,
                'feature_timestamp': timestamp,
                'computation_timestamp': int(time.time() * 1000),
                'window_event_count': len(window_events)
            }
            
            FEATURES_COMPUTED.labels(feature_type='transaction').inc()
            WINDOW_SIZE.labels(window_type='transaction').set(len(window_events))
            
            return features
            
        except Exception as e:
            logger.error("Error computing transaction features", 
                        event=event, 
                        error=str(e))
            return None


class ClickstreamFeatureComputer:
    """Compute features from clickstream events."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.user_windows = defaultdict(lambda: SlidingWindow(
            config.window_size_minutes * 60 * 1000,
            config.window_slide_minutes * 60 * 1000
        ))
        self.session_state = defaultdict(dict)
        
    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a clickstream event and compute features."""
        try:
            user_id = event['user_id']
            session_id = event['session_id']
            timestamp = event['timestamp']
            page_type = event['page_type']
            action_type = event['action_type']
            
            # Add to sliding window
            window = self.user_windows[user_id]
            window.add_event(timestamp, event)
            
            # Update session state
            session_key = f"{user_id}:{session_id}"
            if session_key not in self.session_state:
                self.session_state[session_key] = {
                    'start_time': timestamp,
                    'page_count': 0,
                    'categories': set(),
                    'cart_actions': defaultdict(int),
                    'last_action_time': timestamp
                }
                
            session = self.session_state[session_key]
            session['page_count'] += 1
            session['last_action_time'] = timestamp
            
            if event.get('category_id'):
                session['categories'].add(event['category_id'])
                
            if action_type in ['ADD_TO_CART', 'REMOVE_FROM_CART', 'PURCHASE']:
                session['cart_actions'][action_type] += 1
            
            # Compute windowed features
            window_events = window.get_events()
            
            if not window_events:
                return None
                
            # Session features
            session_duration_min = (timestamp - session['start_time']) / (1000 * 60)
            pages_per_session = session['page_count']
            unique_categories_session = len(session['categories'])
            
            # Engagement features
            dwell_times = [e[1].get('dwell_time_ms', 0) for e in window_events if e[1].get('dwell_time_ms')]
            avg_dwell_time = sum(dwell_times) / len(dwell_times) / 1000 if dwell_times else 0  # seconds
            
            scroll_depths = [e[1].get('scroll_depth', 0) for e in window_events if e[1].get('scroll_depth')]
            avg_scroll_depth = sum(scroll_depths) / len(scroll_depths) if scroll_depths else 0
            
            # Activity features
            page_views = len(window_events)
            unique_pages = len(set(e[1]['page_type'] for e in window_events))
            click_events = sum(1 for e in window_events if e[1]['action_type'] == 'CLICK')
            click_rate = click_events / len(window_events) if window_events else 0
            
            # Purchase funnel features
            cart_adds = session['cart_actions']['ADD_TO_CART']
            cart_removes = session['cart_actions']['REMOVE_FROM_CART']
            purchases = session['cart_actions']['PURCHASE']
            
            conversion_rate = purchases / max(cart_adds, 1)
            cart_abandonment_rate = cart_removes / max(cart_adds, 1)
            
            # Engagement score
            engagement_score = 0.0
            engagement_score += min(avg_dwell_time / 30.0, 1.0) * 0.3  # 30s baseline
            engagement_score += avg_scroll_depth * 0.2
            engagement_score += min(pages_per_session / 10.0, 1.0) * 0.3  # 10 pages baseline
            engagement_score += conversion_rate * 0.2
            
            # Create feature record
            features = {
                'entity_id': user_id,
                'entity_type': 'user',
                'feature_type': 'clickstream',
                
                # Session features
                'session_duration_min': round(session_duration_min, 2),
                'pages_per_session': pages_per_session,
                'unique_categories_session': unique_categories_session,
                
                # Engagement features
                'avg_dwell_time_sec': round(avg_dwell_time, 2),
                'avg_scroll_depth': round(avg_scroll_depth, 3),
                'page_views_5m': page_views,
                'unique_pages_5m': unique_pages,
                'click_rate_5m': round(click_rate, 3),
                
                # Purchase funnel features
                'cart_adds_session': cart_adds,
                'cart_removes_session': cart_removes,
                'purchases_session': purchases,
                'conversion_rate_session': round(conversion_rate, 3),
                'cart_abandonment_rate': round(cart_abandonment_rate, 3),
                
                # Derived features
                'engagement_score': round(engagement_score, 3),
                'is_high_engagement': engagement_score > 0.7,
                'is_likely_purchaser': conversion_rate > 0.1,
                
                # Metadata
                'session_id': session_id,
                'window_size_minutes': self.config.window_size_minutes,
                'feature_timestamp': timestamp,
                'computation_timestamp': int(time.time() * 1000),
                'window_event_count': len(window_events)
            }
            
            FEATURES_COMPUTED.labels(feature_type='clickstream').inc()
            WINDOW_SIZE.labels(window_type='clickstream').set(len(window_events))
            
            return features
            
        except Exception as e:
            logger.error("Error computing clickstream features", 
                        event=event, 
                        error=str(e))
            return None


class FeatureSink:
    """Sink features to Redis."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )
        
    def write_features(self, features: Dict[str, Any]) -> bool:
        """Write features to Redis."""
        try:
            entity_type = features['entity_type']
            entity_id = features['entity_id']
            feature_type = features['feature_type']
            
            # Create Redis keys
            feature_key = f"features:{entity_type}:{entity_id}:{feature_type}"
            latest_key = f"features:latest:{entity_type}:{entity_id}"
            
            # Write features with TTL
            ttl_seconds = self.config.feature_ttl_hours * 3600
            
            # Store detailed features
            self.redis_client.hmset(feature_key, features)
            self.redis_client.expire(feature_key, ttl_seconds)
            
            # Store latest features pointer
            self.redis_client.set(latest_key, json.dumps(features), ex=ttl_seconds)
            
            # Also store in time-series format for historical analysis
            ts_key = f"features:ts:{entity_type}:{entity_id}:{feature_type}"
            timestamp = features['feature_timestamp']
            self.redis_client.zadd(ts_key, {json.dumps(features): timestamp})
            self.redis_client.expire(ts_key, ttl_seconds)
            
            REDIS_WRITES.labels(status='success').inc()
            
            logger.debug("Wrote features to Redis",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        feature_type=feature_type,
                        key=feature_key)
            
            return True
            
        except Exception as e:
            logger.error("Failed to write features to Redis",
                        features=features,
                        error=str(e))
            REDIS_WRITES.labels(status='error').inc()
            return False


class StreamProcessor:
    """Main stream processing engine."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.running = False
        
        # Initialize components
        self.watermark_config = WatermarkConfig(
            max_out_of_orderness_ms=config.max_out_of_order_seconds * 1000
        )
        self.watermark_generators = defaultdict(lambda: WatermarkGenerator(self.watermark_config))
        self.late_event_handler = LateEventHandler(self.watermark_config)
        
        # Feature computers
        self.tx_computer = TransactionFeatureComputer(config)
        self.click_computer = ClickstreamFeatureComputer(config)
        
        # Feature sink
        self.feature_sink = FeatureSink(config)
        
        # Kafka consumer
        self.consumer = KafkaConsumer(
            *config.topics,
            bootstrap_servers=config.kafka_bootstrap_servers,
            group_id=config.consumer_group,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            enable_auto_commit=True,
            auto_offset_reset='latest'
        )
        
        logger.info("Stream processor initialized",
                   topics=config.topics,
                   consumer_group=config.consumer_group)
        
    def start(self):
        """Start the stream processor."""
        self.running = True
        
        # Start metrics server
        start_http_server(self.config.metrics_port)
        logger.info(f"Metrics server started on port {self.config.metrics_port}")
        
        logger.info("Starting stream processor...")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                    
                self.process_message(message)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()
            
    def stop(self):
        """Stop the stream processor."""
        self.running = False
        self.consumer.close()
        logger.info("Stream processor stopped")
        
    def process_message(self, message):
        """Process a single Kafka message."""
        try:
            with PROCESSING_LATENCY.time():
                topic = message.topic
                event = message.value
                
                # Extract timestamp
                event_timestamp = event.get('timestamp', int(time.time() * 1000))
                
                # Check watermark and late events
                watermark_gen = self.watermark_generators[topic]
                watermark = watermark_gen.generate_watermark(event_timestamp)
                
                is_late = watermark_gen.is_late_event(event_timestamp)
                if is_late and self.config.enable_late_events:
                    action = self.late_event_handler.handle_late_event(event, event_timestamp, watermark_gen.get_current_watermark())
                    logger.warning("Late event detected", 
                                  topic=topic, 
                                  lateness_ms=watermark_gen.get_current_watermark() - event_timestamp,
                                  action=action)
                    if action == 'dropped':
                        EVENTS_PROCESSED.labels(topic=topic, status='dropped_late').inc()
                        return
                
                # Process based on topic
                features = None
                if topic == 'txn.events':
                    features = self.tx_computer.process_event(event)
                elif topic == 'click.events':
                    features = self.click_computer.process_event(event)
                
                # Write features to sink
                if features:
                    success = self.feature_sink.write_features(features)
                    status = 'success' if success else 'sink_error'
                else:
                    status = 'processing_error'
                    
                EVENTS_PROCESSED.labels(topic=topic, status=status).inc()
                
        except Exception as e:
            logger.error("Error processing message",
                        topic=message.topic,
                        error=str(e))
            EVENTS_PROCESSED.labels(topic=message.topic, status='error').inc()


# Import numpy for standard deviation calculation
try:
    import numpy as np
except ImportError:
    # Fallback implementation
    class np:
        @staticmethod
        def std(arr):
            if len(arr) < 2:
                return 0.0
            mean = sum(arr) / len(arr)
            variance = sum((x - mean) ** 2 for x in arr) / len(arr)
            return variance ** 0.5


@click.command()
@click.option('--kafka-servers', default='localhost:9092', help='Kafka bootstrap servers')
@click.option('--redis-host', default='localhost', help='Redis host')
@click.option('--consumer-group', default='feature-processor', help='Kafka consumer group')
@click.option('--window-size', default=5, help='Window size in minutes')
@click.option('--topics', default='txn.events,click.events', help='Comma-separated topic list')
@click.option('--metrics-port', default=8088, help='Metrics server port')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def main(kafka_servers, redis_host, consumer_group, window_size, topics, metrics_port, verbose):
    """Run the stream processor for real-time feature engineering."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    config = ProcessorConfig(
        kafka_bootstrap_servers=kafka_servers,
        redis_host=redis_host,
        consumer_group=consumer_group,
        window_size_minutes=window_size,
        topics=topics.split(','),
        metrics_port=metrics_port
    )
    
    processor = StreamProcessor(config)
    
    try:
        processor.start()
    except Exception as e:
        logger.error("Stream processor failed", error=str(e))
        raise


if __name__ == '__main__':
    main()
