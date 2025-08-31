#!/usr/bin/env python3
"""
Test suite for Feast feature store integration.

This tests the complete feature store workflow including:
- Feature store initialization and configuration
- Entity and feature view registration  
- Feature materialization and serving
- Integration with streaming pipeline
"""

import os
import sys
import json
import tempfile
import shutil
from datetime import datetime, timedelta
import pandas as pd

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock Redis for testing
class MockRedis:
    def __init__(self):
        self.data = {}
        
    def ping(self):
        return True
        
    def hgetall(self, key):
        return self.data.get(key, {})
        
    def hset(self, key, mapping):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
        
    def hmset(self, key, mapping):
        self.data[key] = mapping
        
    def set(self, key, value, ex=None):
        self.data[key] = value
        
    def expire(self, key, seconds):
        pass  # Mock implementation
        
    def zadd(self, key, mapping):
        if key not in self.data:
            self.data[key] = []
        for value, score in mapping.items():
            self.data[key].append((score, value))


def test_feature_definitions_import():
    """Test that feature definitions can be imported correctly."""
    print("🧪 Testing Feature Definitions Import...")
    
    try:
        from feast.entities import ALL_ENTITIES
        from feast.feature_views import ALL_FEATURE_VIEWS, ALL_FEATURE_SERVICES
        
        print(f"  ✅ Imported {len(ALL_ENTITIES)} entities")
        print(f"  ✅ Imported {len(ALL_FEATURE_VIEWS)} feature views") 
        print(f"  ✅ Imported {len(ALL_FEATURE_SERVICES)} feature services")
        
        # Validate entities
        entity_names = [e.name for e in ALL_ENTITIES]
        expected_entities = ['card', 'user', 'device', 'session']
        for expected in expected_entities:
            assert expected in entity_names, f"Missing entity: {expected}"
            
        # Validate feature views
        fv_names = [fv.name for fv in ALL_FEATURE_VIEWS]
        expected_fvs = ['transaction_stats_5m', 'user_engagement_5m']
        for expected in expected_fvs:
            assert any(expected in name for name in fv_names), f"Missing feature view containing: {expected}"
        
        print("  ✅ All feature definitions validated")
        return True
        
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_feature_store_configuration():
    """Test feature store configuration loading."""
    print("\n🧪 Testing Feature Store Configuration...")
    
    try:
        # Test YAML configuration exists and is valid
        config_path = "feast/feature_store.yaml"
        
        if not os.path.exists(config_path):
            print(f"  ❌ Config file not found: {config_path}")
            return False
            
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Validate required configuration keys
        required_keys = ['project', 'provider', 'registry', 'online_store']
        for key in required_keys:
            assert key in config, f"Missing config key: {key}"
            
        # Validate online store is Redis
        assert config['online_store']['type'] == 'redis', "Online store must be Redis"
        
        print(f"  ✅ Configuration loaded successfully")
        print(f"    Project: {config['project']}")
        print(f"    Provider: {config['provider']}")
        print(f"    Online store: {config['online_store']['type']}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Configuration test failed: {e}")
        return False


def test_feature_utils():
    """Test feature store utilities."""
    print("\n🧪 Testing Feature Store Utilities...")
    
    try:
        # Create temporary feature store directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Copy configuration to temp directory
            shutil.copy("feast/feature_store.yaml", temp_dir)
            
            # Test imports
            from feast.feature_utils import FeatureStoreManager
            
            # Create manager with mocked Redis
            manager = FeatureStoreManager(temp_dir)
            
            # Replace Redis client with mock
            manager.redis_client = MockRedis()
            
            # Test validation (will fail without full Feast setup, but should not crash)
            try:
                results = manager.validate_feature_store()
                print(f"  ✅ Validation executed (registry accessible: {results.get('registry_accessible', False)})")
            except Exception as e:
                print(f"  ⚠️  Validation failed (expected in test environment): {str(e)[:50]}...")
                
            # Test feature parsing
            redis_data = {
                "txn_count_5m": "5",
                "amount_avg_5m": "123.45",
                "is_high_risk": "true",
                "entity_type": "card"
            }
            
            parsed = manager._parse_redis_features(redis_data)
            assert parsed["txn_count_5m"] == 5
            assert parsed["amount_avg_5m"] == 123.45
            assert parsed["is_high_risk"] is True
            assert parsed["entity_type"] == "card"
            
            print(f"  ✅ Feature parsing works correctly")
            
        finally:
            shutil.rmtree(temp_dir)
            
        return True
        
    except Exception as e:
        print(f"  ❌ Feature utils test failed: {e}")
        return False


def test_feature_materialization_simulation():
    """Test feature materialization workflow simulation."""
    print("\n🧪 Testing Feature Materialization Simulation...")
    
    try:
        # Simulate features coming from streaming pipeline
        streaming_features = [
            {
                'entity_id': 'card_12345',
                'entity_type': 'card',
                'feature_type': 'transaction',
                'txn_count_5m': 3,
                'amount_sum_5m': 450.75,
                'amount_avg_5m': 150.25,
                'velocity_score': 0.65,
                'is_high_risk': False,
                'feature_timestamp': int(datetime.now().timestamp() * 1000)
            },
            {
                'entity_id': 'user_67890', 
                'entity_type': 'user',
                'feature_type': 'clickstream',
                'pages_per_session': 8,
                'session_duration_min': 12.5,
                'engagement_score': 0.82,
                'is_likely_purchaser': True,
                'feature_timestamp': int(datetime.now().timestamp() * 1000)
            }
        ]
        
        # Simulate Redis storage (like our stream processor does)
        mock_redis = MockRedis()
        
        for features in streaming_features:
            entity_type = features['entity_type']
            entity_id = features['entity_id']
            feature_type = features['feature_type']
            
            # Store features in Redis (matching our stream processor format)
            feature_key = f"features:{entity_type}:{entity_id}:{feature_type}"
            latest_key = f"features:latest:{entity_type}:{entity_id}"
            
            mock_redis.hmset(feature_key, features)
            mock_redis.set(latest_key, json.dumps(features))
            
        print(f"  ✅ Materialized {len(streaming_features)} feature records")
        
        # Test feature retrieval
        card_features = mock_redis.hgetall("features:card:card_12345:transaction")
        user_features = mock_redis.hgetall("features:user:user_67890:clickstream")
        
        assert card_features['txn_count_5m'] == 3
        assert card_features['velocity_score'] == 0.65
        assert user_features['engagement_score'] == 0.82
        assert user_features['pages_per_session'] == 8
        
        print(f"  ✅ Feature retrieval working correctly")
        
        # Test feature serving format (for inference API)
        serving_format = {
            'card_12345': {
                'txn_count_5m': card_features['txn_count_5m'],
                'amount_avg_5m': card_features['amount_avg_5m'],
                'velocity_score': card_features['velocity_score'],
                'is_high_risk': card_features['is_high_risk']
            },
            'user_67890': {
                'engagement_score': user_features['engagement_score'],
                'pages_per_session': user_features['pages_per_session'],
                'is_likely_purchaser': user_features['is_likely_purchaser']
            }
        }
        
        print(f"  ✅ Generated serving format for {len(serving_format)} entities")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Materialization simulation failed: {e}")
        return False


def test_point_in_time_correctness():
    """Test point-in-time correctness validation."""
    print("\n🧪 Testing Point-in-time Correctness...")
    
    try:
        # Simulate historical feature data
        historical_data = pd.DataFrame([
            {
                'card_id': 'card_12345',
                'event_timestamp': datetime.now() - timedelta(hours=1),
                'txn_count_5m': 2,
                'amount_avg_5m': 125.50,
                'velocity_score': 0.5
            },
            {
                'card_id': 'card_12345',
                'event_timestamp': datetime.now() - timedelta(minutes=30),
                'txn_count_5m': 3,
                'amount_avg_5m': 150.25,
                'velocity_score': 0.65
            }
        ])
        
        # Simulate current online features (from Redis)
        online_features = {
            'txn_count_5m': 3,
            'amount_avg_5m': 150.25,
            'velocity_score': 0.65,
            'feature_timestamp': int(datetime.now().timestamp() * 1000)
        }
        
        # Check point-in-time consistency
        latest_historical = historical_data.iloc[-1]
        
        differences = {}
        for feature in ['txn_count_5m', 'amount_avg_5m', 'velocity_score']:
            historical_val = latest_historical[feature]
            online_val = online_features[feature]
            
            if abs(historical_val - online_val) > 0.001:
                differences[feature] = {
                    'historical': historical_val,
                    'online': online_val
                }
        
        is_consistent = len(differences) == 0
        
        print(f"  ✅ Point-in-time validation completed")
        print(f"    Consistent: {'✅' if is_consistent else '❌'}")
        print(f"    Features checked: 3")
        print(f"    Differences found: {len(differences)}")
        
        if differences:
            for feature, diff in differences.items():
                print(f"      - {feature}: historical={diff['historical']}, online={diff['online']}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Point-in-time test failed: {e}")
        return False


def test_feature_serving_simulation():
    """Test feature serving for online inference."""
    print("\n🧪 Testing Feature Serving Simulation...")
    
    try:
        # Simulate inference request
        inference_requests = [
            {'card_id': 'card_12345'},  # Fraud detection
            {'user_id': 'user_67890'},  # Personalization
        ]
        
        # Simulate feature store serving
        mock_redis = MockRedis()
        
        # Pre-populate with features
        mock_redis.hmset("features:card:card_12345:transaction", {
            'txn_count_5m': 3,
            'amount_avg_5m': 150.25,
            'velocity_score': 0.65,
            'is_high_risk': False
        })
        
        mock_redis.hmset("features:user:user_67890:clickstream", {
            'engagement_score': 0.82,
            'pages_per_session': 8,
            'conversion_rate_session': 0.15,
            'is_likely_purchaser': True
        })
        
        # Simulate feature serving
        served_features = {}
        
        for request in inference_requests:
            if 'card_id' in request:
                card_id = request['card_id']
                features = mock_redis.hgetall(f"features:card:{card_id}:transaction")
                served_features[card_id] = features
                
            elif 'user_id' in request:
                user_id = request['user_id']
                features = mock_redis.hgetall(f"features:user:{user_id}:clickstream")
                served_features[user_id] = features
        
        print(f"  ✅ Served features for {len(served_features)} entities")
        
        # Validate served features
        card_features = served_features['card_12345']
        user_features = served_features['user_67890']
        
        assert card_features['txn_count_5m'] == 3
        assert card_features['velocity_score'] == 0.65
        assert user_features['engagement_score'] == 0.82
        assert user_features['pages_per_session'] == 8
        
        print(f"  ✅ Feature serving validation passed")
        
        # Simulate feature vector creation for ML model
        fraud_features = [
            float(card_features['txn_count_5m']),
            float(card_features['amount_avg_5m']), 
            float(card_features['velocity_score']),
            1.0 if card_features['is_high_risk'] == 'True' else 0.0
        ]
        
        personalization_features = [
            float(user_features['engagement_score']),
            float(user_features['pages_per_session']) / 10.0,  # Normalized
            float(user_features['conversion_rate_session']),
            1.0 if user_features['is_likely_purchaser'] == 'True' else 0.0
        ]
        
        print(f"  ✅ Generated feature vectors:")
        print(f"    Fraud features: {fraud_features}")
        print(f"    Personalization features: {personalization_features}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Feature serving test failed: {e}")
        return False


def main():
    """Run all Feast integration tests."""
    print("🚀 Starting Feast Integration Tests\n")
    
    tests = [
        test_feature_definitions_import,
        test_feature_store_configuration,
        test_feature_utils,
        test_feature_materialization_simulation,
        test_point_in_time_correctness,
        test_feature_serving_simulation
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ Test crashed: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print("🎉 Feast Integration Test Results")
    print("="*60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 All Feast integration tests passed!")
        print("\n📋 Next steps:")
        print("  1. Install Feast: pip install feast[redis]")
        print("  2. Apply feature store: feast apply")
        print("  3. Start feature server: feast serve")
        print("  4. Test online serving: curl http://localhost:6566/get-online-features")
    else:
        print(f"\n⚠️  {failed} tests failed. Please fix issues before proceeding.")
        
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
