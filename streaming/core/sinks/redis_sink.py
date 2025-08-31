"""
Redis sink for feature storage.

Handles writing computed features to Redis with proper serialization
and key management for online feature serving.
"""

import json
from typing import Dict, Any
import redis
import structlog
from prometheus_client import Counter

from consumers.core.models.config import ProcessorConfig, FeatureJobConfig

logger = structlog.get_logger(__name__)

# Metrics
REDIS_WRITES = Counter('redis_writes_total', 'Redis write operations', ['status'])


class FlinkRedisSink:
    """Redis sink specifically for PyFlink jobs with proper initialization."""
    
    def __init__(self, config: FeatureJobConfig):
        self.config = config
        self.redis_client = None
        
    def open(self, runtime_context):
        """Initialize Redis connection for Flink runtime."""
        import redis
        
        self.redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            decode_responses=True
        )
        logger.info("FlinkRedisSink connected to Redis", 
                   host=self.config.redis_host, 
                   port=self.config.redis_port)
    
    def write(self, features: Dict[str, Any]) -> str:
        """Write features to Redis and return status."""
        try:
            # Serialize for Redis compatibility
            serialized_features = self._serialize_for_redis(features)
            
            # Create Redis key
            entity_type = features.get('entity_type', 'unknown')
            entity_id = features.get('entity_id', 'unknown')
            feature_key = f"features:{entity_type}:{entity_id}"
            
            # Set features with TTL (24 hours)
            self.redis_client.hmset(feature_key, serialized_features)
            self.redis_client.expire(feature_key, 86400)
            
            # Also maintain latest features pointer
            latest_key = f"features:latest:{entity_type}:{entity_id}"
            self.redis_client.set(latest_key, json.dumps(serialized_features), ex=86400)
            
            REDIS_WRITES.labels(status='success').inc()
            
            logger.debug("FlinkRedisSink wrote features", 
                        key=feature_key, 
                        entity_type=entity_type,
                        entity_id=entity_id)
            
            return f"SUCCESS:{feature_key}"
            
        except Exception as e:
            REDIS_WRITES.labels(status='error').inc()
            logger.error("FlinkRedisSink failed to write features", 
                        features=features, 
                        error=str(e))
            return f"ERROR:{str(e)}"
    
    def _serialize_for_redis(self, features: Dict[str, Any]) -> Dict[str, str]:
        """Convert feature values to Redis-compatible strings."""
        serialized = {}
        for key, value in features.items():
            if value is None:
                serialized[key] = "null"
            elif isinstance(value, bool):
                serialized[key] = "true" if value else "false"
            elif isinstance(value, (int, float)):
                serialized[key] = str(value)
            elif isinstance(value, str):
                serialized[key] = value
            else:
                # For complex objects, JSON serialize
                serialized[key] = json.dumps(value)
        return serialized


class FeatureSink:
    """Sink features to Redis for online serving."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )
        
    def _serialize_for_redis(self, features: Dict[str, Any]) -> Dict[str, str]:
        """Convert feature values to Redis-compatible strings."""
        serialized = {}
        for key, value in features.items():
            if value is None:
                serialized[key] = "null"
            elif isinstance(value, bool):
                serialized[key] = "true" if value else "false"
            elif isinstance(value, (int, float, str)):
                serialized[key] = str(value)
            else:
                # Handle complex objects by JSON serializing them
                serialized[key] = json.dumps(value)
        return serialized
    
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
            
            # Serialize features for Redis (convert bools/None to strings)
            redis_features = self._serialize_for_redis(features)
            
            # Store detailed features
            self.redis_client.hmset(feature_key, redis_features)
            self.redis_client.expire(feature_key, ttl_seconds)
            
            # Store latest features pointer (JSON format for API consumption)
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


class FlinkRedisSink:
    """Redis sink for PyFlink jobs."""
    
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
        
    def write(self, value: Dict[str, Any]) -> str:
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
