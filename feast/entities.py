#!/usr/bin/env python3
"""
Entity definitions for the streaming feature store.

Entities define the primary keys for feature views and enable
proper feature joining and serving.
"""

from datetime import timedelta
from feast import Entity, ValueType


# Card Entity - Primary key for transaction features
card_entity = Entity(
    name="card",
    description="Payment card entity for fraud detection features",
    value_type=ValueType.STRING,
    join_keys=["card_id"],
    tags={
        "owner": "fraud_team",
        "domain": "payments",
        "criticality": "high"
    }
)

# User Entity - Primary key for personalization features  
user_entity = Entity(
    name="user",
    description="User entity for personalization and behavioral features",
    value_type=ValueType.STRING,
    join_keys=["user_id"],
    tags={
        "owner": "personalization_team", 
        "domain": "user_behavior",
        "criticality": "high"
    }
)

# Device Entity - Primary key for device-based features
device_entity = Entity(
    name="device",
    description="Device entity for device fingerprinting and risk features",
    value_type=ValueType.STRING,
    join_keys=["device_id"],
    tags={
        "owner": "security_team",
        "domain": "device_intelligence", 
        "criticality": "medium"
    }
)

# Session Entity - For session-based features
session_entity = Entity(
    name="session",
    description="User session entity for session-based behavioral features",
    value_type=ValueType.STRING,
    join_keys=["session_id"],
    tags={
        "owner": "analytics_team",
        "domain": "user_sessions",
        "criticality": "low"
    }
)

# Export all entities
ALL_ENTITIES = [
    card_entity,
    user_entity, 
    device_entity,
    session_entity
]
