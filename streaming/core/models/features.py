"""
Feature data models for machine learning.

These models define the structure of computed features that are stored
in Redis and consumed by ML models for inference.
"""

from typing import Optional
from pydantic import BaseModel


class TransactionFeatures(BaseModel):
    """Computed transaction features for fraud detection."""
    entity_id: str  # card_id
    entity_type: str = "card"
    feature_type: str = "transaction"
    
    # Count features
    txn_count_5m: int = 0
    txn_count_30m: int = 0
    txn_count_24h: int = 0
    
    # Amount features
    amount_sum_5m: float = 0.0
    amount_avg_5m: float = 0.0
    amount_max_5m: float = 0.0
    amount_min_5m: float = 0.0
    amount_std_5m: float = 0.0
    amount_sum_30m: float = 0.0
    amount_avg_30m: float = 0.0
    
    # Geographic features
    unique_countries_5m: int = 0
    unique_cities_5m: int = 0
    geo_diversity_score: float = 0.0
    
    # Temporal features
    time_since_last_txn_min: Optional[float] = None
    avg_time_between_txns_min: Optional[float] = None
    velocity_score: float = 0.0
    is_weekend: bool = False
    hour_of_day: int = 0
    
    # Risk indicators
    has_high_risk_mcc: bool = False
    high_risk_txn_ratio: float = 0.0
    is_high_velocity: bool = False
    is_geo_diverse: bool = False
    
    # Velocity features
    txn_velocity_per_min: float = 0.0
    amount_velocity_per_min: float = 0.0
    
    # Pattern features
    most_active_hour_5m: int = 0
    weekend_ratio_5m: float = 0.0
    
    # Metadata
    window_size_minutes: int = 5
    feature_timestamp: int
    computation_timestamp: int
    window_event_count: int = 0


class ClickstreamFeatures(BaseModel):
    """Computed clickstream features for personalization."""
    entity_id: str  # user_id
    entity_type: str = "user"
    feature_type: str = "clickstream"
    
    # Session features
    session_id: str = ""
    session_duration_min: float = 0.0
    pages_per_session: int = 0
    unique_categories_session: int = 0
    
    # Engagement features
    avg_dwell_time_sec: float = 0.0
    avg_scroll_depth: float = 0.0
    page_views_5m: int = 0
    unique_pages_5m: int = 0
    click_rate_5m: float = 0.0
    
    # Purchase funnel features
    cart_adds_session: int = 0
    cart_removes_session: int = 0
    purchases_session: int = 0
    conversion_rate_session: float = 0.0
    cart_abandonment_rate: float = 0.0
    
    # Derived features
    engagement_score: float = 0.0
    is_high_engagement: bool = False
    is_likely_purchaser: bool = False
    
    # Temporal features
    sessions_24h: int = 0
    total_page_views_24h: int = 0
    
    # Metadata
    window_size_minutes: int = 5
    feature_timestamp: int
    computation_timestamp: int
    window_event_count: int = 0
