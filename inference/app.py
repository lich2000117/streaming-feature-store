#!/usr/bin/env python3
"""
FastAPI Inference Service for Streaming Feature Store

Production-grade real-time ML inference service providing:
- Sub-150ms fraud detection scoring
- Personalization recommendations
- Comprehensive monitoring and observability
- Feature store integration
- Model versioning and A/B testing
"""

import time
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

import structlog
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from config import InferenceConfig
from schemas import (
    FraudScoreRequest, FraudScoreResponse,
    PersonalizationScoreRequest, PersonalizationScoreResponse,
    BatchScoreRequest, BatchScoreResponse,
    HealthResponse, ReadinessResponse, ErrorResponse, ErrorDetail,
    HealthStatus, ModelType
)
from features import FeatureStoreClient, FeatureMetadata
from models import ModelManager, interpret_fraud_prediction, interpret_personalization_prediction

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global state
config: Optional[InferenceConfig] = None
feature_client: Optional[FeatureStoreClient] = None
model_manager: Optional[ModelManager] = None
service_start_time = time.time()

# Prometheus metrics
REQUEST_COUNT = Counter(
    'inference_requests_total',
    'Total inference requests',
    ['method', 'endpoint', 'status']
)
REQUEST_DURATION = Histogram(
    'inference_request_duration_seconds',
    'Request duration in seconds',
    ['endpoint']
)
FEATURE_FETCH_DURATION = Histogram(
    'feature_fetch_duration_seconds',
    'Feature fetch duration from Redis'
)
MODEL_INFERENCE_DURATION = Histogram(
    'model_inference_duration_seconds',
    'Model inference duration'
)
ACTIVE_REQUESTS = Gauge(
    'inference_active_requests',
    'Number of active requests'
)
PREDICTION_SCORES = Histogram(
    'prediction_scores',
    'Distribution of prediction scores',
    ['model_type']
)
ERROR_COUNT = Counter(
    'inference_errors_total',
    'Total errors',
    ['error_type', 'endpoint']
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global config, feature_client, model_manager
    
    # Startup
    logger.info("Starting Streaming Feature Store Inference Service")
    
    try:
        # Load configuration
        config = InferenceConfig.from_env()
        logger.info("Configuration loaded", environment=config.environment)
        
        # Validate model paths
        if not config.validate_paths():
            raise ValueError("Required model files not found")
        
        # Initialize feature store client
        feature_client = FeatureStoreClient(config)
        logger.info("Feature store client initialized")
        
        # Initialize model manager
        model_manager = ModelManager(config)
        logger.info("Model manager initialized")
        
        # Test components
        if not feature_client.health_check():
            logger.warning("Feature store health check failed")
        
        model_info = model_manager.get_model_info()
        logger.info("Service startup completed", model_info=model_info)
        
    except Exception as e:
        logger.error("Service startup failed", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down inference service")
    
    if feature_client:
        feature_client.close()
    
    logger.info("Service shutdown completed")


# Initialize FastAPI app
app = FastAPI(
    title="Streaming Feature Store - Inference API",
    description="Real-time fraud detection and personalization scoring with sub-150ms latency",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Request middleware for logging, timing, and metrics."""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # Add request ID to context
    request.state.request_id = request_id
    
    # Increment active requests
    ACTIVE_REQUESTS.inc()
    
    # Log request start
    logger.info(
        "Request started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host
    )
    
    try:
        response = await call_next(request)
        status_code = response.status_code
        
    except Exception as e:
        logger.error(
            "Request failed with exception",
            request_id=request_id,
            error=str(e)
        )
        status_code = 500
        raise
    
    finally:
        # Decrement active requests
        ACTIVE_REQUESTS.dec()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Record metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=status_code
        ).inc()
        
        REQUEST_DURATION.labels(endpoint=request.url.path).observe(duration)
        
        # Log request completion
        logger.info(
            "Request completed",
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration * 1000
        )
        
        # Add timing header
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(duration)
    
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    ERROR_COUNT.labels(error_type="validation", endpoint=request.url.path).inc()
    
    logger.warning(
        "Request validation failed",
        request_id=request_id,
        errors=exc.errors()
    )
    
    error_detail = ErrorDetail(
        error_code="VALIDATION_ERROR",
        error_message=f"Request validation failed: {exc.errors()}",
        error_type="validation",
        timestamp=datetime.now(),
        request_id=request_id
    )
    
    return ErrorResponse(error=error_detail)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    ERROR_COUNT.labels(error_type="http", endpoint=request.url.path).inc()
    
    error_detail = ErrorDetail(
        error_code=f"HTTP_{exc.status_code}",
        error_message=exc.detail,
        error_type="http",
        timestamp=datetime.now(),
        request_id=request_id
    )
    
    return ErrorResponse(error=error_detail)


def get_request_id(request: Request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, 'request_id', 'unknown')


# === Health and Monitoring Endpoints ===

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check endpoint."""
    try:
        # Check Redis connection
        redis_healthy = feature_client.health_check() if feature_client else False
        
        # Check model status
        model_healthy = model_manager is not None
        if model_manager:
            try:
                model_info = model_manager.get_model_info()
                model_healthy = True
            except Exception:
                model_healthy = False
        
        # Calculate uptime
        uptime_seconds = time.time() - service_start_time
        
        # Get cache stats
        cache_stats = feature_client.get_cache_stats() if feature_client else {}
        
        # Determine overall health
        if redis_healthy and model_healthy:
            status = HealthStatus.HEALTHY
        elif model_healthy:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        
        components = {
            "redis": {
                "status": "healthy" if redis_healthy else "unhealthy",
                "cache_hit_rate": cache_stats.get("hit_rate", 0.0)
            },
            "model": {
                "status": "healthy" if model_healthy else "unhealthy",
                "loaded_models": model_manager.list_models() if model_manager else []
            }
        }
        
        return HealthResponse(
            status=status,
            timestamp=datetime.now(),
            version=config.api.version if config else "unknown",
            components=components,
            uptime_seconds=uptime_seconds,
            request_count=0,  # Would come from metrics in production
            error_rate=0.0,   # Would come from metrics in production
            avg_latency_ms=0.0  # Would come from metrics in production
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    """Readiness check for load balancer."""
    model_loaded = model_manager is not None
    redis_connected = feature_client.health_check() if feature_client else False
    dependencies_ready = model_loaded and redis_connected
    
    return ReadinessResponse(
        ready=dependencies_ready,
        timestamp=datetime.now(),
        model_loaded=model_loaded,
        redis_connected=redis_connected,
        dependencies_ready=dependencies_ready
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# === Fraud Detection Endpoint ===

@app.post("/score/fraud", response_model=FraudScoreResponse)
async def score_fraud(request: FraudScoreRequest, request_id: str = Depends(get_request_id)):
    """
    Real-time fraud detection endpoint.
    
    Target: p95 latency < 150ms
    """
    start_time = time.time()
    
    try:
        # Fetch features from Redis
        feature_start = time.time()
        features, feature_metadata = feature_client.get_card_features(request.card_id)
        FEATURE_FETCH_DURATION.observe(time.time() - feature_start)
        
        # Add transaction context to features
        if request.transaction_amount is not None:
            features["transaction_amount"] = request.transaction_amount
        if request.mcc_code:
            features["mcc_code"] = request.mcc_code
        
        # Model inference
        inference_start = time.time()
        prediction_score, model_metadata = model_manager.predict(features)
        MODEL_INFERENCE_DURATION.observe(time.time() - inference_start)
        
        # Record prediction score distribution
        PREDICTION_SCORES.labels(model_type="fraud").observe(prediction_score)
        
        # Interpret prediction
        interpretation = interpret_fraud_prediction(prediction_score, features, model_metadata)
        
        # Calculate total latency
        latency_ms = (time.time() - start_time) * 1000
        
        # Log successful prediction
        logger.info(
            "Fraud score computed",
            request_id=request_id,
            card_id=request.card_id,
            score=prediction_score,
            risk_level=interpretation["risk_level"],
            latency_ms=latency_ms,
            features_count=feature_metadata.feature_count,
            cache_hit=feature_metadata.cache_hit
        )
        
        return FraudScoreResponse(
            request_id=request_id,
            timestamp=datetime.now(),
            model_version=model_metadata["model_version"],
            latency_ms=latency_ms,
            fraud_score=prediction_score,
            risk_level=interpretation["risk_level"],
            confidence=interpretation["confidence"],
            features_used=feature_metadata.feature_count,
            top_risk_factors=interpretation["top_risk_factors"],
            feature_importance=model_metadata.get("feature_importance"),
            recommended_action=interpretation["recommended_action"],
            explanation=interpretation["explanation"],
            feature_freshness_sec=feature_metadata.freshness_seconds
        )
        
    except Exception as e:
        ERROR_COUNT.labels(error_type="prediction", endpoint="/score/fraud").inc()
        logger.error(
            "Fraud scoring failed",
            request_id=request_id,
            card_id=request.card_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Fraud scoring failed")


# === Personalization Endpoint ===

@app.post("/score/personalization", response_model=PersonalizationScoreResponse)
async def score_personalization(request: PersonalizationScoreRequest, request_id: str = Depends(get_request_id)):
    """
    Real-time personalization scoring endpoint.
    
    Target: p95 latency < 150ms
    """
    start_time = time.time()
    
    try:
        # Fetch features from Redis
        feature_start = time.time()
        features, feature_metadata = feature_client.get_user_features(request.user_id)
        FEATURE_FETCH_DURATION.observe(time.time() - feature_start)
        
        # Add context features
        if request.item_category:
            features["item_category"] = request.item_category
        if request.item_price is not None:
            features["item_price"] = request.item_price
        
        # Model inference (using same model for now, but could be different)
        inference_start = time.time()
        prediction_score, model_metadata = model_manager.predict(features)
        MODEL_INFERENCE_DURATION.observe(time.time() - inference_start)
        
        # Record prediction score
        PREDICTION_SCORES.labels(model_type="personalization").observe(prediction_score)
        
        # Interpret prediction
        interpretation = interpret_personalization_prediction(prediction_score, features, model_metadata)
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "Personalization score computed",
            request_id=request_id,
            user_id=request.user_id,
            score=prediction_score,
            user_segment=interpretation["user_segment"],
            latency_ms=latency_ms,
            features_count=feature_metadata.feature_count
        )
        
        return PersonalizationScoreResponse(
            request_id=request_id,
            timestamp=datetime.now(),
            model_version=model_metadata["model_version"],
            latency_ms=latency_ms,
            relevance_score=prediction_score,
            conversion_probability=prediction_score * 0.8,  # Derived score
            engagement_score=features.get("engagement_score", 0.5),
            features_used=feature_metadata.feature_count,
            user_segment=interpretation["user_segment"],
            behavioral_signals=interpretation["behavioral_signals"],
            feature_freshness_sec=feature_metadata.freshness_seconds
        )
        
    except Exception as e:
        ERROR_COUNT.labels(error_type="prediction", endpoint="/score/personalization").inc()
        logger.error(
            "Personalization scoring failed",
            request_id=request_id,
            user_id=request.user_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Personalization scoring failed")


# === Batch Scoring Endpoint ===

@app.post("/score/batch", response_model=BatchScoreResponse)
async def score_batch(request: BatchScoreRequest, request_id: str = Depends(get_request_id)):
    """Batch scoring endpoint for multiple requests."""
    start_time = time.time()
    
    if len(request.requests) > 1000:
        raise HTTPException(status_code=400, detail="Batch size too large (max 1000)")
    
    try:
        responses = []
        errors = []
        
        for i, req in enumerate(request.requests):
            try:
                if request.model_type == ModelType.FRAUD_DETECTION:
                    # Process fraud request
                    features, _ = feature_client.get_card_features(req.card_id)
                    prediction_score, metadata = model_manager.predict(features)
                    interpretation = interpret_fraud_prediction(prediction_score, features, metadata)
                    
                    response = FraudScoreResponse(
                        request_id=f"{request_id}-{i}",
                        timestamp=datetime.now(),
                        model_version=metadata["model_version"],
                        latency_ms=metadata["inference_time_ms"],
                        fraud_score=prediction_score,
                        risk_level=interpretation["risk_level"],
                        confidence=interpretation["confidence"],
                        features_used=len(features),
                        top_risk_factors=interpretation["top_risk_factors"],
                        recommended_action=interpretation["recommended_action"],
                        explanation=interpretation["explanation"]
                    )
                    
                elif request.model_type == ModelType.PERSONALIZATION:
                    # Process personalization request
                    features, _ = feature_client.get_user_features(req.user_id)
                    prediction_score, metadata = model_manager.predict(features)
                    interpretation = interpret_personalization_prediction(prediction_score, features, metadata)
                    
                    response = PersonalizationScoreResponse(
                        request_id=f"{request_id}-{i}",
                        timestamp=datetime.now(),
                        model_version=metadata["model_version"],
                        latency_ms=metadata["inference_time_ms"],
                        relevance_score=prediction_score,
                        conversion_probability=prediction_score * 0.8,
                        engagement_score=features.get("engagement_score", 0.5),
                        features_used=len(features),
                        user_segment=interpretation["user_segment"],
                        behavioral_signals=interpretation["behavioral_signals"]
                    )
                
                responses.append(response)
                
            except Exception as e:
                error_detail = {
                    "request_index": i,
                    "error": str(e)
                }
                errors.append(error_detail)
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        return BatchScoreResponse(
            batch_id=request.batch_id,
            model_type=request.model_type,
            total_requests=len(request.requests),
            successful_responses=len(responses),
            failed_responses=len(errors),
            responses=responses,
            errors=errors if errors else None,
            processing_time_ms=processing_time_ms,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error("Batch scoring failed", request_id=request_id, error=str(e))
        raise HTTPException(status_code=500, detail="Batch scoring failed")


# === Utility Endpoints ===

@app.get("/models")
async def list_models():
    """List available models."""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")
    
    models = {}
    for model_name in model_manager.list_models():
        model_info = model_manager.get_model_info(model_name)
        models[model_name] = model_info
    
    return {"models": models}


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Streaming Feature Store - Inference API",
        "version": config.api.version if config else "unknown",
        "status": "healthy",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "metrics": "/metrics",
            "docs": "/docs",
            "fraud_scoring": "/score/fraud",
            "personalization": "/score/personalization",
            "batch_scoring": "/score/batch"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)