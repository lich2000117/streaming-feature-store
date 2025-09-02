#!/usr/bin/env python3
"""
Inference Service Configuration

Centralized configuration management for the real-time inference service.
Supports environment-based configuration for different deployment environments.
"""

import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from pathlib import Path


class RedisConfig(BaseModel):
    """Redis configuration for feature store."""
    
    host: str = Field(default="redis", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    
    # Connection settings
    socket_connect_timeout: int = Field(default=5, description="Connection timeout seconds")
    socket_timeout: int = Field(default=5, description="Socket timeout seconds")
    retry_on_timeout: bool = Field(default=True, description="Retry on timeout")
    health_check_interval: int = Field(default=30, description="Health check interval")
    
    # Feature cache settings
    feature_cache_ttl: int = Field(default=300, description="Feature cache TTL in seconds")
    max_connections: int = Field(default=100, description="Max Redis connections")


class ModelConfig(BaseModel):
    """Model configuration for inference."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    # Model paths
    model_path: str = Field(default="training/outputs/model.pkl", description="Trained model path")
    feature_names_path: str = Field(default="training/outputs/feature_names.json", description="Feature names path")
    onnx_model_path: Optional[str] = Field(default="training/outputs/model.onnx", description="ONNX model path")
    
    # Model metadata
    model_version: str = Field(default="v1.0", description="Model version")
    model_type: str = Field(default="fraud_detection", description="Model type")
    
    # Inference settings
    use_onnx: bool = Field(default=False, description="Use ONNX runtime for inference")
    batch_size: int = Field(default=1, description="Batch size for inference")
    prediction_threshold: float = Field(default=0.5, description="Binary classification threshold")
    
    # Feature settings
    max_feature_age_minutes: int = Field(default=5, description="Max age of features in minutes")
    default_feature_values: Dict[str, Any] = Field(
        default_factory=lambda: {
            "txn_count_5m": 0,
            "txn_count_30m": 0,
            "txn_count_24h": 0,
            "amount_avg_5m": 0.0,
            "amount_sum_5m": 0.0,
            "amount_max_5m": 0.0,
            "amount_std_5m": 0.0,
            "unique_countries_5m": 1,
            "geo_diversity_score": 0.0,
            "time_since_last_txn_min": 0.0,
            "is_weekend": False,
            "hour_of_day": 12,
            "velocity_score": 0.0,
            "high_risk_txn_ratio": 0.0,
            "has_high_risk_mcc": False,
            "is_high_velocity": False,
            "is_geo_diverse": False
        },
        description="Default values for missing features"
    )


class APIConfig(BaseModel):
    """API configuration."""
    
    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    workers: int = Field(default=1, description="Number of workers")
    
    # API settings
    title: str = Field(default="Streaming Feature Store - Inference API", description="API title")
    description: str = Field(
        default="Real-time fraud detection and personalization scoring with sub-150ms latency",
        description="API description"
    )
    version: str = Field(default="1.0.0", description="API version")
    
    # Performance settings
    max_request_size: int = Field(default=1024 * 1024, description="Max request size in bytes")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # Rate limiting
    rate_limit_requests: int = Field(default=1000, description="Requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    
    # CORS settings
    cors_origins: List[str] = Field(default_factory=lambda: ["*"], description="CORS allowed origins")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = Field(default="DEBUG", description="Log level")
    format: str = Field(default="json", description="Log format: json or text")
    
    # Structured logging fields
    service_name: str = Field(default="inference-api", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")
    environment: str = Field(default="production", description="Environment")
    
    # Log destinations
    log_to_file: bool = Field(default=False, description="Log to file")
    log_file_path: str = Field(default="logs/inference.log", description="Log file path")


class MonitoringConfig(BaseModel):
    """Monitoring and observability configuration."""
    
    # Metrics
    enable_prometheus: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_path: str = Field(default="/metrics", description="Metrics endpoint path")
    
    # Health checks
    health_check_path: str = Field(default="/health", description="Health check endpoint")
    readiness_check_path: str = Field(default="/ready", description="Readiness check endpoint")
    
    # Performance targets
    target_p95_latency_ms: float = Field(default=150.0, description="Target p95 latency in milliseconds")
    target_p99_latency_ms: float = Field(default=300.0, description="Target p99 latency in milliseconds")
    
    # Alerting thresholds
    error_rate_threshold: float = Field(default=0.01, description="Error rate threshold")
    latency_threshold_ms: float = Field(default=500.0, description="Latency threshold in milliseconds")


class InferenceConfig(BaseModel):
    """Complete inference service configuration."""
    
    # Component configurations
    redis: RedisConfig = Field(default_factory=RedisConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    # Global settings
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="production", description="Environment")
    
    @classmethod
    def from_env(cls) -> "InferenceConfig":
        """Load configuration from environment variables."""
        config = cls()
        
        # Redis configuration
        if os.getenv("REDIS_HOST"):
            config.redis.host = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            config.redis.port = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_PASSWORD"):
            config.redis.password = os.getenv("REDIS_PASSWORD")
        
        # Model configuration
        if os.getenv("MODEL_PATH"):
            config.model.model_path = os.getenv("MODEL_PATH")
        if os.getenv("MODEL_VERSION"):
            config.model.model_version = os.getenv("MODEL_VERSION")
        if os.getenv("USE_ONNX"):
            config.model.use_onnx = os.getenv("USE_ONNX").lower() == "true"
        
        # API configuration
        if os.getenv("API_HOST"):
            config.api.host = os.getenv("API_HOST")
        if os.getenv("API_PORT"):
            config.api.port = int(os.getenv("API_PORT"))
        
        # Logging configuration
        if os.getenv("LOG_LEVEL"):
            config.logging.level = os.getenv("LOG_LEVEL")
        if os.getenv("ENVIRONMENT"):
            config.environment = os.getenv("ENVIRONMENT")
            config.logging.environment = os.getenv("ENVIRONMENT")
        
        return config
    
    def validate_paths(self) -> bool:
        """Validate that required paths exist."""
        required_paths = [
            self.model.model_path,
            self.model.feature_names_path
        ]
        
        for path in required_paths:
            if not Path(path).exists():
                return False
        
        # ONNX model is optional
        if self.model.use_onnx and self.model.onnx_model_path:
            if not Path(self.model.onnx_model_path).exists():
                return False
        
        return True


# Feature names are used directly from Redis without mapping
