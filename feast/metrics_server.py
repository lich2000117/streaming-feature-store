#!/usr/bin/env python3
"""
Feast Metrics Server for Prometheus Integration

Exposes Feast feature store metrics in Prometheus format.
Runs alongside the main Feast server.
"""

import time
import logging
from threading import Thread
from typing import Dict, Any

from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
import feast
from feast import FeatureStore

logger = logging.getLogger(__name__)

# Feast-specific metrics
FEAST_FEATURE_RETRIEVALS = Counter(
    'feast_feature_retrievals_total',
    'Total feature retrievals from Feast',
    ['entity_type', 'feature_view', 'status']
)

FEAST_FEATURE_RETRIEVAL_DURATION = Histogram(
    'feast_feature_retrieval_duration_seconds',
    'Time spent retrieving features',
    ['entity_type', 'feature_view']
)

FEAST_ONLINE_STORE_CONNECTIONS = Gauge(
    'feast_online_store_connections',
    'Number of active online store connections'
)

FEAST_REGISTRY_OBJECTS = Gauge(
    'feast_registry_objects_total',
    'Number of objects in Feast registry',
    ['object_type']
)

FEAST_FEATURE_VIEWS = Gauge(
    'feast_feature_views_total',
    'Number of feature views in registry'
)

FEAST_ENTITIES = Gauge(
    'feast_entities_total', 
    'Number of entities in registry'
)

FEAST_INFO = Info(
    'feast_server_info',
    'Feast server information'
)


class FeastMetricsCollector:
    """Collects metrics from Feast feature store."""
    
    def __init__(self, feature_store: FeatureStore):
        self.fs = feature_store
        self.running = False
        
    def start_collection(self, interval: int = 30):
        """Start collecting metrics every interval seconds."""
        self.running = True
        
        def collect_loop():
            while self.running:
                try:
                    self.collect_metrics()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Error collecting Feast metrics: {e}")
                    time.sleep(interval)
        
        thread = Thread(target=collect_loop, daemon=True)
        thread.start()
        logger.info("Started Feast metrics collection")
    
    def collect_metrics(self):
        """Collect current metrics from Feast."""
        try:
            # Get registry objects
            registry = self.fs.registry
            
            # Count feature views
            feature_views = registry.list_feature_views(self.fs.project)
            FEAST_FEATURE_VIEWS.set(len(feature_views))
            
            # Count entities
            entities = registry.list_entities(self.fs.project)
            FEAST_ENTITIES.set(len(entities))
            
            # Count different object types
            FEAST_REGISTRY_OBJECTS.labels(object_type='feature_views').set(len(feature_views))
            FEAST_REGISTRY_OBJECTS.labels(object_type='entities').set(len(entities))
            
            # Get feature services
            try:
                feature_services = registry.list_feature_services(self.fs.project)
                FEAST_REGISTRY_OBJECTS.labels(object_type='feature_services').set(len(feature_services))
            except:
                pass
                
            # Update server info
            online_store_type = "unknown"
            try:
                if hasattr(self.fs, 'online_store') and self.fs.online_store:
                    online_store_type = type(self.fs.online_store).__name__
            except Exception:
                pass
                
            FEAST_INFO.info({
                'version': feast.__version__,
                'project': self.fs.project,
                'registry_type': type(registry).__name__,
                'online_store_type': online_store_type
            })
            
            logger.debug("Collected Feast metrics successfully")
            
        except Exception as e:
            logger.error(f"Failed to collect Feast metrics: {e}")
    
    def stop_collection(self):
        """Stop metrics collection."""
        self.running = False


def start_feast_metrics_server(port: int = 8567, feature_store_path: str = "."):
    """Start Prometheus metrics server for Feast."""
    try:
        # Initialize feature store
        fs = FeatureStore(repo_path=feature_store_path)
        
        # Start metrics collector
        collector = FeastMetricsCollector(fs)
        collector.start_collection(interval=30)
        
        # Start Prometheus metrics server
        start_http_server(port)
        logger.info(f"Feast metrics server started on port {port}")
        
        # Keep the server running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down Feast metrics server")
            collector.stop_collection()
            
    except Exception as e:
        logger.error(f"Failed to start Feast metrics server: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Feast Prometheus Metrics Server")
    parser.add_argument("--port", type=int, default=8567, help="Metrics server port")
    parser.add_argument("--feature-store-path", default=".", help="Path to feature store")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    start_feast_metrics_server(args.port, args.feature_store_path)
