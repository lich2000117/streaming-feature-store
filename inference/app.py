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
from typing import Dict, Any, Optional, List, Union

import structlog
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
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
from features import FeatureStoreClient, FeatureMetadata, FEATURE_CACHE_HITS, FEATURE_CACHE_MISSES, FEATURE_FRESHNESS
from models import ModelManager, interpret_fraud_prediction, interpret_personalization_prediction

# Configure structured logging
structlog.configure(
    processors=[
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
service_start_time = time.perf_counter()

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

# Note: Feature cache and freshness metrics are defined in features.py
# to avoid duplicate registration conflicts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global config, feature_client, model_manager

    logger.info("Starting Streaming Feature Store Inference Service")
    try:
        config = InferenceConfig.from_env()
        
        # Configure Python logging level for structlog filter_by_level
        log_level = getattr(config.logging, 'level', 'INFO').upper()
        logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))
        
        # Set specific loggers to DEBUG level
        logging.getLogger('inference.features').setLevel(getattr(logging, log_level, logging.INFO))
        logging.getLogger('inference.models').setLevel(getattr(logging, log_level, logging.INFO))
        
        logger.info("Configuration loaded", environment=getattr(config, "environment", "unknown"), log_level=log_level)

        if hasattr(config, "validate_paths") and not config.validate_paths():
            raise ValueError("Required model files not found")

        feature_client = FeatureStoreClient(config)
        logger.info("Feature store client initialized")

        model_manager = ModelManager(config)
        logger.info("Model manager initialized")

        # Optional sanity checks
        try:
            _ = feature_client.health_check()
        except Exception as e:
            logger.warning("Feature store health check failed", error=str(e))

        try:
            model_info = model_manager.get_model_info()
        except Exception as e:
            logger.warning("Model info retrieval failed", error=str(e))
            model_info = {}

        logger.info("Service startup completed", model_info=model_info)
    except Exception as e:
        logger.error("Service startup failed", error=str(e))
        raise

    try:
        yield
    finally:
        logger.info("Shutting down inference service")
        if feature_client:
            try:
                feature_client.close()
            except Exception as e:
                logger.warning("Feature client close failed", error=str(e))
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

# Add CORS middleware (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # In prod, set explicit origins
    allow_credentials=False,        # "*" + credentials is invalid; set False here
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> datetime:
    return datetime.now()


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Request middleware for logging, timing, and metrics."""
    start_time = time.perf_counter()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    ACTIVE_REQUESTS.inc()

    method = request.method
    path = request.url.path
    status_code: int = 500
    response: Optional[Response] = None

    logger.info("Request started", request_id=request_id, method=method, path=path, client_ip=getattr(request.client, "host", "unknown"))

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as e:
        ERROR_COUNT.labels(error_type="unhandled", endpoint=path).inc()
        logger.exception("Request failed with exception", request_id=request_id, error=str(e))
        # Re-raise so registered exception handlers can format the response.
        raise
    finally:
        ACTIVE_REQUESTS.dec()
        duration = time.perf_counter() - start_time

        # Prometheus expects label values as strings
        REQUEST_COUNT.labels(method=method, endpoint=path, status=str(status_code)).inc()
        REQUEST_DURATION.labels(endpoint=path).observe(duration)

        logger.info("Request completed", request_id=request_id, status_code=status_code, duration_ms=duration * 1000.0)

        # Only set headers if we actually have a response object
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration:.6f}"


# === Exception Handlers ===

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors (422)."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    ERROR_COUNT.labels(error_type="validation", endpoint=request.url.path).inc()

    logger.warning("Request validation failed", request_id=request_id, errors=exc.errors())

    error_detail = ErrorDetail(
        error_code="VALIDATION_ERROR",
        error_message=f"Request validation failed: {exc.errors()}",
        error_type="validation",
        timestamp=_now(),
        request_id=request_id
    )
    payload = ErrorResponse(error=error_detail)
    return JSONResponse(status_code=422, content=payload.model_dump(mode='json'))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions (uses given status)."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    ERROR_COUNT.labels(error_type="http", endpoint=request.url.path).inc()

    error_detail = ErrorDetail(
        error_code=f"HTTP_{exc.status_code}",
        error_message=str(exc.detail),
        error_type="http",
        timestamp=_now(),
        request_id=request_id
    )
    payload = ErrorResponse(error=error_detail)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode='json'))


def get_request_id(request: Request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, 'request_id', 'unknown')


# === Health and Monitoring Endpoints ===

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check endpoint."""
    try:
        redis_healthy = feature_client.health_check() if feature_client else False

        model_healthy = model_manager is not None
        if model_manager:
            try:
                _ = model_manager.get_model_info()
                model_healthy = True
            except Exception:
                model_healthy = False

        uptime_seconds = time.perf_counter() - service_start_time

        cache_stats: Dict[str, Any] = {}
        try:
            cache_stats = feature_client.get_cache_stats() if feature_client else {}
        except Exception:
            cache_stats = {}

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
            timestamp=_now(),
            version=getattr(getattr(config, "api", None), "version", "unknown"),
            components=components,
            uptime_seconds=uptime_seconds,
            request_count=0.0,
            error_rate=0.0,
            avg_latency_ms=0.0,
        )
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    """Readiness check for load balancer."""
    model_loaded = model_manager is not None
    try:
        redis_connected = feature_client.health_check() if feature_client else False
    except Exception:
        redis_connected = False

    dependencies_ready = model_loaded and redis_connected

    return ReadinessResponse(
        ready=dependencies_ready,
        timestamp=_now(),
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
    start_time = time.perf_counter()
    try:
        feature_start = time.perf_counter()
        features, feature_metadata = feature_client.get_card_features(request.card_id)
        FEATURE_FETCH_DURATION.observe(time.perf_counter() - feature_start)
        print("features", features)
        if request.transaction_amount is not None:
            features["transaction_amount"] = request.transaction_amount
        if request.mcc_code:
            features["mcc_code"] = request.mcc_code

        inference_start = time.perf_counter()
        prediction_score, model_metadata = model_manager.predict(features)
        MODEL_INFERENCE_DURATION.observe(time.perf_counter() - inference_start)

        PREDICTION_SCORES.labels(model_type="fraud").observe(prediction_score)

        interpretation = interpret_fraud_prediction(prediction_score, features, model_metadata)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Check for ground truth to validate prediction accuracy
        actual_fraud = features.get('actual_fraud')
        predicted_fraud = prediction_score > 0.5
        accuracy_info = {}
        if actual_fraud is not None:
            accuracy_info = {
                "actual_fraud": actual_fraud,
                "predicted_fraud": predicted_fraud,
                "correct_prediction": (actual_fraud == predicted_fraud)
            }

        logger.info(
            "Fraud score computed",
            request_id=request_id,
            card_id=request.card_id,
            score=prediction_score,
            risk_level=interpretation["risk_level"],
            latency_ms=latency_ms,
            features_count=getattr(feature_metadata, "feature_count", len(features)),
            cache_hit=getattr(feature_metadata, "cache_hit", False),
            **accuracy_info
        )

        return FraudScoreResponse(
            request_id=request_id,
            timestamp=_now(),
            model_version=model_metadata["model_version"],
            latency_ms=latency_ms,
            fraud_score=prediction_score,
            risk_level=interpretation["risk_level"],
            confidence=interpretation["confidence"],
            features_used=getattr(feature_metadata, "feature_count", len(features)),
            top_risk_factors=interpretation["top_risk_factors"],
            feature_importance=model_metadata.get("feature_importance"),
            recommended_action=interpretation["recommended_action"],
            explanation=interpretation["explanation"],
            feature_freshness_sec=getattr(feature_metadata, "freshness_seconds", None),
        )
    except Exception as e:
        ERROR_COUNT.labels(error_type="prediction", endpoint="/score/fraud").inc()
        logger.error("Fraud scoring failed", request_id=request_id, card_id=request.card_id, error=str(e))
        raise HTTPException(status_code=500, detail="Fraud scoring failed")


# === Personalization Endpoint ===

@app.post("/score/personalization", response_model=PersonalizationScoreResponse)
async def score_personalization(request: PersonalizationScoreRequest, request_id: str = Depends(get_request_id)):
    """
    Real-time personalization scoring endpoint.
    Target: p95 latency < 150ms
    """
    start_time = time.perf_counter()
    try:
        feature_start = time.perf_counter()
        features, feature_metadata = feature_client.get_user_features(request.user_id)
        FEATURE_FETCH_DURATION.observe(time.perf_counter() - feature_start)

        if request.item_category:
            features["item_category"] = request.item_category
        if request.item_price is not None:
            features["item_price"] = request.item_price

        inference_start = time.perf_counter()
        prediction_score, model_metadata = model_manager.predict(features)
        MODEL_INFERENCE_DURATION.observe(time.perf_counter() - inference_start)

        PREDICTION_SCORES.labels(model_type="personalization").observe(prediction_score)

        interpretation = interpret_personalization_prediction(prediction_score, features, model_metadata)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        logger.info(
            "Personalization score computed",
            request_id=request_id,
            user_id=request.user_id,
            score=prediction_score,
            user_segment=interpretation["user_segment"],
            latency_ms=latency_ms,
            features_count=getattr(feature_metadata, "feature_count", len(features)),
        )

        return PersonalizationScoreResponse(
            request_id=request_id,
            timestamp=_now(),
            model_version=model_metadata["model_version"],
            latency_ms=latency_ms,
            relevance_score=prediction_score,
            conversion_probability=prediction_score * 0.8,
            engagement_score=features.get("engagement_score", 0.5),
            features_used=getattr(feature_metadata, "feature_count", len(features)),
            user_segment=interpretation["user_segment"],
            behavioral_signals=interpretation["behavioral_signals"],
            feature_freshness_sec=getattr(feature_metadata, "freshness_seconds", None),
        )
    except Exception as e:
        ERROR_COUNT.labels(error_type="prediction", endpoint="/score/personalization").inc()
        logger.error("Personalization scoring failed", request_id=request_id, user_id=request.user_id, error=str(e))
        raise HTTPException(status_code=500, detail="Personalization scoring failed")


# === Batch Scoring Endpoint ===

@app.post("/score/batch", response_model=BatchScoreResponse)
async def score_batch(request: BatchScoreRequest, request_id: str = Depends(get_request_id)):
    """Batch scoring endpoint for multiple requests."""
    start_time = time.perf_counter()

    if len(request.requests) > 1000:
        raise HTTPException(status_code=400, detail="Batch size too large (max 1000)")

    responses: List[Union[FraudScoreResponse, PersonalizationScoreResponse]] = []
    errors: List[Dict[str, Any]] = []

    for i, req in enumerate(request.requests):
        try:
            if request.model_type == ModelType.FRAUD_DETECTION:
                features, feature_metadata = feature_client.get_card_features(req.card_id)
                s = time.perf_counter()
                score, meta = model_manager.predict(features)
                MODEL_INFERENCE_DURATION.observe(time.perf_counter() - s)
                PREDICTION_SCORES.labels(model_type="fraud").observe(score)
                interp = interpret_fraud_prediction(score, features, meta)

                responses.append(FraudScoreResponse(
                    request_id=f"{request_id}-{i}",
                    timestamp=_now(),
                    model_version=meta["model_version"],
                    latency_ms=meta.get("inference_time_ms", 0.0),
                    fraud_score=score,
                    risk_level=interp["risk_level"],
                    confidence=interp["confidence"],
                    features_used=getattr(feature_metadata, "feature_count", len(features)),
                    top_risk_factors=interp["top_risk_factors"],
                    recommended_action=interp["recommended_action"],
                    explanation=interp["explanation"],
                    feature_freshness_sec=getattr(feature_metadata, "freshness_seconds", None),
                ))

            elif request.model_type == ModelType.PERSONALIZATION:
                features, feature_metadata = feature_client.get_user_features(req.user_id)
                s = time.perf_counter()
                score, meta = model_manager.predict(features)
                MODEL_INFERENCE_DURATION.observe(time.perf_counter() - s)
                PREDICTION_SCORES.labels(model_type="personalization").observe(score)
                interp = interpret_personalization_prediction(score, features, meta)

                responses.append(PersonalizationScoreResponse(
                    request_id=f"{request_id}-{i}",
                    timestamp=_now(),
                    model_version=meta["model_version"],
                    latency_ms=meta.get("inference_time_ms", 0.0),
                    relevance_score=score,
                    conversion_probability=score * 0.8,
                    engagement_score=features.get("engagement_score", 0.5),
                    features_used=getattr(feature_metadata, "feature_count", len(features)),
                    user_segment=interp["user_segment"],
                    behavioral_signals=interp["behavioral_signals"],
                    feature_freshness_sec=getattr(feature_metadata, "freshness_seconds", None),
                ))
            else:
                raise ValueError(f"Unsupported model_type: {request.model_type}")

        except Exception as e:
            # Collect per-item error and continue
            ERROR_COUNT.labels(error_type="prediction", endpoint="/score/batch").inc()
            logger.error("Batch item failed", request_id=request_id, index=i, error=str(e))
            errors.append({"request_index": i, "error": str(e)})

    processing_time_ms = (time.perf_counter() - start_time) * 1000.0

    return BatchScoreResponse(
        batch_id=request.batch_id,
        model_type=request.model_type,
        total_requests=len(request.requests),
        successful_responses=len(responses),
        failed_responses=len(errors),
        responses=responses,
        errors=errors or None,
        processing_time_ms=processing_time_ms,
        timestamp=_now(),
    )


# === Utility Endpoints ===

@app.get("/models")
async def list_models():
    """List available models."""
    if not model_manager:
        raise HTTPException(status_code=503, detail="Model manager not initialized")

    models: Dict[str, Any] = {}
    for model_name in model_manager.list_models():
        models[model_name] = model_manager.get_model_info(model_name)

    return {"models": models}


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Streaming Feature Store - Inference API",
        "version": getattr(getattr(config, "api", None), "version", "unknown"),
        "status": "healthy",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "metrics": "/metrics",
            "docs": "/docs",
            "fraud_scoring": "/score/fraud",
            "personalization_scoring": "/score/personalization",
            "batch_scoring": "/score/batch"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
