#!/usr/bin/env python3
"""
Real-Time Fraud Detection Service

Integrates with the inference API to automatically detect fraud
when new transactions are processed in the streaming pipeline.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import aiohttp
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger(__name__)

# Fraud detection metrics
FRAUD_DETECTIONS_TOTAL = Counter(
    'fraud_detections_total',
    'Total fraud detections',
    ['risk_level', 'action_taken']
)

FRAUD_DETECTION_LATENCY = Histogram(
    'fraud_detection_latency_seconds',
    'Time to get fraud score from API'
)

FRAUD_SCORE_DISTRIBUTION = Histogram(
    'fraud_score_distribution',
    'Distribution of fraud scores',
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

FRAUD_RATE_GAUGE = Gauge(
    'fraud_rate_current',
    'Current fraud detection rate (last 100 transactions)'
)

BLOCKED_TRANSACTIONS = Counter(
    'blocked_transactions_total',
    'Total transactions blocked due to fraud'
)

HIGH_RISK_TRANSACTIONS = Counter(
    'high_risk_transactions_total',
    'Total high-risk transactions requiring review'
)


@dataclass
class FraudResult:
    """Result of fraud detection."""
    card_id: str
    fraud_score: float
    risk_level: str
    confidence: float
    recommended_action: str
    top_risk_factors: List[str]
    explanation: str
    latency_ms: float
    features_used: int
    feature_freshness_sec: Optional[int] = None


class FraudDetectionService:
    """Service for real-time fraud detection using the inference API."""
    
    def __init__(self, inference_api_url: str = "http://inference-api:8080"):
        self.inference_api_url = inference_api_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.recent_results: List[bool] = []  # Track recent fraud detections for rate calculation
        self.max_recent_results = 100
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5.0),
            headers={'Content-Type': 'application/json'}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def detect_fraud(self, transaction: Dict[str, Any]) -> Optional[FraudResult]:
        """
        Detect fraud for a transaction using the inference API.
        
        Args:
            transaction: Transaction event dict
            
        Returns:
            FraudResult if successful, None if API call fails
        """
        if not self.session:
            logger.error("FraudDetectionService not properly initialized")
            return None
            
        start_time = time.perf_counter()
        
        try:
            # Prepare request payload
            request_payload = {
                "card_id": transaction.get("card_id"),
                "transaction_amount": transaction.get("amount"),
                "mcc_code": transaction.get("mcc"),
                "country_code": transaction.get("geo_country")
            }
            
            # Remove None values
            request_payload = {k: v for k, v in request_payload.items() if v is not None}
            
            # Call fraud detection API
            async with self.session.post(
                f"{self.inference_api_url}/score/fraud",
                json=request_payload
            ) as response:
                
                if response.status == 200:
                    result_data = await response.json()
                    
                    # Parse response
                    fraud_result = FraudResult(
                        card_id=request_payload["card_id"],
                        fraud_score=result_data["fraud_score"],
                        risk_level=result_data["risk_level"],
                        confidence=result_data["confidence"],
                        recommended_action=result_data["recommended_action"],
                        top_risk_factors=result_data.get("top_risk_factors", []),
                        explanation=result_data["explanation"],
                        latency_ms=result_data["latency_ms"],
                        features_used=result_data["features_used"],
                        feature_freshness_sec=result_data.get("feature_freshness_sec")
                    )
                    
                    # Record metrics
                    detection_latency = time.perf_counter() - start_time
                    FRAUD_DETECTION_LATENCY.observe(detection_latency)
                    
                    FRAUD_SCORE_DISTRIBUTION.observe(fraud_result.fraud_score)
                    
                    FRAUD_DETECTIONS_TOTAL.labels(
                        risk_level=fraud_result.risk_level,
                        action_taken=fraud_result.recommended_action
                    ).inc()
                    
                    # Track fraud rate
                    is_fraud = fraud_result.risk_level in ['high', 'critical']
                    self._update_fraud_rate(is_fraud)
                    
                    # Count blocked/high-risk transactions
                    if fraud_result.recommended_action == "block":
                        BLOCKED_TRANSACTIONS.inc()
                    elif fraud_result.risk_level in ['high', 'critical']:
                        HIGH_RISK_TRANSACTIONS.inc()
                    
                    logger.info(
                        "Fraud detection completed",
                        card_id=fraud_result.card_id,
                        fraud_score=fraud_result.fraud_score,
                        risk_level=fraud_result.risk_level,
                        action=fraud_result.recommended_action,
                        latency_ms=detection_latency * 1000,
                        api_latency_ms=fraud_result.latency_ms,
                        features_used=fraud_result.features_used
                    )
                    
                    return fraud_result
                    
                else:
                    logger.error(
                        "Fraud API returned error",
                        status=response.status,
                        response=await response.text()
                    )
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("Fraud detection API timeout", card_id=request_payload.get("card_id"))
            return None
        except Exception as e:
            logger.error(
                "Fraud detection failed",
                card_id=request_payload.get("card_id"),
                error=str(e)
            )
            return None
    
    def _update_fraud_rate(self, is_fraud: bool):
        """Update the rolling fraud rate calculation."""
        self.recent_results.append(is_fraud)
        
        # Keep only recent results
        if len(self.recent_results) > self.max_recent_results:
            self.recent_results = self.recent_results[-self.max_recent_results:]
        
        # Calculate current fraud rate
        if self.recent_results:
            fraud_rate = sum(self.recent_results) / len(self.recent_results)
            FRAUD_RATE_GAUGE.set(fraud_rate)
    
    async def health_check(self) -> bool:
        """Check if the fraud detection API is healthy."""
        if not self.session:
            return False
            
        try:
            async with self.session.get(f"{self.inference_api_url}/health") as response:
                return response.status == 200
        except Exception:
            return False


class SyncFraudDetectionService:
    """Synchronous version of fraud detection service for non-async code."""
    
    def __init__(self, inference_api_url: str = "http://inference-api:8080"):
        self.inference_api_url = inference_api_url
        self.recent_results: List[bool] = []
        self.max_recent_results = 100
        
    def detect_fraud(self, transaction: Dict[str, Any]) -> Optional[FraudResult]:
        """
        Detect fraud synchronously using requests.
        
        Args:
            transaction: Transaction event dict
            
        Returns:
            FraudResult if successful, None if API call fails
        """
        import requests
        
        start_time = time.perf_counter()
        
        try:
            # Prepare request payload
            request_payload = {
                "card_id": transaction.get("card_id"),
                "transaction_amount": transaction.get("amount"),
                "mcc_code": transaction.get("mcc"),
                "country_code": transaction.get("geo_country")
            }
            
            # Remove None values
            request_payload = {k: v for k, v in request_payload.items() if v is not None}
            
            # Call fraud detection API
            response = requests.post(
                f"{self.inference_api_url}/score/fraud",
                json=request_payload,
                timeout=5.0,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result_data = response.json()
                
                # Parse response
                fraud_result = FraudResult(
                    card_id=request_payload["card_id"],
                    fraud_score=result_data["fraud_score"],
                    risk_level=result_data["risk_level"],
                    confidence=result_data["confidence"],
                    recommended_action=result_data["recommended_action"],
                    top_risk_factors=result_data.get("top_risk_factors", []),
                    explanation=result_data["explanation"],
                    latency_ms=result_data["latency_ms"],
                    features_used=result_data["features_used"],
                    feature_freshness_sec=result_data.get("feature_freshness_sec")
                )
                
                # Record metrics
                detection_latency = time.perf_counter() - start_time
                FRAUD_DETECTION_LATENCY.observe(detection_latency)
                
                FRAUD_SCORE_DISTRIBUTION.observe(fraud_result.fraud_score)
                
                FRAUD_DETECTIONS_TOTAL.labels(
                    risk_level=fraud_result.risk_level,
                    action_taken=fraud_result.recommended_action
                ).inc()
                
                # Track fraud rate
                is_fraud = fraud_result.risk_level in ['high', 'critical']
                self._update_fraud_rate(is_fraud)
                
                # Count blocked/high-risk transactions
                if fraud_result.recommended_action == "block":
                    BLOCKED_TRANSACTIONS.inc()
                elif fraud_result.risk_level in ['high', 'critical']:
                    HIGH_RISK_TRANSACTIONS.inc()
                
                logger.info(
                    "Fraud detection completed",
                    card_id=fraud_result.card_id,
                    fraud_score=fraud_result.fraud_score,
                    risk_level=fraud_result.risk_level,
                    action=fraud_result.recommended_action,
                    latency_ms=detection_latency * 1000,
                    api_latency_ms=fraud_result.latency_ms,
                    features_used=fraud_result.features_used
                )
                
                return fraud_result
                
            else:
                logger.error(
                    "Fraud API returned error",
                    status=response.status_code,
                    response=response.text
                )
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Fraud detection API timeout", card_id=request_payload.get("card_id"))
            return None
        except Exception as e:
            logger.error(
                "Fraud detection failed",
                card_id=request_payload.get("card_id"),
                error=str(e)
            )
            return None
    
    def _update_fraud_rate(self, is_fraud: bool):
        """Update the rolling fraud rate calculation."""
        self.recent_results.append(is_fraud)
        
        # Keep only recent results
        if len(self.recent_results) > self.max_recent_results:
            self.recent_results = self.recent_results[-self.max_recent_results:]
        
        # Calculate current fraud rate
        if self.recent_results:
            fraud_rate = sum(self.recent_results) / len(self.recent_results)
            FRAUD_RATE_GAUGE.set(fraud_rate)
    
    def health_check(self) -> bool:
        """Check if the fraud detection API is healthy."""
        try:
            import requests
            response = requests.get(f"{self.inference_api_url}/health", timeout=3.0)
            return response.status_code == 200
        except Exception:
            return False
