#!/usr/bin/env python3
"""
MLflow Metrics Server for Prometheus Integration

Exposes MLflow experiment and training metrics in Prometheus format.
"""

import time
import logging
import sqlite3
from threading import Thread
from typing import Dict, Any, List
from pathlib import Path

from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
import mlflow
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)

# MLflow-specific metrics
MLFLOW_EXPERIMENTS_TOTAL = Gauge(
    'mlflow_experiments_total',
    'Total number of MLflow experiments'
)

MLFLOW_RUNS_TOTAL = Gauge(
    'mlflow_runs_total',
    'Total number of MLflow runs',
    ['experiment_name', 'status']
)

MLFLOW_MODELS_TOTAL = Gauge(
    'mlflow_models_total',
    'Total number of registered models'
)

MLFLOW_MODEL_VERSIONS = Gauge(
    'mlflow_model_versions_total',
    'Total number of model versions',
    ['model_name', 'stage']
)

MLFLOW_RUN_DURATION = Histogram(
    'mlflow_run_duration_seconds',
    'Duration of MLflow runs',
    ['experiment_name', 'status']
)

MLFLOW_METRICS_VALUES = Gauge(
    'mlflow_metric_value',
    'MLflow metric values',
    ['experiment_name', 'run_id', 'metric_name']
)

MLFLOW_TRAINING_ACCURACY = Gauge(
    'mlflow_training_model_accuracy',
    'Latest model accuracy scores',
    ['experiment_name', 'model_name', 'metric_type']
)

MLFLOW_INFO = Info(
    'mlflow_server_info',
    'MLflow server information'
)


class MLflowMetricsCollector:
    """Collects metrics from MLflow tracking server."""
    
    def __init__(self, tracking_uri: str = "http://mlflow:5001"):
        self.tracking_uri = tracking_uri
        self.client = MlflowClient(tracking_uri)
        self.running = False
        
    def start_collection(self, interval: int = 60):
        """Start collecting metrics every interval seconds."""
        self.running = True
        
        def collect_loop():
            while self.running:
                try:
                    self.collect_metrics()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Error collecting MLflow metrics: {e}")
                    time.sleep(interval)
        
        thread = Thread(target=collect_loop, daemon=True)
        thread.start()
        logger.info("Started MLflow metrics collection")
    
    def collect_metrics(self):
        """Collect current metrics from MLflow."""
        try:
            # Get all experiments
            experiments = self.client.search_experiments()
            MLFLOW_EXPERIMENTS_TOTAL.set(len(experiments))
            
            total_models = 0
            
            for experiment in experiments:
                exp_name = experiment.name
                
                # Get runs for this experiment
                runs = self.client.search_runs(
                    experiment_ids=[experiment.experiment_id],
                    max_results=1000
                )
                
                # Count runs by status
                status_counts = {}
                for run in runs:
                    status = run.info.status
                    status_counts[status] = status_counts.get(status, 0) + 1
                    
                    # Collect run duration
                    if run.info.end_time and run.info.start_time:
                        duration = (run.info.end_time - run.info.start_time) / 1000.0
                        MLFLOW_RUN_DURATION.labels(
                            experiment_name=exp_name,
                            status=status
                        ).observe(duration)
                    
                    # Collect latest metrics for completed runs
                    if status == "FINISHED" and run.data.metrics:
                        for metric_name, metric_value in run.data.metrics.items():
                            MLFLOW_METRICS_VALUES.labels(
                                experiment_name=exp_name,
                                run_id=run.info.run_id[:8],  # Short run ID
                                metric_name=metric_name
                            ).set(metric_value)
                            
                            # Special handling for model performance metrics
                            if metric_name in ['test_auc', 'test_accuracy', 'test_f1', 'test_precision', 'test_recall']:
                                MLFLOW_TRAINING_ACCURACY.labels(
                                    experiment_name=exp_name,
                                    model_name=run.data.tags.get('mlflow.runName', 'unknown'),
                                    metric_type=metric_name
                                ).set(metric_value)
                
                # Set run counts by status
                for status, count in status_counts.items():
                    MLFLOW_RUNS_TOTAL.labels(
                        experiment_name=exp_name,
                        status=status
                    ).set(count)
            
            # Get registered models
            try:
                models = self.client.search_registered_models()
                MLFLOW_MODELS_TOTAL.set(len(models))
                total_models = len(models)
                
                # Count model versions by stage
                stage_counts = {}
                for model in models:
                    for version in model.latest_versions:
                        stage = version.current_stage
                        stage_counts[stage] = stage_counts.get(stage, 0) + 1
                        
                        MLFLOW_MODEL_VERSIONS.labels(
                            model_name=model.name,
                            stage=stage
                        ).set(1)
                        
            except Exception as e:
                logger.warning(f"Could not collect model registry metrics: {e}")
                MLFLOW_MODELS_TOTAL.set(0)
            
            # Update server info
            MLFLOW_INFO.info({
                'tracking_uri': self.tracking_uri,
                'total_experiments': str(len(experiments)),
                'total_models': str(total_models)
            })
            
            logger.debug("Collected MLflow metrics successfully")
            
        except Exception as e:
            logger.error(f"Failed to collect MLflow metrics: {e}")
    
    def stop_collection(self):
        """Stop metrics collection."""
        self.running = False


def start_mlflow_metrics_server(port: int = 8568, tracking_uri: str = "http://mlflow:5001"):
    """Start Prometheus metrics server for MLflow."""
    try:
        # Initialize MLflow client
        collector = MLflowMetricsCollector(tracking_uri)
        collector.start_collection(interval=60)  # Collect every minute
        
        # Start Prometheus metrics server
        start_http_server(port)
        logger.info(f"MLflow metrics server started on port {port}")
        
        # Keep the server running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down MLflow metrics server")
            collector.stop_collection()
            
    except Exception as e:
        logger.error(f"Failed to start MLflow metrics server: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MLflow Prometheus Metrics Server")
    parser.add_argument("--port", type=int, default=8568, help="Metrics server port")
    parser.add_argument("--tracking-uri", default="http://mlflow:5001", help="MLflow tracking URI")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    start_mlflow_metrics_server(args.port, args.tracking_uri)
