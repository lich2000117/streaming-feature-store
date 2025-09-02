#!/usr/bin/env python3
"""
Request and Response Schemas for Inference API

Pydantic models for type-safe API contracts with comprehensive validation
and documentation for both fraud detection and personalization endpoints.
"""

from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, validator, ConfigDict


class ModelType(str, Enum):
    """Supported model types."""
    FRAUD_DETECTION = "fraud_detection"
    PERSONALIZATION = "personalization"


class ScoringMode(str, Enum):
    """Scoring mode options."""
    REAL_TIME = "real_time"
    BATCH = "batch"


# === Base Models ===

class BaseRequest(BaseModel):
    """Base request model with common fields."""
    
    request_id: Optional[str] = Field(
        default=None,
        description="Unique request identifier for tracing"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Request timestamp (auto-generated if not provided)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional request metadata"
    )
    
    model_config = ConfigDict(extra="allow")


class BaseResponse(BaseModel):
    """Base response model with common fields."""
    
    request_id: Optional[str] = Field(description="Request identifier")
    timestamp: datetime = Field(description="Response timestamp")
    model_version: str = Field(description="Model version used")
    latency_ms: float = Field(description="Request latency in milliseconds")
    
    model_config = ConfigDict(extra="forbid")


# === Fraud Detection Models ===

class FraudScoreRequest(BaseRequest):
    """Fraud detection scoring request."""
    
    card_id: str = Field(
        ...,
        description="Credit card identifier",
        min_length=1,
        max_length=50,
        pattern=r"^card_[a-zA-Z0-9_]+$"
    )
    
    # Transaction context (optional for enhanced scoring)
    transaction_amount: Optional[float] = Field(
        default=None,
        description="Transaction amount in USD",
        ge=0.0,
        le=100000.0
    )
    merchant_id: Optional[str] = Field(
        default=None,
        description="Merchant identifier",
        max_length=50
    )
    mcc_code: Optional[str] = Field(
        default=None,
        description="Merchant Category Code",
        pattern=r"^\d{4}$"
    )
    country_code: Optional[str] = Field(
        default=None,
        description="Transaction country code (ISO 3166-1 alpha-2)",
        pattern=r"^[A-Z]{2}$"
    )
    
    # Additional context
    user_agent: Optional[str] = Field(
        default=None,
        description="User agent string",
        max_length=500
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="Client IP address"
    )
    
    @validator('transaction_amount')
    def validate_amount(cls, v):
        if v is not None and v < 0:
            raise ValueError('Transaction amount must be non-negative')
        return v


class FraudScoreResponse(BaseResponse):
    """Fraud detection scoring response."""
    
    fraud_score: float = Field(
        description="Fraud probability score (0.0 = legitimate, 1.0 = fraudulent)",
        ge=0.0,
        le=1.0
    )
    risk_level: str = Field(
        description="Risk level classification",
        pattern=r"^(low|medium|high|critical)$"
    )
    confidence: float = Field(
        description="Model confidence score",
        ge=0.0,
        le=1.0
    )
    
    # Feature insights
    features_used: int = Field(description="Number of features used for scoring")
    top_risk_factors: List[str] = Field(
        description="Top contributing risk factors",
        max_items=5
    )
    feature_importance: Optional[Dict[str, float]] = Field(
        default=None,
        description="Feature importance scores for interpretability"
    )
    
    # Decision support
    recommended_action: str = Field(
        description="Recommended action",
        pattern=r"^(approve|review|decline|block)$"
    )
    explanation: str = Field(
        description="Human-readable explanation of the decision",
        max_length=500
    )
    
    # Monitoring metadata
    feature_freshness_sec: Optional[int] = Field(
        default=None,
        description="Age of features in seconds"
    )


# === Personalization Models ===

class PersonalizationScoreRequest(BaseRequest):
    """Personalization scoring request."""
    
    user_id: str = Field(
        ...,
        description="User identifier",
        min_length=1,
        max_length=50,
        pattern=r"^user_[a-zA-Z0-9_]+$"
    )
    
    # Content context
    item_id: Optional[str] = Field(
        default=None,
        description="Item/content identifier",
        max_length=50
    )
    item_category: Optional[str] = Field(
        default=None,
        description="Item category",
        max_length=50
    )
    item_price: Optional[float] = Field(
        default=None,
        description="Item price",
        ge=0.0
    )
    
    # User context
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier",
        max_length=100
    )
    page_url: Optional[str] = Field(
        default=None,
        description="Current page URL",
        max_length=500
    )
    referrer: Optional[str] = Field(
        default=None,
        description="Referrer URL",
        max_length=500
    )
    
    # Experimentation
    experiment_id: Optional[str] = Field(
        default=None,
        description="A/B test experiment identifier",
        max_length=50
    )
    treatment_group: Optional[str] = Field(
        default=None,
        description="A/B test treatment group",
        max_length=20
    )


class PersonalizationScoreResponse(BaseResponse):
    """Personalization scoring response."""
    
    relevance_score: float = Field(
        description="Item relevance score (0.0 = not relevant, 1.0 = highly relevant)",
        ge=0.0,
        le=1.0
    )
    conversion_probability: float = Field(
        description="Predicted conversion probability",
        ge=0.0,
        le=1.0
    )
    engagement_score: float = Field(
        description="Predicted engagement score",
        ge=0.0,
        le=1.0
    )
    
    # Recommendations
    recommended_items: Optional[List[str]] = Field(
        default=None,
        description="Recommended item IDs",
        max_items=10
    )
    recommended_categories: Optional[List[str]] = Field(
        default=None,
        description="Recommended categories",
        max_items=5
    )
    
    # Insights
    features_used: int = Field(description="Number of features used for scoring")
    user_segment: Optional[str] = Field(
        default=None,
        description="Predicted user segment",
        max_length=50
    )
    behavioral_signals: Optional[List[str]] = Field(
        default=None,
        description="Key behavioral signals driving the score",
        max_items=5
    )
    
    # Monitoring metadata
    feature_freshness_sec: Optional[int] = Field(
        default=None,
        description="Age of features in seconds"
    )


# === Batch Scoring Models ===

class BatchScoreRequest(BaseModel):
    """Batch scoring request for multiple entities."""
    
    model_type: ModelType = Field(description="Type of model to use")
    requests: List[Union[FraudScoreRequest, PersonalizationScoreRequest]] = Field(
        description="List of scoring requests",
        min_items=1,
        max_items=1000
    )
    batch_id: Optional[str] = Field(
        default=None,
        description="Batch identifier for tracking"
    )
    
    @validator('requests')
    def validate_request_types(cls, v, values):
        model_type = values.get('model_type')
        if model_type == ModelType.FRAUD_DETECTION:
            if not all(isinstance(req, FraudScoreRequest) for req in v):
                raise ValueError('All requests must be FraudScoreRequest for fraud detection')
        elif model_type == ModelType.PERSONALIZATION:
            if not all(isinstance(req, PersonalizationScoreRequest) for req in v):
                raise ValueError('All requests must be PersonalizationScoreRequest for personalization')
        return v


class BatchScoreResponse(BaseModel):
    """Batch scoring response."""
    
    batch_id: Optional[str] = Field(description="Batch identifier")
    model_type: ModelType = Field(description="Model type used")
    total_requests: int = Field(description="Total number of requests processed")
    successful_responses: int = Field(description="Number of successful responses")
    failed_responses: int = Field(description="Number of failed responses")
    
    responses: List[Union[FraudScoreResponse, PersonalizationScoreResponse]] = Field(
        description="Individual scoring responses"
    )
    errors: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Error details for failed requests"
    )
    
    processing_time_ms: float = Field(description="Total processing time in milliseconds")
    timestamp: datetime = Field(description="Batch completion timestamp")


# === Health and Monitoring Models ===

class HealthStatus(str, Enum):
    """Health status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: HealthStatus = Field(description="Overall health status")
    timestamp: datetime = Field(description="Health check timestamp")
    version: str = Field(description="Service version")
    
    # Component health
    components: Dict[str, Dict[str, Any]] = Field(
        description="Health status of individual components"
    )
    
    # Performance metrics
    uptime_seconds: float = Field(description="Service uptime in seconds")
    request_count: int = Field(description="Total requests processed")
    error_rate: float = Field(description="Current error rate")
    avg_latency_ms: float = Field(description="Average latency in milliseconds")


class ReadinessResponse(BaseModel):
    """Readiness check response."""
    
    ready: bool = Field(description="Whether service is ready to handle requests")
    timestamp: datetime = Field(description="Readiness check timestamp")
    
    # Readiness checks
    model_loaded: bool = Field(description="Whether ML model is loaded")
    redis_connected: bool = Field(description="Whether Redis is connected")
    dependencies_ready: bool = Field(description="Whether all dependencies are ready")


# === Error Models ===

class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    error_code: str = Field(description="Error code")
    error_message: str = Field(description="Human-readable error message")
    error_type: str = Field(description="Error type/category")
    timestamp: datetime = Field(description="Error timestamp")
    
    # Context
    request_id: Optional[str] = Field(default=None, description="Request ID where error occurred")
    component: Optional[str] = Field(default=None, description="Component that generated the error")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace (debug mode only)")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    success: bool = Field(default=False, description="Request success status")
    error: ErrorDetail = Field(description="Error details")
    
    model_config = ConfigDict(extra="forbid")
