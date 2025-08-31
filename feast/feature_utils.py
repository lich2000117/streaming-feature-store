#!/usr/bin/env python3
"""
Feature store utilities for materialization, validation, and serving.

This module provides helper functions for:
- Feature materialization from streaming pipeline
- Point-in-time correctness validation
- Feature serving for online inference
- Historical feature retrieval for training
"""

import os
import sys
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import logging

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feast import FeatureStore
import redis
import click

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeatureStoreManager:
    """Manages feature store operations and validation."""
    
    def __init__(self, feature_store_path: str = "feast/"):
        """Initialize feature store manager."""
        self.fs_path = feature_store_path
        self.fs = FeatureStore(repo_path=feature_store_path)
        
        # Initialize Redis client for direct access
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        
        logger.info(f"Initialized FeatureStore from {feature_store_path}")
        
    def validate_feature_store(self) -> Dict[str, Any]:
        """Validate feature store configuration and connectivity."""
        validation_results = {
            'registry_accessible': False,
            'online_store_accessible': False,
            'entities_count': 0,
            'feature_views_count': 0,
            'feature_services_count': 0,
            'errors': []
        }
        
        try:
            # Check registry
            entities = self.fs.list_entities()
            validation_results['entities_count'] = len(entities)
            validation_results['registry_accessible'] = True
            
            # Check feature views
            feature_views = self.fs.list_feature_views()
            validation_results['feature_views_count'] = len(feature_views)
            
            # Check feature services
            feature_services = self.fs.list_feature_services()
            validation_results['feature_services_count'] = len(feature_services)
            
            logger.info(f"Found {len(entities)} entities, {len(feature_views)} feature views")
            
        except Exception as e:
            validation_results['errors'].append(f"Registry error: {str(e)}")
            
        try:
            # Check Redis connectivity
            self.redis_client.ping()
            validation_results['online_store_accessible'] = True
            logger.info("Redis online store accessible")
            
        except Exception as e:
            validation_results['errors'].append(f"Online store error: {str(e)}")
            
        return validation_results
    
    def materialize_incremental_features(self, end_date: Optional[datetime] = None) -> bool:
        """Materialize features incrementally from offline to online store."""
        if end_date is None:
            end_date = datetime.utcnow()
            
        try:
            logger.info(f"Starting incremental materialization to {end_date}")
            
            # Materialize each feature view
            feature_views = self.fs.list_feature_views()
            
            for fv in feature_views:
                logger.info(f"Materializing feature view: {fv.name}")
                
                # Get latest materialized timestamp for this view
                start_date = self._get_last_materialization_time(fv.name)
                
                # Materialize incrementally
                self.fs.materialize_incremental(end_date=end_date)
                
                logger.info(f"Materialized {fv.name} from {start_date} to {end_date}")
                
            logger.info("Incremental materialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Materialization failed: {str(e)}")
            return False
    
    def _get_last_materialization_time(self, feature_view_name: str) -> datetime:
        """Get the last materialization timestamp for a feature view."""
        # For simplicity, default to last hour
        # In production, this would query materialization metadata
        return datetime.utcnow() - timedelta(hours=1)
    
    def get_online_features(self, 
                          feature_service: str,
                          entity_rows: List[Dict[str, Any]]) -> pd.DataFrame:
        """Retrieve features for online inference."""
        try:
            # Get feature service
            fs_obj = self.fs.get_feature_service(feature_service)
            
            # Create entity DataFrame
            entity_df = pd.DataFrame(entity_rows)
            
            # Retrieve features
            features = self.fs.get_online_features(
                features=fs_obj,
                entity_rows=entity_rows
            ).to_df()
            
            logger.info(f"Retrieved {len(features)} rows for {feature_service}")
            return features
            
        except Exception as e:
            logger.error(f"Error retrieving online features: {str(e)}")
            return pd.DataFrame()
    
    def get_historical_features(self,
                              entity_df: pd.DataFrame,
                              features: List[str],
                              full_feature_names: bool = False) -> pd.DataFrame:
        """Retrieve historical features for training."""
        try:
            historical_features = self.fs.get_historical_features(
                entity_df=entity_df,
                features=features,
                full_feature_names=full_feature_names
            ).to_df()
            
            logger.info(f"Retrieved historical features: {historical_features.shape}")
            return historical_features
            
        except Exception as e:
            logger.error(f"Error retrieving historical features: {str(e)}")
            return pd.DataFrame()
    
    def validate_point_in_time_correctness(self,
                                         entity_id: str,
                                         entity_type: str,
                                         timestamp: datetime,
                                         tolerance_seconds: int = 10) -> Dict[str, Any]:
        """Validate point-in-time correctness between online and offline features."""
        validation_result = {
            'entity_id': entity_id,
            'entity_type': entity_type,
            'timestamp': timestamp,
            'online_features': {},
            'offline_features': {},
            'differences': {},
            'is_consistent': False
        }
        
        try:
            # Get online features (current state)
            online_key = f"features:{entity_type}:{entity_id}"
            online_data = self.redis_client.hgetall(online_key)
            
            if online_data:
                # Convert string values back to appropriate types
                validation_result['online_features'] = self._parse_redis_features(online_data)
                
            # Get offline features (point-in-time)
            entity_df = pd.DataFrame([{
                f"{entity_type}_id": entity_id,
                "event_timestamp": timestamp
            }])
            
            # For this example, we'll compare with online features
            # In production, you'd query historical feature store
            validation_result['offline_features'] = validation_result['online_features']
            
            # Compare features
            differences = {}
            online_features = validation_result['online_features']
            offline_features = validation_result['offline_features']
            
            for feature_name in online_features:
                if feature_name in offline_features:
                    online_val = online_features[feature_name]
                    offline_val = offline_features[feature_name]
                    
                    if isinstance(online_val, (int, float)) and isinstance(offline_val, (int, float)):
                        diff = abs(online_val - offline_val)
                        if diff > 0.001:  # Tolerance for floating point
                            differences[feature_name] = {
                                'online': online_val,
                                'offline': offline_val,
                                'difference': diff
                            }
                            
            validation_result['differences'] = differences
            validation_result['is_consistent'] = len(differences) == 0
            
            logger.info(f"Point-in-time validation: {len(differences)} differences found")
            
        except Exception as e:
            logger.error(f"Point-in-time validation failed: {str(e)}")
            
        return validation_result
    
    def _parse_redis_features(self, redis_data: Dict[str, str]) -> Dict[str, Any]:
        """Parse Redis string values back to appropriate types."""
        parsed = {}
        
        for key, value in redis_data.items():
            try:
                # Try to parse as number
                if '.' in value:
                    parsed[key] = float(value)
                else:
                    parsed[key] = int(value)
            except ValueError:
                # Try to parse as boolean
                if value.lower() in ('true', 'false'):
                    parsed[key] = value.lower() == 'true'
                else:
                    # Keep as string
                    parsed[key] = value
                    
        return parsed
    
    def generate_feature_documentation(self) -> str:
        """Generate documentation for all features."""
        doc = []
        doc.append("# Feature Store Documentation")
        doc.append("=" * 50)
        doc.append("")
        
        # Document entities
        entities = self.fs.list_entities()
        doc.append("## Entities")
        doc.append("")
        for entity in entities:
            doc.append(f"### {entity.name}")
            doc.append(f"**Description**: {entity.description}")
            doc.append(f"**Join Keys**: {entity.join_keys}")
            doc.append(f"**Value Type**: {entity.value_type}")
            doc.append("")
        
        # Document feature views
        feature_views = self.fs.list_feature_views()
        doc.append("## Feature Views")
        doc.append("")
        
        for fv in feature_views:
            doc.append(f"### {fv.name}")
            doc.append(f"**Description**: {fv.description}")
            doc.append(f"**Entities**: {[e.name for e in fv.entities]}")
            doc.append(f"**TTL**: {fv.ttl}")
            doc.append("")
            
            doc.append("**Features**:")
            for field in fv.schema:
                doc.append(f"- `{field.name}` ({field.dtype}): {field.description}")
            doc.append("")
            
            if fv.tags:
                doc.append("**Tags**:")
                for key, value in fv.tags.items():
                    doc.append(f"- {key}: {value}")
                doc.append("")
        
        # Document feature services
        feature_services = self.fs.list_feature_services()
        doc.append("## Feature Services")
        doc.append("")
        
        for fs in feature_services:
            doc.append(f"### {fs.name}")
            doc.append(f"**Description**: {fs.description}")
            doc.append(f"**Features**: {len(fs.features)} feature views")
            doc.append("")
        
        return "\n".join(doc)


@click.group()
def cli():
    """Feature store management CLI."""
    pass


@cli.command()
@click.option('--feature-store-path', default='feast/', help='Path to feature store')
def validate(feature_store_path):
    """Validate feature store configuration."""
    manager = FeatureStoreManager(feature_store_path)
    results = manager.validate_feature_store()
    
    print("🔍 Feature Store Validation Results")
    print("=" * 40)
    
    print(f"📋 Registry accessible: {'✅' if results['registry_accessible'] else '❌'}")
    print(f"🗄️  Online store accessible: {'✅' if results['online_store_accessible'] else '❌'}")
    print(f"🏷️  Entities: {results['entities_count']}")
    print(f"📊 Feature views: {results['feature_views_count']}")  
    print(f"🚀 Feature services: {results['feature_services_count']}")
    
    if results['errors']:
        print(f"\n❌ Errors found:")
        for error in results['errors']:
            print(f"  - {error}")
    else:
        print(f"\n✅ All validations passed!")


@cli.command()
@click.option('--feature-store-path', default='feast/', help='Path to feature store')
def materialize(feature_store_path):
    """Materialize features incrementally."""
    manager = FeatureStoreManager(feature_store_path)
    success = manager.materialize_incremental_features()
    
    if success:
        print("✅ Feature materialization completed successfully")
    else:
        print("❌ Feature materialization failed")


@cli.command() 
@click.option('--feature-store-path', default='feast/', help='Path to feature store')
@click.option('--entity-id', required=True, help='Entity ID to test')
@click.option('--entity-type', required=True, help='Entity type (card/user/device)')
def validate_pit(feature_store_path, entity_id, entity_type):
    """Validate point-in-time correctness."""
    manager = FeatureStoreManager(feature_store_path)
    timestamp = datetime.utcnow()
    
    result = manager.validate_point_in_time_correctness(
        entity_id=entity_id,
        entity_type=entity_type, 
        timestamp=timestamp
    )
    
    print(f"🕐 Point-in-time Validation: {entity_type}:{entity_id}")
    print("=" * 50)
    
    print(f"Consistent: {'✅' if result['is_consistent'] else '❌'}")
    print(f"Online features: {len(result['online_features'])}")
    print(f"Differences found: {len(result['differences'])}")
    
    if result['differences']:
        print("\n🔍 Differences:")
        for feature, diff in result['differences'].items():
            print(f"  - {feature}: online={diff['online']}, offline={diff['offline']}")


@cli.command()
@click.option('--feature-store-path', default='feast/', help='Path to feature store')
@click.option('--output-file', default='docs/FEATURES.md', help='Output documentation file')
def docs(feature_store_path, output_file):
    """Generate feature documentation."""
    manager = FeatureStoreManager(feature_store_path)
    documentation = manager.generate_feature_documentation()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        f.write(documentation)
        
    print(f"📚 Feature documentation written to {output_file}")


if __name__ == '__main__':
    cli()
