"""
Configuration models for stream processing.

Centralized configuration management for both PyFlink and simplified processors.
"""

from typing import List
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


@dataclass
class ProcessorConfig:
    """Configuration for the simplified stream processor."""
    
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
    
    # Schema settings
    schema_dir: str = "schemas"
    
    # Monitoring
    metrics_port: int = 8000


class FeatureJobConfig(BaseModel):
    """Configuration for the PyFlink feature engineering job."""
    
    # Kafka configuration
    kafka_bootstrap_servers: str = Field(default="localhost:9092")
    schema_registry_url: str = Field(default="http://localhost:8081")
    consumer_group: str = Field(default="flink-feature-job")
    
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
