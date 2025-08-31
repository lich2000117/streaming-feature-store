#!/usr/bin/env python3
"""
Model and Data Drift Detection

This module monitors for:
1. Data drift - changes in feature distributions
2. Model drift - degradation in model performance  
3. Prediction drift - changes in model output distributions

Integration with monitoring pipeline for production alerts.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np
import click
from scipy import stats
import redis

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.config import TrainingConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DriftDetector:
    """Data and model drift detection system."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.data.redis_host,
            port=config.data.redis_port,
            db=config.data.redis_db,
            decode_responses=True
        )
        
    def detect_data_drift(self, 
                         reference_data: pd.DataFrame, 
                         current_data: pd.DataFrame,
                         significance_level: float = 0.05) -> Dict[str, Any]:
        """Detect data drift using statistical tests."""
        logger.info("Detecting data drift between reference and current datasets")
        
        drift_results = {
            'timestamp': datetime.now().isoformat(),
            'reference_samples': len(reference_data),
            'current_samples': len(current_data),
            'features_analyzed': [],
            'drift_detected': False,
            'drifted_features': [],
            'feature_drift_scores': {}
        }
        
        common_features = list(set(reference_data.columns) & set(current_data.columns))
        drift_results['features_analyzed'] = common_features
        
        for feature in common_features:
            try:
                # Get feature values
                ref_values = reference_data[feature].dropna()
                curr_values = current_data[feature].dropna()
                
                if len(ref_values) == 0 or len(curr_values) == 0:
                    continue
                
                # Perform statistical test based on feature type
                if pd.api.types.is_numeric_dtype(reference_data[feature]):
                    # Kolmogorov-Smirnov test for continuous features
                    statistic, p_value = stats.ks_2samp(ref_values, curr_values)
                    test_name = "KS_test"
                else:
                    # Chi-square test for categorical features
                    # Create contingency table
                    ref_counts = ref_values.value_counts()
                    curr_counts = curr_values.value_counts()
                    
                    # Align categories
                    all_categories = set(ref_counts.index) | set(curr_counts.index)
                    ref_aligned = [ref_counts.get(cat, 0) for cat in all_categories]
                    curr_aligned = [curr_counts.get(cat, 0) for cat in all_categories]
                    
                    if sum(ref_aligned) > 0 and sum(curr_aligned) > 0:
                        statistic, p_value = stats.chisquare(curr_aligned, ref_aligned)
                        test_name = "chi_square_test"
                    else:
                        continue
                
                # Check for drift
                is_drifted = p_value < significance_level
                
                drift_results['feature_drift_scores'][feature] = {
                    'test_name': test_name,
                    'statistic': float(statistic),
                    'p_value': float(p_value),
                    'is_drifted': is_drifted,
                    'severity': self._get_drift_severity(p_value, significance_level)
                }
                
                if is_drifted:
                    drift_results['drifted_features'].append(feature)
                    
                logger.debug(f"Feature {feature}: {test_name} p-value = {p_value:.6f}, drift = {is_drifted}")
                
            except Exception as e:
                logger.warning(f"Failed to analyze drift for feature {feature}: {e}")
                continue
        
        drift_results['drift_detected'] = len(drift_results['drifted_features']) > 0
        
        logger.info(f"Drift detection completed: {len(drift_results['drifted_features'])} features drifted out of {len(common_features)}")
        
        return drift_results
    
    def _get_drift_severity(self, p_value: float, significance_level: float) -> str:
        """Classify drift severity based on p-value."""
        if p_value >= significance_level:
            return "none"
        elif p_value >= significance_level / 10:
            return "low"  
        elif p_value >= significance_level / 100:
            return "medium"
        else:
            return "high"
    
    def calculate_psi(self, expected: pd.Series, actual: pd.Series, buckets: int = 10) -> float:
        """Calculate Population Stability Index (PSI)."""
        def scale_range(input_series, buckets):
            """Scale series to buckets."""
            try:
                # Create quantile-based bins
                _, bin_edges = pd.qcut(input_series, q=buckets, retbins=True, duplicates='drop')
                return bin_edges
            except:
                # Fallback to equal-width bins
                return np.linspace(input_series.min(), input_series.max(), buckets + 1)
        
        # Create bins based on expected distribution
        bin_edges = scale_range(expected, buckets)
        
        # Calculate frequencies
        expected_counts = pd.cut(expected, bins=bin_edges, include_lowest=True).value_counts().sort_index()
        actual_counts = pd.cut(actual, bins=bin_edges, include_lowest=True).value_counts().sort_index()
        
        # Calculate percentages
        expected_pct = expected_counts / expected_counts.sum()
        actual_pct = actual_counts / actual_counts.sum()
        
        # Add small epsilon to avoid division by zero
        epsilon = 1e-6
        expected_pct = expected_pct + epsilon
        actual_pct = actual_pct + epsilon
        
        # Calculate PSI
        psi = ((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)).sum()
        
        return psi
    
    def monitor_prediction_drift(self, 
                               recent_predictions: List[float],
                               historical_predictions: List[float]) -> Dict[str, Any]:
        """Monitor drift in model predictions."""
        logger.info("Monitoring prediction drift")
        
        recent_pred = pd.Series(recent_predictions)
        hist_pred = pd.Series(historical_predictions)
        
        # Calculate PSI for predictions
        psi_score = self.calculate_psi(hist_pred, recent_pred)
        
        # Statistical test
        statistic, p_value = stats.ks_2samp(historical_predictions, recent_predictions)
        
        # Interpret PSI score
        if psi_score < 0.1:
            psi_interpretation = "no_shift"
        elif psi_score < 0.2:
            psi_interpretation = "minor_shift"  
        else:
            psi_interpretation = "major_shift"
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'psi_score': float(psi_score),
            'psi_interpretation': psi_interpretation,
            'ks_statistic': float(statistic),
            'ks_p_value': float(p_value),
            'recent_samples': len(recent_predictions),
            'historical_samples': len(historical_predictions),
            'recent_mean': float(recent_pred.mean()),
            'historical_mean': float(hist_pred.mean()),
            'drift_detected': psi_score > 0.2 or p_value < 0.05
        }
        
        logger.info(f"Prediction drift PSI: {psi_score:.4f} ({psi_interpretation})")
        
        return results
    
    def get_current_features_from_redis(self, 
                                      feature_keys: List[str] = None,
                                      max_samples: int = 1000) -> pd.DataFrame:
        """Get current feature data from Redis for drift detection."""
        logger.info("Retrieving current features from Redis")
        
        if feature_keys is None:
            # Get all card and user feature keys
            card_keys = self.redis_client.keys("features:card:*:transaction")
            user_keys = self.redis_client.keys("features:user:*:clickstream")
            feature_keys = card_keys + user_keys
        
        # Limit to max samples for performance
        if len(feature_keys) > max_samples:
            feature_keys = np.random.choice(feature_keys, max_samples, replace=False)
        
        features_list = []
        
        for key in feature_keys:
            try:
                raw_features = self.redis_client.hgetall(key)
                if not raw_features:
                    continue
                
                # Parse features
                features = {}
                for k, v in raw_features.items():
                    try:
                        if '.' in v or 'e' in v.lower():
                            features[k] = float(v)
                        elif v.lower() in ('true', 'false'):
                            features[k] = v.lower() == 'true'
                        else:
                            features[k] = int(v)
                    except:
                        features[k] = v
                
                features_list.append(features)
                
            except Exception as e:
                logger.warning(f"Failed to process key {key}: {e}")
                continue
        
        if not features_list:
            logger.warning("No current features found in Redis")
            return pd.DataFrame()
        
        df = pd.DataFrame(features_list)
        logger.info(f"Retrieved {len(df)} current feature samples")
        
        return df
    
    def load_reference_data(self, reference_path: str = None) -> pd.DataFrame:
        """Load reference data for drift comparison."""
        if reference_path and os.path.exists(reference_path):
            logger.info(f"Loading reference data from {reference_path}")
            return pd.read_parquet(reference_path)
        else:
            logger.info("No reference data found, using synthetic data")
            # Generate synthetic reference data for testing
            from ml.datasets import create_synthetic_features_for_testing
            X, y = create_synthetic_features_for_testing(n_samples=2000, fraud_rate=0.02)
            X['is_fraud'] = y
            return X
    
    def save_drift_report(self, drift_results: Dict[str, Any], output_path: str = None):
        """Save drift detection report."""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"ml/outputs/drift_report_{timestamp}.json"
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(drift_results, f, indent=2)
        
        logger.info(f"Drift report saved to {output_path}")


@click.command()
@click.option('--reference-data', default=None, help='Path to reference dataset')
@click.option('--max-samples', default=1000, type=int, help='Maximum samples to analyze')
@click.option('--significance-level', default=0.05, type=float, help='Statistical significance level')
@click.option('--output-path', default=None, help='Output path for drift report')
@click.option('--redis-host', default='localhost', help='Redis host')
@click.option('--redis-port', default=6379, type=int, help='Redis port')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging')
def main(reference_data, max_samples, significance_level, output_path, redis_host, redis_port, verbose):
    """Run drift detection analysis."""
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting drift detection analysis")
    
    try:
        # Initialize drift detector
        config = TrainingConfig.from_env()
        config.data.redis_host = redis_host
        config.data.redis_port = redis_port
        
        detector = DriftDetector(config)
        
        # Load reference data
        reference_df = detector.load_reference_data(reference_data)
        if len(reference_df) == 0:
            logger.error("No reference data available")
            return
        
        # Get current data from Redis
        current_df = detector.get_current_features_from_redis(max_samples=max_samples)
        if len(current_df) == 0:
            logger.warning("No current data available in Redis - try running generators and stream processor first")
            return
        
        # Detect drift
        drift_results = detector.detect_data_drift(
            reference_df, 
            current_df, 
            significance_level=significance_level
        )
        
        # Save report
        detector.save_drift_report(drift_results, output_path)
        
        # Print summary
        print("\n" + "="*50)
        print("Drift Detection Summary")
        print("="*50)
        print(f"Features analyzed: {len(drift_results['features_analyzed'])}")
        print(f"Features with drift: {len(drift_results['drifted_features'])}")
        print(f"Overall drift detected: {'Yes' if drift_results['drift_detected'] else 'No'}")
        
        if drift_results['drifted_features']:
            print(f"\nDrifted features:")
            for feature in drift_results['drifted_features']:
                score_info = drift_results['feature_drift_scores'][feature]
                print(f"  - {feature}: {score_info['severity']} (p={score_info['p_value']:.6f})")
        
        print(f"\nDetailed report saved to: {output_path or 'ml/outputs/drift_report_<timestamp>.json'}")
        
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == '__main__':
    main()
