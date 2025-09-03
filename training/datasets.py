#!/usr/bin/env python3
"""
Dataset creation from feature store.

This module handles:
- Feature retrieval from Redis feature store
- Label generation for fraud detection and personalization
- Data quality validation and preprocessing
- Train/validation/test splits
"""

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional


import pandas as pd
import numpy as np
import redis
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder

from config import TrainingConfig, FRAUD_FEATURES

logger = logging.getLogger(__name__)


class FeatureStoreDataset:
    """Dataset creator that interfaces with our Redis feature store."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.redis_client = redis.Redis(
            host=config.data.redis_host,
            port=config.data.redis_port,
            db=config.data.redis_db,
            decode_responses=True
        )
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        
    def create_fraud_dataset(self) -> Tuple[pd.DataFrame, pd.Series]:
        """Create fraud detection dataset from feature store."""
        logger.info("Creating fraud detection dataset from feature store")
        
        # Get all card entities with features
        card_features = self._get_card_features()
        logger.info(f"Retrieved features for {len(card_features)} cards")
        
        if len(card_features) < self.config.data.min_samples_per_entity:
            logger.warning(f"Insufficient data: {len(card_features)} cards, minimum required: {self.config.data.min_samples_per_entity}")
            return pd.DataFrame(), pd.Series()
        
        # Convert to DataFrame
        df = pd.DataFrame(card_features)
        
        # Ensure ground truth fraud labels are available
        if 'actual_fraud' not in df.columns:
            raise ValueError("Ground truth fraud labels not found in feature store. Ensure transaction generator is running with fraud labels enabled.")
        
        logger.info("Using ground truth fraud labels from transaction generator")
        df['is_fraud'] = df['actual_fraud'].fillna(False)
        
        # Log fraud label statistics
        fraud_count = df['actual_fraud'].sum()
        total_count = len(df)
        fraud_rate = fraud_count / total_count if total_count > 0 else 0
        logger.info(f"Ground truth fraud labels: {fraud_count}/{total_count} ({fraud_rate:.2%} fraud rate)")
        
        # Validate data quality
        df = self._validate_data_quality(df)
        
        # Prepare features and target
        feature_cols = [col for col in FRAUD_FEATURES if col in df.columns]
        X = df[feature_cols].copy()
        y = df['is_fraud'].copy()
        
        logger.info(f"Created dataset: {X.shape[0]} samples, {X.shape[1]} features")
        logger.info(f"Fraud rate: {y.mean():.2%}")
        
        return X, y
    
    def _get_card_features(self) -> List[Dict[str, Any]]:
        """Retrieve all card features from Redis."""
        features_list = []
        
        # Get all card feature keys
        pattern = "features:card:*:transaction"
        card_keys = self.redis_client.keys(pattern)
        
        logger.info(f"Found {len(card_keys)} card feature keys")
        
        for key in card_keys:
            try:
                # Extract card ID from key
                card_id = key.split(':')[2]
                
                # Get features from Redis
                raw_features = self.redis_client.hgetall(key)
                
                if not raw_features:
                    continue
                    
                # Parse features
                features = self._parse_redis_features(raw_features)
                features['card_id'] = card_id
                
                # Add timestamp if available
                if 'feature_timestamp' in features:
                    features['timestamp'] = pd.to_datetime(features['feature_timestamp'], unit='ms')
                
                features_list.append(features)
                
            except Exception as e:
                logger.warning(f"Failed to process key {key}: {e}")
                continue
        
        return features_list
    
    def _parse_redis_features(self, redis_data: Dict[str, str]) -> Dict[str, Any]:
        """Parse Redis string values back to appropriate types."""
        parsed = {}
        
        for key, value in redis_data.items():
            if key in ['entity_id', 'entity_type', 'feature_type']:
                parsed[key] = value
                continue
                
            try:
                # Try to parse as number
                if '.' in value or 'e' in value.lower():
                    parsed[key] = float(value)
                else:
                    parsed[key] = int(value)
            except ValueError:
                try:
                    # Try to parse as boolean
                    if value.lower() in ('true', 'false'):
                        parsed[key] = value.lower() == 'true'
                    else:
                        # Keep as string
                        parsed[key] = value
                except:
                    parsed[key] = value
                    
        return parsed
    
    
    def _validate_data_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean data quality issues."""
        logger.info("Validating data quality")
        
        initial_rows = len(df)
        
        # Remove rows with too many missing values
        missing_rate = df.isnull().sum(axis=1) / len(df.columns)
        df = df[missing_rate <= self.config.data.max_missing_rate]
        
        # Handle missing values
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
        
        # Handle categorical missing values
        categorical_cols = df.select_dtypes(include=['object', 'bool']).columns
        for col in categorical_cols:
            if col in df.columns:
                df[col] = df[col].fillna(df[col].mode()[0] if len(df[col].mode()) > 0 else False)
        
        # Remove outliers using IQR method for key numerical features
        key_features = ['amount_avg_5m', 'amount_sum_5m', 'velocity_score']
        for feature in key_features:
            if feature in df.columns:
                Q1 = df[feature].quantile(0.25)
                Q3 = df[feature].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                outlier_mask = (df[feature] < lower_bound) | (df[feature] > upper_bound)
                df = df[~outlier_mask]
        
        logger.info(f"Data quality validation: {initial_rows} -> {len(df)} rows ({len(df)/initial_rows:.1%} retained)")
        
        return df
    
    def create_train_val_test_split(self, X: pd.DataFrame, y: pd.Series) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
        """Create stratified train/validation/test splits."""
        logger.info("Creating train/validation/test splits")
        
        # First split: train+val vs test
        X_temp, X_test, y_temp, y_test = train_test_split(
            X, y,
            test_size=self.config.model.test_size,
            stratify=y,
            random_state=42
        )
        
        # Second split: train vs validation
        val_size_adjusted = self.config.model.validation_size / (1 - self.config.model.test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp,
            test_size=val_size_adjusted,
            stratify=y_temp,
            random_state=42
        )
        
        logger.info(f"Data splits - Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
        logger.info(f"Train fraud rate: {y_train.mean():.2%}")
        logger.info(f"Val fraud rate: {y_val.mean():.2%}")
        logger.info(f"Test fraud rate: {y_test.mean():.2%}")
        
        return X_train, X_val, X_test, y_train, y_val, y_test
    
    def prepare_features(self, X_train: pd.DataFrame, X_val: pd.DataFrame, X_test: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Prepare features for training (scaling, encoding, etc.)."""
        logger.info("Preparing features for training")
        
        # Identify numeric and categorical columns
        numeric_cols = X_train.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = X_train.select_dtypes(include=['object']).columns.tolist()
        boolean_cols = X_train.select_dtypes(include=['bool']).columns.tolist()
        
        logger.info(f"Feature types - Numeric: {len(numeric_cols)}, Categorical: {len(categorical_cols)}, Boolean: {len(boolean_cols)}")
        
        # Prepare copies
        X_train_prep = X_train.copy()
        X_val_prep = X_val.copy()
        X_test_prep = X_test.copy()
        
        # Scale numeric features
        if numeric_cols:
            X_train_prep[numeric_cols] = self.scaler.fit_transform(X_train[numeric_cols])
            X_val_prep[numeric_cols] = self.scaler.transform(X_val[numeric_cols])
            X_test_prep[numeric_cols] = self.scaler.transform(X_test[numeric_cols])
        
        # Convert boolean to numeric
        for col in boolean_cols:
            X_train_prep[col] = X_train_prep[col].astype(int)
            X_val_prep[col] = X_val_prep[col].astype(int)
            X_test_prep[col] = X_test_prep[col].astype(int)
        
        # Handle categorical variables (if any)
        for col in categorical_cols:
            # Simple label encoding for now
            combined_values = pd.concat([X_train[col], X_val[col], X_test[col]])
            self.label_encoder.fit(combined_values.astype(str))
            
            X_train_prep[col] = self.label_encoder.transform(X_train[col].astype(str))
            X_val_prep[col] = self.label_encoder.transform(X_val[col].astype(str))
            X_test_prep[col] = self.label_encoder.transform(X_test[col].astype(str))
        
        return X_train_prep, X_val_prep, X_test_prep
    
    def create_personalization_dataset(self) -> Tuple[pd.DataFrame, pd.Series]:
        """Create personalization dataset (placeholder for future implementation)."""
        logger.info("Personalization dataset creation not yet implemented")
        return pd.DataFrame(), pd.Series()



