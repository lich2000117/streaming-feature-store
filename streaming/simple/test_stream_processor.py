#!/usr/bin/env python3
"""
Test script for the stream processor.

This script tests the streaming feature engineering pipeline without requiring
Kafka infrastructure by simulating streaming events.
"""

import os
import sys
import json
import time
import threading
from typing import Dict, Any, List
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from streaming.simple.stream_processor import StreamProcessor
from streaming.core.models.config import ProcessorConfig
from streaming.core.processors.transaction import TransactionFeatureComputer
from streaming.core.processors.clickstream import ClickstreamFeatureComputer
from streaming.core.sinks.redis_sink import FeatureSink
from streaming.core.utils.watermarks import WatermarkGenerator, WatermarkConfig
from generators.txgen import TransactionGenerator
from generators.clickgen import ClickstreamGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.data = {}
        self.expirations = {}
        
    def hmset(self, key: str, data: Dict[str, Any]):
        """Set hash values."""
        self.data[key] = data.copy()
        
    def set(self, key: str, value: str, ex: int = None):
        """Set string value."""
        self.data[key] = value
        if ex:
            self.expirations[key] = time.time() + ex
            
    def expire(self, key: str, seconds: int):
        """Set expiration."""
        self.expirations[key] = time.time() + seconds
        
    def zadd(self, key: str, mapping: Dict[str, float]):
        """Add to sorted set."""
        if key not in self.data:
            self.data[key] = []
        for value, score in mapping.items():
            self.data[key].append((score, value))
            
    def get_all_data(self) -> Dict[str, Any]:
        """Get all stored data."""
        return self.data.copy()


def test_transaction_features():
    """Test transaction feature computation."""
    print("🧪 Testing Transaction Feature Computer...")
    
    config = ProcessorConfig(window_size_minutes=5)
    computer = TransactionFeatureComputer(config)
    
    # Generate test events
    card_id = "card_test_001"
    base_time = int(time.time() * 1000)
    
    test_events = [
        {
            'card_id': card_id,
            'user_id': 'user_001',
            'amount': 50.0,
            'mcc': '5411',  # Grocery
            'geo_country': 'US',
            'timestamp': base_time + 1000
        },
        {
            'card_id': card_id,
            'user_id': 'user_001', 
            'amount': 150.0,
            'mcc': '6011',  # ATM (high risk)
            'geo_country': 'CA',
            'timestamp': base_time + 2000
        },
        {
            'card_id': card_id,
            'user_id': 'user_001',
            'amount': 25.0,
            'mcc': '5812',  # Restaurant
            'geo_country': 'US',
            'timestamp': base_time + 3000
        }
    ]
    
    features_list = []
    for event in test_events:
        features = computer.process_event(event)
        if features:
            features_list.append(features)
            
    print(f"  ✅ Processed {len(test_events)} transaction events")
    print(f"  📊 Generated {len(features_list)} feature records")
    
    if features_list:
        latest_features = features_list[-1]
        print(f"  📝 Latest features for {card_id}:")
        print(f"    - Transaction count: {latest_features['txn_count_5m']}")
        print(f"    - Amount sum: ${latest_features['amount_sum_5m']}")
        print(f"    - Amount average: ${latest_features['amount_avg_5m']:.2f}")
        print(f"    - Unique countries: {latest_features['unique_countries_5m']}")
        print(f"    - High risk ratio: {latest_features['high_risk_txn_ratio']:.2%}")
        print(f"    - Velocity score: {latest_features['velocity_score']:.3f}")
        
        # Validate features
        assert latest_features['txn_count_5m'] == 3
        assert latest_features['unique_countries_5m'] == 2
        assert latest_features['high_risk_txn_ratio'] > 0  # Should detect ATM transaction
        
    print("  ✅ Transaction feature tests passed!")
    return features_list


def test_clickstream_features():
    """Test clickstream feature computation."""
    print("\n🧪 Testing Clickstream Feature Computer...")
    
    config = ProcessorConfig(window_size_minutes=5)
    computer = ClickstreamFeatureComputer(config)
    
    # Generate test events
    user_id = "user_test_001"
    session_id = "session_test_001"
    base_time = int(time.time() * 1000)
    
    test_events = [
        {
            'user_id': user_id,
            'session_id': session_id,
            'page_type': 'HOME',
            'action_type': 'VIEW',
            'dwell_time_ms': 15000,
            'scroll_depth': 0.3,
            'category_id': None,
            'timestamp': base_time + 1000
        },
        {
            'user_id': user_id,
            'session_id': session_id,
            'page_type': 'CATEGORY',
            'action_type': 'CLICK',
            'dwell_time_ms': 25000,
            'scroll_depth': 0.6,
            'category_id': 'electronics',
            'timestamp': base_time + 2000
        },
        {
            'user_id': user_id,
            'session_id': session_id,
            'page_type': 'PRODUCT',
            'action_type': 'ADD_TO_CART',
            'dwell_time_ms': 45000,
            'scroll_depth': 0.8,
            'category_id': 'electronics',
            'timestamp': base_time + 3000
        },
        {
            'user_id': user_id,
            'session_id': session_id,
            'page_type': 'CART',
            'action_type': 'PURCHASE',
            'dwell_time_ms': 30000,
            'scroll_depth': 1.0,
            'category_id': None,
            'timestamp': base_time + 4000
        }
    ]
    
    features_list = []
    for event in test_events:
        features = computer.process_event(event)
        if features:
            features_list.append(features)
            
    print(f"  ✅ Processed {len(test_events)} clickstream events")
    print(f"  📊 Generated {len(features_list)} feature records")
    
    if features_list:
        latest_features = features_list[-1]
        print(f"  📝 Latest features for {user_id}:")
        print(f"    - Session duration: {latest_features['session_duration_min']:.2f} minutes")
        print(f"    - Pages per session: {latest_features['pages_per_session']}")
        print(f"    - Unique categories: {latest_features['unique_categories_session']}")
        print(f"    - Average dwell time: {latest_features['avg_dwell_time_sec']:.1f}s")
        print(f"    - Cart adds: {latest_features['cart_adds_session']}")
        print(f"    - Purchases: {latest_features['purchases_session']}")
        print(f"    - Conversion rate: {latest_features['conversion_rate_session']:.2%}")
        print(f"    - Engagement score: {latest_features['engagement_score']:.3f}")
        
        # Validate features
        assert latest_features['pages_per_session'] == 4
        assert latest_features['unique_categories_session'] == 1
        assert latest_features['cart_adds_session'] == 1
        assert latest_features['purchases_session'] == 1
        assert latest_features['conversion_rate_session'] == 1.0
        
    print("  ✅ Clickstream feature tests passed!")
    return features_list


def test_feature_sink():
    """Test feature sink to Redis."""
    print("\n🧪 Testing Feature Sink...")
    
    # Create mock Redis and feature sink
    config = ProcessorConfig()
    sink = FeatureSink(config)
    
    # Replace Redis client with mock
    mock_redis = MockRedisClient()
    sink.redis_client = mock_redis
    
    # Test features
    test_features = {
        'entity_id': 'test_entity_001',
        'entity_type': 'card',
        'feature_type': 'transaction',
        'txn_count_5m': 5,
        'amount_sum_5m': 250.50,
        'velocity_score': 0.75,
        'feature_timestamp': int(time.time() * 1000),
        'computation_timestamp': int(time.time() * 1000)
    }
    
    # Write features
    success = sink.write_features(test_features)
    
    print(f"  ✅ Feature write success: {success}")
    
    # Check stored data
    stored_data = mock_redis.get_all_data()
    print(f"  📊 Stored {len(stored_data)} keys in Redis")
    
    for key, value in stored_data.items():
        print(f"    - {key}: {type(value).__name__}")
        
    # Validate storage
    assert success is True
    assert len(stored_data) > 0
    
    # Check specific keys exist
    feature_key = "features:card:test_entity_001:transaction"
    latest_key = "features:latest:card:test_entity_001"
    
    assert feature_key in stored_data
    assert latest_key in stored_data
    
    print("  ✅ Feature sink tests passed!")
    return stored_data


def test_watermark_generation():
    """Test watermark generation and late event handling."""
    print("\n🧪 Testing Watermark Generation...")
    
    config = WatermarkConfig(max_out_of_orderness_ms=2000)  # 2 second tolerance
    watermark_gen = WatermarkGenerator(config)
    
    # Test event timestamps
    base_time = int(time.time() * 1000)
    test_timestamps = [
        base_time + 1000,
        base_time + 2000,
        base_time + 1500,  # Out of order
        base_time + 3000,
        base_time + 500,   # Very late
        base_time + 4000
    ]
    
    watermarks = []
    late_events = []
    
    for i, timestamp in enumerate(test_timestamps):
        watermark = watermark_gen.generate_watermark(timestamp)
        is_late = watermark_gen.is_late_event(timestamp)
        
        print(f"  Event {i+1}: ts={timestamp}, watermark={watermark}, late={is_late}")
        
        if watermark:
            watermarks.append(watermark)
        if is_late:
            late_events.append(timestamp)
            
    print(f"  📊 Generated {len(watermarks)} watermarks")
    print(f"  ⚠️  Detected {len(late_events)} late events")
    
    # Validate watermark behavior
    assert len(watermarks) > 0
    assert len(late_events) > 0  # Should detect the very late event
    
    # Check watermarks are monotonically increasing
    for i in range(1, len(watermarks)):
        assert watermarks[i] >= watermarks[i-1]
        
    print("  ✅ Watermark generation tests passed!")


def test_end_to_end_pipeline():
    """Test end-to-end streaming pipeline."""
    print("\n🚀 Testing End-to-End Pipeline...")
    
    # Setup
    config = ProcessorConfig(window_size_minutes=5)
    tx_computer = TransactionFeatureComputer(config)
    click_computer = ClickstreamFeatureComputer(config)
    
    # Mock feature sink
    sink = FeatureSink(config)
    mock_redis = MockRedisClient()
    sink.redis_client = mock_redis
    
    # Mock the Kafka producer before creating generators
    import generators.base_generator as bg
    original_producer_class = bg.KafkaProducer
    
    class MockProducer:
        def __init__(self, **kwargs):
            self.events = []
        def send(self, topic, key=None, value=None):
            self.events.append(value)
            class Future:
                def add_callback(self, cb): cb(None)
                def add_errback(self, cb): pass
            return Future()
        def flush(self, timeout=None): pass
        def close(self): pass
    
    bg.KafkaProducer = MockProducer
    
    try:
        # Generate realistic events using our generators
        tx_gen = TransactionGenerator(events_per_second=1, duration_seconds=1, fraud_rate=0.1)
        click_gen = ClickstreamGenerator(events_per_second=1, duration_seconds=1)
        
        # Generate events
        tx_events = [tx_gen.generate_event() for _ in range(10)]
        click_events = [click_gen.generate_event() for _ in range(10)]
        
    finally:
        # Restore original producer class
        bg.KafkaProducer = original_producer_class
    
    print(f"  📥 Generated {len(tx_events)} transaction events")
    print(f"  📥 Generated {len(click_events)} clickstream events")
    
    # Process events through pipeline
    tx_features_count = 0
    click_features_count = 0
    total_redis_writes = 0
    
    # Process transaction events
    for event in tx_events:
        features = tx_computer.process_event(event)
        if features:
            success = sink.write_features(features)
            if success:
                tx_features_count += 1
                total_redis_writes += 1
                
    # Process clickstream events
    for event in click_events:
        features = click_computer.process_event(event)
        if features:
            success = sink.write_features(features)
            if success:
                click_features_count += 1
                total_redis_writes += 1
    
    print(f"  ⚙️  Computed {tx_features_count} transaction feature records")
    print(f"  ⚙️  Computed {click_features_count} clickstream feature records")
    print(f"  💾 Wrote {total_redis_writes} feature records to Redis")
    
    # Check Redis storage
    stored_data = mock_redis.get_all_data()
    print(f"  🗄️  Total Redis keys: {len(stored_data)}")
    
    # Sample some features
    feature_keys = [k for k in stored_data.keys() if k.startswith('features:') and ':latest:' not in k]
    if feature_keys:
        sample_key = feature_keys[0]
        sample_features = stored_data[sample_key]
        print(f"  📝 Sample features ({sample_key}):")
        for key, value in list(sample_features.items())[:5]:
            print(f"    - {key}: {value}")
    
    # Validate pipeline
    assert tx_features_count > 0 or click_features_count > 0
    assert total_redis_writes > 0
    assert len(stored_data) > 0
    
    print("  ✅ End-to-end pipeline test passed!")
    
    return {
        'tx_events': len(tx_events),
        'click_events': len(click_events),
        'tx_features': tx_features_count,
        'click_features': click_features_count,
        'redis_writes': total_redis_writes,
        'redis_keys': len(stored_data)
    }


def main():
    """Run all stream processor tests."""
    print("🚀 Starting Stream Processor Tests\n")
    
    try:
        # Run individual component tests
        tx_features = test_transaction_features()
        click_features = test_clickstream_features()
        redis_data = test_feature_sink()
        test_watermark_generation()
        
        # Run end-to-end test
        pipeline_results = test_end_to_end_pipeline()
        
        print("\n" + "="*60)
        print("🎉 All Stream Processor Tests Passed!")
        print("="*60)
        
        print(f"📊 Test Summary:")
        print(f"  - Transaction features generated: {len(tx_features)}")
        print(f"  - Clickstream features generated: {len(click_features)}")
        print(f"  - Redis keys stored: {len(redis_data)}")
        print(f"  - End-to-end pipeline: {pipeline_results['tx_features']} + {pipeline_results['click_features']} features")
        
        print(f"\n📋 Next steps:")
        print(f"  1. Start infrastructure: make up")
        print(f"  2. Test with real Kafka: python flink/stream_processor.py")
        print(f"  3. Generate events: python generators/txgen.py & python generators/clickgen.py")
        print(f"  4. Check Redis: redis-cli KEYS 'features:*'")
        print(f"  5. View metrics: http://localhost:8088")
        
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0


if __name__ == '__main__':
    exit(main())
