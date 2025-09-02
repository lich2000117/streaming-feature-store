#!/usr/bin/env python3
"""
ML Training Pipeline Entry Point

This script orchestrates the complete ML training pipeline:
1. Feature extraction from Redis feature store
2. Dataset creation and validation
3. Model training with cross-validation
4. Model evaluation and metrics
5. MLflow experiment tracking
6. Model registration and ONNX export

Usage:
    python training/train.py
    make train
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import click
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import TrainingConfig
from datasets import FeatureStoreDataset, create_synthetic_features_for_testing
from models import ModelTrainer, MLflowExperimentManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('training/training.log')
    ]
)
logger = logging.getLogger(__name__)


class TrainingPipeline:
    """Complete ML training pipeline."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.dataset_creator = FeatureStoreDataset(config)
        self.model_trainer = ModelTrainer(config)
        self.mlflow_manager = MLflowExperimentManager(config)
        
        # Create output directory
        self.output_dir = config.create_output_dir()
        
    def run_training_pipeline(self) -> bool:
        """Run the complete training pipeline."""
        logger.info("="*50)
        logger.info("Starting ML Training Pipeline")
        logger.info("="*50)
        
        try:
            # Start MLflow run
            run_name = self.config.get_run_name()
            self.mlflow_manager.start_run(run_name)
            logger.info(f"Started MLflow run: {run_name}")
            
            # Step 1: Create dataset
            logger.info("Step 1: Creating dataset from feature store")
            X, y = self._create_dataset()
            
            if len(X) == 0:
                logger.error("No data available for training")
                return False
            
            # Step 2: Train/validation/test split
            logger.info("Step 2: Creating train/validation/test splits")
            X_train, X_val, X_test, y_train, y_val, y_test = self.dataset_creator.create_train_val_test_split(X, y)
            
            # Step 3: Feature preprocessing
            logger.info("Step 3: Preprocessing features")
            X_train_prep, X_val_prep, X_test_prep = self.dataset_creator.prepare_features(X_train, X_val, X_test)
            
            # Log dataset statistics
            self._log_dataset_stats(X_train_prep, y_train, X_val_prep, y_val, X_test_prep, y_test)
            
            # Step 4: Train model
            logger.info("Step 4: Training model")
            model = self.model_trainer.train_model(X_train_prep, y_train, X_val_prep, y_val)
            
            # Step 5: Cross-validation
            logger.info("Step 5: Performing cross-validation")
            cv_scores = self.model_trainer.cross_validate(X_train_prep, y_train)
            self.mlflow_manager.log_metrics(cv_scores)
            
            # Step 6: Model evaluation
            logger.info("Step 6: Evaluating model")
            test_metrics = self.model_trainer.evaluate_model(
                X_test_prep, y_test, X_train_prep, y_train
            )
            self.mlflow_manager.log_metrics(test_metrics)
            
            # Step 7: Save artifacts
            logger.info("Step 7: Saving model artifacts")
            artifacts = self.model_trainer.save_model_artifacts(str(self.output_dir))
            self.mlflow_manager.log_artifacts(artifacts)
            
            # Step 8: Register model
            logger.info("Step 8: Registering model in MLflow")
            model_info = self.mlflow_manager.register_model(model)
            
            # Step 9: Final summary
            self._log_training_summary(test_metrics, artifacts)
            
            logger.info("Training pipeline completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Training pipeline failed: {str(e)}")
            logger.exception("Full traceback:")
            return False
            
        finally:
            self.mlflow_manager.end_run()
    
    def _create_dataset(self) -> tuple[pd.DataFrame, pd.Series]:
        """Create training dataset from feature store or synthetic data."""
        try:
            # Try to get data from Redis feature store
            X, y = self.dataset_creator.create_fraud_dataset()
            
            if len(X) > 0:
                logger.info(f"Successfully created dataset from feature store: {len(X)} samples")
                return X, y
            else:
                logger.warning("No data in feature store, creating synthetic dataset for testing")
                
        except Exception as e:
            logger.warning(f"Failed to connect to feature store: {e}")
            logger.info("Creating synthetic dataset for testing")
        
        # Fallback to synthetic data
        X, y = create_synthetic_features_for_testing(
            n_samples=5000,
            fraud_rate=self.config.data.fraud_rate_target
        )
        
        return X, y
    
    def _log_dataset_stats(self, X_train, y_train, X_val, y_val, X_test, y_test):
        """Log dataset statistics to MLflow."""
        stats = {
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'test_samples': len(X_test),
            'total_features': X_train.shape[1],
            'train_fraud_rate': y_train.mean(),
            'val_fraud_rate': y_val.mean(),
            'test_fraud_rate': y_test.mean()
        }
        
        self.mlflow_manager.log_metrics(stats)
        
        logger.info("Dataset Statistics:")
        for key, value in stats.items():
            if 'rate' in key:
                logger.info(f"  {key}: {value:.2%}")
            else:
                logger.info(f"  {key}: {value}")
    
    def _log_training_summary(self, metrics: dict, artifacts: dict):
        """Log training summary."""
        logger.info("="*50)
        logger.info("Training Summary")
        logger.info("="*50)
        
        logger.info("Model Performance:")
        logger.info(f"  Test AUC: {metrics.get('test_auc', 0):.4f}")
        logger.info(f"  Test Precision: {metrics.get('test_precision', 0):.4f}")
        logger.info(f"  Test Recall: {metrics.get('test_recall', 0):.4f}")
        logger.info(f"  Test F1: {metrics.get('test_f1', 0):.4f}")
        
        logger.info("Artifacts Created:")
        for name, path in artifacts.items():
            logger.info(f"  {name}: {path}")
        
        # Model readiness assessment
        auc_score = metrics.get('test_auc', 0)
        if auc_score > 0.8:
            logger.info("✓ Model performance is good (AUC > 0.8)")
        elif auc_score > 0.7:
            logger.info("⚠ Model performance is acceptable (AUC > 0.7)")  
        else:
            logger.info("✗ Model performance needs improvement (AUC <= 0.7)")


@click.command()
@click.option('--config-file', default=None, help='Path to configuration file')
@click.option('--model-type', default='xgboost', help='Model type: xgboost, lightgbm, random_forest, logistic_regression')
@click.option('--experiment-name', default='fraud_detection', help='MLflow experiment name')
@click.option('--fraud-rate', default=0.02, type=float, help='Target fraud rate for synthetic data')
@click.option('--cv-folds', default=5, type=int, help='Number of cross-validation folds')
@click.option('--test-size', default=0.2, type=float, help='Test set proportion')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def main(config_file, model_type, experiment_name, fraud_rate, cv_folds, test_size, verbose):
    """Run ML training pipeline."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info(f"Starting training with model_type={model_type}, experiment={experiment_name}")
    
    try:
        # Load configuration
        if config_file and os.path.exists(config_file):
            # TODO: Load from YAML file
            config = TrainingConfig.from_env()
        else:
            config = TrainingConfig.from_env()
        
        # Override config with CLI arguments
        config.model.model_type = model_type
        config.mlflow.experiment_name = experiment_name
        config.data.fraud_rate_target = fraud_rate
        config.model.cv_folds = cv_folds
        config.model.test_size = test_size
        
        # Run training pipeline
        pipeline = TrainingPipeline(config)
        success = pipeline.run_training_pipeline()
        
        if success:
            logger.info("Training completed successfully!")
            
            # Print next steps
            print("\n" + "="*50)
            print("Next Steps:")
            print("="*50)
            print("1. View experiment in MLflow UI: http://localhost:5000")
            print("2. Check model artifacts in: training/outputs/")
            print("3. Test model serving: make serve")
            print("4. Run inference: curl -X POST http://localhost:8080/score")
            
        else:
            logger.error("Training failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Training script failed: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == '__main__':
    main()
