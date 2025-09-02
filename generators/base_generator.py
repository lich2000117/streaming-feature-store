#!/usr/bin/env python3
"""
Base generator class for streaming data generation.

This module provides common functionality for all event generators:
- Kafka producer configuration
- Rate limiting and backpressure
- Schema-based serialization
- Metrics and monitoring
"""

import json
import time
import uuid
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import logging

from kafka import KafkaProducer
from kafka.errors import KafkaError
import avro.schema
import avro.io
import io
from prometheus_client import Counter, Gauge, Histogram, start_http_server


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaseEventGenerator(ABC):
    """Base class for all event generators."""
    
    def __init__(
        self,
        topic: str,
        schema_file: str,
        bootstrap_servers: str = "localhost:9092",
        events_per_second: float = 10.0,
        duration_seconds: Optional[int] = None,
        batch_size: int = 100,
        metrics_port: Optional[int] = None
    ):
        """
        Initialize the event generator.
        
        Args:
            topic: Kafka topic to produce to
            schema_file: Path to Avro schema file
            bootstrap_servers: Kafka broker addresses
            events_per_second: Target event generation rate
            duration_seconds: How long to run (None = infinite)
            batch_size: Number of events to batch before sending
        """
        self.topic = topic
        self.events_per_second = events_per_second
        self.duration_seconds = duration_seconds
        self.batch_size = batch_size
        
        # Load schema
        self.schema = self._load_schema(schema_file)
        
        # Initialize Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers.split(','),
            value_serializer=self._serialize_avro,
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',  # Wait for all replicas
            retries=3,
            max_in_flight_requests_per_connection=1,  # Ensure ordering
            compression_type='snappy',
            batch_size=16384,
            linger_ms=10,  # Small batching delay
        )
        
        # Statistics
        self.events_produced = 0
        self.start_time = None
        self.errors = 0
        
        # Metrics
        self.metrics_port = metrics_port
        self._setup_metrics()
        
    def _load_schema(self, schema_file: str) -> avro.schema.Schema:
        """Load Avro schema from file."""
        try:
            with open(schema_file, 'r') as f:
                schema_json = json.load(f)
                return avro.schema.parse(json.dumps(schema_json))
        except Exception as e:
            logger.error(f"Failed to load schema {schema_file}: {e}")
            raise
    
    def _setup_metrics(self):
        """Set up Prometheus metrics."""
        self.events_counter = Counter(
            'generator_events_total',
            'Total number of events generated',
            ['generator_type', 'topic', 'status']
        )
        self.events_rate = Gauge(
            'generator_events_per_second',
            'Current event generation rate',
            ['generator_type', 'topic']
        )
        self.generation_duration = Histogram(
            'generator_event_generation_duration_seconds',
            'Time taken to generate a single event',
            ['generator_type', 'topic']
        )
            
    def _serialize_avro(self, event: Dict[str, Any]) -> bytes:
        """Serialize event to Avro binary format."""
        try:
            writer = avro.io.DatumWriter(self.schema)
            bytes_writer = io.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(event, encoder)
            return bytes_writer.getvalue()
        except Exception as e:
            logger.error(f"Failed to serialize event: {e}")
            logger.error(f"Event data: {event}")
            raise
            
    @abstractmethod
    def generate_event(self) -> Dict[str, Any]:
        """Generate a single event. Must be implemented by subclasses."""
        pass
        
    @abstractmethod
    def get_partition_key(self, event: Dict[str, Any]) -> str:
        """Get the partition key for an event. Must be implemented by subclasses."""
        pass
        
    def _on_send_success(self, record_metadata):
        """Callback for successful sends."""
        self.events_produced += 1
        
        # Update metrics
        generator_type = self.__class__.__name__
        self.events_counter.labels(
            generator_type=generator_type,
            topic=self.topic,
            status='success'
        ).inc()
        
        if self.events_produced % 1000 == 0:
            elapsed = time.time() - self.start_time
            rate = self.events_produced / elapsed
            self.events_rate.labels(
                generator_type=generator_type,
                topic=self.topic
            ).set(rate)
            logger.info(f"Produced {self.events_produced} events, rate: {rate:.1f}/sec")
            
    def _on_send_error(self, ex):
        """Callback for send errors."""
        self.errors += 1
        
        # Update metrics
        generator_type = self.__class__.__name__
        self.events_counter.labels(
            generator_type=generator_type,
            topic=self.topic,
            status='error'
        ).inc()
        
        logger.error(f"Failed to send event: {ex}")
        
    def produce_event(self, event: Dict[str, Any]) -> None:
        """Send a single event to Kafka."""
        try:
            key = self.get_partition_key(event)
            future = self.producer.send(
                self.topic,
                key=key,
                value=event
            )
            future.add_callback(self._on_send_success)
            future.add_errback(self._on_send_error)
            
        except Exception as e:
            logger.error(f"Failed to produce event: {e}")
            self.errors += 1
            
    def run(self) -> None:
        """Main execution loop."""
        logger.info(f"Starting {self.__class__.__name__}")
        logger.info(f"Target rate: {self.events_per_second} events/sec")
        logger.info(f"Topic: {self.topic}")
        logger.info(f"Duration: {self.duration_seconds}s" if self.duration_seconds else "Duration: infinite")
        
        # Start metrics server if port specified
        if self.metrics_port:
            start_http_server(self.metrics_port)
            logger.info(f"Metrics server started on port {self.metrics_port}")
        
        self.start_time = time.time()
        
        try:
            # Calculate delay between events
            delay = 1.0 / self.events_per_second if self.events_per_second > 0 else 0
            
            while True:
                # Check duration limit
                if self.duration_seconds:
                    elapsed = time.time() - self.start_time
                    if elapsed >= self.duration_seconds:
                        logger.info(f"Reached duration limit of {self.duration_seconds}s")
                        break
                
                # Generate and send event
                generator_type = self.__class__.__name__
                with self.generation_duration.labels(
                    generator_type=generator_type,
                    topic=self.topic
                ).time():
                    event = self.generate_event()
                    self.produce_event(event)
                
                # Rate limiting
                if delay > 0:
                    time.sleep(delay)
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
            
        finally:
            # Cleanup
            logger.info("Flushing producer...")
            self.producer.flush(timeout=30)
            self.producer.close()
            
            # Final statistics
            elapsed = time.time() - self.start_time
            avg_rate = self.events_produced / elapsed if elapsed > 0 else 0
            
            logger.info("="*50)
            logger.info(f"Generator completed:")
            logger.info(f"  Events produced: {self.events_produced}")
            logger.info(f"  Errors: {self.errors}")
            logger.info(f"  Duration: {elapsed:.1f}s")
            logger.info(f"  Average rate: {avg_rate:.1f} events/sec")
            logger.info("="*50)


class TimestampMixin:
    """Mixin for adding timestamp utilities."""
    
    @staticmethod
    def current_timestamp_ms() -> int:
        """Get current timestamp in milliseconds."""
        return int(datetime.now(timezone.utc).timestamp() * 1000)
        
    @staticmethod
    def random_timestamp_last_n_days(days: int = 7) -> int:
        """Generate random timestamp within last N days."""
        now = datetime.now(timezone.utc)
        start = now.timestamp() - (days * 24 * 3600)
        end = now.timestamp()
        random_ts = random.uniform(start, end)
        return int(random_ts * 1000)


class UserSessionManager:
    """Manages user sessions across generators for referential integrity."""
    
    def __init__(self, max_users: int = 10000, session_duration_min: int = 30):
        self.max_users = max_users
        self.session_duration_min = session_duration_min
        self.users = {}  # user_id -> session_info
        self.user_ids = [f"user_{i:06d}" for i in range(max_users)]
        
    def get_user_session(self) -> Dict[str, str]:
        """Get a user session, creating new ones as needed."""
        user_id = random.choice(self.user_ids)
        
        now = time.time()
        
        # Check if user has active session
        if user_id in self.users:
            session = self.users[user_id]
            # Session expired?
            if now - session['start_time'] > (self.session_duration_min * 60):
                # Create new session
                session = self._create_session(user_id, now)
                self.users[user_id] = session
        else:
            # New user
            session = self._create_session(user_id, now)
            self.users[user_id] = session
            
        return {
            'user_id': user_id,
            'session_id': session['session_id'],
            'device_id': session['device_id']
        }
        
    def _create_session(self, user_id: str, start_time: float) -> Dict[str, Any]:
        """Create a new user session."""
        return {
            'session_id': f"sess_{uuid.uuid4().hex[:12]}",
            'device_id': f"dev_{uuid.uuid4().hex[:12]}",
            'start_time': start_time
        }


# Global session manager instance
session_manager = UserSessionManager()
