#!/usr/bin/env python3
"""
Model Loading and Inference for Real-Time Scoring

This module handles:
- Loading trained ML models (pickle and ONNX)
- Model inference with performance optimization
- Model versioning and A/B testing support
- Feature preprocessing and validation
"""

import json
import pickle
import time
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from config import InferenceConfig
from features import FeatureMetadata

logger = logging.getLogger(__name__)

# Optional ONNX dependencies
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("ONNX Runtime not available, falling back to pickle models")


class ModelInterface(ABC):
    """Abstract interface for ML models."""
    
    @abstractmethod
    def predict(self, features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """
        Make prediction from features.
        
        Returns:
            Tuple of (prediction_score, prediction_metadata)
        """
        pass
    
    @abstractmethod
    def predict_batch(self, features_list: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
        """Make batch predictions."""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        pass


class SklearnModel(ModelInterface):
    """Scikit-learn model wrapper."""
    
    def __init__(self, model: BaseEstimator, feature_names: List[str], config: InferenceConfig):
        self.model = model
        self.feature_names = feature_names
        self.config = config
        self.model_version = config.model.model_version
        self.prediction_count = 0
        
        logger.info(
            "Loaded sklearn model: model_type=%s, feature_count=%d, version=%s",
            type(model).__name__, len(feature_names), self.model_version
        )
    
    def predict(self, features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Make single prediction."""
        start_time = time.time()
        
        try:
            # Prepare feature vector
            feature_vector = self._prepare_features(features)
            
            # Get prediction and probability
            if hasattr(self.model, 'predict_proba'):
                # Classification model - return probability of positive class
                probabilities = self.model.predict_proba([feature_vector])
                prediction_score = float(probabilities[0][1])  # Positive class probability
            else:
                # Regression model
                prediction = self.model.predict([feature_vector])
                prediction_score = float(prediction[0])
            
            # Get feature importance if available
            feature_importance = {}
            if hasattr(self.model, 'feature_importances_'):
                for name, importance in zip(self.feature_names, self.model.feature_importances_):
                    if name in features:
                        feature_importance[name] = float(importance)
            
            self.prediction_count += 1
            inference_time_ms = (time.time() - start_time) * 1000
            
            metadata = {
                "model_type": type(self.model).__name__,
                "model_version": self.model_version,
                "inference_time_ms": inference_time_ms,
                "feature_importance": feature_importance,
                "confidence": self._calculate_confidence(prediction_score)
            }
            
            logger.debug(
                "Model prediction completed: score=%.4f, inference_ms=%.2f, feature_count=%d",
                prediction_score, inference_time_ms, len(feature_vector)
            )
            
            return prediction_score, metadata
            
        except Exception as e:
            logger.error("Model prediction failed: %s", str(e))
            # Return default prediction
            return 0.5, {
                "model_type": "error",
                "model_version": self.model_version,
                "error": str(e),
                "inference_time_ms": (time.time() - start_time) * 1000
            }
    
    def predict_batch(self, features_list: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
        """Make batch predictions."""
        start_time = time.time()
        
        try:
            # Prepare feature matrix
            feature_matrix = [self._prepare_features(features) for features in features_list]
            
            # Batch prediction
            if hasattr(self.model, 'predict_proba'):
                probabilities = self.model.predict_proba(feature_matrix)
                prediction_scores = [float(prob[1]) for prob in probabilities]
            else:
                predictions = self.model.predict(feature_matrix)
                prediction_scores = [float(pred) for pred in predictions]
            
            batch_time_ms = (time.time() - start_time) * 1000
            avg_time_per_prediction = batch_time_ms / len(features_list)
            
            # Create results with metadata
            results = []
            for i, score in enumerate(prediction_scores):
                metadata = {
                    "model_type": type(self.model).__name__,
                    "model_version": self.model_version,
                    "inference_time_ms": avg_time_per_prediction,
                    "confidence": self._calculate_confidence(score),
                    "batch_index": i
                }
                results.append((score, metadata))
            
            self.prediction_count += len(features_list)
            
            logger.debug(
                "Batch prediction completed: batch_size=%d, total_time_ms=%.2f, avg_time_per_pred_ms=%.2f",
                len(features_list), batch_time_ms, avg_time_per_prediction
            )
            
            return results
            
        except Exception as e:
            logger.error("Batch prediction failed: %s", str(e))
            # Return default predictions
            error_metadata = {
                "model_type": "error",
                "model_version": self.model_version,
                "error": str(e)
            }
            return [(0.5, error_metadata) for _ in features_list]
    
    def _prepare_features(self, features: Dict[str, Any]) -> List[float]:
        """Prepare feature vector from feature dictionary."""
        feature_vector = []
        
        for feature_name in self.feature_names:
            if feature_name in features:
                value = features[feature_name]
                
                # Convert to float, handling different types
                if isinstance(value, bool):
                    feature_vector.append(float(value))
                elif isinstance(value, (int, float)):
                    feature_vector.append(float(value))
                elif isinstance(value, str):
                    # Handle string booleans
                    if value.lower() in ('true', 'false'):
                        converted = 1.0 if value.lower() == 'true' else 0.0
                        feature_vector.append(converted)
                    else:
                        # Try to convert string to float
                        try:
                            feature_vector.append(float(value))
                        except ValueError:
                            # Use default for non-numeric strings
                            feature_vector.append(0.0)
                else:
                    feature_vector.append(0.0)
            else:
                # Use default value for missing features
                default_value = self.config.model.default_feature_values.get(feature_name, 0.0)
                feature_vector.append(float(default_value))
        
        return feature_vector
    
    def _calculate_confidence(self, prediction_score: float) -> float:
        """Calculate prediction confidence score."""
        # For binary classification, confidence is distance from 0.5
        return abs(prediction_score - 0.5) * 2
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "model_type": type(self.model).__name__,
            "model_version": self.model_version,
            "feature_count": len(self.feature_names),
            "feature_names": self.feature_names,
            "prediction_count": self.prediction_count,
            "supports_probability": hasattr(self.model, 'predict_proba'),
            "supports_feature_importance": hasattr(self.model, 'feature_importances_')
        }


class ONNXModel(ModelInterface):
    """ONNX model wrapper for optimized inference."""
    
    def __init__(self, onnx_path: str, feature_names: List[str], config: InferenceConfig):
        if not ONNX_AVAILABLE:
            raise ImportError("ONNX Runtime not available")
        
        self.feature_names = feature_names
        self.config = config
        self.model_version = config.model.model_version
        self.prediction_count = 0
        
        # Create ONNX session
        self.session = ort.InferenceSession(
            onnx_path,
            providers=['CPUExecutionProvider']  # Can be extended to support GPU
        )
        
        # Get input/output info
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        
        logger.info(
            "Loaded ONNX model: model_path=%s, feature_count=%d, version=%s, input_name=%s, output_name=%s",
            onnx_path, len(feature_names), self.model_version, self.input_name, self.output_name
        )
    
    def predict(self, features: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Make single prediction using ONNX."""
        start_time = time.time()
        
        try:
            # Prepare feature vector
            feature_vector = self._prepare_features(features)
            input_array = np.array([feature_vector], dtype=np.float32)
            
            # Run ONNX inference
            outputs = self.session.run([self.output_name], {self.input_name: input_array})
            
            # Extract prediction score
            if len(outputs[0][0]) > 1:
                # Binary classification - get positive class probability
                prediction_score = float(outputs[0][0][1])
            else:
                # Single output
                prediction_score = float(outputs[0][0][0])
            
            self.prediction_count += 1
            inference_time_ms = (time.time() - start_time) * 1000
            
            metadata = {
                "model_type": "onnx",
                "model_version": self.model_version,
                "inference_time_ms": inference_time_ms,
                "confidence": self._calculate_confidence(prediction_score)
            }
            
            logger.debug(
                "ONNX prediction completed: score=%.4f, inference_ms=%.2f",
                prediction_score, inference_time_ms
            )
            
            return prediction_score, metadata
            
        except Exception as e:
            logger.error("ONNX prediction failed: %s", str(e))
            return 0.5, {
                "model_type": "onnx_error",
                "model_version": self.model_version,
                "error": str(e),
                "inference_time_ms": (time.time() - start_time) * 1000
            }
    
    def predict_batch(self, features_list: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
        """Make batch predictions using ONNX."""
        start_time = time.time()
        
        try:
            # Prepare feature matrix
            feature_matrix = [self._prepare_features(features) for features in features_list]
            input_array = np.array(feature_matrix, dtype=np.float32)
            
            # Batch ONNX inference
            outputs = self.session.run([self.output_name], {self.input_name: input_array})
            
            # Extract prediction scores
            if len(outputs[0][0]) > 1:
                # Binary classification
                prediction_scores = [float(output[1]) for output in outputs[0]]
            else:
                # Single output
                prediction_scores = [float(output[0]) for output in outputs[0]]
            
            batch_time_ms = (time.time() - start_time) * 1000
            avg_time_per_prediction = batch_time_ms / len(features_list)
            
            # Create results
            results = []
            for i, score in enumerate(prediction_scores):
                metadata = {
                    "model_type": "onnx",
                    "model_version": self.model_version,
                    "inference_time_ms": avg_time_per_prediction,
                    "confidence": self._calculate_confidence(score),
                    "batch_index": i
                }
                results.append((score, metadata))
            
            self.prediction_count += len(features_list)
            
            logger.debug(
                "ONNX batch prediction completed: batch_size=%d, total_time_ms=%.2f",
                len(features_list), batch_time_ms
            )
            
            return results
            
        except Exception as e:
            logger.error("ONNX batch prediction failed: %s", str(e))
            error_metadata = {
                "model_type": "onnx_error",
                "model_version": self.model_version,
                "error": str(e)
            }
            return [(0.5, error_metadata) for _ in features_list]
    
    def _prepare_features(self, features: Dict[str, Any]) -> List[float]:
        """Prepare feature vector from feature dictionary."""
        feature_vector = []
        
        for feature_name in self.feature_names:
            if feature_name in features:
                value = features[feature_name]
                
                if isinstance(value, bool):
                    feature_vector.append(float(value))
                elif isinstance(value, (int, float)):
                    feature_vector.append(float(value))
                else:
                    feature_vector.append(0.0)
            else:
                default_value = self.config.model.default_feature_values.get(feature_name, 0.0)
                feature_vector.append(float(default_value))
        
        return feature_vector
    
    def _calculate_confidence(self, prediction_score: float) -> float:
        """Calculate prediction confidence score."""
        return abs(prediction_score - 0.5) * 2
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "model_type": "onnx",
            "model_version": self.model_version,
            "feature_count": len(self.feature_names),
            "feature_names": self.feature_names,
            "prediction_count": self.prediction_count,
            "input_name": self.input_name,
            "output_name": self.output_name
        }


class ModelManager:
    """Manages multiple models and handles model versioning."""
    
    def __init__(self, config: InferenceConfig):
        self.config = config
        self.models: Dict[str, ModelInterface] = {}
        self.active_model_name = "default"
        self.load_models()
    
    def load_models(self) -> None:
        """Load all configured models."""
        try:
            # Load feature names
            feature_names = self._load_feature_names()
            
            # Load primary model
            if self.config.model.use_onnx and ONNX_AVAILABLE and self.config.model.onnx_model_path:
                if Path(self.config.model.onnx_model_path).exists():
                    self.models["default"] = ONNXModel(
                        self.config.model.onnx_model_path,
                        feature_names,
                        self.config
                    )
                    logger.info("Loaded ONNX model as default")
                else:
                    logger.warning("ONNX model path not found, falling back to pickle")
                    self._load_pickle_model(feature_names)
            else:
                self._load_pickle_model(feature_names)
            
            logger.info(f"Model manager initialized with {len(self.models)} models")
            
        except Exception as e:
            logger.error(f"Failed to load models: {str(e)}")
            raise
    
    def _load_pickle_model(self, feature_names: List[str]) -> None:
        """Load pickle model."""
        if not Path(self.config.model.model_path).exists():
            raise FileNotFoundError(f"Model file not found: {self.config.model.model_path}")
        
        with open(self.config.model.model_path, 'rb') as f:
            sklearn_model = pickle.load(f)
        
        self.models["default"] = SklearnModel(sklearn_model, feature_names, self.config)
        logger.info("Loaded pickle model as default")
    
    def _load_feature_names(self) -> List[str]:
        """Load feature names from JSON file."""
        if not Path(self.config.model.feature_names_path).exists():
            raise FileNotFoundError(f"Feature names file not found: {self.config.model.feature_names_path}")
        
        with open(self.config.model.feature_names_path, 'r') as f:
            feature_names = json.load(f)
        
        logger.info(f"Loaded {len(feature_names)} feature names")
        return feature_names
    
    def predict(self, features: Dict[str, Any], model_name: str = None) -> Tuple[float, Dict[str, Any]]:
        """Make prediction using specified or default model."""
        model_name = model_name or self.active_model_name
        
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")
        
        return self.models[model_name].predict(features)
    
    def predict_batch(self, features_list: List[Dict[str, Any]], model_name: str = None) -> List[Tuple[float, Dict[str, Any]]]:
        """Make batch predictions."""
        model_name = model_name or self.active_model_name
        
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")
        
        return self.models[model_name].predict_batch(features_list)
    
    def get_model_info(self, model_name: str = None) -> Dict[str, Any]:
        """Get model information."""
        model_name = model_name or self.active_model_name
        
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")
        
        return self.models[model_name].get_model_info()
    
    def list_models(self) -> List[str]:
        """List available models."""
        return list(self.models.keys())
    
    def set_active_model(self, model_name: str) -> None:
        """Set the active model for predictions."""
        if model_name not in self.models:
            raise ValueError(f"Model '{model_name}' not found")
        
        self.active_model_name = model_name
        logger.info(f"Active model set to: {model_name}")


def interpret_fraud_prediction(prediction_score: float, features: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Generate human-readable interpretation of fraud prediction."""
    
    # Determine risk level (aligned with model output distribution)
    if prediction_score >= 0.7:
        risk_level = "critical"
        recommended_action = "block"
    elif prediction_score >= 0.4:
        risk_level = "high"
        recommended_action = "review"
    elif prediction_score >= 0.15:
        risk_level = "medium"
        recommended_action = "review"
    else:
        risk_level = "low"
        recommended_action = "approve"
    
    # Identify top risk factors
    risk_factors = []
    
    if features.get("velocity_score", 0) > 0.7:
        risk_factors.append("high_transaction_velocity")
    if features.get("geo_diversity_score", 0) > 0.6:
        risk_factors.append("unusual_geographic_pattern")
    if features.get("has_high_risk_mcc", False):
        risk_factors.append("high_risk_merchant_category")
    if features.get("is_high_velocity", False):
        risk_factors.append("velocity_flag_triggered")
    if features.get("txn_count_5m", 0) > 5:
        risk_factors.append("multiple_recent_transactions")
    
    # Generate explanation
    if risk_level == "critical":
        explanation = "Multiple high-risk patterns detected indicating likely fraud"
    elif risk_level == "high":
        explanation = "Suspicious patterns warrant manual review"
    elif risk_level == "medium":
        explanation = "Some risk indicators present, recommend verification"
    else:
        explanation = "Transaction appears legitimate with low risk indicators"
    
    return {
        "risk_level": risk_level,
        "recommended_action": recommended_action,
        "top_risk_factors": risk_factors[:5],
        "explanation": explanation,
        "confidence": metadata.get("confidence", 0.5)
    }


def interpret_personalization_prediction(prediction_score: float, features: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Generate human-readable interpretation of personalization prediction."""
    
    # Determine user segment
    engagement = features.get("engagement_score", 0.5)
    session_duration = features.get("session_duration_min", 0)
    
    if engagement > 0.8 and session_duration > 300:
        user_segment = "high_value_engaged"
    elif engagement > 0.6:
        user_segment = "engaged"
    elif session_duration > 180:
        user_segment = "browser"
    else:
        user_segment = "casual"
    
    # Identify behavioral signals
    behavioral_signals = []
    
    if features.get("is_high_engagement", False):
        behavioral_signals.append("high_engagement_session")
    if features.get("pages_per_session", 1) > 3:
        behavioral_signals.append("multi_page_session")
    if features.get("click_rate_5m", 0) > 0.1:
        behavioral_signals.append("active_clicking")
    if features.get("conversion_rate_session", 0) > 0.05:
        behavioral_signals.append("conversion_likely")
    
    return {
        "user_segment": user_segment,
        "behavioral_signals": behavioral_signals[:5],
        "confidence": metadata.get("confidence", 0.5)
    }
