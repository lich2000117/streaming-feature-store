"""
FastAPI Inference Service for Streaming Feature Store

Provides real-time fraud detection and personalization scoring
with sub-150ms p95 latency target.
"""

import time
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
import structlog
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

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

# Metrics
REQUEST_COUNT = Counter('inference_requests_total', 'Total inference requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('inference_request_duration_seconds', 'Request duration')
FEATURE_FETCH_DURATION = Histogram('feature_fetch_duration_seconds', 'Feature fetch duration')

# Global Redis connection
redis_client: Optional[redis.Redis] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client
    
    # Startup
    logger.info("Starting inference service")
    
    # Initialize Redis connection
    redis_client = redis.Redis(
        host='redis',
        port=6379,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    
    # Test Redis connection
    try:
        redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error("Failed to connect to Redis", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down inference service")
    if redis_client:
        redis_client.close()

app = FastAPI(
    title="Streaming Feature Store - Inference API",
    description="Real-time fraud detection and personalization scoring",
    version="1.0.0",
    lifespan=lifespan
)

# Request/Response Models
class FraudScoreRequest(BaseModel):
    card_id: str = Field(..., description="Credit card ID")
    transaction_amount: Optional[float] = Field(None, description="Transaction amount")
    
class PersonalizationScoreRequest(BaseModel):
    user_id: str = Field(..., description="User ID")
    item_id: Optional[str] = Field(None, description="Item ID for scoring")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")

class ScoreResponse(BaseModel):
    score: float = Field(..., description="Prediction score")
    model_version: str = Field(..., description="Model version used")
    latency_ms: float = Field(..., description="Request latency in milliseconds")
    features_used: int = Field(..., description="Number of features used")

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add request timing and logging"""
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    REQUEST_DURATION.observe(process_time)
    
    return response

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Check Redis connectivity
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/score/fraud", response_model=ScoreResponse)
async def score_fraud(request: FraudScoreRequest):
    """
    Real-time fraud scoring endpoint
    
    Target: p95 latency < 150ms
    """
    start_time = time.time()
    
    try:
        # Fetch features from Redis
        feature_start = time.time()
        features = await fetch_card_features(request.card_id)
        FEATURE_FETCH_DURATION.observe(time.time() - feature_start)
        
        # Simple rule-based scoring for now (replace with ONNX model)
        score = calculate_fraud_score(features, request.transaction_amount)
        
        latency_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "Fraud score computed",
            card_id=request.card_id,
            score=score,
            latency_ms=latency_ms,
            features_count=len(features)
        )
        
        return ScoreResponse(
            score=score,
            model_version="rule-based-v1",
            latency_ms=latency_ms,
            features_used=len(features)
        )
        
    except Exception as e:
        logger.error("Fraud scoring failed", error=str(e), card_id=request.card_id)
        raise HTTPException(status_code=500, detail="Scoring failed")

@app.post("/score/personalization", response_model=ScoreResponse)
async def score_personalization(request: PersonalizationScoreRequest):
    """
    Real-time personalization scoring endpoint
    
    Target: p95 latency < 150ms
    """
    start_time = time.time()
    
    try:
        # Fetch features from Redis
        feature_start = time.time()
        features = await fetch_user_features(request.user_id)
        FEATURE_FETCH_DURATION.observe(time.time() - feature_start)
        
        # Simple rule-based scoring for now (replace with ONNX model)
        score = calculate_personalization_score(features, request.item_id)
        
        latency_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "Personalization score computed",
            user_id=request.user_id,
            item_id=request.item_id,
            score=score,
            latency_ms=latency_ms,
            features_count=len(features)
        )
        
        return ScoreResponse(
            score=score,
            model_version="rule-based-v1",
            latency_ms=latency_ms,
            features_used=len(features)
        )
        
    except Exception as e:
        logger.error("Personalization scoring failed", error=str(e), user_id=request.user_id)
        raise HTTPException(status_code=500, detail="Scoring failed")

async def fetch_card_features(card_id: str) -> Dict[str, Any]:
    """Fetch card features from Redis"""
    try:
        # Try to get precomputed features
        feature_key = f"features:card:{card_id}"
        features_raw = redis_client.get(feature_key)
        
        if features_raw:
            # In real implementation, deserialize from Avro/JSON
            features = {
                "txn_count_5m": 2,
                "txn_sum_5m": 150.0,
                "avg_amount": 75.0,
                "geo_mismatch": 0.0,
                "time_since_last": 300,
                "velocity_flag": False
            }
        else:
            # Fallback to default/computed features
            features = {
                "txn_count_5m": 0,
                "txn_sum_5m": 0.0,
                "avg_amount": 0.0,
                "geo_mismatch": 0.0,
                "time_since_last": 86400,
                "velocity_flag": False
            }
            
        return features
        
    except Exception as e:
        logger.error("Failed to fetch card features", error=str(e), card_id=card_id)
        raise

async def fetch_user_features(user_id: str) -> Dict[str, Any]:
    """Fetch user features from Redis"""
    try:
        # Try to get precomputed features
        feature_key = f"features:user:{user_id}"
        features_raw = redis_client.get(feature_key)
        
        if features_raw:
            features = {
                "click_count_1h": 15,
                "session_duration": 450,
                "pages_per_session": 3.2,
                "bounce_rate": 0.1,
                "conversion_rate": 0.05,
                "preferred_category": "electronics"
            }
        else:
            # Fallback features
            features = {
                "click_count_1h": 0,
                "session_duration": 0,
                "pages_per_session": 1.0,
                "bounce_rate": 1.0,
                "conversion_rate": 0.01,
                "preferred_category": "unknown"
            }
            
        return features
        
    except Exception as e:
        logger.error("Failed to fetch user features", error=str(e), user_id=user_id)
        raise

def calculate_fraud_score(features: Dict[str, Any], transaction_amount: Optional[float] = None) -> float:
    """
    Simple rule-based fraud scoring
    Replace with ONNX model inference in production
    """
    score = 0.0
    
    # High velocity indicator
    if features.get("txn_count_5m", 0) > 5:
        score += 0.3
        
    # Amount velocity
    if features.get("txn_sum_5m", 0) > 500:
        score += 0.2
        
    # Geo anomaly
    if features.get("geo_mismatch", 0) > 0.5:
        score += 0.4
        
    # Velocity flag
    if features.get("velocity_flag", False):
        score += 0.3
        
    # Large transaction
    if transaction_amount and transaction_amount > 1000:
        score += 0.2
        
    return min(score, 1.0)

def calculate_personalization_score(features: Dict[str, Any], item_id: Optional[str] = None) -> float:
    """
    Simple rule-based personalization scoring
    Replace with ONNX model inference in production
    """
    score = 0.5  # Base score
    
    # High engagement
    if features.get("click_count_1h", 0) > 10:
        score += 0.2
        
    # Long session duration
    if features.get("session_duration", 0) > 300:
        score += 0.1
        
    # Low bounce rate
    if features.get("bounce_rate", 1.0) < 0.3:
        score += 0.15
        
    # High conversion rate
    if features.get("conversion_rate", 0) > 0.03:
        score += 0.15
        
    return min(score, 1.0)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
