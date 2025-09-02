# 🧠 ML Training Pipeline

> **Production-grade ML training system** for fraud detection and personalization models with automated drift detection and continuous learning.

## 🎯 Overview

The training pipeline is a **core component** of the streaming feature store that transforms real-time features into production ML models. It demonstrates senior-level MLOps practices including:

- **Automated training** from streaming feature store
- **Multi-algorithm support** (XGBoost, LightGBM, scikit-learn)
- **MLflow integration** for experiment tracking and model registry
- **Drift detection** for production model monitoring
- **ONNX export** for high-performance inference
- **Containerized deployment** with Docker

## 🏗️ Architecture Role

```
Event Stream → Feature Store → Training Pipeline → Model Registry → Inference Service
     ↓              ↓              ↓                ↓              ↓
Generators    Redis (Feast)   ML Training    MLflow Registry   FastAPI + ONNX
```

### **Data Flow:**
1. **Streaming Pipeline** computes features in real-time → Redis
2. **Training Pipeline** extracts features + generates synthetic labels
3. **Model Training** with cross-validation and evaluation
4. **Model Registration** in MLflow with versioning
5. **ONNX Export** for high-performance inference
6. **Drift Monitoring** ensures model health in production

## 🚀 Quick Start

### **Prerequisites**
```bash
# Install dependencies
pip install -r requirements.txt

# Ensure Redis is running (from project root)
make up
```

### **One-Command Training**
```bash
# Train fraud detection model with default settings
python train.py

# Train with custom parameters
python train.py --model-type xgboost --fraud-rate 0.03 --cv-folds 10
```

### **Drift Detection**
```bash
# Check for data/model drift
python drift_check.py --max-samples 1000 --significance-level 0.05
```

## 📊 Training Pipeline

### **1. Dataset Creation**
```python
# Features come from Redis feature store (no labels)
# Labels generated using rule-based fraud detection:
fraud_conditions = [
    (df['velocity_score'] > 0.8) & (df['txn_count_5m'] > 5),      # High velocity
    (df['geo_diversity_score'] > 0.7) & (df['unique_countries_5m'] > 2),  # Geo anomalies
    df['has_high_risk_mcc'] & (df['amount_avg_5m'] > 500),         # Risky merchants
    df['is_weekend'] & (df.get('hour_of_day', 12) < 6),            # Suspicious timing
    (df['amount_max_5m'] > 1000) & (df['txn_count_5m'] == 1)      # Large single txns
]
```

### **2. Model Training**
- **Algorithm Selection**: XGBoost, LightGBM, Random Forest, Logistic Regression
- **Cross-Validation**: Stratified K-fold with multiple metrics
- **Hyperparameter Tuning**: Configurable via config.py
- **Early Stopping**: For gradient boosting models

### **3. Model Evaluation**
- **Metrics**: AUC, Precision, Recall, F1, Confusion Matrix
- **Feature Importance**: Top features for interpretability
- **Performance Assessment**: Model readiness scoring

### **4. Model Deployment**
- **MLflow Registry**: Version control and staging
- **ONNX Export**: Production-ready inference format
- **Artifact Management**: Model files, feature names, metadata

## 🔍 Drift Detection System

### **Types of Drift Monitored:**
1. **Data Drift**: Feature distribution changes
2. **Model Drift**: Performance degradation
3. **Prediction Drift**: Output distribution shifts

### **Statistical Methods:**
- **Kolmogorov-Smirnov Test**: For continuous features
- **Chi-Square Test**: For categorical features
- **Population Stability Index (PSI)**: Distribution similarity

### **Drift Severity Classification:**
```python
def _get_drift_severity(p_value, significance_level):
    if p_value >= significance_level:
        return "none"
    elif p_value >= significance_level / 10:
        return "low"
    elif p_value >= significance_level / 100:
        return "medium"
    else:
        return "high"
```

## ⚙️ Configuration

### **Training Configuration (`config.py`)**
```python
class TrainingConfig(BaseModel):
    data: DataConfig          # Redis, data quality, fraud rate
    model: ModelConfig        # Algorithm, hyperparameters, validation
    mlflow: MLflowConfig      # Experiment tracking, model registry
    export_onnx: bool         # ONNX export for production
    feature_views: List[str]  # Feast feature views to use
```

### **Environment Variables**
```bash
export REDIS_HOST=localhost
export MLFLOW_TRACKING_URI=http://localhost:5000
export MODEL_TYPE=xgboost
export FRAUD_RATE_TARGET=0.02
```

### **CLI Options**
```bash
python train.py \
    --model-type xgboost \
    --experiment-name fraud_detection_v2 \
    --fraud-rate 0.03 \
    --cv-folds 10 \
    --test-size 0.15 \
    --verbose
```

## 📈 Model Performance

### **Target Metrics**
| Metric | Target | Good | Acceptable | Needs Improvement |
|--------|--------|------|------------|-------------------|
| **AUC** | > 0.8 | > 0.8 | > 0.7 | ≤ 0.7 |
| **Precision** | > 0.8 | > 0.8 | > 0.7 | ≤ 0.7 |
| **Recall** | > 0.8 | > 0.8 | > 0.7 | ≤ 0.7 |
| **F1** | > 0.8 | > 0.8 | > 0.7 | ≤ 0.7 |

### **Performance Assessment**
```python
# Model readiness assessment
auc_score = metrics.get('test_auc', 0)
if auc_score > 0.8:
    logger.info("✓ Model performance is good (AUC > 0.8)")
elif auc_score > 0.7:
    logger.info("⚠ Model performance is acceptable (AUC > 0.7)")
else:
    logger.info("✗ Model performance needs improvement (AUC <= 0.7)")
```

## 🔄 Continuous Learning Workflow

### **Automated Retraining Triggers:**
1. **Scheduled**: Weekly/monthly retraining
2. **Drift-Based**: When drift exceeds thresholds
3. **Performance-Based**: When metrics degrade
4. **Data-Based**: When new fraud patterns detected

### **Model Lifecycle:**
```
Training → Validation → Staging → Production → Monitoring → Retraining
   ↓           ↓          ↓          ↓           ↓           ↓
MLflow     Cross-Val   MLflow    Inference   Drift      New Model
Run        Metrics      Registry   Service     Detection   Version
```

## 🐳 Containerization

### **Docker Support**
```bash
# Build training container
docker build -f training/Dockerfile -t ml-training .

# Run training job
docker run -v $(pwd)/training/outputs:/app/training/outputs ml-training

# Run drift detection
docker run -v $(pwd)/training/outputs:/app/training/outputs ml-training python drift_check.py
```

### **Docker Compose Integration**
```yaml
# From project root
services:
  ml-training:
    build: ./training
    volumes:
      - ./training/outputs:/app/training/outputs
      - ./training/models:/app/training/models
    environment:
      - REDIS_HOST=redis
      - MLFLOW_TRACKING_URI=http://mlflow:5000
```

## 🧪 Testing & Validation

### **Test Suite**
```bash
# Run all tests
python test_ml_pipeline.py

# Test individual components
python -c "
from test_ml_pipeline import *
test_config_loading()
test_synthetic_dataset_creation()
test_model_factory()
test_model_training()
"
```

### **Test Coverage**
- ✅ Configuration loading and validation
- ✅ Synthetic dataset creation
- ✅ Model factory for different algorithms
- ✅ End-to-end training pipeline
- ✅ Artifact generation and validation

## 📊 Monitoring & Observability

### **MLflow Integration**
- **Experiment Tracking**: All training runs logged
- **Model Registry**: Version control and staging
- **Artifact Storage**: Model files and metadata
- **Metrics Comparison**: Performance across runs

### **Logging & Metrics**
```python
# Structured logging with different levels
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ml/training.log')
    ]
)
```

## 🚀 Production Deployment

### **Model Serving Pipeline**
1. **Training**: Generate ONNX model
2. **Validation**: Performance and drift checks
3. **Staging**: MLflow staging environment
4. **Production**: Deploy to inference service
5. **Monitoring**: Real-time drift detection

### **Integration Points**
- **Feature Store**: Redis for real-time features
- **Model Registry**: MLflow for versioning
- **Inference Service**: FastAPI with ONNX models
- **Monitoring**: Prometheus + Grafana dashboards

## 🔧 Development Workflow

### **Local Development**
```bash
# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run training
python train.py --verbose

# Check drift
python drift_check.py --verbose
```

### **Code Changes**
```bash
# After modifying code
make rebuild-training

# Or manually
docker build -f training/Dockerfile -t ml-training .
```

## 📚 Key Files Explained

| File | Purpose | Key Components |
|------|---------|----------------|
| **`config.py`** | Configuration management | Data, model, MLflow configs |
| **`datasets.py`** | Feature extraction & labeling | Redis integration, synthetic labels |
| **`models.py`** | Model training & evaluation | Multi-algorithm support, MLflow |
| **`train.py`** | Training pipeline orchestration | End-to-end workflow |
| **`drift_check.py`** | Drift detection & monitoring | Statistical tests, PSI calculation |
| **`test_ml_pipeline.py`** | Test suite | Component validation |

## 🎯 Use Cases

### **Fraud Detection**
- **Features**: Transaction patterns, velocity, geography, timing
- **Labels**: Rule-based fraud scoring
- **Models**: XGBoost, LightGBM for high performance
- **Monitoring**: Real-time drift detection

### **Personalization**
- **Features**: User behavior, engagement, preferences
- **Labels**: Purchase propensity, engagement scores
- **Models**: Logistic regression for interpretability
- **Monitoring**: User behavior drift

## 🔮 Future Enhancements

### **Planned Features**
- [ ] **AutoML**: Automated hyperparameter tuning
- [ ] **Feature Engineering**: Automated feature selection
- [ ] **A/B Testing**: Model comparison framework
- [ ] **Federated Learning**: Multi-party model training
- [ ] **Explainability**: SHAP, LIME integration

### **Cloud Migration**
| Component | Local | AWS | GCP |
|-----------|-------|-----|-----|
| **Training** | Docker | SageMaker | Vertex AI |
| **Registry** | MLflow | SageMaker | Vertex AI |
| **Storage** | Local | S3 | GCS |
| **Compute** | Docker | EC2/ECS | GCE/GKE |

## 📈 Performance Benchmarks

### **Training Performance**
- **Dataset Size**: 10k+ samples in < 5 minutes
- **Cross-Validation**: 5-fold CV in < 2 minutes
- **Model Export**: ONNX conversion in < 30 seconds
- **Drift Detection**: 1000 samples analyzed in < 10 seconds

### **Resource Usage**
- **Memory**: < 4GB RAM for 10k samples
- **CPU**: Utilizes all available cores
- **Storage**: < 100MB for model artifacts
- **Network**: Minimal (local Redis connection)

## 🤝 Contributing

This training pipeline demonstrates **production MLOps practices**:
- ✅ **Automated workflows** with proper error handling
- ✅ **Comprehensive testing** with synthetic data
- ✅ **Production monitoring** with drift detection
- ✅ **Cloud-ready architecture** with containerization
- ✅ **Senior-level design** with proper abstractions

## 📄 License

MIT License - see project root LICENSE file for details.

---

**Next Steps:**
1. **Run Training**: `python training/train.py`
2. **Check Drift**: `python training/drift_check.py`
3. **View Experiments**: http://localhost:5000 (MLflow)
4. **Deploy Model**: Use generated ONNX model in inference service

This training pipeline is the **brain** of your streaming feature store, continuously learning from real-time data to improve fraud detection and personalization! 🧠✨
