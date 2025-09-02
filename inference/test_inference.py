#!/usr/bin/env python3
"""
Test script for the FastAPI inference service.

This tests core functionality without requiring external dependencies
like Redis or a running server.
"""

import sys
import json
import pickle
from pathlib import Path

# Add current directory to path
sys.path.append('.')
sys.path.append('..')

def test_configuration():
    """Test configuration loading."""
    print("Testing configuration...")
    
    try:
        from config import InferenceConfig
        
        config = InferenceConfig.from_env()
        
        assert config.model.model_path == "training/outputs/model.pkl"
        assert config.redis.host == "redis"
        assert config.api.port == 8080
        
        print("  ✓ Configuration loaded and validated")
        return True
        
    except Exception as e:
        print(f"  ✗ Configuration test failed: {e}")
        return False


def test_schemas():
    """Test Pydantic schema validation."""
    print("Testing schemas...")
    
    try:
        from schemas import FraudScoreRequest, FraudScoreResponse, PersonalizationScoreRequest
        
        # Test fraud request validation
        fraud_req = FraudScoreRequest(
            card_id="card_12345",
            transaction_amount=100.0,
            mcc_code="5411"
        )
        assert fraud_req.card_id == "card_12345"
        assert fraud_req.transaction_amount == 100.0
        
        # Test personalization request
        person_req = PersonalizationScoreRequest(
            user_id="user_67890",
            item_id="item_123",
            item_category="electronics"
        )
        assert person_req.user_id == "user_67890"
        
        print("  ✓ Schema validation working correctly")
        return True
        
    except Exception as e:
        print(f"  ✗ Schema test failed: {e}")
        return False


def test_model_loading():
    """Test model loading capabilities."""
    print("Testing model loading...")
    
    try:
        from models import ModelManager
        from config import InferenceConfig
        
        # Check if trained model exists
        model_path = Path("../training/outputs/model.pkl")
        feature_names_path = Path("../training/outputs/feature_names.json")
        
        if not model_path.exists():
            print("  ⚠ Trained model not found - run training pipeline first")
            return False
        
        if not feature_names_path.exists():
            print("  ⚠ Feature names not found - run training pipeline first")
            return False
        
        # Load feature names
        with open(feature_names_path, 'r') as f:
            feature_names = json.load(f)
        
        print(f"  ✓ Feature names loaded: {len(feature_names)} features")
        print(f"  ✓ Sample features: {feature_names[:3]}")
        
        # Check model file
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        print(f"  ✓ Model loaded: {type(model).__name__}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Model loading test failed: {e}")
        return False


def test_feature_mapping():
    """Test feature mapping and validation."""
    print("Testing feature mapping...")
    
    try:
        from config import FRAUD_FEATURE_MAPPING, PERSONALIZATION_FEATURE_MAPPING
        
        # Test fraud feature mapping
        assert "txn_count_5m" in FRAUD_FEATURE_MAPPING
        assert "velocity_score" in FRAUD_FEATURE_MAPPING
        
        print(f"  ✓ Fraud features mapped: {len(FRAUD_FEATURE_MAPPING)} features")
        
        # Test personalization feature mapping  
        assert "engagement_score" in PERSONALIZATION_FEATURE_MAPPING
        
        print(f"  ✓ Personalization features mapped: {len(PERSONALIZATION_FEATURE_MAPPING)} features")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Feature mapping test failed: {e}")
        return False


def test_model_inference():
    """Test model inference with synthetic data."""
    print("Testing model inference...")
    
    try:
        from models import SklearnModel
        from config import InferenceConfig
        import json
        import pickle
        
        model_path = Path("../training/outputs/model.pkl")
        feature_names_path = Path("../training/outputs/feature_names.json")
        
        if not model_path.exists() or not feature_names_path.exists():
            print("  ⚠ Model files not available - skipping inference test")
            return True
        
        # Load model and feature names
        with open(model_path, 'rb') as f:
            sklearn_model = pickle.load(f)
        
        with open(feature_names_path, 'r') as f:
            feature_names = json.load(f)
        
        config = InferenceConfig.from_env()
        model_wrapper = SklearnModel(sklearn_model, feature_names, config)
        
        # Create test features
        test_features = {
            "txn_count_5m": 2,
            "amount_avg_5m": 150.0,
            "velocity_score": 0.3,
            "geo_diversity_score": 0.1,
            "has_high_risk_mcc": False,
            "is_weekend": False
        }
        
        # Test single prediction
        score, metadata = model_wrapper.predict(test_features)
        
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
        assert "model_version" in metadata
        assert "inference_time_ms" in metadata
        
        print(f"  ✓ Single prediction: score={score:.3f}, latency={metadata['inference_time_ms']:.1f}ms")
        
        # Test batch prediction
        test_batch = [test_features.copy() for _ in range(5)]
        batch_results = model_wrapper.predict_batch(test_batch)
        
        assert len(batch_results) == 5
        
        print(f"  ✓ Batch prediction: {len(batch_results)} predictions completed")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Model inference test failed: {e}")
        return False


def test_interpretation():
    """Test prediction interpretation functions."""
    print("Testing prediction interpretation...")
    
    try:
        from models import interpret_fraud_prediction, interpret_personalization_prediction
        
        # Test fraud interpretation
        test_features = {
            "velocity_score": 0.8,
            "geo_diversity_score": 0.5,
            "has_high_risk_mcc": True,
            "txn_count_5m": 6
        }
        
        interpretation = interpret_fraud_prediction(0.85, test_features, {"confidence": 0.9})
        
        assert interpretation["risk_level"] in ["low", "medium", "high", "critical"]
        assert interpretation["recommended_action"] in ["approve", "review", "decline", "block"]
        assert len(interpretation["top_risk_factors"]) > 0
        
        print(f"  ✓ Fraud interpretation: {interpretation['risk_level']} risk, {interpretation['recommended_action']}")
        
        # Test personalization interpretation
        person_features = {
            "engagement_score": 0.9,
            "session_duration_min": 400,
            "is_high_engagement": True,
            "pages_per_session": 5
        }
        
        person_interpretation = interpret_personalization_prediction(0.75, person_features, {"confidence": 0.8})
        
        assert "user_segment" in person_interpretation
        assert isinstance(person_interpretation["behavioral_signals"], list)
        
        print(f"  ✓ Personalization interpretation: {person_interpretation['user_segment']} segment")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Interpretation test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Testing FastAPI Inference Service Components\n")
    
    tests = [
        test_configuration,
        test_schemas,
        test_model_loading,
        test_feature_mapping,
        test_model_inference,
        test_interpretation
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ✗ Test {test_func.__name__} failed with exception: {e}")
            failed += 1
        print()  # Add spacing
    
    print("="*60)
    print("FastAPI Inference Service Test Results")
    print("="*60)
    print(f"✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 All inference service tests passed!")
        print("\nNext steps:")
        print("1. Start Redis: docker run -d -p 6379:6379 redis")
        print("2. Run service: uvicorn app:app --host 0.0.0.0 --port 8080")
        print("3. Test API: curl -X POST http://localhost:8080/score/fraud")
        print("4. View docs: http://localhost:8080/docs")
    else:
        print(f"\n⚠ {failed} tests failed. Check errors above.")
    
    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
