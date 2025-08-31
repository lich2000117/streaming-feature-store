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
import time
from typing import Dict, Any
from collections import defaultdict
import logging

# Add project root to path (go up two levels from streaming/simple/ to project root)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kafka import KafkaConsumer
import click
import structlog
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Import our modular components
from streaming.core.models.config import ProcessorConfig
from streaming.core.utils.watermarks import WatermarkGenerator, WatermarkConfig, LateEventHandler
from streaming.core.utils.avro import AvroDeserializer
from streaming.core.sinks.redis_sink import FeatureSink
from streaming.core.processors.transaction import TransactionFeatureComputer
from streaming.core.processors.clickstream import ClickstreamFeatureComputer
from streaming.core.utils.metrics import EVENTS_PROCESSED, PROCESSING_DURATION

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


# Removed - now using modular components from processors/, sinks/, utils/


class StreamProcessor:
    """Main stream processing engine."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.running = False
        
        # Initialize Avro deserializer
        self.avro_deserializer = AvroDeserializer(config)
        
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
        
        # Kafka consumer - no value deserializer, we'll handle Avro manually
        self.consumer = KafkaConsumer(
            *config.topics,
            bootstrap_servers=config.kafka_bootstrap_servers,
            group_id=config.consumer_group,
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
            topic = message.topic
            with PROCESSING_DURATION.labels(event_type=topic, processor='simple').time():
                
                # Deserialize Avro message
                event = self.avro_deserializer.deserialize_message(topic, message.value)
                
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
                        EVENTS_PROCESSED.labels(event_type=topic, status='dropped_late').inc()
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
                    
                EVENTS_PROCESSED.labels(event_type=topic, status=status).inc()
                
        except Exception as e:
            logger.error("Error processing message",
                        topic=message.topic,
                        error=str(e))
            EVENTS_PROCESSED.labels(event_type=message.topic, status='error').inc()


# Removed - numpy calculation now handled in processor modules


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
