"""
Shared Prometheus metrics for stream processors.

This module provides centralized metric definitions to avoid
duplicate registrations across different processor modules.
"""

from prometheus_client import Counter, Gauge, Histogram

# Feature computation metrics
FEATURES_COMPUTED = Counter(
    'stream_features_computed_total',
    'Total features computed',
    ['feature_type', 'entity_type']
)

# Window metrics
WINDOW_SIZE = Gauge(
    'stream_window_size',
    'Current window size',
    ['window_type', 'processor']
)

# Processing metrics
PROCESSING_DURATION = Histogram(
    'stream_processing_duration_seconds',
    'Time spent processing events',
    ['event_type', 'processor']
)

# Event metrics
EVENTS_PROCESSED = Counter(
    'stream_events_processed_total',
    'Total events processed',
    ['event_type', 'status']
)

# Late event metrics
LATE_EVENTS = Counter(
    'stream_late_events_total',
    'Total late events detected',
    ['event_type', 'action']
)
