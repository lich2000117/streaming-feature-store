"""
Clickstream feature processors.

Contains business logic for computing personalization features
from clickstream events. Supports both simplified and PyFlink processors.
"""

import time
from typing import Dict, Any
from collections import defaultdict
import structlog

from streaming.core.models.config import ProcessorConfig
from streaming.core.models.events import ClickEvent
from streaming.core.models.features import ClickstreamFeatures
from streaming.core.utils.windowing import SlidingWindow
from streaming.core.utils.metrics import FEATURES_COMPUTED, WINDOW_SIZE, PROCESSING_DURATION

logger = structlog.get_logger(__name__)


class ClickstreamFeatureComputer:
    """Compute features from clickstream events (simplified processor)."""
    
    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.user_windows = defaultdict(lambda: SlidingWindow(
            config.window_size_minutes * 60 * 1000,
            config.window_slide_minutes * 60 * 1000
        ))
        self.session_state = defaultdict(dict)
        
    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a clickstream event and compute features."""
        try:
            user_id = event['user_id']
            session_id = event['session_id']
            timestamp = event['timestamp']
            page_type = event['page_type']
            action_type = event['action_type']
            
            # Add to sliding window
            window = self.user_windows[user_id]
            window.add_event(timestamp, event)
            
            # Update session state
            session_key = f"{user_id}:{session_id}"
            if session_key not in self.session_state:
                self.session_state[session_key] = {
                    'start_time': timestamp,
                    'page_count': 0,
                    'categories': set(),
                    'cart_actions': defaultdict(int),
                    'last_action_time': timestamp
                }
                
            session = self.session_state[session_key]
            session['page_count'] += 1
            session['last_action_time'] = timestamp
            
            if event.get('category_id'):
                session['categories'].add(event['category_id'])
                
            if action_type in ['ADD_TO_CART', 'REMOVE_FROM_CART', 'PURCHASE']:
                session['cart_actions'][action_type] += 1
            
            # Compute windowed features
            window_events = window.get_events()
            
            if not window_events:
                return None
                
            # Session features
            session_duration_min = (timestamp - session['start_time']) / (1000 * 60)
            pages_per_session = session['page_count']
            unique_categories_session = len(session['categories'])
            
            # Engagement features
            dwell_times = [e[1].get('dwell_time_ms', 0) for e in window_events if e[1].get('dwell_time_ms')]
            avg_dwell_time = sum(dwell_times) / len(dwell_times) / 1000 if dwell_times else 0  # seconds
            
            scroll_depths = [e[1].get('scroll_depth', 0) for e in window_events if e[1].get('scroll_depth')]
            avg_scroll_depth = sum(scroll_depths) / len(scroll_depths) if scroll_depths else 0
            
            # Activity features
            page_views = len(window_events)
            unique_pages = len(set(e[1]['page_type'] for e in window_events))
            click_events = sum(1 for e in window_events if e[1]['action_type'] == 'CLICK')
            click_rate = click_events / len(window_events) if window_events else 0
            
            # Purchase funnel features
            cart_adds = session['cart_actions']['ADD_TO_CART']
            cart_removes = session['cart_actions']['REMOVE_FROM_CART']
            purchases = session['cart_actions']['PURCHASE']
            
            conversion_rate = purchases / max(cart_adds, 1)
            cart_abandonment_rate = cart_removes / max(cart_adds, 1)
            
            # Engagement score
            engagement_score = 0.0
            engagement_score += min(avg_dwell_time / 30.0, 1.0) * 0.3  # 30s baseline
            engagement_score += avg_scroll_depth * 0.2
            engagement_score += min(pages_per_session / 10.0, 1.0) * 0.3  # 10 pages baseline
            engagement_score += conversion_rate * 0.2
            
            # Create feature record
            features = {
                'entity_id': user_id,
                'entity_type': 'user',
                'feature_type': 'clickstream',
                
                # Session features
                'session_duration_min': round(session_duration_min, 2),
                'pages_per_session': pages_per_session,
                'unique_categories_session': unique_categories_session,
                
                # Engagement features
                'avg_dwell_time_sec': round(avg_dwell_time, 2),
                'avg_scroll_depth': round(avg_scroll_depth, 3),
                'page_views_5m': page_views,
                'unique_pages_5m': unique_pages,
                'click_rate_5m': round(click_rate, 3),
                
                # Purchase funnel features
                'cart_adds_session': cart_adds,
                'cart_removes_session': cart_removes,
                'purchases_session': purchases,
                'conversion_rate_session': round(conversion_rate, 3),
                'cart_abandonment_rate': round(cart_abandonment_rate, 3),
                
                # Derived features
                'engagement_score': round(engagement_score, 3),
                'is_high_engagement': engagement_score > 0.7,
                'is_likely_purchaser': conversion_rate > 0.1,
                
                # Metadata
                'session_id': session_id,
                'window_size_minutes': self.config.window_size_minutes,
                'feature_timestamp': timestamp,
                'computation_timestamp': int(time.time() * 1000),
                'window_event_count': len(window_events)
            }
            
            FEATURES_COMPUTED.labels(feature_type='clickstream', entity_type='user').inc()
            WINDOW_SIZE.labels(window_type='clickstream', processor='simple').set(len(window_events))
            
            return features
            
        except Exception as e:
            logger.error("Error computing clickstream features", 
                        event=event, 
                        error=str(e))
            return None


def compute_clickstream_features_from_window(events: list, session_state: Dict[str, Any], config: ProcessorConfig) -> Dict[str, Any]:
    """
    Compute clickstream features from a list of events in a window.
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
                event = ClickEvent(**event_dict)
                parsed_events.append(event.dict())
        except Exception as e:
            logger.warning("Failed to parse event in window", event=event_dict, error=str(e))
            continue
    
    if not parsed_events:
        return None
    
    # Get first event for basic info
    first_event = parsed_events[0]
    user_id = first_event['user_id']
    session_id = first_event['session_id']
    
    # Engagement features
    dwell_times = [e.get('dwell_time_ms', 0) for e in parsed_events if e.get('dwell_time_ms')]
    avg_dwell_time = sum(dwell_times) / len(dwell_times) / 1000 if dwell_times else 0  # seconds
    
    scroll_depths = [e.get('scroll_depth', 0) for e in parsed_events if e.get('scroll_depth')]
    avg_scroll_depth = sum(scroll_depths) / len(scroll_depths) if scroll_depths else 0
    
    # Activity features
    page_views = len(parsed_events)
    unique_pages = len(set(e['page_type'] for e in parsed_events))
    click_events = sum(1 for e in parsed_events if e['action_type'] == 'CLICK')
    click_rate = click_events / page_views if page_views else 0
    
    # Category analysis
    categories = set(e.get('category_id') for e in parsed_events if e.get('category_id'))
    unique_categories = len(categories)
    
    # Cart actions analysis
    cart_adds = sum(1 for e in parsed_events if e['action_type'] == 'ADD_TO_CART')
    cart_removes = sum(1 for e in parsed_events if e['action_type'] == 'REMOVE_FROM_CART')
    purchases = sum(1 for e in parsed_events if e['action_type'] == 'PURCHASE')
    
    conversion_rate = purchases / max(cart_adds, 1)
    cart_abandonment_rate = cart_removes / max(cart_adds, 1)
    
    # Session duration
    timestamps = [e['timestamp'] for e in parsed_events]
    session_duration_min = (max(timestamps) - min(timestamps)) / (1000 * 60) if len(timestamps) > 1 else 0
    
    # Engagement score
    engagement_score = 0.0
    engagement_score += min(avg_dwell_time / 30.0, 1.0) * 0.3  # 30s baseline
    engagement_score += avg_scroll_depth * 0.2
    engagement_score += min(page_views / 10.0, 1.0) * 0.3  # 10 pages baseline
    engagement_score += conversion_rate * 0.2
    
    return {
        'user_id': user_id,
        'session_id': session_id,
        'session_duration_min': session_duration_min,
        'pages_per_session': page_views,
        'unique_categories_session': unique_categories,
        'avg_dwell_time_sec': avg_dwell_time,
        'avg_scroll_depth': avg_scroll_depth,
        'page_views_5m': page_views,
        'unique_pages_5m': unique_pages,
        'click_rate_5m': click_rate,
        'cart_adds_session': cart_adds,
        'cart_removes_session': cart_removes,
        'purchases_session': purchases,
        'conversion_rate_session': conversion_rate,
        'cart_abandonment_rate': cart_abandonment_rate,
        'engagement_score': engagement_score,
        'is_high_engagement': engagement_score > 0.7,
        'is_likely_purchaser': conversion_rate > 0.1
    }
