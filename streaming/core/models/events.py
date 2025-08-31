"""
Event data models for streaming feature engineering.

These models define the structure of events consumed from Kafka topics.
Used by both PyFlink and simplified stream processors.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TransactionEvent(BaseModel):
    """Transaction event model for fraud detection features."""
    txn_id: str
    card_id: str
    user_id: str
    amount: float
    currency: str
    mcc: str
    device_id: str
    ip_address: str
    geo_country: Optional[str] = None
    geo_city: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    timestamp: int  # milliseconds
    metadata: Dict[str, str] = Field(default_factory=dict)


class ClickEvent(BaseModel):
    """Clickstream event model for personalization features."""
    event_id: str
    user_id: str
    session_id: str
    page_url: str
    page_type: str
    item_id: Optional[str] = None
    category_id: Optional[str] = None
    action_type: str
    device_id: str
    dwell_time_ms: Optional[int] = None
    scroll_depth: Optional[float] = None
    timestamp: int
    experiment_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)


class DeviceEvent(BaseModel):
    """Device event model for device fingerprinting."""
    device_id: str
    user_agent: str
    screen_resolution: str
    timezone: str
    language: str
    ip_address: str
    timestamp: int
    metadata: Dict[str, str] = Field(default_factory=dict)
