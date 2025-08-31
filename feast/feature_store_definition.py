#!/usr/bin/env python3
"""
Main feature store definition file.

This file imports and registers all entities, feature views, and services
with the Feast feature store. This is the entry point for Feast CLI operations.

Usage:
    feast plan
    feast apply  
    feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
    feast serve
"""

# Import all feature store components
from entities import ALL_ENTITIES
from feature_views import ALL_FEATURE_VIEWS, ALL_FEATURE_SERVICES

# Register all components
# Feast will automatically discover these when running CLI commands

# Entities define the primary keys for features
entities = ALL_ENTITIES

# Feature views define the feature schemas and metadata  
feature_views = ALL_FEATURE_VIEWS

# Feature services define logical groupings for serving
feature_services = ALL_FEATURE_SERVICES

# Print summary for debugging
if __name__ == "__main__":
    print("🏪 Streaming Feature Store Definition")
    print("=" * 40)
    
    print(f"📋 Entities: {len(entities)}")
    for entity in entities:
        print(f"  - {entity.name}: {entity.description}")
        
    print(f"\n📊 Feature Views: {len(feature_views)}")
    for fv in feature_views:
        print(f"  - {fv.name}: {fv.description}")
        print(f"    Entities: {[e.name for e in fv.entities]}")
        print(f"    Features: {len(fv.schema)}")
        
    print(f"\n🚀 Feature Services: {len(feature_services)}")
    for fs in feature_services:
        print(f"  - {fs.name}: {fs.description}")
        print(f"    Features: {len(fs.features)}")
        
    print("\n✅ Feature store definition loaded successfully!")
