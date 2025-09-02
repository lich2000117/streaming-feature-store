"""
Transaction feature processors.

Contains business logic for computing fraud detection features
from transaction events. Supports both simplified and PyFlink processors.
"""

import time
from datetime import datetime
from typing import Dict, Any
from collections import defaultdict
import structlog

from streaming.core.models.config import ProcessorConfig, FeatureJobConfig
from streaming.core.models.events import TransactionEvent
from streaming.core.models.features import TransactionFeatures
from streaming.core.utils.windowing import SlidingWindow
from streaming.core.utils.metrics import FEATURES_COMPUTED, WINDOW_SIZE, PROCESSING_DURATION

logger = structlog.get_logger(__name__)


class TransactionFeatureComputer:
    """Compute features from transaction events (simplified processor)."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.windows = defaultdict(lambda: SlidingWindow(
            config.window_size_minutes * 60 * 1000,
            config.window_slide_minutes * 60 * 1000
        ))
        
    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a transaction event and compute features."""
        try:
            card_id = event['card_id']
            timestamp = event['timestamp']
            amount = event['amount']
            
            # Add to sliding window
            window = self.windows[card_id]
            window.add_event(timestamp, event)
            
            # Compute windowed features
            window_events = window.get_events()
            
            if not window_events:
                return None
                
            # Count features
            txn_count = len(window_events)
            
            # Amount features
            amounts = [e[1]['amount'] for e in window_events]
            amount_sum = sum(amounts)
            amount_avg = amount_sum / len(amounts)
            amount_max = max(amounts)
            amount_min = min(amounts)
            
            # Geographic features
            countries = set(e[1].get('geo_country') for e in window_events if e[1].get('geo_country'))
            unique_countries = len(countries)
            
            # Time-based features
            timestamps = [e[0] for e in window_events]
            if len(timestamps) > 1:
                timestamps.sort()
                time_since_last = (timestamps[-1] - timestamps[-2]) / (1000 * 60)  # minutes
                avg_time_between = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1) / (1000 * 60)
            else:
                time_since_last = None
                avg_time_between = None
                
            # Risk indicators (aligned with generator fraud_likelihood >= 0.2)
            high_risk_mccs = ['6011', '5967', '7011', '5311']  # atm, online, hotel, retail
            high_risk_txns = sum(1 for e in window_events if e[1].get('mcc') in high_risk_mccs)
            risk_ratio = high_risk_txns / len(window_events)
            has_high_risk_mcc = risk_ratio > 0
            
            # Velocity features
            velocity_score = 0.0
            if len(window_events) > 1:
                time_span_hours = (timestamps[-1] - timestamps[0]) / (1000 * 3600)
                if time_span_hours > 0:
                    txn_per_hour = len(window_events) / time_span_hours
                    velocity_score = min(txn_per_hour / 10.0, 1.0)  # Normalize to 0-1
            
            # Standard deviation calculation
            std_dev = 0.0
            if len(amounts) > 1:
                mean = amount_avg
                variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
                std_dev = variance ** 0.5
                
            # Time-based features
            current_time = datetime.fromtimestamp(timestamp / 1000)
            is_weekend = current_time.weekday() >= 5
            hour_of_day = current_time.hour
            
            # Compute 30m and 24h windows for additional features
            window_30m = [e for e in window_events if (timestamp - e[0]) <= (30 * 60 * 1000)]
            window_24h = [e for e in window_events if (timestamp - e[0]) <= (24 * 60 * 60 * 1000)]
            txn_count_30m = len(window_30m)
            txn_count_24h = len(window_24h)
            
            # Create feature record
            features = {
                'entity_id': card_id,
                'entity_type': 'card',
                'feature_type': 'transaction',
                
                # Count features
                'txn_count_5m': txn_count,
                'txn_count_30m': txn_count_30m,
                'txn_count_24h': txn_count_24h,
                
                # Amount features
                'amount_sum_5m': round(amount_sum, 2),
                'amount_avg_5m': round(amount_avg, 2),
                'amount_max_5m': round(amount_max, 2),
                'amount_min_5m': round(amount_min, 2),
                'amount_std_5m': round(std_dev, 2),
                
                # Geographic features
                'unique_countries_5m': unique_countries,
                'geo_diversity_score': min(unique_countries / 3.0, 1.0),
                
                # Temporal features
                'time_since_last_txn_min': round(time_since_last, 2) if time_since_last else None,
                'avg_time_between_txns_min': round(avg_time_between, 2) if avg_time_between else None,
                'is_weekend': is_weekend,
                'hour_of_day': hour_of_day,
                'velocity_score': round(velocity_score, 3),
                
                # Risk features
                'high_risk_txn_ratio': round(risk_ratio, 3),
                'has_high_risk_mcc': has_high_risk_mcc,
                'is_high_velocity': velocity_score > 0.7,
                'is_geo_diverse': unique_countries > 2,
                
                # Ground truth (if available from current event)
                'actual_fraud': event.get('is_fraud'),  # Store ground truth for validation
                
                # Metadata
                'window_size_minutes': self.config.window_size_minutes,
                'feature_timestamp': timestamp,
                'computation_timestamp': int(time.time() * 1000),
                'window_event_count': len(window_events)
            }
            
            FEATURES_COMPUTED.labels(feature_type='transaction', entity_type='card').inc()
            WINDOW_SIZE.labels(window_type='transaction', processor='simple').set(len(window_events))
            
            return features
            
        except Exception as e:
            logger.error("Error computing transaction features", 
                        event=event, 
                        error=str(e))
            return None


def compute_transaction_features_from_window(events: list, config: ProcessorConfig) -> Dict[str, Any]:
    """
    Compute transaction features from a list of events in a window.
    Used by both simplified and PyFlink processors.
    """
    if not events:
        return None
        
    # Parse all events
    parsed_events = []
    for event_dict in events:
        try:
            if isinstance(event_dict, dict):
                # Direct dict (from simplified processor)
                parsed_events.append(event_dict)
            else:
                # Parse with Pydantic (from PyFlink)
                event = TransactionEvent(**event_dict)
                parsed_events.append(event.dict())
        except Exception as e:
            logger.warning("Failed to parse event in window", event=event_dict, error=str(e))
            continue
    
    if not parsed_events:
        return None
    
    # Compute windowed aggregations
    amounts = [e['amount'] for e in parsed_events]
    timestamps = [e['timestamp'] for e in parsed_events]
    countries = set(e.get('geo_country') for e in parsed_events if e.get('geo_country'))
    mccs = [e.get('mcc') for e in parsed_events if e.get('mcc')]
    
    # Aggregated features
    txn_count = len(parsed_events)
    amount_sum = sum(amounts)
    amount_avg = amount_sum / txn_count
    amount_max = max(amounts)
    amount_min = min(amounts)
    amount_std = 0.0
    if txn_count > 1:
        variance = sum((x - amount_avg) ** 2 for x in amounts) / (txn_count - 1)
        amount_std = variance ** 0.5
    
    unique_countries = len(countries)
    
    # Time-based features
    timestamps.sort()
    time_span_minutes = (timestamps[-1] - timestamps[0]) / (1000 * 60) if len(timestamps) > 1 else 0
    avg_time_between_txns = time_span_minutes / max(txn_count - 1, 1)
    
    # Risk indicators (aligned with generator fraud_likelihood >= 0.2)
    high_risk_mccs = ['6011', '5967', '7011', '5311']  # atm, online, hotel, retail
    high_risk_count = sum(1 for mcc in mccs if mcc in high_risk_mccs)
    high_risk_ratio = high_risk_count / txn_count if txn_count > 0 else 0
    
    # Velocity features
    velocity_per_minute = txn_count / max(time_span_minutes, 1)
    amount_velocity = amount_sum / max(time_span_minutes, 1)
    
    # Weekend/hour analysis
    weekend_count = 0
    hour_distribution = {}
    for event in parsed_events:
        event_time = datetime.fromtimestamp(event['timestamp'] / 1000)
        if event_time.weekday() >= 5:
            weekend_count += 1
        hour = event_time.hour
        hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
    
    weekend_ratio = weekend_count / txn_count
    most_active_hour = max(hour_distribution.keys(), key=lambda h: hour_distribution[h]) if hour_distribution else 0
    
    return {
        'txn_count': txn_count,
        'amount_sum': amount_sum,
        'amount_avg': amount_avg,
        'amount_max': amount_max,
        'amount_min': amount_min,
        'amount_std': amount_std,
        'unique_countries': unique_countries,
        'velocity_per_minute': velocity_per_minute,
        'amount_velocity': amount_velocity,
        'high_risk_ratio': high_risk_ratio,
        'weekend_ratio': weekend_ratio,
        'most_active_hour': most_active_hour,
        'avg_time_between_txns': avg_time_between_txns
    }
