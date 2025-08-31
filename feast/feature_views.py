#!/usr/bin/env python3
"""
Feature view definitions for the streaming feature store.

Feature views define the schema and metadata for features computed
by the streaming pipeline and served for online inference.
"""

from datetime import timedelta
from feast import FeatureView, Field, FileSource
from feast.types import Float32, Float64, Int32, Int64, String, Bool, Array
from entities import card_entity, user_entity, device_entity, session_entity


# Data Sources
# These connect to our feature storage (Redis for online, files for offline)

# Note: Redis is now configured in feature_store.yaml as the online store
# We no longer need to define a RedisSource separately

# File source for offline features (for training)
offline_source = FileSource(
    name="streaming_features_offline", 
    path="data/offline_features/",
    timestamp_field="feature_timestamp",
    created_timestamp_column="computation_timestamp"
)


# Transaction Feature Views (Fraud Detection)

transaction_stats_5m = FeatureView(
    name="transaction_stats_5m",
    description="5-minute transaction statistics for fraud detection",
    entities=[card_entity],
    ttl=timedelta(hours=24),
    schema=[
        # Count features
        Field(name="txn_count_5m", dtype=Int32, description="Transaction count in last 5 minutes"),
        Field(name="txn_count_30m", dtype=Int32, description="Transaction count in last 30 minutes"),  
        Field(name="txn_count_24h", dtype=Int32, description="Transaction count in last 24 hours"),
        
        # Amount features
        Field(name="amount_sum_5m", dtype=Float64, description="Sum of transaction amounts in last 5 minutes"),
        Field(name="amount_avg_5m", dtype=Float64, description="Average transaction amount in last 5 minutes"),
        Field(name="amount_max_5m", dtype=Float64, description="Maximum transaction amount in last 5 minutes"),
        Field(name="amount_min_5m", dtype=Float64, description="Minimum transaction amount in last 5 minutes"),
        Field(name="amount_std_5m", dtype=Float64, description="Standard deviation of amounts in last 5 minutes"),
        
        # Geographic features
        Field(name="unique_countries_5m", dtype=Int32, description="Number of unique countries in last 5 minutes"),
        Field(name="unique_cities_5m", dtype=Int32, description="Number of unique cities in last 5 minutes"),
        Field(name="geo_diversity_score", dtype=Float32, description="Geographic diversity score (0-1)"),
        Field(name="geo_mismatch_rate_5m", dtype=Float32, description="Rate of geographic mismatches"),
        
        # Temporal features
        Field(name="time_since_last_txn_min", dtype=Float64, description="Minutes since last transaction"),
        Field(name="avg_time_between_txns_min", dtype=Float64, description="Average time between transactions"),
        Field(name="is_weekend", dtype=Bool, description="Whether transaction occurred on weekend"),
        Field(name="hour_of_day", dtype=Int32, description="Hour of day for transaction (0-23)"),
        
        # Risk features
        Field(name="velocity_score", dtype=Float32, description="Transaction velocity score (0-1)"),
        Field(name="high_risk_txn_ratio", dtype=Float32, description="Ratio of high-risk transactions"),
        Field(name="is_high_velocity", dtype=Bool, description="Whether card shows high velocity"),
        Field(name="is_geo_diverse", dtype=Bool, description="Whether card shows geographic diversity"),
        Field(name="has_high_risk_mcc", dtype=Bool, description="Whether transaction has high-risk MCC"),
        Field(name="device_location_mismatch", dtype=Bool, description="Device and transaction location mismatch"),
        
        # Metadata
        Field(name="window_size_minutes", dtype=Int32, description="Feature computation window size"),
        Field(name="window_event_count", dtype=Int32, description="Number of events in feature window"),
    ],
    source=offline_source,
    tags={
        "team": "fraud_detection",
        "use_case": "real_time_scoring", 
        "criticality": "high",
        "feature_type": "transaction_aggregates"
    }
)

# Device risk features
device_risk_features = FeatureView(
    name="device_risk_features",
    description="Device-based risk features for fraud detection",
    entities=[device_entity],
    ttl=timedelta(days=7),
    schema=[
        Field(name="device_first_seen_days", dtype=Int32, description="Days since device first seen"),
        Field(name="device_txn_count_24h", dtype=Int32, description="Transactions from device in 24h"),
        Field(name="device_unique_cards_24h", dtype=Int32, description="Unique cards used by device in 24h"),
        Field(name="device_unique_users_24h", dtype=Int32, description="Unique users on device in 24h"),
        Field(name="device_country_diversity", dtype=Int32, description="Countries device seen in"),
        Field(name="is_new_device", dtype=Bool, description="Whether device is newly seen"),
        Field(name="is_suspicious_device", dtype=Bool, description="Whether device shows suspicious patterns"),
        Field(name="device_risk_score", dtype=Float32, description="Overall device risk score"),
    ],
    source=offline_source,
    tags={
        "team": "fraud_detection",
        "use_case": "device_intelligence",
        "criticality": "medium"
    }
)

# Clickstream Feature Views (Personalization)

user_engagement_5m = FeatureView(
    name="user_engagement_5m", 
    description="5-minute user engagement features for personalization",
    entities=[user_entity],
    ttl=timedelta(hours=12),
    schema=[
        # Session features
        Field(name="session_duration_min", dtype=Float64, description="Current session duration in minutes"),
        Field(name="pages_per_session", dtype=Int32, description="Pages viewed in current session"),
        Field(name="unique_categories_session", dtype=Int32, description="Unique categories browsed in session"),
        
        # Engagement features
        Field(name="avg_dwell_time_sec", dtype=Float64, description="Average page dwell time in seconds"),
        Field(name="avg_scroll_depth", dtype=Float32, description="Average scroll depth (0-1)"),
        Field(name="page_views_5m", dtype=Int32, description="Page views in last 5 minutes"), 
        Field(name="unique_pages_5m", dtype=Int32, description="Unique pages in last 5 minutes"),
        Field(name="click_rate_5m", dtype=Float32, description="Click rate in last 5 minutes"),
        
        # Purchase funnel features
        Field(name="cart_adds_session", dtype=Int32, description="Cart additions in current session"),
        Field(name="cart_removes_session", dtype=Int32, description="Cart removals in current session"),
        Field(name="purchases_session", dtype=Int32, description="Purchases in current session"),
        Field(name="conversion_rate_session", dtype=Float32, description="Session conversion rate"),
        Field(name="cart_abandonment_rate", dtype=Float32, description="Cart abandonment rate"),
        
        # Behavioral scores
        Field(name="engagement_score", dtype=Float32, description="Overall engagement score (0-1)"),
        Field(name="is_high_engagement", dtype=Bool, description="Whether user shows high engagement"),
        Field(name="is_likely_purchaser", dtype=Bool, description="Whether user likely to purchase"),
        
        # Metadata
        Field(name="window_event_count", dtype=Int32, description="Events in computation window"),
    ],
    source=offline_source,
    tags={
        "team": "personalization",
        "use_case": "real_time_recommendations",
        "criticality": "high",
        "feature_type": "behavioral_aggregates"
    }
)

user_purchase_history = FeatureView(
    name="user_purchase_history",
    description="User purchase history and preferences",
    entities=[user_entity],
    ttl=timedelta(days=30),
    schema=[
        Field(name="total_purchases_30d", dtype=Int32, description="Total purchases in last 30 days"),
        Field(name="total_spent_30d", dtype=Float64, description="Total amount spent in last 30 days"),
        Field(name="avg_order_value", dtype=Float64, description="Average order value"),
        Field(name="favorite_category", dtype=String, description="Most purchased category"),
        Field(name="purchase_frequency_score", dtype=Float32, description="Purchase frequency score"),
        Field(name="price_sensitivity_score", dtype=Float32, description="Price sensitivity score"),
        Field(name="brand_loyalty_score", dtype=Float32, description="Brand loyalty score"),
        Field(name="seasonal_shopper_score", dtype=Float32, description="Seasonal shopping patterns"),
    ],
    source=offline_source,
    tags={
        "team": "personalization",
        "use_case": "recommendation_ranking",
        "criticality": "medium"
    }
)

# Cross-entity features (advanced)
user_device_features = FeatureView(
    name="user_device_features",
    description="Cross-entity features linking users and devices",
    entities=[user_entity, device_entity],
    ttl=timedelta(days=7),
    schema=[
        Field(name="devices_per_user_7d", dtype=Int32, description="Devices used by user in 7 days"),
        Field(name="users_per_device_7d", dtype=Int32, description="Users on device in 7 days"),
        Field(name="is_primary_device", dtype=Bool, description="Whether this is user's primary device"),
        Field(name="device_usage_score", dtype=Float32, description="How much user uses this device"),
        Field(name="cross_contamination_risk", dtype=Float32, description="Risk of account sharing"),
    ],
    source=offline_source,
    tags={
        "team": "security",
        "use_case": "account_security",
        "criticality": "low"
    }
)

# Export all feature views
ALL_FEATURE_VIEWS = [
    transaction_stats_5m,
    device_risk_features,
    user_engagement_5m,
    user_purchase_history,
    user_device_features
]

# Feature service definitions (for serving specific sets of features)
from feast import FeatureService

# Fraud detection service
fraud_detection_service = FeatureService(
    name="fraud_detection_v1",
    description="Real-time fraud detection feature service",
    features=[
        transaction_stats_5m,
        device_risk_features,
    ],
    tags={
        "team": "fraud_detection",
        "version": "v1.0",
        "sla": "p95_latency_50ms"
    }
)

# Personalization service  
personalization_service = FeatureService(
    name="personalization_v1",
    description="Real-time personalization feature service", 
    features=[
        user_engagement_5m,
        user_purchase_history,
        user_device_features,
    ],
    tags={
        "team": "personalization",
        "version": "v1.0", 
        "sla": "p95_latency_100ms"
    }
)

ALL_FEATURE_SERVICES = [
    fraud_detection_service,
    personalization_service
]
