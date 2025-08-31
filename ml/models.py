#!/usr/bin/env python3
"""
ML Model definitions and training.

This module contains:
- Model factory for different ML algorithms
- Training pipeline with cross-validation
- Model evaluation and metrics
- ONNX export for production serving
"""

import logging
import pickle
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score, 
    precision_recall_curve, roc_curve, average_precision_score
)
from sklearn.model_selection import cross_val_score, StratifiedKFold
import xgboost as xgb
import lightgbm as lgb

# ONNX export
import onnxmltools
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

import mlflow
import mlflow.sklearn
import mlflow.xgboost
import mlflow.lightgbm

from config import TrainingConfig

logger = logging.getLogger(__name__)


class ModelFactory:
    """Factory for creating different types of ML models."""
    
    @staticmethod
    def create_model(config: TrainingConfig, problem_type: str = "fraud_detection") -> Any:
        """Create model based on configuration."""
        model_type = config.model.model_type.lower()
        
        logger.info(f"Creating {model_type} model for {problem_type}")
        
        if model_type == "xgboost":
            return xgb.XGBClassifier(**config.model.xgb_params)
        
        elif model_type == "lightgbm":
            lgb_params = {
                "objective": "binary",
                "metric": "auc",
                "boosting_type": "gbdt",
                "num_leaves": 31,
                "learning_rate": 0.1,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "bagging_freq": 5,
                "verbose": -1,
                "random_state": 42
            }
            return lgb.LGBMClassifier(**lgb_params)
        
        elif model_type == "random_forest":
            rf_params = {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 5,
                "min_samples_leaf": 2,
                "random_state": 42,
                "class_weight": "balanced"
            }
            return RandomForestClassifier(**rf_params)
        
        elif model_type == "logistic_regression":
            lr_params = {
                "random_state": 42,
                "class_weight": "balanced",
                "max_iter": 1000
            }
            return LogisticRegression(**lr_params)
        
        else:
            raise ValueError(f"Unsupported model type: {model_type}")


class ModelTrainer:
    """Model training pipeline with MLflow integration."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.feature_names = None
        
    def train_model(self, 
                   X_train: pd.DataFrame, 
                   y_train: pd.Series,
                   X_val: pd.DataFrame,
                   y_val: pd.Series) -> Any:
        """Train model with validation."""
        
        logger.info("Starting model training")
        
        # Create model
        self.model = ModelFactory.create_model(self.config)
        self.feature_names = list(X_train.columns)
        
        # Train model with validation set for early stopping (if supported)
        if isinstance(self.model, (xgb.XGBClassifier, lgb.LGBMClassifier)):
            eval_set = [(X_val, y_val)]
            
            if isinstance(self.model, xgb.XGBClassifier):
                self.model.fit(
                    X_train, y_train,
                    eval_set=eval_set,
                    verbose=False
                )
            else:  # LightGBM
                self.model.fit(
                    X_train, y_train,
                    eval_set=eval_set,
                    callbacks=[lgb.early_stopping(10), lgb.log_evaluation(0)]
                )
        else:
            # Standard scikit-learn models
            self.model.fit(X_train, y_train)
        
        logger.info("Model training completed")
        return self.model
    
    def cross_validate(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """Perform cross-validation."""
        logger.info("Performing cross-validation")
        
        cv = StratifiedKFold(n_splits=self.config.model.cv_folds, shuffle=True, random_state=42)
        
        # Cross-validate different metrics
        cv_scores = {}
        
        scoring_metrics = ['roc_auc', 'precision', 'recall', 'f1']
        for metric in scoring_metrics:
            scores = cross_val_score(self.model, X, y, cv=cv, scoring=metric)
            cv_scores[f'cv_{metric}_mean'] = scores.mean()
            cv_scores[f'cv_{metric}_std'] = scores.std()
            
            logger.info(f"CV {metric}: {scores.mean():.4f} (+/- {scores.std() * 2:.4f})")
        
        return cv_scores
    
    def evaluate_model(self, 
                      X_test: pd.DataFrame, 
                      y_test: pd.Series,
                      X_train: pd.DataFrame = None,
                      y_train: pd.Series = None) -> Dict[str, Any]:
        """Comprehensive model evaluation."""
        logger.info("Evaluating model performance")
        
        # Predictions
        y_pred = self.model.predict(X_test)
        y_pred_proba = self.model.predict_proba(X_test)[:, 1]
        
        # Basic metrics
        metrics = {
            'test_auc': roc_auc_score(y_test, y_pred_proba),
            'test_average_precision': average_precision_score(y_test, y_pred_proba),
        }
        
        # Classification report
        class_report = classification_report(y_test, y_pred, output_dict=True)
        
        # Add precision, recall, f1 for each class
        metrics.update({
            'test_precision': class_report['1']['precision'],
            'test_recall': class_report['1']['recall'],
            'test_f1': class_report['1']['f1-score'],
            'test_accuracy': class_report['accuracy']
        })
        
        # Confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        metrics.update({
            'test_true_negatives': int(cm[0, 0]),
            'test_false_positives': int(cm[0, 1]),
            'test_false_negatives': int(cm[1, 0]),
            'test_true_positives': int(cm[1, 1])
        })
        
        # Train set performance (if provided)
        if X_train is not None and y_train is not None:
            y_train_pred = self.model.predict(X_train)
            y_train_proba = self.model.predict_proba(X_train)[:, 1]
            
            metrics.update({
                'train_auc': roc_auc_score(y_train, y_train_proba),
                'train_accuracy': (y_train_pred == y_train).mean()
            })
        
        # Feature importance (if available)
        if hasattr(self.model, 'feature_importances_'):
            feature_importance = pd.DataFrame({
                'feature': self.feature_names,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)
            
            # Log top 10 features
            top_features = feature_importance.head(10)
            logger.info("Top 10 most important features:")
            for idx, row in top_features.iterrows():
                logger.info(f"  {row['feature']}: {row['importance']:.4f}")
            
            metrics['feature_importance'] = feature_importance.to_dict('records')
        
        # Log key metrics
        logger.info(f"Model Performance:")
        logger.info(f"  AUC: {metrics['test_auc']:.4f}")
        logger.info(f"  Precision: {metrics['test_precision']:.4f}")
        logger.info(f"  Recall: {metrics['test_recall']:.4f}")
        logger.info(f"  F1: {metrics['test_f1']:.4f}")
        
        return metrics
    
    def export_to_onnx(self, output_path: str) -> bool:
        """Export model to ONNX format for serving."""
        try:
            logger.info(f"Exporting model to ONNX: {output_path}")
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Create initial type with feature count
            n_features = len(self.feature_names)
            initial_type = [('float_input', FloatTensorType([None, n_features]))]
            
            if isinstance(self.model, xgb.XGBClassifier):
                # Convert XGBoost to ONNX
                onnx_model = onnxmltools.convert_xgboost(
                    self.model,
                    initial_types=initial_type,
                    target_opset=12
                )
            elif isinstance(self.model, lgb.LGBMClassifier):
                # Convert LightGBM to ONNX
                onnx_model = onnxmltools.convert_lightgbm(
                    self.model,
                    initial_types=initial_type,
                    target_opset=12
                )
            else:
                # Convert scikit-learn to ONNX
                onnx_model = convert_sklearn(
                    self.model,
                    initial_types=initial_type,
                    target_opset=12
                )
            
            # Save ONNX model
            with open(output_path, "wb") as f:
                f.write(onnx_model.SerializeToString())
            
            logger.info(f"Model exported to ONNX successfully: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export model to ONNX: {e}")
            return False
    
    def save_model_artifacts(self, output_dir: str) -> Dict[str, str]:
        """Save model and related artifacts."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        artifacts = {}
        
        # Save model pickle
        model_path = output_path / "model.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(self.model, f)
        artifacts['model_pickle'] = str(model_path)
        
        # Save feature names
        features_path = output_path / "feature_names.json"
        import json
        with open(features_path, 'w') as f:
            json.dump(self.feature_names, f)
        artifacts['feature_names'] = str(features_path)
        
        # Export to ONNX
        if self.config.export_onnx:
            onnx_path = output_path / "model.onnx"
            if self.export_to_onnx(str(onnx_path)):
                artifacts['onnx_model'] = str(onnx_path)
        
        logger.info(f"Model artifacts saved to {output_path}")
        return artifacts


class MLflowExperimentManager:
    """Manages MLflow experiments and model registration."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self._setup_mlflow()
    
    def _setup_mlflow(self):
        """Setup MLflow tracking."""
        mlflow.set_tracking_uri(self.config.mlflow.tracking_uri)
        mlflow.set_experiment(self.config.mlflow.experiment_name)
        
        logger.info(f"MLflow tracking URI: {self.config.mlflow.tracking_uri}")
        logger.info(f"MLflow experiment: {self.config.mlflow.experiment_name}")
    
    def start_run(self, run_name: str = None):
        """Start MLflow run."""
        run_name = run_name or self.config.get_run_name()
        mlflow.start_run(run_name=run_name)
        
        # Log configuration
        mlflow.log_params({
            "model_type": self.config.model.model_type,
            "cv_folds": self.config.model.cv_folds,
            "test_size": self.config.model.test_size,
            "lookback_days": self.config.data.lookback_days,
            "fraud_rate_target": self.config.data.fraud_rate_target
        })
        
        if hasattr(self.config.model, 'xgb_params'):
            mlflow.log_params(self.config.model.xgb_params)
    
    def log_metrics(self, metrics: Dict[str, Any]):
        """Log metrics to MLflow."""
        # Filter out non-numeric metrics for MLflow
        numeric_metrics = {k: v for k, v in metrics.items() 
                         if isinstance(v, (int, float, np.integer, np.floating))}
        
        mlflow.log_metrics(numeric_metrics)
    
    def log_artifacts(self, artifacts: Dict[str, str]):
        """Log artifacts to MLflow."""
        for artifact_name, artifact_path in artifacts.items():
            if Path(artifact_path).exists():
                mlflow.log_artifact(artifact_path)
    
    def register_model(self, model, model_name: str = None):
        """Register model in MLflow Model Registry."""
        if not self.config.mlflow.register_model:
            return None
        
        model_name = model_name or self.config.mlflow.model_name
        
        if isinstance(model, xgb.XGBClassifier):
            model_info = mlflow.xgboost.log_model(
                model, 
                self.config.mlflow.artifact_path,
                registered_model_name=model_name
            )
        elif isinstance(model, lgb.LGBMClassifier):
            model_info = mlflow.lightgbm.log_model(
                model,
                self.config.mlflow.artifact_path, 
                registered_model_name=model_name
            )
        else:
            model_info = mlflow.sklearn.log_model(
                model,
                self.config.mlflow.artifact_path,
                registered_model_name=model_name
            )
        
        logger.info(f"Model registered: {model_name}")
        return model_info
    
    def end_run(self):
        """End MLflow run."""
        mlflow.end_run()
