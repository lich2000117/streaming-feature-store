#!/usr/bin/env python3
"""
Feature Store Integration for Real-Time Inference

This module handles:
- Feature retrieval from Redis feature store
- Feature validation and preprocessing
- Caching and performance optimization
- Missing feature handling with defaults
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

import redis
import numpy as np
from redis.exceptions import RedisError, ConnectionError, TimeoutError
from prometheus_client import Counter, Gauge

from config import InferenceConfig

logger = logging.getLogger(__name__)

# Prometheus metrics for feature operations
FEATURE_CACHE_HITS = Counter(
    'feature_cache_hits_total',
    'Total feature cache hits',
    ['entity_type']
)
FEATURE_CACHE_MISSES = Counter(
    'feature_cache_misses_total',
    'Total feature cache misses',
    ['entity_type']
)
FEATURE_FRESHNESS = Gauge(
    'feature_freshness_seconds',
    'Age of features in seconds',
    ['entity_type', 'feature_view']
)


@dataclass
class FeatureMetadata:
    """Metadata about retrieved features."""
    feature_count: int
    missing_features: List[str]
    freshness_seconds: int
    cache_hit: bool
    retrieval_time_ms: float


class FeatureStoreClient:
    """Redis feature store client with caching and error handling."""
    
    def __init__(self, config: InferenceConfig):
        self.config = config
        self.redis_client = None
        self._connection_pool = None
        self._last_health_check = 0
        self._is_healthy = False
        
        # Local cache for features (simple in-memory cache)
        self._feature_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        
        self._connect_redis()
    
    def _connect_redis(self) -> None:
        """Initialize Redis connection with proper configuration."""
        try:
            self._connection_pool = redis.ConnectionPool(
                host=self.config.redis.host,
                port=self.config.redis.port,
                db=self.config.redis.db,
                password=self.config.redis.password,
                socket_connect_timeout=self.config.redis.socket_connect_timeout,
                socket_timeout=self.config.redis.socket_timeout,
                retry_on_timeout=self.config.redis.retry_on_timeout,
                max_connections=self.config.redis.max_connections,
                decode_responses=True
            )
            
            self.redis_client = redis.Redis(connection_pool=self._connection_pool)
            
            # Test connection
            self.redis_client.ping()
            self._is_healthy = True
            self._last_health_check = time.time()
            
            logger.info(
                "Connected to Redis feature store: host=%s, port=%d, db=%d",
                self.config.redis.host,
                self.config.redis.port,
                self.config.redis.db
            )
            print("DEBUG TEST: Redis connection established successfully")
            
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", str(e))
            self._is_healthy = False
            raise
    
    def health_check(self) -> bool:
        """Check Redis connection health."""
        current_time = time.time()
        
        # Only check health every N seconds to avoid overhead
        if current_time - self._last_health_check < self.config.redis.health_check_interval:
            return self._is_healthy
        
        try:
            if self.redis_client:
                self.redis_client.ping()
                self._is_healthy = True
            else:
                self._is_healthy = False
        except Exception as e:
            logger.warning("Redis health check failed: %s", str(e))
            self._is_healthy = False
        
        self._last_health_check = current_time
        return self._is_healthy
    
    def get_card_features(self, card_id: str) -> Tuple[Dict[str, Any], FeatureMetadata]:
        """
        Retrieve card features for fraud detection.
        
        Args:
            card_id: Credit card identifier
            
        Returns:
            Tuple of (features_dict, metadata)
        """
        start_time = time.time()
        cache_key = f"card_features:{card_id}"
        
        # Check local cache first
        if cache_key in self._feature_cache:
            cached_features, cache_time = self._feature_cache[cache_key]
            if time.time() - cache_time < self.config.redis.feature_cache_ttl:
                self._cache_hits += 1
                FEATURE_CACHE_HITS.labels(entity_type='card').inc()
                
                metadata = FeatureMetadata(
                    feature_count=len(cached_features),
                    missing_features=[],
                    freshness_seconds=int(time.time() - cache_time),
                    cache_hit=True,
                    retrieval_time_ms=(time.time() - start_time) * 1000
                )
                
                return cached_features, metadata
            else:
                # Remove expired cache entry
                del self._feature_cache[cache_key]
        
        self._cache_misses += 1
        FEATURE_CACHE_MISSES.labels(entity_type='card').inc()
        
        # Retrieve from Redis
        features = {}
        missing_features = []
        feature_timestamp = None
        
        try:
            # Get transaction features
            redis_key = f"features:card:{card_id}:transaction"
            raw_features = self.redis_client.hgetall(redis_key)
            
            if raw_features:
                # Parse Redis hash values
                parsed_features = self._parse_redis_features(raw_features)
                features.update(parsed_features)
                
                # Extract feature timestamp if available
                if 'feature_timestamp' in parsed_features:
                    feature_timestamp = parsed_features['feature_timestamp']
            
            # Add defaults for missing features and validate
            mapped_features = self._map_and_validate_features(
                features, 
                {},  # No mapping needed
                self.config.model.default_feature_values
            )
            
            # Identify missing features
            expected_features = set(self.config.model.default_feature_values.keys())
            available_features = set(mapped_features.keys())
            missing_features = list(expected_features - available_features)
            
            # Calculate feature freshness
            freshness_seconds = 0
            if feature_timestamp:
                try:
                    if isinstance(feature_timestamp, (int, float)):
                        # Unix timestamp in milliseconds
                        feature_time = datetime.fromtimestamp(feature_timestamp / 1000)
                    else:
                        # ISO format string
                        feature_time = datetime.fromisoformat(str(feature_timestamp))
                    
                    freshness_seconds = int((datetime.now() - feature_time).total_seconds())
                except Exception as e:
                    logger.warning("Failed to parse feature timestamp: %s", str(e))
            
            # Cache the results
            self._feature_cache[cache_key] = (mapped_features, time.time())
            
            # Clean up cache if it gets too large
            if len(self._feature_cache) > 10000:
                self._cleanup_cache()
            
            # Record feature freshness metric
            FEATURE_FRESHNESS.labels(entity_type='card', feature_view='transaction').set(freshness_seconds)
            
            metadata = FeatureMetadata(
                feature_count=len(mapped_features),
                missing_features=missing_features,
                freshness_seconds=freshness_seconds,
                cache_hit=False,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
            
            return mapped_features, metadata
            
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error("Redis error retrieving card features for card_id=%s: %s", card_id, str(e))
            # Return default features on Redis error
            default_features = self.config.model.default_feature_values.copy()
            
            metadata = FeatureMetadata(
                feature_count=len(default_features),
                missing_features=list(self.config.model.default_feature_values.keys()),
                freshness_seconds=0,
                cache_hit=False,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
            
            return default_features, metadata
    
    def get_user_features(self, user_id: str) -> Tuple[Dict[str, Any], FeatureMetadata]:
        """
        Retrieve user features for personalization.
        
        Args:
            user_id: User identifier
            
        Returns:
            Tuple of (features_dict, metadata)
        """
        start_time = time.time()
        cache_key = f"user_features:{user_id}"
        
        # Check local cache first
        if cache_key in self._feature_cache:
            cached_features, cache_time = self._feature_cache[cache_key]
            if time.time() - cache_time < self.config.redis.feature_cache_ttl:
                self._cache_hits += 1
                FEATURE_CACHE_HITS.labels(entity_type='user').inc()
                
                metadata = FeatureMetadata(
                    feature_count=len(cached_features),
                    missing_features=[],
                    freshness_seconds=int(time.time() - cache_time),
                    cache_hit=True,
                    retrieval_time_ms=(time.time() - start_time) * 1000
                )
                
                return cached_features, metadata
            else:
                del self._feature_cache[cache_key]
        
        self._cache_misses += 1
        FEATURE_CACHE_MISSES.labels(entity_type='user').inc()
        
        # Retrieve from Redis
        features = {}
        missing_features = []
        feature_timestamp = None
        
        try:
            # Get clickstream features
            redis_key = f"features:user:{user_id}:clickstream"
            raw_features = self.redis_client.hgetall(redis_key)
            
            if raw_features:
                parsed_features = self._parse_redis_features(raw_features)
                features.update(parsed_features)
                
                if 'feature_timestamp' in parsed_features:
                    feature_timestamp = parsed_features['feature_timestamp']
            
            # Add defaults and validate
            default_values = {
                "session_duration_min": 0.0,
                "pages_per_session": 1.0,
                "click_rate_5m": 0.0,
                "engagement_score": 0.5,
                "is_high_engagement": False
            }
            
            mapped_features = self._map_and_validate_features(
                features,
                {},  # No mapping needed
                default_values
            )
            
            # Identify missing features
            expected_features = set(default_values.keys())
            available_features = set(mapped_features.keys())
            missing_features = list(expected_features - available_features)
            
            # Calculate freshness
            freshness_seconds = 0
            if feature_timestamp:
                try:
                    if isinstance(feature_timestamp, (int, float)):
                        feature_time = datetime.fromtimestamp(feature_timestamp / 1000)
                    else:
                        feature_time = datetime.fromisoformat(str(feature_timestamp))
                    
                    freshness_seconds = int((datetime.now() - feature_time).total_seconds())
                except Exception:
                    pass
            
            # Cache results
            self._feature_cache[cache_key] = (mapped_features, time.time())
            
            # Record feature freshness metric
            FEATURE_FRESHNESS.labels(entity_type='user', feature_view='clickstream').set(freshness_seconds)
            
            metadata = FeatureMetadata(
                feature_count=len(mapped_features),
                missing_features=missing_features,
                freshness_seconds=freshness_seconds,
                cache_hit=False,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
            
            print(
                "Retrieved user features: user_id=%s, feature_count=%d, missing_count=%d, freshness_sec=%d",
                user_id, len(mapped_features), len(missing_features), freshness_seconds
            )
            
            return mapped_features, metadata
            
        except (RedisError, ConnectionError, TimeoutError) as e:
            logger.error("Redis error retrieving user features for user_id=%s: %s", user_id, str(e))
            
            # Return default features
            default_features = {
                "session_duration_min": 0.0,
                "pages_per_session": 1.0,
                "click_rate_5m": 0.0,
                "engagement_score": 0.5,
                "is_high_engagement": False
            }
            
            metadata = FeatureMetadata(
                feature_count=len(default_features),
                missing_features=["session_duration_min", "pages_per_session", "click_rate_5m", "engagement_score", "is_high_engagement"],
                freshness_seconds=0,
                cache_hit=False,
                retrieval_time_ms=(time.time() - start_time) * 1000
            )
            
            return default_features, metadata
    
    def _parse_redis_features(self, raw_features: Dict[str, str]) -> Dict[str, Any]:
        """Parse Redis string values to appropriate Python types."""
        parsed = {}
        
        for key, value in raw_features.items():
            if key in ['entity_id', 'entity_type', 'feature_type']:
                parsed[key] = value
                continue
            
            try:
                # Handle null values
                if value == 'null' or value is None:
                    parsed[key] = None
                # Try to parse as number
                elif '.' in value or 'e' in value.lower():
                    parsed[key] = float(value)
                elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                    parsed[key] = int(value)
                elif value.lower() in ('true', 'false'):
                    parsed[key] = value.lower() == 'true'
                else:
                    # Keep as string
                    parsed[key] = value
            except (ValueError, AttributeError):
                parsed[key] = value
        
        return parsed
    
    def _map_and_validate_features(self, 
                                  features: Dict[str, Any], 
                                  feature_mapping: Dict[str, str],
                                  defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Add defaults for missing features and validate them."""
        # Use features directly without mapping
        mapped_features = features.copy()
        
        # Add defaults for missing features
        for feature_name, default_value in defaults.items():
            if feature_name not in mapped_features:
                mapped_features[feature_name] = default_value
        
        # Validate feature types and ranges
        mapped_features = self._validate_feature_values(mapped_features)
        
        return mapped_features
    
    def _validate_feature_values(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean feature values."""
        validated = {}
        
        for feature_name, value in features.items():
            try:
                # Handle different data types
                if isinstance(value, bool):
                    validated[feature_name] = value
                elif isinstance(value, (int, float)):
                    # Check for NaN or inf values
                    if np.isnan(value) or np.isinf(value):
                        # Use default value
                        validated[feature_name] = self.config.model.default_feature_values.get(feature_name, 0.0)
                    else:
                        validated[feature_name] = float(value)
                elif isinstance(value, str):
                    # Try to convert string to appropriate type
                    try:
                        if '.' in value:
                            validated[feature_name] = float(value)
                        else:
                            validated[feature_name] = int(value)
                    except ValueError:
                        # Keep as string or use default
                        validated[feature_name] = value
                else:
                    validated[feature_name] = value
                    
            except Exception as e:
                logger.warning(
                    "Feature validation failed: feature=%s, value=%s, error=%s",
                    feature_name, value, str(e)
                )
                # Use default value
                validated[feature_name] = self.config.model.default_feature_values.get(feature_name, 0.0)
        
        return validated
    
    def _cleanup_cache(self) -> None:
        """Clean up expired cache entries."""
        current_time = time.time()
        expired_keys = []
        
        for key, (_, cache_time) in self._feature_cache.items():
            if current_time - cache_time > self.config.redis.feature_cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._feature_cache[key]
        
        print("Cleaned up cache, expired_entries=%d", len(expired_keys))
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0
        
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "cache_size": len(self._feature_cache),
            "redis_healthy": self._is_healthy
        }
    
    def close(self) -> None:
        """Close Redis connections."""
        if self.redis_client:
            self.redis_client.close()
        if self._connection_pool:
            self._connection_pool.disconnect()
        
        logger.info("Closed Redis connections")
