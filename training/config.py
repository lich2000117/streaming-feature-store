#!/usr/bin/env python3
"""
ML Training Configuration

Centralized configuration for all ML training pipelines with environment-specific settings.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from pathlib import Path


class DataConfig(BaseModel):
    """Data configuration for training."""
    
    # NOTE, edit parameter at @train.py
    # Redis connection for feature store
    redis_host: str = Field(default="localhost", description="Redis host for feature store")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    
    # Training data parameters
    lookback_days: int = Field(default=7, description="Days of historical data to use")
    min_samples_per_entity: int = Field(default=10, description="Minimum samples per entity")
    fraud_rate_target: float = Field(default=0.02, description="Target fraud rate in training data")
    
    # Data quality
    max_missing_rate: float = Field(default=0.1, description="Maximum allowed missing value rate")
    outlier_threshold: float = Field(default=3.0, description="Z-score threshold for outliers")


class ModelConfig(BaseModel):
    """Model configuration."""
    
    # Model selection
    model_type: str = Field(default="xgboost", description="Model type: xgboost, lightgbm, sklearn")
    
    # XGBoost parameters
    xgb_params: Dict[str, Any] = Field(
        default_factory=lambda: {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": 6,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42
        },
        description="XGBoost hyperparameters"
    )
    
    # Feature selection
    feature_selection: bool = Field(default=True, description="Enable feature selection")
    max_features: int = Field(default=50, description="Maximum number of features to select")
    
    # Model validation
    cv_folds: int = Field(default=5, description="Cross-validation folds")
    test_size: float = Field(default=0.2, description="Test set proportion")
    validation_size: float = Field(default=0.2, description="Validation set proportion")


class MLflowConfig(BaseModel):
    """MLflow configuration."""
    
    tracking_uri: str = Field(default="http://localhost:5000", description="MLflow tracking server")
    experiment_name: str = Field(default="fraud_detection", description="MLflow experiment name")
    model_name: str = Field(default="fraud_classifier", description="Model registry name")
    artifact_path: str = Field(default="models", description="Model artifact path")
    
    # Model registration
    register_model: bool = Field(default=True, description="Register model in MLflow")
    model_stage: str = Field(default="Staging", description="Initial model stage")


class TrainingConfig(BaseModel):
    """Complete training configuration."""
    
    # Component configurations
    data: DataConfig = Field(default_factory=DataConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)
    
    # Training job configuration
    job_name: str = Field(default="fraud_detection_training", description="Training job name")
    output_dir: str = Field(default="training/outputs", description="Output directory")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Model serving preparation
    export_onnx: bool = Field(default=True, description="Export model to ONNX format")
    onnx_path: str = Field(default="training/models/fraud_model.onnx", description="ONNX model path")
    
    # Feature store integration
    feature_views: List[str] = Field(
        default_factory=lambda: [
            "transaction_stats_5m",
            "device_risk_features"
        ],
        description="Feast feature views to use for training"
    )
    
    @classmethod
    def from_env(cls) -> "TrainingConfig":
        """Load configuration from environment variables."""
        config = cls()
        
        # Override with environment variables
        if os.getenv("REDIS_HOST"):
            config.data.redis_host = os.getenv("REDIS_HOST")
        if os.getenv("MLFLOW_TRACKING_URI"):
            config.mlflow.tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if os.getenv("MODEL_TYPE"):
            config.model.model_type = os.getenv("MODEL_TYPE")
            
        return config
    
    def create_output_dir(self) -> Path:
        """Create output directory if it doesn't exist."""
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path
    
    def get_run_name(self) -> str:
        """Generate unique run name for MLflow."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.job_name}_{timestamp}"


# Feature configurations for different models
FRAUD_FEATURES = [
    # Count features
    "txn_count_5m",
    "txn_count_30m", 
    "txn_count_24h",
    
    # Amount features
    "amount_sum_5m",
    "amount_avg_5m",
    "amount_max_5m",
    "amount_std_5m",
    
    # Geographic features
    "unique_countries_5m",
    "geo_diversity_score",
    
    # Temporal features
    "time_since_last_txn_min",
    "is_weekend",
    "hour_of_day",
    
    # Risk features
    "velocity_score",
    "high_risk_txn_ratio",
    "medium_risk_txn_ratio",  # New: medium risk MCC ratio
    "is_high_velocity",
    "is_geo_diverse",
    "has_high_risk_mcc",
    
    # New fraud detection features
    "small_amount_ratio",      # Detect card testing patterns
    "round_amount_ratio",      # Detect suspicious round amounts
    "amount_zscore",           # Amount deviation from normal
    "is_high_risk_country",    # Geographic risk indicator
    "is_suspicious_ip",        # Suspicious IP patterns
    "device_reuse_ratio",      # Device reuse patterns
    "is_amount_outlier",       # Amount outlier flag
    "has_small_amounts",       # Small amount testing flag
    "has_round_amounts"        # Round amount pattern flag
]

PERSONALIZATION_FEATURES = [
    # Session features
    "session_duration_min",
    "pages_per_session",
    "unique_categories_session",
    
    # Engagement features
    "avg_dwell_time_sec",
    "avg_scroll_depth",
    "click_rate_5m",
    
    # Purchase funnel features
    "cart_adds_session",
    "conversion_rate_session",
    "engagement_score",
    
    # Behavioral indicators
    "is_high_engagement",
    "is_likely_purchaser"
]

# Model type configurations
MODEL_CONFIGS = {
    "fraud_detection": {
        "features": FRAUD_FEATURES,
        "target": "is_fraud",
        "problem_type": "classification",
        "metrics": ["auc", "precision", "recall", "f1"],
        "class_weight": "balanced"
    },
    "personalization": {
        "features": PERSONALIZATION_FEATURES, 
        "target": "will_purchase",
        "problem_type": "classification",
        "metrics": ["auc", "precision", "recall"],
        "class_weight": None
    }
}
